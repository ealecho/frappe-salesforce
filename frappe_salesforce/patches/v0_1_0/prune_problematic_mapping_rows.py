"""Drop mapping rows that are FLS-blocked on common NPSP orgs.

The ``v0_1_0.extend_default_mappings`` patch reintroduced
``Contact.RecordTypeId → custom_sf_record_type`` (a row that v0.0.2 had
already learned to prune). NPSP orgs frequently FLS-restrict
``Contact.RecordTypeId`` from the integration user, causing the entire
Contact sync to abort with ``INVALID_FIELD`` 400 before any record is
fetched.

This patch removes the offending row from any existing site's Contact
mapping. It's idempotent: re-running it does nothing if the row is
already absent. Admins whose org *does* expose Contact.RecordTypeId can
re-add the row via the Salesforce Field Mapping UI.

(Mirrors v0.0.2's ``prune_problematic_mapping_rows`` strategy.)
"""

from __future__ import annotations

import frappe

#: Mapping rows to remove. Format: ``(salesforce_object, sf_field, frappe_field)``.
PROBLEMATIC_ROWS: list[tuple[str, str, str]] = [
    ("Contact", "RecordTypeId", "custom_sf_record_type"),
]


def execute() -> None:
    for sf_obj, sf_field, frappe_field in PROBLEMATIC_ROWS:
        mapping_name = frappe.db.get_value(
            "Salesforce Field Mapping",
            {"salesforce_object": sf_obj},
            "name",
        )
        if not mapping_name:
            continue
        doc = frappe.get_doc("Salesforce Field Mapping", mapping_name)
        keep = []
        dropped = 0
        for row in doc.field_mappings:
            if row.sf_field == sf_field and row.frappe_field == frappe_field:
                dropped += 1
                continue
            keep.append(row)
        if dropped:
            doc.field_mappings = keep
            doc.save(ignore_permissions=True)
            print(
                f"  pruned {dropped} {sf_obj} mapping row(s): "
                f"{sf_field} -> {frappe_field}"
            )
