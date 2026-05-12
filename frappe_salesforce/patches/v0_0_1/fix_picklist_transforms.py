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

    # 4. (Removed in v0.0.2) Previously appended a second StageName row
    #    (StageName → lost_reason) here. That row violates the Salesforce
    #    Field Mapping validator (duplicate sf_field per mapping) and broke
    #    subsequent doc.save() calls. Deriving lost_reason from StageName
    #    is now handled in OpportunitySyncer.enrich_values, and the
    #    v0_0_2.extend_default_mappings patch cleans up any duplicate rows
    #    inserted by older versions of this patch.

    frappe.db.commit()
