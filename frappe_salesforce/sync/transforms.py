"""Value transforms for mapping Salesforce field values to Frappe field values.

Transforms are dispatched by name from ``Salesforce Field Mapping Row.transform``.

Two transform shapes are supported:

* **Scalar** — receive a single SF value, return a single Frappe value
  (``to_bool``, ``to_date``, ``map_user_by_email``, …).
* **Multi-input** — receive a ``dict[str, Any]`` of ``{sf_field: value}``
  populated via the row's ``sf_fields`` Long Text. Used for compound
  fields like Address blocks and multi-channel emails / phones.
  Multi-input transforms returning ``list[dict]`` are routed by
  ``BaseSyncer._upsert_doc`` to a child-table fieldname instead of
  ``doc.update``.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

try:
    import frappe
    from frappe.utils import get_datetime
except ModuleNotFoundError:  # pragma: no cover - supports no-site static tests
    frappe = None

    def get_datetime(value):
        if isinstance(value, datetime):
            return value
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)

_TAG_RE = re.compile(r"<[^>]+>")


# ----------------------------------------------------------------------
# Scalar transforms
# ----------------------------------------------------------------------
def to_bool(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return 1 if value else 0


def to_date(value: Any) -> str | None:
    if not value:
        return None
    # SF dates are ISO "YYYY-MM-DD"; normalise via frappe utility.
    return str(get_datetime(value).date())


def to_datetime(value: Any) -> str | None:
    if not value:
        return None
    dt = get_datetime(value)
    return str(dt.replace(tzinfo=None))


def html_strip(value: Any) -> str | None:
    if not value:
        return None
    text = _TAG_RE.sub("", str(value))
    return html.unescape(text).strip()


# ----------------------------------------------------------------------
# Bucketing / Link upserts
# ----------------------------------------------------------------------
def employee_bucket(value: Any) -> str | None:
    """Map an integer employee count to ``CRM Organization.no_of_employees``.

    Frappe stores it as a Select bucket (1-10/11-50/51-200/201-500/501-1000/1000+);
    Salesforce returns a raw integer. Empty / 0 / non-numeric → ``None``.
    """
    if value in (None, ""):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n <= 10:
        return "1-10"
    if n <= 50:
        return "11-50"
    if n <= 200:
        return "51-200"
    if n <= 500:
        return "201-500"
    if n <= 1000:
        return "501-1000"
    return "1000+"


def _ensure_link(
    doctype: str, value: Any, *name_field_candidates: str
) -> str | None:
    """Resolve / upsert a Link parent by name.

    Returns the row name (== ``value``) for use as a Link field value.

    Behaviour:
    * Empty / whitespace input → ``None``.
    * If the target DocType doesn't exist on this site (e.g. installs that
      pre-date a particular CRM version), return the bare string so callers
      writing into Select fields are unaffected.
    * If a row with that name already exists → return the name.
    * Otherwise determine the autoname target fieldname from DocType meta
      (``autoname: field:<x>``) and try that first; then fall through to
      the caller-supplied ``name_field_candidates``; finally fall back to
      inserting with ``name=value``. All errors are swallowed; on failure
      the bare string is still returned so the caller's write attempt
      fails loudly with a ``LinkValidationError`` pinpointing exactly
      which row was missing.
    """
    if value is None or value == "":
        return None
    name = str(value).strip()
    if not name:
        return None
    # No DocType installed → callers writing to a Select field still want the
    # mapped string; return as-is.
    if not frappe.db.exists("DocType", doctype):
        return name
    if frappe.db.exists(doctype, name):
        return name

    # Build the candidate list, autoname-derived field first. Upstream
    # ``frappe/crm`` periodically renames these primary fields (e.g.
    # ``CRM Lead Source`` changed from a ``lead_source`` field to
    # ``source_name``); reading the live meta means we don't need to
    # ship a code change every time. Falls through to hand-coded
    # candidates as a defensive guard if the meta lookup fails or the
    # DocType uses a different ``autoname`` rule.
    candidates: list[str] = []
    try:
        autoname = (frappe.get_meta(doctype).autoname or "").strip()
        if autoname.lower().startswith("field:"):
            candidates.append(autoname.split(":", 1)[1].strip())
    except Exception:
        pass
    for fld in name_field_candidates:
        if fld and fld not in candidates:
            candidates.append(fld)

    for fld in candidates:
        try:
            frappe.get_doc({"doctype": doctype, fld: name}).insert(
                ignore_permissions=True
            )
            return name
        except Exception:
            continue
    try:
        frappe.get_doc({"doctype": doctype, "name": name}).insert(
            ignore_permissions=True
        )
        return name
    except Exception:
        frappe.log_error(
            title=f"SF auto-create {doctype} failed: {name}",
            message=frappe.get_traceback(),
        )
        # Return the value anyway — letting the upstream insert raise its own
        # LinkValidationError makes the failure mode explicit per record
        # rather than silently dropping the field.
        return name


def industry_link(value: Any) -> str | None:
    """Resolve / upsert a ``CRM Industry`` record by name."""
    return _ensure_link("CRM Industry", value, "industry")


def lead_source_link(value: Any) -> str | None:
    """Resolve / upsert a ``CRM Lead Source`` record by name.

    Upstream ``frappe/crm`` autonames this DocType via ``field:source_name``
    — NOT ``lead_source`` as the older v0.1.x candidates assumed. Inserting
    with the wrong fieldname raises "Source Name is required" and the
    parent row never gets created, so the subsequent Lead save fails
    with ``LinkValidationError: Could not find Source: <value>``. Try
    the correct candidate first, fall back to the legacy guess for
    forks that may have renamed the field.
    """
    return _ensure_link("CRM Lead Source", value, "source_name", "lead_source")


def lost_reason_link(value: Any) -> str | None:
    """Resolve / upsert a ``CRM Lost Reason`` record by name."""
    return _ensure_link("CRM Lost Reason", value, "lost_reason")


def salutation_link(value: Any) -> str | None:
    """Resolve / upsert a Frappe ``Salutation`` record.

    Salesforce stores salutations with a trailing period (``"Mr."``,
    ``"Mrs."``, ``"Dr."``) but Frappe's standard ``Salutation`` rows are
    period-less (``"Mr"``, ``"Mrs"``, ``"Dr"``, ``"Ms"``, ``"Miss"``,
    ``"Madam"``, ``"Mx"``, ``"Prof"``). Without normalisation every
    Contact / Lead with a populated SF salutation fails to save with
    ``LinkValidationError: Could not find Salutation: Mr.``.

    Strategy:
    1. Strip surrounding whitespace and any trailing period(s).
    2. ``_ensure_link`` will use the existing standard row if present,
       or auto-create a row for any genuinely novel salutation
       (``"Rev"``, ``"The Honourable"``) so the parent save succeeds.

    We deliberately don't lowercase / title-case — leaving the casing
    untouched preserves whatever the operator agreed on for novel
    values and avoids ``"Mr"`` vs ``"mr"`` duplicate rows.
    """
    if value is None or value == "":
        return None
    name = str(value).strip().rstrip(".").strip()
    if not name:
        return None
    return _ensure_link("Salutation", name, "salutation")


# ----------------------------------------------------------------------
# Reference lookups (resolve SF Id → Frappe docname)
# ----------------------------------------------------------------------
def lookup_record_link(salesforce_id: str | None) -> dict | None:
    """Return the Salesforce Record Link row for ``salesforce_id`` or None."""
    if not salesforce_id:
        return None
    return frappe.db.get_value(
        "Salesforce Record Link",
        {"salesforce_id": salesforce_id},
        ["frappe_doctype", "frappe_name", "salesforce_object"],
        as_dict=True,
    )


def map_account(salesforce_account_id: str | None) -> str | None:
    """Resolve a Salesforce AccountId to a CRM Organization name."""
    if not salesforce_account_id:
        return None
    return frappe.db.get_value(
        "CRM Organization",
        {"custom_salesforce_id": salesforce_account_id},
        "name",
    )


def map_contact(salesforce_contact_id: str | None) -> str | None:
    """Resolve a Salesforce ContactId to a Frappe Contact name."""
    if not salesforce_contact_id:
        return None
    link = frappe.db.get_value(
        "Salesforce Record Link",
        {
            "salesforce_id": salesforce_contact_id,
            "salesforce_object": "Contact",
        },
        ["frappe_name"],
        as_dict=True,
    )
    if link and link.frappe_name:
        return link.frappe_name
    # Fallback: direct match by custom_salesforce_id.
    return frappe.db.get_value(
        "Contact", {"custom_salesforce_id": salesforce_contact_id}, "name"
    )


def map_polymorphic(salesforce_id: str | None) -> str | None:
    """Resolve a polymorphic SF reference to whatever Frappe doc it links.

    Returns the Frappe docname only; the corresponding doctype lives on
    the ``Salesforce Record Link`` row but is not returned here. Callers
    needing the doctype should use ``lookup_record_link`` directly.
    """
    link = lookup_record_link(salesforce_id)
    if link:
        return link.get("frappe_name")
    return None


def map_campaign(salesforce_campaign_id: str | None) -> str | None:
    """Stub: store the SF Campaign Id verbatim.

    No SF Campaign DocType exists in this app (yet). The ``custom_sf_campaign``
    field on ``CRM Deal`` is a plain ``Data`` field, so we just pass the Id
    through as text. Replace with a real lookup once Campaign syncing is added.
    """
    if not salesforce_campaign_id:
        return None
    return str(salesforce_campaign_id)


def map_user_by_email(salesforce_user_id: str | None) -> str | None:
    """Resolve a Salesforce OwnerId to a Frappe User email.

    Strategy:
    1. Look up the SF User via ``Salesforce Record Link``.
    2. Use the stored Frappe User (matched by email) if present.
    3. Fall back to ``Salesforce Settings.fallback_owner``.
    4. Return ``None`` if no fallback configured.
    """
    if salesforce_user_id:
        link = frappe.db.get_value(
            "Salesforce Record Link",
            {
                "salesforce_id": salesforce_user_id,
                "salesforce_object": "User",
            },
            ["frappe_name"],
            as_dict=True,
        )
        if link and link.frappe_name:
            if frappe.db.exists("User", link.frappe_name):
                return link.frappe_name

    fallback = frappe.db.get_single_value("Salesforce Settings", "fallback_owner")
    return fallback or None


# ----------------------------------------------------------------------
# Picklist mapping
# ----------------------------------------------------------------------
LEAD_STATUS_MAP = {
    "Open - Not Contacted": "New",
    "Working - Contacted": "Contacted",
    "Closed - Converted": "Converted",
    "Closed - Not Converted": "Unqualified",
}


def map_lead_status(sf_status: str | None) -> str | None:
    if not sf_status:
        return None
    return LEAD_STATUS_MAP.get(sf_status, sf_status)


def lead_status_link(sf_status: str | None) -> str | None:
    """Map SF Lead.Status → ``CRM Lead Status``, auto-creating missing rows.

    ``CRM Lead.status`` is a Link field in Frappe CRM, not a Select. SF
    picklists are an open vocabulary; new statuses must materialise as
    ``CRM Lead Status`` rows or the upsert dies with ``LinkValidationError``.
    """
    return _ensure_link("CRM Lead Status", map_lead_status(sf_status), "lead_status")


# PEAS NPSP stages → Frappe CRM Deal statuses.
# Standard SF stages kept for defensive coverage.
#
# The active PEAS pipeline stages (Research, Cold proposal…, Warm proposal…,
# Final stage proposal, Finalising, Won, Lost, Reporting Delivered) are
# mirrored 1:1 as CRM Deal Status records carrying the exact SF probability
# (seeded by ``setup/deal_statuses.py``). Those stages are therefore *not*
# remapped here — ``map_deal_stage`` falls back to returning the stage name
# unchanged, so they link straight to the matching status and ``peas_crm``
# derives the right probability from it. Only synonyms / legacy / standard
# SF stages are normalised onto a canonical mirror status below.
DEAL_STAGE_MAP = {
    # Won synonyms → the "Won" mirror status
    "Grant Won": "Won",
    "Donation received": "Won",
    "Closed Won": "Won",
    # Lost synonyms → the "Lost" mirror status
    "Withdrawn": "Lost",
    "Grant unsuccessful": "Lost",
    "Unsuccesful": "Lost",  # SF data carries this misspelling
    "Closed Lost": "Lost",
    # Legacy / standard SF stages → nearest active mirror stage
    "Fundraising target": "Research",
    "Pledged": "Finalising",
    "Prospecting": "Research",
    "Qualification": "Research",
    "Needs Analysis": "Cold proposal or positive meeting",
    "Value Proposition": "Warm proposal to new funder",
    "Proposal/Price Quote": "Final stage proposal",
    "Negotiation/Review": "Finalising",
}


def map_deal_stage(sf_stage: str | None) -> str | None:
    if not sf_stage:
        return None
    return DEAL_STAGE_MAP.get(sf_stage, sf_stage)


def deal_stage_link(sf_stage: str | None) -> str | None:
    """Map SF Opportunity.StageName → ``CRM Deal Status``, auto-creating missing rows.

    ``CRM Deal.status`` is a Link → ``CRM Deal Status``. Without this wrapper
    SF stages that the org has added but the Frappe site hasn't seeded
    (e.g. ``Proposal/Quotation`` on a clean install) cause ``LinkValidationError``.
    """
    return _ensure_link("CRM Deal Status", map_deal_stage(sf_stage), "status", "deal_status")


# Maps SF stages that resolve to "Lost" → a CRM Lost Reason record name.
# Returns None for non-lost stages so the value is stripped by _upsert_doc.
DEAL_LOST_REASON_MAP = {
    "Lost": "Lost",
    "Withdrawn": "Withdrawn",
    "Grant unsuccessful": "Grant unsuccessful",
    "Closed Lost": "Lost",
}


def map_deal_lost_reason(sf_stage: str | None) -> str | None:
    if not sf_stage:
        return None
    return DEAL_LOST_REASON_MAP.get(sf_stage)


def deal_lost_reason_link(sf_stage: str | None) -> str | None:
    """SF stage → ``CRM Lost Reason`` Link, auto-creating missing rows."""
    return _ensure_link(
        "CRM Lost Reason", map_deal_lost_reason(sf_stage), "lost_reason"
    )


TASK_STATUS_MAP = {
    "Not Started": "Todo",
    "In Progress": "In Progress",
    "Completed": "Done",
    "Deferred": "Backlog",
    "Submitted on Time": "Done",
    "Waiting on someone else": "Todo",
}


def map_task_status(sf_status: str | None) -> str | None:
    if not sf_status:
        return "Todo"
    return TASK_STATUS_MAP.get(sf_status, "Todo")


def task_status_link(sf_status: str | None) -> str | None:
    """Map SF Task.Status → ``CRM Task Status`` Link, auto-creating missing rows.

    Newer Frappe CRM exposes ``status`` on ``CRM Task`` as a Link field; older
    builds keep it as a Select. ``_ensure_link`` returns the bare string when
    the DocType doesn't exist, so this works either way.
    """
    return _ensure_link("CRM Task Status", map_task_status(sf_status), "status")


TASK_PRIORITY_MAP = {
    "Normal": "Medium",
    "High": "High",
    "Low": "Low",
}


def map_task_priority(sf_priority: str | None) -> str | None:
    if not sf_priority:
        return "Medium"
    return TASK_PRIORITY_MAP.get(sf_priority, "Medium")


def task_priority_link(sf_priority: str | None) -> str | None:
    """Map SF Task.Priority → ``CRM Task Priority`` Link, auto-creating missing rows.

    Same Link-vs-Select compatibility as ``task_status_link`` (see above).
    """
    return _ensure_link("CRM Task Priority", map_task_priority(sf_priority), "priority")


# ----------------------------------------------------------------------
# Multi-input transforms (receive ``dict[str, Any]`` of {sf_field: value})
# ----------------------------------------------------------------------
def address_block(payload: Any) -> dict | None:
    """Build a Frappe ``Address``-shaped dict from an SF address block.

    Expected keys (any subset; missing → None): ``Street``, ``City``,
    ``State``, ``PostalCode``, ``Country`` — optionally prefixed (e.g.
    ``BillingStreet``, ``MailingCity``). Returns the canonical dict
    consumed by ``BaseSyncer.after_upsert`` via ``sync.addresses``;
    the syncer is responsible for picking up the per-syncer ``__address__``
    key in ``values`` and routing it to ``Address`` doc upsert.

    Returned shape: ``{"address_line1", "city", "state", "pincode", "country"}``,
    or ``None`` if every SF field is empty.
    """
    if not isinstance(payload, dict):
        return None
    norm: dict[str, str | None] = {}
    for sf_key, sf_val in payload.items():
        if sf_val in (None, ""):
            continue
        # Strip the prefix (Billing, Mailing, Other, Shipping) to get the
        # generic suffix (Street, City, State, PostalCode, Country).
        suffix = sf_key
        for prefix in ("Billing", "Mailing", "Other", "Shipping"):
            if sf_key.startswith(prefix):
                suffix = sf_key[len(prefix):]
                break
        norm[suffix] = str(sf_val).strip() or None
    if not norm:
        return None
    return {
        "address_line1": norm.get("Street"),
        "city": norm.get("City"),
        "state": norm.get("State"),
        "pincode": norm.get("PostalCode"),
        "country": norm.get("Country"),
    }


def email_table(payload: Any) -> list[dict] | None:
    """Build a ``Contact.email_ids`` child-table payload from SF email fields.

    The first non-empty SF field marks ``is_primary=1``. Empty fields are
    dropped. Duplicate addresses are collapsed (case-insensitive).
    """
    if not isinstance(payload, dict):
        return None
    rows: list[dict] = []
    seen: set[str] = set()
    is_primary = 1
    for sf_field in (
        "Email",
        "npe01__WorkEmail__c",
        "npe01__HomeEmail__c",
        "npe01__AlternateEmail__c",
    ):
        val = payload.get(sf_field)
        if not val:
            continue
        addr = str(val).strip()
        if not addr or addr.lower() in seen:
            continue
        seen.add(addr.lower())
        rows.append({"email_id": addr, "is_primary": is_primary})
        is_primary = 0
    return rows or None


def phone_table(payload: Any) -> list[dict] | None:
    """Build a ``Contact.phone_nos`` child-table payload from SF phone fields.

    ``Phone`` becomes the primary phone; ``MobilePhone`` becomes the primary
    mobile. Duplicates collapsed by exact-string comparison (no normalisation;
    +44 vs 044 vs 0044 stay distinct because we don't have a parser here).
    """
    if not isinstance(payload, dict):
        return None
    rows: list[dict] = []
    seen: set[str] = set()
    field_flags = {
        "Phone": {"is_primary_phone": 1},
        "MobilePhone": {"is_primary_mobile_no": 1},
        "HomePhone": {},
        "OtherPhone": {},
        "AssistantPhone": {},
        "Fax": {},
    }
    for sf_field, flags in field_flags.items():
        val = payload.get(sf_field)
        if not val:
            continue
        # A handful of SF records cram two numbers into one field
        # (e.g. "+256 718093205 / +260 961110246") — split on the common
        # separators rather than passing the combined garbage through,
        # which Frappe's phone validator rejects wholesale.
        parts = [p.strip() for p in re.split(r"[/,;]", str(val)) if p.strip()]
        # Some "phone" fields actually hold a URL (e.g. a WhatsApp link),
        # which splitting on "/" shreds into non-numeric fragments like
        # "https:" — drop anything with no digits at all rather than feed
        # it to Frappe's phone validator.
        parts = [p for p in parts if any(ch.isdigit() for ch in p)]
        for i, num in enumerate(parts):
            if num in seen:
                continue
            seen.add(num)
            row = {"phone": num}
            if i == 0:
                row.update(flags)
            rows.append(row)
    return rows or None


# ----------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------
TRANSFORMS = {
    "none": lambda v: v,
    "boolean": to_bool,
    "date": to_date,
    "datetime": to_datetime,
    "html_strip": html_strip,
    "user_lookup": map_user_by_email,
    "account_lookup": map_account,
    "contact_lookup": map_contact,
    "polymorphic_lookup": map_polymorphic,
    "campaign_lookup": map_campaign,
    "deal_stage": map_deal_stage,
    "deal_stage_link": deal_stage_link,
    "lead_status": map_lead_status,
    "lead_status_link": lead_status_link,
    "lead_source": lead_source_link,
    "task_status": map_task_status,
    "task_status_link": task_status_link,
    "task_priority": map_task_priority,
    "task_priority_link": task_priority_link,
    "deal_lost_reason": map_deal_lost_reason,
    "deal_lost_reason_link": deal_lost_reason_link,
    "employee_bucket": employee_bucket,
    "industry_link": industry_link,
    "lost_reason_link": lost_reason_link,
    "salutation_link": salutation_link,
    "address": address_block,
    "email_table": email_table,
    "phone_table": phone_table,
}


def apply_transform(name: str | None, value: Any) -> Any:
    if not name:
        return value
    fn = TRANSFORMS.get(name)
    if fn is None:
        return value
    return fn(value)
