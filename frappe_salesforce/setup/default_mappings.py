"""Seed default Salesforce → Frappe field mappings.

These are idempotent: mappings are only created if one does not already exist
for the Salesforce object.
"""

from __future__ import annotations

import frappe

DEFAULT_MAPPINGS: list[dict] = [
    {
        "salesforce_object": "Account",
        "frappe_doctype": "CRM Organization",
        "rows": [
            {"sf_field": "Name", "frappe_field": "organization_name"},
            {"sf_field": "Website", "frappe_field": "website"},
            {"sf_field": "Industry", "frappe_field": "industry"},
            {"sf_field": "AnnualRevenue", "frappe_field": "annual_revenue"},
            {"sf_field": "NumberOfEmployees", "frappe_field": "no_of_employees"},
            {"sf_field": "BillingCity", "frappe_field": "city"},
            {"sf_field": "BillingState", "frappe_field": "state"},
            {"sf_field": "BillingCountry", "frappe_field": "country"},
            {
                "sf_field": "OwnerId",
                "frappe_field": "deal_owner",
                "transform": "user_lookup",
            },
        ],
    },
    {
        "salesforce_object": "Contact",
        "frappe_doctype": "Contact",
        "rows": [
            {"sf_field": "FirstName", "frappe_field": "first_name"},
            {"sf_field": "LastName", "frappe_field": "last_name"},
            {"sf_field": "Email", "frappe_field": "email_id"},
            {"sf_field": "Phone", "frappe_field": "phone"},
            {"sf_field": "MobilePhone", "frappe_field": "mobile_no"},
            {"sf_field": "Title", "frappe_field": "designation"},
            {
                "sf_field": "AccountId",
                "frappe_field": "company_name",
                "transform": "account_lookup",
            },
        ],
    },
    {
        "salesforce_object": "Lead",
        "frappe_doctype": "CRM Lead",
        "rows": [
            {"sf_field": "FirstName", "frappe_field": "first_name"},
            {"sf_field": "LastName", "frappe_field": "last_name"},
            {"sf_field": "Company", "frappe_field": "organization"},
            {"sf_field": "Email", "frappe_field": "email"},
            {"sf_field": "Phone", "frappe_field": "phone"},
            {"sf_field": "MobilePhone", "frappe_field": "mobile_no"},
            {"sf_field": "Title", "frappe_field": "job_title"},
            {"sf_field": "LeadSource", "frappe_field": "source"},
            {"sf_field": "Status", "frappe_field": "status"},
            {
                "sf_field": "OwnerId",
                "frappe_field": "lead_owner",
                "transform": "user_lookup",
            },
        ],
    },
    {
        "salesforce_object": "Opportunity",
        "frappe_doctype": "CRM Deal",
        "rows": [
            {"sf_field": "Name", "frappe_field": "deal_name"},
            {
                "sf_field": "AccountId",
                "frappe_field": "organization",
                "transform": "account_lookup",
            },
            {"sf_field": "Amount", "frappe_field": "annual_revenue"},
            {
                "sf_field": "CloseDate",
                "frappe_field": "close_date",
                "transform": "date",
            },
            {
                "sf_field": "StageName",
                "frappe_field": "status",
                "transform": "deal_stage",
            },
            {"sf_field": "Probability", "frappe_field": "probability"},
            {
                "sf_field": "OwnerId",
                "frappe_field": "deal_owner",
                "transform": "user_lookup",
            },
        ],
    },
    {
        "salesforce_object": "Task",
        "frappe_doctype": "CRM Task",
        "rows": [
            {"sf_field": "Subject", "frappe_field": "title"},
            {
                "sf_field": "Description",
                "frappe_field": "description",
                "transform": "html_strip",
            },
            {
                "sf_field": "ActivityDate",
                "frappe_field": "due_date",
                "transform": "date",
            },
            {"sf_field": "Status", "frappe_field": "status"},
            {"sf_field": "Priority", "frappe_field": "priority"},
            {
                "sf_field": "OwnerId",
                "frappe_field": "assigned_to",
                "transform": "user_lookup",
            },
        ],
    },
    {
        "salesforce_object": "Event",
        "frappe_doctype": "CRM Task",
        "rows": [
            {"sf_field": "Subject", "frappe_field": "title"},
            {
                "sf_field": "Description",
                "frappe_field": "description",
                "transform": "html_strip",
            },
            {
                "sf_field": "ActivityDate",
                "frappe_field": "due_date",
                "transform": "date",
            },
            {
                "sf_field": "StartDateTime",
                "frappe_field": "custom_sf_start_datetime",
                "transform": "datetime",
            },
            {
                "sf_field": "EndDateTime",
                "frappe_field": "custom_sf_end_datetime",
                "transform": "datetime",
            },
            {
                "sf_field": "OwnerId",
                "frappe_field": "assigned_to",
                "transform": "user_lookup",
            },
        ],
    },
]


def seed_default_field_mappings() -> None:
    for mapping in DEFAULT_MAPPINGS:
        if frappe.db.exists(
            "Salesforce Field Mapping",
            {"salesforce_object": mapping["salesforce_object"]},
        ):
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Salesforce Field Mapping",
                "salesforce_object": mapping["salesforce_object"],
                "frappe_doctype": mapping["frappe_doctype"],
                "enabled": 1,
                "field_mappings": [
                    {
                        "sf_field": row["sf_field"],
                        "frappe_field": row["frappe_field"],
                        "transform": row.get("transform") or "none",
                    }
                    for row in mapping["rows"]
                ],
            }
        )
        doc.insert(ignore_permissions=True)
