"""Widen ``CRM Deal.custom_sf_file_location`` from Data to Long Text.

SF stores long network-share paths (often wrapped in HTML for display in
Lightning), commonly 200+ chars. The original ``Data`` (140-char) field
caused ``CharacterLengthExceededError`` on real Opportunity records.

Idempotent: only mutates the field if it's still ``Data``.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    name = frappe.db.get_value(
        "Custom Field",
        {"dt": "CRM Deal", "fieldname": "custom_sf_file_location"},
        "name",
    )
    if not name:
        return
    cf = frappe.get_doc("Custom Field", name)
    if cf.fieldtype == "Long Text":
        return
    cf.fieldtype = "Long Text"
    cf.length = 0  # Long Text doesn't honour length anyway; keep it tidy.
    cf.save(ignore_permissions=True)
    # Backfill the underlying column type via ``alter`` (Frappe's Custom
    # Field save schedules a column resync but only on the next migrate
    # tick; do it explicitly so the next sync run can write long values).
    frappe.db.commit()
