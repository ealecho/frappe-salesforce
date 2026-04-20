"""Wire picklist transforms onto existing Salesforce Field Mapping rows.

Existing sites already have Task/Status and Task/Priority rows from install
but without transform functions — raw SF picklist values pass through and
fail Frappe validation.  This patch sets the correct transforms and updates
the Select options on the child doctype so the UI exposes the new choices.

Also creates CRM Lost Reason records for SF lost-deal stages and adds the
StageName → lost_reason mapping row to the Opportunity Field Mapping.
"""

from __future__ import annotations

import frappe


# (parent_name, sf_field) → transform to set
_TRANSFORM_FIXES: list[tuple[str, str, str]] = [
    ("Task", "Status", "task_status"),
    ("Task", "Priority", "task_priority"),
    ("Event", "Status", "task_status"),
    ("Event", "Priority", "task_priority"),
    ("Lead", "Status", "lead_status"),
    ("Opportunity", "StageName", "deal_stage"),
]

# Full list of transform options — must match TRANSFORMS dict in
# frappe_salesforce/sync/transforms.py.
_ALL_TRANSFORM_OPTIONS = (
    "none\nboolean\ndate\ndatetime\nhtml_strip\n"
    "user_lookup\naccount_lookup\ndeal_stage\ndeal_lost_reason\n"
    "lead_status\ntask_status\ntask_priority"
)

# CRM Lost Reason records to create for SF lost-deal stages.
_LOST_REASONS = ["Lost", "Withdrawn", "Grant unsuccessful"]


def execute() -> None:
    # 1. Update the Select options on the transform field so the UI
    #    allows the new values.
    frappe.db.set_value(
        "DocField",
        {"parent": "Salesforce Field Mapping Row", "fieldname": "transform"},
        "options",
        _ALL_TRANSFORM_OPTIONS,
    )

    # 2. Set transforms on existing child-table rows where missing.
    for parent_name, sf_field, transform in _TRANSFORM_FIXES:
        frappe.db.sql(
            """
            UPDATE `tabSalesforce Field Mapping Row`
            SET `transform` = %s
            WHERE `parent` = %s
              AND `sf_field` = %s
              AND (`transform` IS NULL OR `transform` = '' OR `transform` = 'none')
            """,
            (transform, parent_name, sf_field),
        )

    # 3. Create CRM Lost Reason records for SF lost-deal stages.
    for reason in _LOST_REASONS:
        if not frappe.db.exists("CRM Lost Reason", reason):
            frappe.get_doc(
                {"doctype": "CRM Lost Reason", "reason": reason}
            ).insert(ignore_permissions=True)

    # 4. Add StageName → lost_reason mapping row to Opportunity if missing.
    opp_mapping = frappe.db.get_value(
        "Salesforce Field Mapping",
        {"salesforce_object": "Opportunity"},
        "name",
    )
    if opp_mapping:
        already_has = frappe.db.exists(
            "Salesforce Field Mapping Row",
            {
                "parent": opp_mapping,
                "sf_field": "StageName",
                "frappe_field": "lost_reason",
            },
        )
        if not already_has:
            doc = frappe.get_doc("Salesforce Field Mapping", opp_mapping)
            doc.append(
                "field_mappings",
                {
                    "sf_field": "StageName",
                    "frappe_field": "lost_reason",
                    "transform": "deal_lost_reason",
                },
            )
            doc.save(ignore_permissions=True)

    frappe.db.commit()
