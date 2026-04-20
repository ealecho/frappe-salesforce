"""Seed quota-safety defaults on existing installs.

Idempotent. Safe to run on fresh installs (no-op when values already set).
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime


def execute() -> None:
    if not frappe.db.exists("DocType", "Salesforce Settings"):
        return

    # Reload the doctype so new fields (max_calls_per_tick, etc.) exist in
    # the DB schema before we try to write to them.
    frappe.reload_doc("frappe_salesforce", "doctype", "salesforce_settings")
    frappe.reload_doc("frappe_salesforce", "doctype", "salesforce_sync_log")
    frappe.reload_doc("frappe_salesforce", "doctype", "salesforce_sync_log_item")

    settings = frappe.get_single("Salesforce Settings")
    changed = False

    for field, default in (
        ("max_calls_per_tick", 500),
        ("max_calls_per_day", 50_000),
        ("preflight_threshold", 80),
    ):
        if not settings.get(field):
            settings.set(field, default)
            changed = True

    # Seed any still-empty HWMs to now() so we never backfill from epoch.
    # We deliberately do NOT touch fields that already have a value — the
    # user may have intentionally set an earlier HWM via the Backfill
    # action.
    hwm_fields = [
        "last_sync_user",
        "last_sync_account",
        "last_sync_contact",
        "last_sync_lead",
        "last_sync_opportunity",
        "last_sync_task",
        "last_sync_event",
    ]
    install_now = now_datetime()
    for field in hwm_fields:
        if not settings.get(field):
            settings.set(field, install_now)
            changed = True

    if changed:
        settings.save(ignore_permissions=True)
        frappe.db.commit()
