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
    #: Extra SOQL fields the syncer needs (for ``enrich_values`` /
    #: ``after_upsert``) but that aren't represented as mapping rows.
    extra_soql_fields: ClassVar[tuple[str, ...]] = ()

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
        new_hwm = get_datetime(since).replace(tzinfo=None) if since else None
        calls_before = self.client.calls_this_tick
        processed_since_checkpoint = 0

        try:
            for rec in self.client.query(soql):
                try:
                    self._process_record(rec)
                    self.log.fetched = (self.log.fetched or 0) + 1
                    modstamp = get_datetime(rec["SystemModstamp"]).replace(tzinfo=None)
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
            doc = self._upsert_doc(link, values, sf_id)
            if doc is not None:
                try:
                    self.after_upsert(rec, doc)
                except Exception as e:
                    # after_upsert side-effects (e.g. address upsert) must
                    # not fail the whole record sync.
                    frappe.log_error(
                        title=f"SF after_upsert {self.salesforce_object} {sf_id}",
                        message=frappe.get_traceback() or str(e),
                    )

        link.sf_system_modstamp = get_datetime(rec["SystemModstamp"]).replace(tzinfo=None)
        link.last_synced_at = now_datetime()
        link.sync_status = "Synced"
        link.error_message = None
        link.save(ignore_permissions=True)

    def _upsert_doc(self, link, values: dict, sf_id: str):
        """Insert or update the target Frappe doc.

        Returns the resulting ``Document`` so subclasses (via ``after_upsert``)
        can run linked-record side effects.
        """
        # Strip ``None`` so we never blank out a field with an empty SF value.
        # Multi-input transforms (``email_table``, ``phone_table``) return
        # ``list[dict]`` — those target a child-table fieldname and are routed
        # to ``_merge_table_payloads`` instead of ``doc.update``.
        # ``address`` returns a ``dict`` for the side-effect placeholder
        # (``custom_sf_address_block``); the real upsert happens in
        # ``after_upsert``, so dicts are dropped here.
        table_payloads: dict[str, list[dict]] = {}
        clean_values: dict[str, Any] = {}
        for k, v in values.items():
            if v is None:
                continue
            if isinstance(v, list) and v and isinstance(v[0], dict):
                table_payloads[k] = v
                continue
            if isinstance(v, dict):
                continue
            clean_values[k] = v
        values = clean_values

        if link.frappe_name and frappe.db.exists(self.frappe_doctype, link.frappe_name):
            doc = frappe.get_doc(self.frappe_doctype, link.frappe_name)
            doc.update(values)
            doc.custom_salesforce_id = sf_id
            self._merge_table_payloads(doc, table_payloads)
            doc.save(ignore_permissions=True)
            self.log.updated = (self.log.updated or 0) + 1
            return doc

        # Try to match an existing doc by SF ID custom field first.
        existing = frappe.db.get_value(
            self.frappe_doctype, {"custom_salesforce_id": sf_id}, "name"
        )
        if existing:
            doc = frappe.get_doc(self.frappe_doctype, existing)
            doc.update(values)
            self._merge_table_payloads(doc, table_payloads)
            doc.save(ignore_permissions=True)
            link.frappe_name = existing
            link.frappe_doctype = self.frappe_doctype
            self.log.updated = (self.log.updated or 0) + 1
            return doc

        doc = frappe.get_doc(
            {
                "doctype": self.frappe_doctype,
                "custom_salesforce_id": sf_id,
                **values,
            }
        )
        self._merge_table_payloads(doc, table_payloads)
        doc.insert(ignore_permissions=True)
        link.frappe_name = doc.name
        link.frappe_doctype = self.frappe_doctype
        self.log.created = (self.log.created or 0) + 1
        return doc

    def _merge_table_payloads(self, doc, payloads: dict[str, list[dict]]) -> None:
        """Merge multi-input child-table payloads into ``doc``.

        ``payloads`` maps a child-table fieldname (e.g. ``"email_ids"``) to
        a list of row dicts. Each row dict must include the row's natural
        key (``"email_id"`` for emails, ``"phone"`` for phones); existing
        rows matching a key are updated in place, new rows appended,
        non-SF rows preserved untouched.
        """
        for fieldname, rows in payloads.items():
            if not rows:
                continue
            # Use the first non-Salesforce-Id key as the natural key.
            sample_keys = set(rows[0].keys())
            key = next(
                (k for k in ("email_id", "phone") if k in sample_keys),
                None,
            )
            if key is None:
                continue
            existing = doc.get(fieldname) or []
            existing_by_key = {
                (row.get(key) or "").lower(): row
                for row in existing
                if row.get(key)
            }
            for new_row in rows:
                k = (new_row.get(key) or "").lower()
                if not k:
                    continue
                if k in existing_by_key:
                    existing_by_key[k].update(new_row)
                else:
                    doc.append(fieldname, new_row)

    # ------------------------------------------------------------------
    # Extension points
    # ------------------------------------------------------------------
    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        """Hook for subclasses to add computed / derived fields."""
        return values

    def after_upsert(self, rec: dict[str, Any], doc) -> None:
        """Hook called after the Frappe doc is saved.

        Used for linked-record side effects that can't be expressed as a
        single mapping (e.g. upserting an ``Address`` doc and linking it
        back via ``Dynamic Link``). Default is a no-op.
        """
        return

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
        fields: list[str] = []
        if self.mapping:
            for row in self.mapping.field_mappings:
                if row.sf_field:
                    fields.append(row.sf_field)
                if getattr(row, "sf_fields", None):
                    fields.extend(_split_sf_fields(row.sf_fields))
        fields.extend(self.extra_soql_fields)
        return fields

    def _apply_mapping(self, rec: dict[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if not self.mapping:
            return values
        for row in self.mapping.field_mappings:
            multi = _split_sf_fields(getattr(row, "sf_fields", None))
            if multi:
                # Multi-input transform: feed dict of {sf_field: value}.
                payload = {f: rec.get(f) for f in multi}
                if all(v is None for v in payload.values()) and not row.default_value:
                    raw: Any = None
                else:
                    raw = payload
            else:
                raw = rec.get(row.sf_field) if row.sf_field else None
                if raw is None and row.default_value:
                    raw = row.default_value
            transformed = apply_transform(row.transform, raw)
            # Multi-input transforms targeting child tables encode the target
            # via ``frappe_field`` prefix ``__table:<fieldname>``.
            values[row.frappe_field] = transformed
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


def _split_sf_fields(value: str | None) -> list[str]:
    """Split a Long Text ``sf_fields`` value into individual SF field names."""
    if not value:
        return []
    return [line.strip() for line in str(value).splitlines() if line.strip()]
