"""Base class for Salesforce → Frappe per-object syncers."""

from __future__ import annotations

from typing import Any, ClassVar

import frappe
from frappe.utils import get_datetime, now_datetime

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.exceptions import SalesforceAPIError
from frappe_salesforce.salesforce.soql import build_incremental_query

from .transforms import apply_transform

#: Commit advanced high-water mark every N successfully processed records
#: so a crash mid-run doesn't force reprocessing the whole page next tick.
HWM_CHECKPOINT_EVERY = 50

#: Tolerate this many consecutive 401s inside the SOQL pagination loop
#: before aborting the syncer. The client already does one transparent
#: refresh-and-retry per call; consecutive 401s here mean the refreshed
#: token is itself being rejected and continuing is futile.
MAX_CONSECUTIVE_AUTH_FAILURES = 3


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
        auth_failures = 0

        try:
            iterator = self.client.query(soql)
            while True:
                try:
                    rec = next(iterator)
                except StopIteration:
                    break
                except SalesforceAPIError as e:
                    # 401 inside the pagination loop means the client's
                    # transparent refresh-and-retry has already failed once.
                    # Allow a small number of consecutive auth failures
                    # (transient network/SF blips), but bail this syncer
                    # cleanly after the threshold so the orchestrator can
                    # move to the next object instead of looping forever.
                    if getattr(e, "status_code", None) == 401:
                        auth_failures += 1
                        frappe.log_error(
                            title=(
                                f"SF auth failure during "
                                f"{self.salesforce_object} sync "
                                f"({auth_failures}/{MAX_CONSECUTIVE_AUTH_FAILURES})"
                            ),
                            message=str(e),
                        )
                        if auth_failures >= MAX_CONSECUTIVE_AUTH_FAILURES:
                            # Surface to the orchestrator's per-syncer
                            # try/except so it logs and continues with
                            # the next syncer rather than aborting the
                            # whole tick.
                            raise
                        continue
                    raise

                try:
                    auth_failures = 0  # any successful fetch resets the counter
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
        """Build the SOQL SELECT field list for this syncer.

        Aggregates every ``sf_field`` and every line of ``sf_fields``
        across mapping rows, plus ``extra_soql_fields``. Then filters the
        result against the SF describe response so FLS-blocked fields
        don't cause ``INVALID_FIELD`` 400s. Dropped fields are logged
        once per sync run for operator visibility.
        """
        fields: list[str] = []
        if self.mapping:
            for row in self.mapping.field_mappings:
                if row.sf_field:
                    fields.append(row.sf_field)
                if getattr(row, "sf_fields", None):
                    fields.extend(_split_sf_fields(row.sf_fields))
        fields.extend(self.extra_soql_fields)
        # Always-required fields (used by run() for HWM checkpointing
        # and link bookkeeping). These should always be accessible — if
        # they're not, the sync genuinely can't proceed and a 400 is the
        # right signal.
        always_required = {"Id", "SystemModstamp"}
        return self._filter_fls_blocked(fields, always_required)

    def _filter_fls_blocked(
        self, fields: list[str], always_required: set[str]
    ) -> list[str]:
        """Drop fields not in the SF describe response (FLS-blocked).

        Falls back to returning ``fields`` unchanged if describe failed
        or returned an empty set (handled by ``client.accessible_fields``).
        """
        try:
            accessible = self.client.accessible_fields(self.salesforce_object)
        except Exception as e:
            frappe.log_error(
                title=f"SF accessible_fields error for {self.salesforce_object}",
                message=str(e),
            )
            return fields
        if not accessible:
            # Describe failed or returned nothing — fail open.
            return fields
        kept: list[str] = []
        dropped: list[str] = []
        for f in fields:
            if f in accessible or f in always_required:
                kept.append(f)
            else:
                dropped.append(f)
        if dropped:
            frappe.log_error(
                title=f"SF FLS-filtered {self.salesforce_object}",
                message=(
                    f"The integration user cannot SELECT the following "
                    f"field(s) on {self.salesforce_object}; they were "
                    f"dropped from the SOQL query for this run:\n\n"
                    f"  {', '.join(sorted(dropped))}\n\n"
                    f"To re-enable, ensure the field is exposed via FLS "
                    f"on the integration user's profile / permission set "
                    f"(or remove the mapping row in Salesforce Field "
                    f"Mapping if you don't need it)."
                ),
            )
        return kept

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
            # Truncate scalar string values to the target field's max length
            # to avoid ``CharacterLengthExceededError`` aborting the whole
            # record. SF text fields routinely exceed Frappe ``Data``'s
            # 140-char default; the alternative — failing the upsert — is
            # strictly worse than dropping the trailing characters.
            transformed = self._truncate_to_max_length(
                row.frappe_field, transformed, sf_id=rec.get("Id")
            )
            values[row.frappe_field] = transformed
        return values

    # Cache target-field metadata per syncer instance to avoid repeated
    # ``frappe.get_meta`` calls (one per record per row otherwise).
    _max_length_cache: dict[str, int | None]

    def _truncate_to_max_length(
        self, frappe_field: str, value: Any, sf_id: str | None = None
    ) -> Any:
        if not isinstance(value, str) or not value:
            return value
        cache = self.__dict__.setdefault("_max_length_cache", {})
        if frappe_field not in cache:
            try:
                meta = frappe.get_meta(self.frappe_doctype)
                df = meta.get_field(frappe_field)
                # Only ``Data`` and ``Link`` enforce the 140-char cap; long
                # text types accept arbitrary length and shouldn't be
                # silently truncated.
                if df and df.fieldtype in ("Data", "Link", "Select"):
                    cache[frappe_field] = int(df.length) if df.length else 140
                else:
                    cache[frappe_field] = None
            except Exception:
                cache[frappe_field] = None
        max_length = cache[frappe_field]
        if max_length is None:
            return value
        if len(value) <= max_length:
            return value
        # Log once per (doctype, field) — repeated truncation is a config
        # smell that deserves operator attention.
        flag_key = f"_truncated_{self.frappe_doctype}_{frappe_field}"
        if not getattr(self, flag_key, False):
            frappe.log_error(
                title=(
                    f"SF value truncated: "
                    f"{self.frappe_doctype}.{frappe_field}"
                ),
                message=(
                    f"Salesforce value exceeds the {max_length}-char "
                    f"limit on {self.frappe_doctype}.{frappe_field}; "
                    f"truncating. Consider widening the field to Small "
                    f"Text / Long Text in setup/custom_fields.py.\n\n"
                    f"First offending SF Id: {sf_id or '?'}\n"
                    f"Length: {len(value)}\n"
                    f"Sample: {value[:200]!r}..."
                ),
            )
            setattr(self, flag_key, True)
        return value[:max_length]

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
