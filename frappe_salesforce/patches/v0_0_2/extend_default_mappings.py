"""Backfill default Salesforce field mappings on existing sites.

For each entry in :data:`DEFAULT_MAPPINGS`:

* If no ``Salesforce Field Mapping`` doc exists for the SF object → create
  it via :func:`seed_default_field_mappings` (same path as fresh install).
* If one exists → append any rows whose ``(sf_field, frappe_field)`` pair
  is not already present. Existing rows are left untouched so admins can
  customise transforms without losing edits on migrate.
"""

from __future__ import annotations

import frappe

from frappe_salesforce.setup.default_mappings import (
    DEFAULT_MAPPINGS,
    seed_default_field_mappings,
)


def execute() -> None:
    # Create any wholly new mappings (Campaign, Recurring Donation, etc.).
    seed_default_field_mappings()

    # Extend existing mappings with new rows.
    for mapping in DEFAULT_MAPPINGS:
        name = frappe.db.get_value(
            "Salesforce Field Mapping",
            {"salesforce_object": mapping["salesforce_object"]},
            "name",
        )
        if not name:
            continue  # seed_default_field_mappings already handled creation
        doc = frappe.get_doc("Salesforce Field Mapping", name)
        existing = {(r.sf_field, r.frappe_field) for r in doc.field_mappings}
        added = False
        for row in mapping["rows"]:
            key = (row["sf_field"], row["frappe_field"])
            if key in existing:
                continue
            doc.append(
                "field_mappings",
                {
                    "sf_field": row["sf_field"],
                    "frappe_field": row["frappe_field"],
                    "transform": row.get("transform") or "none",
                },
            )
            added = True
        if added:
            doc.save(ignore_permissions=True)
