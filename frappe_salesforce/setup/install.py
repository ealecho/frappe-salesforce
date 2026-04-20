"""after_install hook."""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from .default_mappings import seed_default_field_mappings

SF_ID_DOCTYPES = [
    "CRM Organization",
    "Contact",
    "CRM Lead",
    "CRM Deal",
    "CRM Task",
]

# Fields on Salesforce Settings that hold per-syncer high-water marks.
# Default to install-time ``now()`` so the first tick does NOT backfill
# from 1970 — that behaviour nearly blew our API quota once already.
# Users who want a backfill run the "Backfill From Date" action.
HWM_FIELDS = [
    "last_sync_user",
    "last_sync_account",
    "last_sync_contact",
    "last_sync_lead",
    "last_sync_opportunity",
    "last_sync_task",
    "last_sync_event",
]


def after_install() -> None:
    _ensure_custom_fields()
    _ensure_default_settings()
    seed_default_field_mappings()
    frappe.db.commit()


def _ensure_custom_fields() -> None:
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    sf_id_field = {
        "fieldname": "custom_salesforce_id",
        "label": "Salesforce ID",
        "fieldtype": "Data",
        "unique": 1,
        "read_only": 1,
        "no_copy": 1,
        "in_standard_filter": 1,
        "search_index": 1,
    }
    activity_type_field = {
        "fieldname": "custom_sf_activity_type",
        "label": "Salesforce Activity Type",
        "fieldtype": "Select",
        "options": "\nTask\nEvent",
        "read_only": 1,
        "no_copy": 1,
    }

    fields: dict[str, list[dict]] = {dt: [sf_id_field] for dt in SF_ID_DOCTYPES}
    # CRM Task gets the extra activity type discriminator.
    fields["CRM Task"] = [sf_id_field, activity_type_field]

    create_custom_fields(fields, ignore_validate=True)


def _ensure_default_settings() -> None:
    settings = frappe.get_single("Salesforce Settings")
    changed = False
    if not settings.api_version:
        settings.api_version = "v60.0"
        changed = True
    if not settings.login_url:
        settings.login_url = "https://login.salesforce.com"
        changed = True
    if not settings.batch_size:
        settings.batch_size = 500
        changed = True
    if not settings.get("max_calls_per_tick"):
        settings.max_calls_per_tick = 500
        changed = True
    if not settings.get("max_calls_per_day"):
        settings.max_calls_per_day = 50_000
        changed = True
    if not settings.get("preflight_threshold"):
        settings.preflight_threshold = 80
        changed = True
    # Seed HWMs to install-time now() so the first run doesn't backfill
    # from epoch. Only set fields that are still empty — never clobber
    # existing progress.
    install_now = now_datetime()
    for field in HWM_FIELDS:
        if not settings.get(field):
            settings.set(field, install_now)
            changed = True
    if changed:
        settings.save(ignore_permissions=True)
