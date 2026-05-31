"""Surgically rewrite buggy mapping rows from v0.0.x.

Targets rows on existing sites that pre-date v0.1.0:

1. ``Opportunity.Amount → annual_revenue``  →  ``Amount → deal_value``
2. ``Opportunity.CloseDate → close_date``    →  ``CloseDate → expected_closure_date`` (transform: date)
3. ``Account.NumberOfEmployees → no_of_employees`` (no transform)
   →  add transform ``employee_bucket``
4. ``Account.Industry → industry`` / ``Lead.Industry → industry`` (no transform)
   →  add transform ``industry_link``
5. ``Lead.LeadSource → source`` (no transform)
   →  add transform ``lead_source``
6. ``Task.ActivityDate → due_date`` (transform=date)
   →  transform=datetime
7. ``Contact.Email → email_id`` / ``Phone → phone`` / ``MobilePhone → mobile_no``
   →  delete (replaced by multi-input ``email_table`` / ``phone_table`` rows
   inserted by ``extend_default_mappings``).

This patch is additive; it never removes mappings beyond the three
read-only Contact targets in (7), which are functionally broken.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    _fix_opportunity()
    _fix_account()
    _fix_lead()
    _fix_task_due_date()
    _drop_broken_contact_flat_fields()


def _fix_opportunity() -> None:
    name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Opportunity"}, "name"
    )
    if not name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", name)
    changed = False
    for row in doc.field_mappings:
        if row.sf_field == "Amount" and row.frappe_field == "annual_revenue":
            row.frappe_field = "deal_value"
            changed = True
        if row.sf_field == "CloseDate" and row.frappe_field == "close_date":
            row.frappe_field = "expected_closure_date"
            row.transform = "date"
            changed = True
    if changed:
        doc.save(ignore_permissions=True)


def _fix_account() -> None:
    name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Account"}, "name"
    )
    if not name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", name)
    changed = False
    for row in doc.field_mappings:
        if (
            row.sf_field == "NumberOfEmployees"
            and row.frappe_field == "no_of_employees"
            and (not row.transform or row.transform == "none")
        ):
            row.transform = "employee_bucket"
            changed = True
        if (
            row.sf_field == "Industry"
            and row.frappe_field == "industry"
            and (not row.transform or row.transform == "none")
        ):
            row.transform = "industry_link"
            changed = True
    if changed:
        doc.save(ignore_permissions=True)


def _fix_lead() -> None:
    name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Lead"}, "name"
    )
    if not name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", name)
    changed = False
    for row in doc.field_mappings:
        if (
            row.sf_field == "Industry"
            and row.frappe_field == "industry"
            and (not row.transform or row.transform == "none")
        ):
            row.transform = "industry_link"
            changed = True
        if (
            row.sf_field == "LeadSource"
            and row.frappe_field == "source"
            and (not row.transform or row.transform == "none")
        ):
            row.transform = "lead_source"
            changed = True
        if (
            row.sf_field == "NumberOfEmployees"
            and row.frappe_field == "no_of_employees"
            and (not row.transform or row.transform == "none")
        ):
            row.transform = "employee_bucket"
            changed = True
    if changed:
        doc.save(ignore_permissions=True)


def _fix_task_due_date() -> None:
    name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Task"}, "name"
    )
    if not name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", name)
    changed = False
    for row in doc.field_mappings:
        if (
            row.sf_field == "ActivityDate"
            and row.frappe_field == "due_date"
            and row.transform == "date"
        ):
            row.transform = "datetime"
            changed = True
    if changed:
        doc.save(ignore_permissions=True)

    # Same for Event mapping (Event also writes ActivityDate → due_date).
    event_name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Event"}, "name"
    )
    if not event_name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", event_name)
    changed = False
    for row in doc.field_mappings:
        if (
            row.sf_field == "ActivityDate"
            and row.frappe_field == "due_date"
            and row.transform == "date"
        ):
            row.transform = "datetime"
            changed = True
    if changed:
        doc.save(ignore_permissions=True)


def _drop_broken_contact_flat_fields() -> None:
    """Remove rows that target read-only Contact fields.

    ``email_id``, ``phone``, ``mobile_no`` on Frappe ``Contact`` are
    auto-derived from the ``email_ids``/``phone_nos`` child tables and
    silently no-op when written to. v0.1.0 inserts proper multi-input
    ``email_table``/``phone_table`` rows via ``extend_default_mappings``.
    """
    name = frappe.db.get_value(
        "Salesforce Field Mapping", {"salesforce_object": "Contact"}, "name"
    )
    if not name:
        return
    doc = frappe.get_doc("Salesforce Field Mapping", name)
    drop_targets = {
        ("Email", "email_id"),
        ("Phone", "phone"),
        ("MobilePhone", "mobile_no"),
    }
    keep = []
    dropped = 0
    for row in doc.field_mappings:
        if (row.sf_field, row.frappe_field) in drop_targets:
            dropped += 1
            continue
        keep.append(row)
    if dropped:
        doc.field_mappings = keep
        doc.save(ignore_permissions=True)
