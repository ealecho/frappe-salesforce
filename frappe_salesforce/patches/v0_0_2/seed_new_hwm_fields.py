"""Seed HWMs for the Wave 3 syncers on existing sites.

The new ``last_sync_*`` fields are added to the ``Salesforce Settings``
DocType JSON in v0.0.2. On migrate the columns appear but are NULL —
which would cause the first incremental run to backfill from epoch and
nearly certainly blow the daily API budget. Seed each new HWM to
``now()`` so admins must opt-in to a backfill via the explicit action.

Only previously empty fields are written; existing values are preserved.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

NEW_HWM_FIELDS = [
    "last_sync_campaign",
    "last_sync_recurring_donation",
    "last_sync_payment",
    "last_sync_relationship",
    "last_sync_affiliation",
    "last_sync_event_relation",
]


def execute() -> None:
    frappe.reload_doc("frappe_salesforce", "doctype", "salesforce_settings")
    settings = frappe.get_single("Salesforce Settings")
    changed = False
    install_now = now_datetime()
    for field in NEW_HWM_FIELDS:
        if not settings.get(field):
            settings.set(field, install_now)
            changed = True
    if changed:
        settings.save(ignore_permissions=True)
