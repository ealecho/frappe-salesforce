"""Base class for Salesforce → Frappe per-object syncers."""

from __future__ import annotations

from typing import Any, ClassVar

import frappe
from frappe.utils import get_datetime, now_datetime

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.soql import build_incremental_query

from .transforms import apply_transform

#: Commit advanced high-water mark every N successfully processed records
#: so a crash mid-run doesn't force reprocessing the whole page next tick.
HWM_CHECKPOINT_EVERY = 50


class BaseSyncer:
    """Abstract base class for syncing a single Salesforce object."""

    #: Salesforce API object name, e.g. ``"Account"``.
    salesforce_object: ClassVar[str] = ""
    #: Target Frappe DocType, e.g. ``"CRM Organization"``.
    frappe_doctype: ClassVar[str] = ""
    #: Field in ``Salesforce Settings`` storing the high-water mark.
    high_water_field: ClassVar[str] = ""
    #: Relative ordering within a sync run (lower = earlier).
    order_in_sync: ClassVar[int] = 100
    #: Extra SOQL WHERE clause to apply to incremental queries.
    extra_where: ClassVar[str | None] = None
    #: If True, syncer does not create Frappe docs (e.g. UserSyncer).
    link_only: ClassVar[bool] = False

    def __init__(self, client: SalesforceClient, log_item: Any):
        self.client = client
        self.log = log_item
        self.settings = frappe.get_single("Salesforce Settings")
        self.mapping = self._load_mapping()

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    def run(self) -> None:
        since = self._get_high_water_mark()
        soql = build_incremental_query(
            sobject=self.salesforce_object,
            fields=self._soql_fields(),
            since=since,
            extra_where=self.extra_where,
        )
        self.log.soql = soql
        new_hwm = get_datetime(since) if since else None
        calls_before = self.client.calls_this_tick
        processed_since_checkpoint = 0

        try:
            for rec in self.client.query(soql):
                try:
                    self._process_record(rec)
                    self.log.fetched = (self.log.fetched or 0) + 1
                    modstamp = get_datetime(rec["SystemModstamp"])
                    if new_hwm is None or modstamp > new_hwm:
                        new_hwm = modstamp
                    processed_since_checkpoint += 1
                    if processed_since_checkpoint >= HWM_CHECKPOINT_EVERY:
                        self._set_high_water_mark(new_hwm)
                        frappe.db.commit()
                        processed_since_checkpoint = 0
                except Exception as e:
                    self.log.failed = (self.log.failed or 0) + 1
                    frappe.log_error(
                        title=f"SF sync {self.salesforce_object} record {rec.get('Id')}",
                        message=frappe.get_traceback() or str(e),
                    )
        finally:
            # Always record API calls spent by this syncer and persist the
            # latest HWM we safely reached — even if the loop aborted due
            # to a budget/quota exception higher up the stack.
            self.log.api_calls_used = self.client.calls_this_tick - calls_before
            if new_hwm is not None:
                self._set_high_water_mark(new_hwm)

    # ------------------------------------------------------------------
    # Per-record processing
    # ------------------------------------------------------------------
    def _process_record(self, rec: dict[str, Any]) -> None:
        sf_id = rec["Id"]
        link = self._get_or_create_link(sf_id)
        values = self._apply_mapping(rec)
        values = self.enrich_values(rec, values)

        if self.link_only:
            frappe_name = self._resolve_link_only(rec, values)
            if frappe_name:
                link.frappe_name = frappe_name
                link.frappe_doctype = self.frappe_doctype
                self.log.updated = (self.log.updated or 0) + 1
            else:
                self.log.skipped = (self.log.skipped or 0) + 1
        else:
            self._upsert_doc(link, values, sf_id)

        link.sf_system_modstamp = rec["SystemModstamp"]
        link.last_synced_at = now_datetime()
        link.sync_status = "Synced"
        link.error_message = None
        link.save(ignore_permissions=True)

    def _upsert_doc(self, link, values: dict, sf_id: str) -> None:
        values = {k: v for k, v in values.items() if v is not None}
        if link.frappe_name and frappe.db.exists(self.frappe_doctype, link.frappe_name):
            doc = frappe.get_doc(self.frappe_doctype, link.frappe_name)
            doc.update(values)
            doc.custom_salesforce_id = sf_id
            doc.save(ignore_permissions=True)
            self.log.updated = (self.log.updated or 0) + 1
        else:
            # Try to match an existing doc by SF ID custom field first.
            existing = frappe.db.get_value(
                self.frappe_doctype, {"custom_salesforce_id": sf_id}, "name"
            )
            if existing:
                doc = frappe.get_doc(self.frappe_doctype, existing)
                doc.update(values)
                doc.save(ignore_permissions=True)
                link.frappe_name = existing
                link.frappe_doctype = self.frappe_doctype
                self.log.updated = (self.log.updated or 0) + 1
            else:
                doc = frappe.get_doc(
                    {
                        "doctype": self.frappe_doctype,
                        "custom_salesforce_id": sf_id,
                        **values,
                    }
                )
                doc.insert(ignore_permissions=True)
                link.frappe_name = doc.name
                link.frappe_doctype = self.frappe_doctype
                self.log.created = (self.log.created or 0) + 1

    # ------------------------------------------------------------------
    # Extension points
    # ------------------------------------------------------------------
    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        """Hook for subclasses to add computed / derived fields."""
        return values

    def _resolve_link_only(self, rec: dict, values: dict) -> str | None:
        """For link-only syncers, return the existing Frappe docname to link."""
        return None

    # ------------------------------------------------------------------
    # Field mapping
    # ------------------------------------------------------------------
    def _load_mapping(self):
        name = frappe.db.get_value(
            "Salesforce Field Mapping",
            {"salesforce_object": self.salesforce_object, "enabled": 1},
            "name",
        )
        if not name:
            return None
        return frappe.get_doc("Salesforce Field Mapping", name)

    def _soql_fields(self) -> list[str]:
        if not self.mapping:
            return []
        return [row.sf_field for row in self.mapping.field_mappings if row.sf_field]

    def _apply_mapping(self, rec: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if not self.mapping:
            return values
        for row in self.mapping.field_mappings:
            raw = rec.get(row.sf_field) if row.sf_field else None
            if raw is None and row.default_value:
                raw = row.default_value
            values[row.frappe_field] = apply_transform(row.transform, raw)
        return values

    # ------------------------------------------------------------------
    # High-water mark
    # ------------------------------------------------------------------
    def _get_high_water_mark(self) -> str:
        if self.high_water_field:
            value = self.settings.get(self.high_water_field)
            if value:
                return str(value)
        # No HWM configured: start from "now" so we never accidentally
        # backfill from epoch. Users who want historical data use the
        # explicit "Backfill From Date" action on Salesforce Settings.
        return str(now_datetime())

    def _set_high_water_mark(self, value) -> None:
        if not self.high_water_field:
            return
        frappe.db.set_single_value("Salesforce Settings", self.high_water_field, value)

    # ------------------------------------------------------------------
    # Record Link helpers
    # ------------------------------------------------------------------
    def _get_or_create_link(self, salesforce_id: str):
        name = frappe.db.get_value(
            "Salesforce Record Link",
            {
                "salesforce_id": salesforce_id,
                "salesforce_object": self.salesforce_object,
            },
            "name",
        )
        if name:
            return frappe.get_doc("Salesforce Record Link", name)
        doc = frappe.get_doc(
            {
                "doctype": "Salesforce Record Link",
                "salesforce_id": salesforce_id,
                "salesforce_object": self.salesforce_object,
                "frappe_doctype": self.frappe_doctype,
            }
        )
        doc.insert(ignore_permissions=True)
        return doc
