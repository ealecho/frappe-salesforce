"""Upgrade picklist transforms to their link-safe variants on existing sites.

Frappe CRM exposes ``CRM Lead.status``, ``CRM Deal.status``,
``CRM Deal.lost_reason``, and (on newer builds) ``CRM Task.status`` /
``CRM Task.priority`` as **Link** fields, not Select. The earlier
``deal_stage`` / ``lead_status`` / ``task_status`` / ``task_priority`` /
``deal_lost_reason`` transforms only mapped values; they didn't ensure the
target Link parent existed, causing ``LinkValidationError`` on any clean
install whose CRM hadn't been seeded by hand (the typical staging case).

This patch is **additive and idempotent**: it rewrites only rows that
still use the bare picklist transform names. Rows that already reference
the ``_link`` variant — or any other custom transform — are left alone.
"""

from __future__ import annotations

import frappe

# (sf_object, sf_field, frappe_field, old_transform, new_transform)
_REWRITES: list[tuple[str, str, str, str, str]] = [
    ("Lead", "Status", "status", "lead_status", "lead_status_link"),
    ("Opportunity", "StageName", "status", "deal_stage", "deal_stage_link"),
    (
        "Opportunity",
        "StageName",
        "lost_reason",
        "deal_lost_reason",
        "deal_lost_reason_link",
    ),
    ("Task", "Status", "status", "task_status", "task_status_link"),
    ("Task", "Priority", "priority", "task_priority", "task_priority_link"),
    ("Event", "Status", "status", "task_status", "task_status_link"),
    ("Event", "Priority", "priority", "task_priority", "task_priority_link"),
]


def execute() -> None:
    by_object: dict[str, list[tuple[str, str, str, str]]] = {}
    for sf_object, sf_field, frappe_field, old, new in _REWRITES:
        by_object.setdefault(sf_object, []).append(
            (sf_field, frappe_field, old, new)
        )

    for sf_object, rules in by_object.items():
        name = frappe.db.get_value(
            "Salesforce Field Mapping", {"salesforce_object": sf_object}, "name"
        )
        if not name:
            continue
        doc = frappe.get_doc("Salesforce Field Mapping", name)
        changed = False
        for row in doc.field_mappings:
            for sf_field, frappe_field, old, new in rules:
                if (
                    row.sf_field == sf_field
                    and row.frappe_field == frappe_field
                    and row.transform == old
                ):
                    row.transform = new
                    changed = True
        if changed:
            doc.save(ignore_permissions=True)
