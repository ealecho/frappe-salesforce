"""Remove mapping rows that cause SOQL 400s on common NPSP orgs, and
upgrade the Lead.LeadSource row to use the new ``lead_source`` transform
which auto-creates missing CRM Lead Source records.

Background:
- ``Account.ParentId`` and ``Contact.RecordTypeId`` are FLS-restricted for
  the integration user in many orgs (incl. NPSP), causing
  ``INVALID_FIELD`` 400s that abort the whole syncer.
- ``Lead.LeadSource`` mapped 1:1 to ``CRM Lead.source`` was failing on
  values like "MailChimp" that didn't exist as ``CRM Lead Source`` rows.
"""

from __future__ import annotations

import frappe


def execute():
    # 1) Drop Account.ParentId mapping row.
    _delete_row("Account", "ParentId")
    # 2) Drop Contact.RecordTypeId mapping row.
    _delete_row("Contact", "RecordTypeId")
    # 3) Upgrade Lead.LeadSource transform.
    _set_transform("Lead", "LeadSource", "lead_source")
    frappe.db.commit()


def _delete_row(salesforce_object: str, sf_field: str) -> None:
    parent = frappe.db.get_value(
        "Salesforce Field Mapping",
        {"salesforce_object": salesforce_object},
        "name",
    )
    if not parent:
        return
    frappe.db.sql(
        """
        DELETE FROM `tabSalesforce Field Mapping Row`
        WHERE parent = %s AND sf_field = %s
        """,
        (parent, sf_field),
    )


def _set_transform(
    salesforce_object: str, sf_field: str, transform: str
) -> None:
    parent = frappe.db.get_value(
        "Salesforce Field Mapping",
        {"salesforce_object": salesforce_object},
        "name",
    )
    if not parent:
        return
    frappe.db.sql(
        """
        UPDATE `tabSalesforce Field Mapping Row`
        SET transform = %s
        WHERE parent = %s AND sf_field = %s
        """,
        (transform, parent, sf_field),
    )
