"""Backfill ``File_location__c`` mapping row to use the ``html_strip`` transform.

SF stores file-location text wrapped in HTML (``<strong>...``) that would
otherwise leak into Frappe verbatim. Idempotent — only sets the transform
if it's still empty / ``none``.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    name = frappe.db.get_value(
        "Salesforce Field Mapping",
        {"salesforce_object": "Opportunity"},
        "name",
    )
    if not name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", name)
    changed = False
    for row in doc.field_mappings:
        if (
            row.sf_field == "File_location__c"
            and row.frappe_field == "custom_sf_file_location"
            and (not row.transform or row.transform == "none")
        ):
            row.transform = "html_strip"
            changed = True
    if changed:
        doc.save(ignore_permissions=True)
