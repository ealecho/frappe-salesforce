"""Remove the Opportunity ``Probability → probability`` mapping row.

Deal probability in this CRM is owned by the status, not Salesforce: the
``peas_crm`` validate hook overwrites ``probability`` from the CRM Deal
Status on every save, so syncing SF ``Probability`` into the field is dead
weight (always clobbered) and misleading. Probability now flows via the
stage→status mapping instead (see ``transforms.DEAL_STAGE_MAP`` +
``setup/deal_statuses.py``).

Idempotent: does nothing if the row is already absent. The row is also
removed from ``default_mappings`` so the ``after_migrate`` self-heal won't
re-add it.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    mapping_name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Opportunity"}, "name"
    )
    if not mapping_name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", mapping_name)
    keep = []
    dropped = 0
    for row in doc.field_mappings:
        if row.sf_field == "Probability" and row.frappe_field == "probability":
            dropped += 1
            continue
        keep.append(row)
    if dropped:
        doc.field_mappings = keep
        doc.save(ignore_permissions=True)
        print(f"  pruned {dropped} Opportunity mapping row(s): Probability -> probability")
