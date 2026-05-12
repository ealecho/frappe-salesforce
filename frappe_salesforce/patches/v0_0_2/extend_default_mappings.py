"""Backfill default Salesforce field mappings on existing sites.

For each entry in :data:`DEFAULT_MAPPINGS`:

* If no ``Salesforce Field Mapping`` doc exists for the SF object → create
  it via :func:`seed_default_field_mappings` (same path as fresh install).
* If one exists → append any rows whose ``(sf_field, frappe_field)`` pair
  is not already present. Existing rows are left untouched so admins can
  customise transforms without losing edits on migrate.

Also cleans up legacy duplicate ``sf_field`` rows previously inserted by
``v0_0_1.fix_picklist_transforms`` (the ``StageName`` row on Opportunity).
The Salesforce Field Mapping validator forbids duplicate ``sf_field`` per
mapping, so any future ``save()`` on those mappings would otherwise fail.
The behaviour those duplicate rows provided (deriving ``lost_reason`` from
``StageName``) is now handled inside ``OpportunitySyncer.enrich_values``.
"""

from __future__ import annotations

import frappe

from frappe_salesforce.setup.default_mappings import (
    DEFAULT_MAPPINGS,
    seed_default_field_mappings,
)


# (salesforce_object, sf_field, frappe_field) tuples to delete from
# `Salesforce Field Mapping Row` because the SF field is now resolved
# inside the syncer's ``enrich_values`` rather than via a duplicate row.
_LEGACY_DUPLICATES_TO_REMOVE: list[tuple[str, str, str]] = [
    ("Opportunity", "StageName", "lost_reason"),
]


def _remove_legacy_duplicate_rows() -> None:
    for sf_object, sf_field, frappe_field in _LEGACY_DUPLICATES_TO_REMOVE:
        parent = frappe.db.get_value(
            "Salesforce Field Mapping",
            {"salesforce_object": sf_object},
            "name",
        )
        if not parent:
            continue
        frappe.db.sql(
            """
            DELETE FROM `tabSalesforce Field Mapping Row`
            WHERE `parent` = %s
              AND `sf_field` = %s
              AND `frappe_field` = %s
            """,
            (parent, sf_field, frappe_field),
        )


def execute() -> None:
    # 0. Remove duplicate-sf_field rows added by v0_0_1 patches.
    _remove_legacy_duplicate_rows()

    # 1. Create any wholly new mappings (Campaign, Recurring Donation, etc.).
    seed_default_field_mappings()

    # 2. Extend existing mappings with new rows.
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

    frappe.db.commit()
