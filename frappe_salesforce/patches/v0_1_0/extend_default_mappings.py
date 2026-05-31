"""Additively backfill v0.1.0 default mapping rows on existing sites.

Existing ``Salesforce Field Mapping`` records get new rows from
``DEFAULT_MAPPINGS`` that aren't already present. Existing rows are
matched by ``(sf_field, frappe_field)`` and left untouched — this patch
NEVER overwrites or deletes user-customised mappings.

For Salesforce objects that have no mapping at all yet, the full default
is created.
"""

from __future__ import annotations

import frappe

from frappe_salesforce.setup.default_mappings import DEFAULT_MAPPINGS, _serialise_row


def execute() -> None:
    for mapping in DEFAULT_MAPPINGS:
        sf_obj = mapping["salesforce_object"]
        existing_name = frappe.db.get_value(
            "Salesforce Field Mapping",
            {"salesforce_object": sf_obj},
            "name",
        )
        if not existing_name:
            doc = frappe.get_doc(
                {
                    "doctype": "Salesforce Field Mapping",
                    "salesforce_object": sf_obj,
                    "frappe_doctype": mapping["frappe_doctype"],
                    "enabled": 1,
                    "field_mappings": [
                        _serialise_row(row) for row in mapping["rows"]
                    ],
                }
            )
            doc.insert(ignore_permissions=True)
            continue

        doc = frappe.get_doc("Salesforce Field Mapping", existing_name)
        existing_pairs = {
            (row.sf_field or "", row.frappe_field or "")
            for row in doc.field_mappings
        }
        added = 0
        for row in mapping["rows"]:
            serialised = _serialise_row(row)
            key = (serialised["sf_field"] or "", serialised["frappe_field"] or "")
            if key in existing_pairs:
                continue
            doc.append("field_mappings", serialised)
            added += 1
        if added:
            doc.save(ignore_permissions=True)
