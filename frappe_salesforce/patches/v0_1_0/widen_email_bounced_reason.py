"""Widen ``custom_sf_email_bounced_reason`` on Contact and CRM Lead to Small Text.

Bounce messages run past Data's 140 chars and carry ``<addresses>``. The
sync truncates to 140, then the save escapes ``<`` to ``&lt;`` and the value
overflows again: a contact failed with ``CharacterLengthExceededError`` on
2026-10-27. ``after_migrate`` also converges the field from
``setup/custom_fields.py``; this patch makes the change explicit, like
``widen_file_location``.

Idempotent: only mutates a field that is still ``Data``.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    for dt in ("Contact", "CRM Lead"):
        name = frappe.db.get_value(
            "Custom Field",
            {"dt": dt, "fieldname": "custom_sf_email_bounced_reason"},
            "name",
        )
        if not name:
            continue
        cf = frappe.get_doc("Custom Field", name)
        if cf.fieldtype in ("Small Text", "Long Text", "Text"):
            continue
        cf.fieldtype = "Small Text"
        cf.length = 0
        cf.save(ignore_permissions=True)
    frappe.db.commit()
