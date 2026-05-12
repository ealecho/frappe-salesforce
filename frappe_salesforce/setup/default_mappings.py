"""Seed default Salesforce → Frappe field mappings.

These are idempotent: mappings are only created if one does not already exist
for the Salesforce object. To backfill rows onto an existing install use the
patch ``frappe_salesforce.patches.v0_0_2.extend_default_mappings``.
"""

from __future__ import annotations

import frappe

DEFAULT_MAPPINGS: list[dict] = [
    {
        "salesforce_object": "Account",
        "frappe_doctype": "CRM Organization",
        "rows": [
            # Identity / classification
            {"sf_field": "Name", "frappe_field": "organization_name"},
            {"sf_field": "Website", "frappe_field": "website"},
            {"sf_field": "Industry", "frappe_field": "industry"},
            {"sf_field": "AnnualRevenue", "frappe_field": "annual_revenue"},
            {"sf_field": "NumberOfEmployees", "frappe_field": "no_of_employees"},
            # Address fields are also persisted via address_prefixes →
            # Frappe Address docs in AccountSyncer.after_upsert. These flat
            # custom_sf_* fields are extra denormalised columns on the parent.
            {"sf_field": "BillingCity", "frappe_field": "city"},
            {"sf_field": "BillingState", "frappe_field": "state"},
            {"sf_field": "BillingCountry", "frappe_field": "country"},
            # Standard SF fields → custom_sf_* on CRM Organization
            {"sf_field": "Phone", "frappe_field": "custom_sf_phone"},
            {"sf_field": "Fax", "frappe_field": "custom_sf_fax"},
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {"sf_field": "AccountNumber", "frappe_field": "custom_sf_account_number"},
            {"sf_field": "Rating", "frappe_field": "custom_sf_rating"},
            {"sf_field": "Site", "frappe_field": "custom_sf_site"},
            {"sf_field": "AccountSource", "frappe_field": "custom_sf_account_source"},
            {"sf_field": "Ownership", "frappe_field": "custom_sf_ownership"},
            {"sf_field": "TickerSymbol", "frappe_field": "custom_sf_ticker"},
            {"sf_field": "Sic", "frappe_field": "custom_sf_sic"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
            {
                "sf_field": "ParentId",
                "frappe_field": "custom_sf_parent_account",
                "transform": "account_lookup",
            },
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
            # Standard SF → custom_sf_* on Contact
            {"sf_field": "HomePhone", "frappe_field": "custom_sf_home_phone"},
            {"sf_field": "OtherPhone", "frappe_field": "custom_sf_other_phone"},
            {"sf_field": "AssistantPhone", "frappe_field": "custom_sf_assistant_phone"},
            {"sf_field": "Fax", "frappe_field": "custom_sf_fax"},
            {"sf_field": "Department", "frappe_field": "department"},
            {"sf_field": "AssistantName", "frappe_field": "custom_sf_assistant_name"},
            {
                "sf_field": "ReportsToId",
                "frappe_field": "custom_sf_reports_to",
                "transform": "contact_lookup",
            },
            {"sf_field": "LeadSource", "frappe_field": "custom_sf_lead_source"},
            {
                "sf_field": "Birthdate",
                "frappe_field": "custom_sf_birthdate",
                "transform": "date",
            },
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {
                "sf_field": "HasOptedOutOfEmail",
                "frappe_field": "custom_sf_opted_out_email",
                "transform": "boolean",
            },
            {
                "sf_field": "DoNotCall",
                "frappe_field": "custom_sf_do_not_call",
                "transform": "boolean",
            },
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
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
            {
                "sf_field": "Status",
                "frappe_field": "status",
                "transform": "lead_status",
            },
            {
                "sf_field": "OwnerId",
                "frappe_field": "lead_owner",
                "transform": "user_lookup",
            },
            # Standard SF additions
            {"sf_field": "Fax", "frappe_field": "custom_sf_fax"},
            {"sf_field": "Website", "frappe_field": "website"},
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {"sf_field": "Industry", "frappe_field": "industry"},
            {"sf_field": "Rating", "frappe_field": "custom_sf_rating"},
            {"sf_field": "AnnualRevenue", "frappe_field": "annual_revenue"},
            {"sf_field": "NumberOfEmployees", "frappe_field": "no_of_employees"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
            # IsConverted is handled in LeadSyncer.enrich_values (it forces
            # status=Converted and populates custom_sf_converted_*). We still
            # request it via a mapping row so it's selected in SOQL.
            {
                "sf_field": "IsConverted",
                "frappe_field": "custom_sf_is_converted",
                "transform": "boolean",
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
            {
                "sf_field": "StageName",
                "frappe_field": "lost_reason",
                "transform": "deal_lost_reason",
            },
            {"sf_field": "Probability", "frappe_field": "probability"},
            {
                "sf_field": "OwnerId",
                "frappe_field": "deal_owner",
                "transform": "user_lookup",
            },
            # Standard SF additions
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {"sf_field": "NextStep", "frappe_field": "custom_sf_next_step"},
            {"sf_field": "LeadSource", "frappe_field": "custom_sf_lead_source"},
            {
                "sf_field": "ContactId",
                "frappe_field": "custom_sf_primary_contact",
                "transform": "contact_lookup",
            },
            {
                "sf_field": "CampaignId",
                "frappe_field": "custom_sf_campaign",
                "transform": "campaign_lookup",
            },
            {"sf_field": "ExpectedRevenue", "frappe_field": "custom_sf_expected_revenue"},
            {
                "sf_field": "IsClosed",
                "frappe_field": "custom_sf_is_closed",
                "transform": "boolean",
            },
            {
                "sf_field": "IsWon",
                "frappe_field": "custom_sf_is_won",
                "transform": "boolean",
            },
            {"sf_field": "ForecastCategory", "frappe_field": "custom_sf_forecast_category"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
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
            {
                "sf_field": "Status",
                "frappe_field": "status",
                "transform": "task_status",
            },
            {
                "sf_field": "Priority",
                "frappe_field": "priority",
                "transform": "task_priority",
            },
            {
                "sf_field": "OwnerId",
                "frappe_field": "assigned_to",
                "transform": "user_lookup",
            },
            # Standard SF additions (WhoId/WhatId already resolved in TaskSyncer.enrich_values)
            {
                "sf_field": "AccountId",
                "frappe_field": "custom_sf_account",
                "transform": "account_lookup",
            },
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {
                "sf_field": "IsClosed",
                "frappe_field": "custom_sf_is_closed",
                "transform": "boolean",
            },
            {
                "sf_field": "IsHighPriority",
                "frappe_field": "custom_sf_is_high_priority",
                "transform": "boolean",
            },
            {"sf_field": "CallDurationInSeconds", "frappe_field": "custom_sf_call_duration"},
            {"sf_field": "CallType", "frappe_field": "custom_sf_call_type"},
            {"sf_field": "CallDisposition", "frappe_field": "custom_sf_call_disposition"},
            {
                "sf_field": "CompletedDateTime",
                "frappe_field": "custom_sf_completed_datetime",
                "transform": "datetime",
            },
            {
                "sf_field": "ReminderDateTime",
                "frappe_field": "custom_sf_reminder_datetime",
                "transform": "datetime",
            },
            {"sf_field": "TaskSubtype", "frappe_field": "custom_sf_task_subtype"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
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
            # Standard SF additions
            {
                "sf_field": "AccountId",
                "frappe_field": "custom_sf_account",
                "transform": "account_lookup",
            },
            {"sf_field": "Location", "frappe_field": "custom_sf_location"},
            {
                "sf_field": "IsAllDayEvent",
                "frappe_field": "custom_sf_is_all_day",
                "transform": "boolean",
            },
            {"sf_field": "DurationInMinutes", "frappe_field": "custom_sf_duration_minutes"},
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {
                "sf_field": "IsPrivate",
                "frappe_field": "custom_sf_is_private",
                "transform": "boolean",
            },
            {"sf_field": "ShowAs", "frappe_field": "custom_sf_show_as"},
            {"sf_field": "EventSubtype", "frappe_field": "custom_sf_event_subtype"},
            {
                "sf_field": "ReminderDateTime",
                "frappe_field": "custom_sf_reminder_datetime",
                "transform": "datetime",
            },
        ],
    },
    {
        "salesforce_object": "Campaign",
        "frappe_doctype": "SF Campaign",
        "rows": [
            {"sf_field": "Name", "frappe_field": "campaign_name"},
            {
                "sf_field": "ParentId",
                "frappe_field": "parent_campaign",
                "transform": "campaign_lookup",
            },
            {"sf_field": "Type", "frappe_field": "campaign_type"},
            {"sf_field": "Status", "frappe_field": "status"},
            {"sf_field": "StartDate", "frappe_field": "start_date", "transform": "date"},
            {"sf_field": "EndDate", "frappe_field": "end_date", "transform": "date"},
            {"sf_field": "ExpectedRevenue", "frappe_field": "expected_revenue"},
            {"sf_field": "BudgetedCost", "frappe_field": "budgeted_cost"},
            {"sf_field": "ActualCost", "frappe_field": "actual_cost"},
            {"sf_field": "IsActive", "frappe_field": "is_active", "transform": "boolean"},
            {
                "sf_field": "Description",
                "frappe_field": "description",
                "transform": "html_strip",
            },
            {"sf_field": "NumberOfLeads", "frappe_field": "number_of_leads"},
            {"sf_field": "NumberOfContacts", "frappe_field": "number_of_contacts"},
            {"sf_field": "NumberOfOpportunities", "frappe_field": "number_of_opportunities"},
            {"sf_field": "NumberOfWonOpportunities", "frappe_field": "number_of_won_opportunities"},
            {"sf_field": "AmountAllOpportunities", "frappe_field": "amount_all_opportunities"},
            {"sf_field": "AmountWonOpportunities", "frappe_field": "amount_won_opportunities"},
        ],
    },
    {
        "salesforce_object": "npe03__Recurring_Donation__c",
        "frappe_doctype": "SF Recurring Donation",
        "rows": [
            {"sf_field": "Name", "frappe_field": "recurring_donation_name"},
            {"sf_field": "npe03__Amount__c", "frappe_field": "amount"},
            {"sf_field": "npe03__Installment_Amount__c", "frappe_field": "installment_amount"},
            {"sf_field": "npe03__Installment_Period__c", "frappe_field": "installment_period"},
            {"sf_field": "npe03__Installments__c", "frappe_field": "installments"},
            {"sf_field": "npe03__Schedule_Type__c", "frappe_field": "schedule_type"},
            {
                "sf_field": "npe03__Date_Established__c",
                "frappe_field": "date_established",
                "transform": "date",
            },
            {
                "sf_field": "npe03__Last_Payment_Date__c",
                "frappe_field": "last_payment_date",
                "transform": "date",
            },
            {
                "sf_field": "npe03__Next_Payment_Date__c",
                "frappe_field": "next_payment_date",
                "transform": "date",
            },
            {
                "sf_field": "npe03__Open_Ended_Status__c",
                "frappe_field": "open_ended_status",
            },
            {"sf_field": "npe03__Paid_Amount__c", "frappe_field": "paid_amount"},
            {
                "sf_field": "npe03__Total_Paid_Installments__c",
                "frappe_field": "total_paid_installments",
            },
            {"sf_field": "npe03__Total__c", "frappe_field": "total"},
            {
                "sf_field": "npe03__Contact__c",
                "frappe_field": "contact",
                "transform": "contact_lookup",
            },
            {
                "sf_field": "npe03__Organization__c",
                "frappe_field": "organization",
                "transform": "account_lookup",
            },
            {
                "sf_field": "npe03__Recurring_Donation_Campaign__c",
                "frappe_field": "campaign",
                "transform": "campaign_lookup",
            },
            {"sf_field": "Donation_type__c", "frappe_field": "donation_type"},
            {"sf_field": "Source__c", "frappe_field": "source"},
            {"sf_field": "Type__c", "frappe_field": "donation_subtype"},
            {"sf_field": "Payment_Method__c", "frappe_field": "payment_method"},
            {"sf_field": "Fund__c", "frappe_field": "fund"},
            {"sf_field": "Income_Stream__c", "frappe_field": "income_stream"},
            {
                "sf_field": "Gift_Aid_eligible__c",
                "frappe_field": "gift_aid_eligible",
                "transform": "boolean",
            },
            {"sf_field": "Gift_Aid_Declaration__c", "frappe_field": "gift_aid_declaration"},
            {"sf_field": "ExternalID__c", "frappe_field": "external_id"},
        ],
    },
    {
        "salesforce_object": "npe4__Relationship__c",
        "frappe_doctype": "SF Contact Relationship",
        "rows": [
            {
                "sf_field": "npe4__Contact__c",
                "frappe_field": "contact",
                "transform": "contact_lookup",
            },
            {
                "sf_field": "npe4__RelatedContact__c",
                "frappe_field": "related_contact",
                "transform": "contact_lookup",
            },
            {"sf_field": "npe4__Type__c", "frappe_field": "relationship_type"},
            {"sf_field": "npe4__Status__c", "frappe_field": "status"},
            {
                "sf_field": "npe4__Description__c",
                "frappe_field": "description",
                "transform": "html_strip",
            },
            {
                "sf_field": "npe4__SYSTEM_SystemCreated__c",
                "frappe_field": "system_created",
                "transform": "boolean",
            },
        ],
    },
    {
        "salesforce_object": "npe5__Affiliation__c",
        "frappe_doctype": "SF Contact Affiliation",
        "rows": [
            {
                "sf_field": "npe5__Contact__c",
                "frappe_field": "contact",
                "transform": "contact_lookup",
            },
            {
                "sf_field": "npe5__Organization__c",
                "frappe_field": "organization",
                "transform": "account_lookup",
            },
            {"sf_field": "npe5__Role__c", "frappe_field": "role"},
            {"sf_field": "Role__c", "frappe_field": "secondary_role"},
            {"sf_field": "npe5__Status__c", "frappe_field": "status"},
            {
                "sf_field": "npe5__StartDate__c",
                "frappe_field": "start_date",
                "transform": "date",
            },
            {
                "sf_field": "npe5__EndDate__c",
                "frappe_field": "end_date",
                "transform": "date",
            },
            {
                "sf_field": "npe5__Primary__c",
                "frappe_field": "is_primary",
                "transform": "boolean",
            },
            {
                "sf_field": "npe5__Description__c",
                "frappe_field": "description",
                "transform": "html_strip",
            },
        ],
    },
    {
        "salesforce_object": "npe01__OppPayment__c",
        "frappe_doctype": "SF Opportunity Payment",
        "rows": [
            {
                "sf_field": "npe01__Opportunity__c",
                "frappe_field": "opportunity",
                "transform": "polymorphic_lookup",
            },
            {"sf_field": "Name", "frappe_field": "payment_name"},
            {"sf_field": "npe01__Payment_Amount__c", "frappe_field": "payment_amount"},
            {
                "sf_field": "npe01__Payment_Date__c",
                "frappe_field": "payment_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__Scheduled_Date__c",
                "frappe_field": "scheduled_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__Paid__c",
                "frappe_field": "is_paid",
                "transform": "boolean",
            },
            {
                "sf_field": "npe01__Written_Off__c",
                "frappe_field": "is_written_off",
                "transform": "boolean",
            },
            {"sf_field": "npe01__Payment_Method__c", "frappe_field": "payment_method"},
            {
                "sf_field": "npe01__Check_Reference_Number__c",
                "frappe_field": "check_reference",
            },
            {
                "sf_field": "Expected_Payment_Amount__c",
                "frappe_field": "expected_amount",
            },
            {
                "sf_field": "Received__c",
                "frappe_field": "is_received",
                "transform": "boolean",
            },
            {
                "sf_field": "Date_Received__c",
                "frappe_field": "date_received",
                "transform": "date",
            },
            {"sf_field": "Amount_Received__c", "frappe_field": "amount_received"},
            {"sf_field": "Variance_Amount__c", "frappe_field": "variance_amount"},
            {"sf_field": "Variance_Reason__c", "frappe_field": "variance_reason"},
            {
                "sf_field": "npsp__Payment_Acknowledged_Date__c",
                "frappe_field": "acknowledged_date",
                "transform": "date",
            },
            {
                "sf_field": "npsp__Payment_Acknowledgment_Status__c",
                "frappe_field": "acknowledgment_status",
            },
            {"sf_field": "Probability__c", "frappe_field": "probability"},
        ],
    },
    {
        "salesforce_object": "EventRelation",
        "frappe_doctype": "SF Event Invitee",
        "rows": [
            {
                "sf_field": "EventId",
                "frappe_field": "event",
                "transform": "polymorphic_lookup",
            },
            {
                "sf_field": "RelationId",
                "frappe_field": "invitee",
                "transform": "polymorphic_lookup",
            },
            {
                "sf_field": "RelationId",
                "frappe_field": "invitee_doctype",
                "transform": "polymorphic_doctype",
            },
            {"sf_field": "Status", "frappe_field": "status"},
            {"sf_field": "Response", "frappe_field": "response"},
            {
                "sf_field": "RespondedDate",
                "frappe_field": "responded_date",
                "transform": "datetime",
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
