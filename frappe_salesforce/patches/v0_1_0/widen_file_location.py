"""Widen ``CRM Deal.custom_sf_file_location`` from Data to Small Text.

SF stores long network-share paths (often wrapped in HTML for display in
Lightning), commonly 200+ chars. The original ``Data`` (140-char) field
caused ``CharacterLengthExceededError`` on real Opportunity records.

We pick **Small Text** (not Long Text) because Frappe's
``ALLOWED_FIELDTYPE_CHANGE`` whitelist only permits ``Data <-> Small Text``
and ``Data <-> Text`` on existing Custom Fields. Small Text has no
practical length cap for our use case.

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
    if cf.fieldtype in ("Small Text", "Long Text", "Text"):
        return
    cf.fieldtype = "Small Text"
    cf.length = 0
    cf.save(ignore_permissions=True)
    frappe.db.commit()
