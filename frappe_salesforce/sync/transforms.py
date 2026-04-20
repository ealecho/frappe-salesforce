"""Value transforms for mapping Salesforce field values to Frappe field values."""

from __future__ import annotations

import html
import re
from typing import Any

import frappe
from frappe.utils import get_datetime

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
    return str(get_datetime(value))


def html_strip(value: Any) -> str | None:
    if not value:
        return None
    text = _TAG_RE.sub("", str(value))
    return html.unescape(text).strip()


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
    "Working - Contacted": "Working",
    "Closed - Converted": "Qualified",
    "Closed - Not Converted": "Unqualified",
}


def map_lead_status(sf_status: str | None) -> str | None:
    if not sf_status:
        return None
    return LEAD_STATUS_MAP.get(sf_status, sf_status)


DEAL_STAGE_MAP = {
    "Prospecting": "Qualification",
    "Qualification": "Qualification",
    "Needs Analysis": "Demo/Making",
    "Value Proposition": "Demo/Making",
    "Id. Decision Makers": "Demo/Making",
    "Perception Analysis": "Demo/Making",
    "Proposal/Price Quote": "Proposal/Quotation",
    "Negotiation/Review": "Negotiation",
    "Closed Won": "Won",
    "Closed Lost": "Lost",
}


def map_deal_stage(sf_stage: str | None) -> str | None:
    if not sf_stage:
        return None
    return DEAL_STAGE_MAP.get(sf_stage, sf_stage)


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
    "deal_stage": map_deal_stage,
    "lead_status": map_lead_status,
}


def apply_transform(name: str | None, value: Any) -> Any:
    if not name:
        return value
    fn = TRANSFORMS.get(name)
    if fn is None:
        return value
    return fn(value)
