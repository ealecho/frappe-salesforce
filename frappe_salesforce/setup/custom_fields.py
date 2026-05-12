"""Custom field definitions for Salesforce → Frappe mapping targets.

Single source of truth used by:
  - ``setup/install.py`` (``after_install`` hook for fresh sites)
  - ``patches/v0_0_2/add_custom_fields`` (backfill for existing sites)

Idempotent via ``create_custom_fields`` (which upserts by ``dt + fieldname``).
"""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# ---------------------------------------------------------------------------
# Reusable field definitions
# ---------------------------------------------------------------------------
SF_ID_FIELD = {
    "fieldname": "custom_salesforce_id",
    "label": "Salesforce ID",
    "fieldtype": "Data",
    "unique": 1,
    "read_only": 1,
    "no_copy": 1,
    "in_standard_filter": 1,
    "search_index": 1,
}

ACTIVITY_TYPE_FIELD = {
    "fieldname": "custom_sf_activity_type",
    "label": "Salesforce Activity Type",
    "fieldtype": "Select",
    "options": "\nTask\nEvent",
    "read_only": 1,
    "no_copy": 1,
}

EVENT_START_FIELD = {
    "fieldname": "custom_sf_start_datetime",
    "label": "SF Event Start",
    "fieldtype": "Datetime",
    "read_only": 1,
    "no_copy": 1,
}

EVENT_END_FIELD = {
    "fieldname": "custom_sf_end_datetime",
    "label": "SF Event End",
    "fieldtype": "Datetime",
    "read_only": 1,
    "no_copy": 1,
}


def _ro(fieldname: str, label: str, fieldtype: str = "Data", **kw) -> dict:
    """Compact builder for read-only, no-copy SF mirror fields."""
    return {
        "fieldname": fieldname,
        "label": label,
        "fieldtype": fieldtype,
        "read_only": 1,
        "no_copy": 1,
        **kw,
    }


# ---------------------------------------------------------------------------
# DocTypes carrying ``custom_salesforce_id``. Used in two places:
#   * here, to attach the field
#   * by setup/install.py for compatibility (kept in sync via SF_ID_DOCTYPES)
# ---------------------------------------------------------------------------
SF_ID_DOCTYPES = [
    "CRM Organization",
    "Contact",
    "CRM Lead",
    "CRM Deal",
    "CRM Task",
]


# ---------------------------------------------------------------------------
# CRM Organization
# ---------------------------------------------------------------------------
ORG_FIELDS: list[dict] = [
    SF_ID_FIELD,
    # Wave 1: standard SF fields
    _ro("custom_sf_phone", "SF Phone"),
    _ro("custom_sf_fax", "SF Fax"),
    _ro("custom_sf_description", "SF Description", "Text Editor"),
    _ro("custom_sf_type", "SF Account Type"),
    _ro("custom_sf_account_number", "SF Account Number"),
    _ro("custom_sf_rating", "SF Rating"),
    _ro("custom_sf_site", "SF Site"),
    _ro("custom_sf_account_source", "SF Account Source"),
    _ro("custom_sf_ownership", "SF Ownership"),
    _ro("custom_sf_ticker", "SF Ticker Symbol"),
    _ro("custom_sf_sic", "SF SIC"),
    _ro("custom_sf_record_type", "SF Record Type Id"),
    _ro("custom_sf_parent_account", "SF Parent Organization", "Link", options="CRM Organization"),
    # Wave 2: NPSP donation rollups + org metadata
    _ro("custom_sf_lifetime_donation_amount", "SF Lifetime Donation Amount", "Currency"),
    _ro("custom_sf_lifetime_donation_number", "SF Lifetime Donation Count", "Int"),
    _ro("custom_sf_first_donation_date", "SF First Donation Date", "Date"),
    _ro("custom_sf_last_donation_date", "SF Last Donation Date", "Date"),
    _ro("custom_sf_last_opp_amount", "SF Last Opp Amount", "Currency"),
    _ro("custom_sf_largest_amount", "SF Largest Donation", "Currency"),
    _ro("custom_sf_smallest_amount", "SF Smallest Donation", "Currency"),
    _ro("custom_sf_average_amount", "SF Average Donation", "Currency"),
    _ro("custom_sf_total_opp_amount", "SF Total Opp Amount", "Currency"),
    _ro("custom_sf_number_closed_opps", "SF # Closed Opps", "Int"),
    _ro("custom_sf_opp_amount_this_year", "SF Opp Amount This Year", "Currency"),
    _ro("custom_sf_opp_amount_last_year", "SF Opp Amount Last Year", "Currency"),
    _ro("custom_sf_opps_closed_this_year", "SF Opps Closed This Year", "Int"),
    _ro("custom_sf_opps_closed_last_year", "SF Opps Closed Last Year", "Int"),
    _ro("custom_sf_best_gift_year", "SF Best Gift Year"),
    _ro("custom_sf_best_gift_year_total", "SF Best Gift Year Total", "Currency"),
    _ro("custom_sf_membership_join_date", "SF Membership Join Date", "Date"),
    _ro("custom_sf_membership_end_date", "SF Membership End Date", "Date"),
    _ro("custom_sf_last_membership_level", "SF Last Membership Level"),
    _ro("custom_sf_org_type", "SF Org Type"),
    _ro("custom_sf_org_sub_type", "SF Org Sub Type"),
    _ro("custom_sf_country_of_origin", "SF Country of Origin"),
    _ro("custom_sf_country_of_interest", "SF Country of Interest"),
    _ro("custom_sf_thematic_areas", "SF Thematic Areas", "Small Text"),
    _ro("custom_sf_capacity_to_give", "SF Capacity to Give"),
    _ro("custom_sf_interests", "SF Interests", "Small Text"),
    _ro("custom_sf_comms_opt_in", "SF Comms Opt-In", "Check"),
    _ro("custom_sf_comms_options", "SF Comms Options", "Small Text"),
    _ro("custom_sf_active_gift_aid_declaration", "SF Active Gift Aid Declaration", "Check"),
    _ro("custom_sf_contact_eligibility", "SF Contact Eligibility"),
    _ro("custom_sf_director", "SF Director"),
    _ro("custom_sf_general_enquiries_email", "SF General Enquiries Email"),
    _ro("custom_sf_address_freeform", "SF Address (Freeform)", "Small Text"),
    _ro("custom_sf_funding_focus", "SF Funding Focus", "Small Text"),
    _ro("custom_sf_grantmaker", "SF Grantmaker", "Check"),
    _ro("custom_sf_one2one_contact", "SF One2One Contact", "Link", options="Contact"),
    _ro("custom_sf_system_account_type", "SF System Account Type"),
    _ro("custom_sf_external_id", "SF External ID"),
]


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------
CONTACT_FIELDS: list[dict] = [
    SF_ID_FIELD,
    # Wave 1
    _ro("custom_sf_home_phone", "SF Home Phone"),
    _ro("custom_sf_other_phone", "SF Other Phone"),
    _ro("custom_sf_assistant_phone", "SF Assistant Phone"),
    _ro("custom_sf_fax", "SF Fax"),
    _ro("custom_sf_assistant_name", "SF Assistant Name"),
    _ro("custom_sf_reports_to", "SF Reports To", "Link", options="Contact"),
    _ro("custom_sf_lead_source", "SF Lead Source"),
    _ro("custom_sf_birthdate", "SF Birthdate", "Date"),
    _ro("custom_sf_description", "SF Description", "Text Editor"),
    _ro("custom_sf_opted_out_email", "SF Opted Out of Email", "Check"),
    _ro("custom_sf_do_not_call", "SF Do Not Call", "Check"),
    _ro("custom_sf_record_type", "SF Record Type Id"),
    # Wave 2: NPSP soft credits + opt-ins
    _ro("custom_sf_home_email", "SF Home Email"),
    _ro("custom_sf_work_email", "SF Work Email"),
    _ro("custom_sf_alternate_email", "SF Alternate Email"),
    _ro("custom_sf_preferred_email", "SF Preferred Email"),
    _ro("custom_sf_assistant_email", "SF Assistant Email"),
    _ro("custom_sf_preferred_phone", "SF Preferred Phone"),
    _ro("custom_sf_lifetime_giving_amount", "SF Lifetime Giving Amount", "Currency"),
    _ro("custom_sf_last_donation_date", "SF Last Donation Date", "Date"),
    _ro("custom_sf_total_opp_amount", "SF Total Opp Amount", "Currency"),
    _ro("custom_sf_largest_amount", "SF Largest Donation", "Currency"),
    _ro("custom_sf_last_opp_amount", "SF Last Opp Amount", "Currency"),
    _ro("custom_sf_number_closed_opps", "SF # Closed Opps", "Int"),
    _ro("custom_sf_opp_amount_this_year", "SF Opp Amount This Year", "Currency"),
    _ro("custom_sf_opp_amount_last_year", "SF Opp Amount Last Year", "Currency"),
    _ro("custom_sf_soft_credit_total", "SF Soft Credit Total", "Currency"),
    _ro("custom_sf_soft_credit_this_year", "SF Soft Credit This Year", "Currency"),
    _ro("custom_sf_soft_credit_last_year", "SF Soft Credit Last Year", "Currency"),
    _ro("custom_sf_soft_credit_two_years_ago", "SF Soft Credit Two Years Ago", "Currency"),
    _ro("custom_sf_email_opt_in", "SF Email Opt-In", "Check"),
    _ro("custom_sf_phone_opt_in", "SF Phone Opt-In", "Check"),
    _ro("custom_sf_post_opt_in", "SF Post Opt-In", "Check"),
    _ro("custom_sf_sms_opt_in", "SF SMS Opt-In", "Check"),
    _ro("custom_sf_comms_opt_in", "SF Comms Opt-In", "Check"),
    _ro("custom_sf_comms_options", "SF Comms Options", "Small Text"),
    _ro("custom_sf_active_gift_aid_declaration", "SF Active Gift Aid Declaration", "Check"),
    _ro("custom_sf_invite_to_events", "SF Invite to Events", "Check"),
    _ro("custom_sf_add_to_partner_mailing_list", "SF Add to Partner Mailing List", "Check"),
    _ro("custom_sf_mc_subscriber", "SF Mailchimp Subscriber", "Check"),
    _ro("custom_sf_household_id", "SF Household ID"),
    _ro("custom_sf_household_phone", "SF Household Phone"),
    _ro("custom_sf_primary_affiliation", "SF Primary Affiliation", "Link", options="CRM Organization"),
    _ro("custom_sf_employer", "SF Employer"),
    _ro("custom_sf_skype_id", "SF Skype ID"),
    _ro("custom_sf_notes", "SF Notes", "Small Text"),
    _ro("custom_sf_bio_type", "SF Bio Type"),
    _ro("custom_sf_maiden_name", "SF Maiden Name"),
    _ro("custom_sf_job_title", "SF Job Title (Custom)"),
    _ro("custom_sf_how_heard", "SF How Heard"),
    _ro("custom_sf_pipeline_stage", "SF Pipeline Stage"),
    _ro("custom_sf_interests", "SF Interests", "Small Text"),
    _ro("custom_sf_originates_from", "SF Originates From"),
    _ro("custom_sf_preferred_contact_method", "SF Preferred Contact Method"),
    _ro("custom_sf_deceased", "SF Deceased", "Check"),
    _ro("custom_sf_do_not_contact", "SF Do Not Contact", "Check"),
    _ro("custom_sf_external_id", "SF External ID"),
]


# ---------------------------------------------------------------------------
# CRM Lead
# ---------------------------------------------------------------------------
LEAD_FIELDS: list[dict] = [
    SF_ID_FIELD,
    # Wave 1 - standards
    _ro("custom_sf_fax", "SF Fax"),
    _ro("custom_sf_description", "SF Description", "Text Editor"),
    _ro("custom_sf_rating", "SF Rating"),
    _ro("custom_sf_record_type", "SF Record Type Id"),
    _ro("custom_sf_is_converted", "SF Is Converted", "Check"),
    # Lead conversion handling (Wave 1c)
    _ro("custom_sf_converted_account", "SF Converted Account Id"),
    _ro("custom_sf_converted_contact", "SF Converted Contact Id"),
    _ro("custom_sf_converted_opportunity", "SF Converted Opportunity Id"),
    _ro("custom_sf_converted_date", "SF Converted Date", "Date"),
    # Wave 2 - NPSP / custom
    _ro("custom_sf_donation_amount", "SF Donation Amount", "Currency"),
    _ro("custom_sf_donation_close_date", "SF Donation Close Date", "Date"),
    _ro("custom_sf_preferred_email", "SF Preferred Email"),
    _ro("custom_sf_preferred_phone", "SF Preferred Phone"),
    _ro("custom_sf_mc_subscriber", "SF Mailchimp Subscriber", "Check"),
]


# ---------------------------------------------------------------------------
# CRM Deal (largest set — Gift Aid + grants + financials)
# ---------------------------------------------------------------------------
DEAL_FIELDS: list[dict] = [
    SF_ID_FIELD,
    # Wave 1 - standards
    _ro("custom_sf_description", "SF Description", "Text Editor"),
    _ro("custom_sf_type", "SF Opportunity Type"),
    _ro("custom_sf_next_step", "SF Next Step", "Small Text"),
    _ro("custom_sf_lead_source", "SF Lead Source"),
    _ro("custom_sf_primary_contact", "SF Primary Contact", "Link", options="Contact"),
    _ro("custom_sf_campaign", "SF Campaign", "Link", options="SF Campaign"),
    _ro("custom_sf_expected_revenue", "SF Expected Revenue", "Currency"),
    _ro("custom_sf_is_closed", "SF Is Closed", "Check"),
    _ro("custom_sf_is_won", "SF Is Won", "Check"),
    _ro("custom_sf_forecast_category", "SF Forecast Category"),
    _ro("custom_sf_record_type", "SF Record Type Id"),
    # Wave 2 - NPSP payment block
    _ro("custom_sf_amount_outstanding", "SF Amount Outstanding", "Currency"),
    _ro("custom_sf_amount_written_off", "SF Amount Written Off", "Currency"),
    _ro("custom_sf_payments_made", "SF Payments Made", "Int"),
    _ro("custom_sf_number_of_payments", "SF Number of Payments", "Int"),
    _ro("custom_sf_do_not_auto_create_payment", "SF Do Not Auto-Create Payment", "Check"),
    # Gift Aid block
    _ro("custom_sf_gift_aid", "SF Gift Aid", "Check"),
    _ro("custom_sf_gift_aid_applicable", "SF Gift Aid Applicable", "Check"),
    _ro("custom_sf_gift_aid_claimed", "SF Gift Aid Claimed", "Check"),
    _ro("custom_sf_gift_aid_claimed_date", "SF Gift Aid Claimed Date", "Date"),
    _ro("custom_sf_gift_aid_declaration", "SF Gift Aid Declaration"),
    _ro("custom_sf_declaration_active", "SF Declaration Active in Date Range", "Check"),
    _ro("custom_sf_is_gift_type_ga_eligible", "SF Gift Type GA-Eligible", "Check"),
    _ro("custom_sf_is_payment_method_ga_eligible", "SF Payment Method GA-Eligible", "Check"),
    # Grant lifecycle
    _ro("custom_sf_grant_contract_date", "SF Grant Contract Date", "Date"),
    _ro("custom_sf_grant_contract_number", "SF Grant Contract Number"),
    _ro("custom_sf_grant_period_start", "SF Grant Period Start", "Date"),
    _ro("custom_sf_grant_period_end", "SF Grant Period End", "Date"),
    _ro("custom_sf_grant_program_areas", "SF Grant Program Areas", "Small Text"),
    _ro("custom_sf_grant_requirements_website", "SF Grant Requirements Website"),
    _ro("custom_sf_requested_amount", "SF Requested Amount", "Currency"),
    _ro("custom_sf_is_grant_renewal", "SF Is Grant Renewal", "Check"),
    _ro("custom_sf_previous_grant_opp", "SF Previous Grant Opportunity"),
    _ro("custom_sf_next_grant_deadline", "SF Next Grant Deadline", "Date"),
    _ro("custom_sf_application_date", "SF Application Date", "Date"),
    _ro("custom_sf_application_name", "SF Application Name"),
    _ro("custom_sf_submitted_to", "SF Submitted To"),
    _ro("custom_sf_submitted_by", "SF Submitted By"),
    _ro("custom_sf_reply_details", "SF Reply Details", "Small Text"),
    _ro("custom_sf_date_of_expected_decision", "SF Date of Expected Decision", "Date"),
    _ro("custom_sf_relates_to_application", "SF Relates to Application"),
    # Financials breakdown
    _ro("custom_sf_opex", "SF OpEx", "Currency"),
    _ro("custom_sf_total_opex", "SF Total OpEx", "Currency"),
    _ro("custom_sf_total_capex", "SF Total CapEx", "Currency"),
    _ro("custom_sf_expected_capex", "SF Expected CapEx", "Currency"),
    _ro("custom_sf_expected_opex", "SF Expected OpEx", "Currency"),
    _ro("custom_sf_confirmed_capex", "SF Confirmed CapEx", "Currency"),
    _ro("custom_sf_confirmed_opex", "SF Confirmed OpEx", "Currency"),
    _ro("custom_sf_amount_requested_grant", "SF Amount Requested (Grant)", "Currency"),
    _ro("custom_sf_amount_sent_to_field", "SF Amount Sent to Field", "Currency"),
    _ro("custom_sf_payment_amount", "SF Payment Amount", "Currency"),
    _ro("custom_sf_total_payments", "SF Total Payments", "Currency"),
    # Fund / project
    _ro("custom_sf_fund", "SF Fund"),
    _ro("custom_sf_fund_destination", "SF Fund Destination"),
    _ro("custom_sf_project_start", "SF Project Start", "Date"),
    _ro("custom_sf_project_end", "SF Project End", "Date"),
    _ro("custom_sf_income_stream", "SF Income Stream"),
    _ro("custom_sf_payment_method", "SF Payment Method"),
    _ro("custom_sf_operating_country", "SF Operating Country"),
    _ro("custom_sf_destination_country", "SF Destination of Funding Country"),
    _ro("custom_sf_restricted", "SF Restricted", "Check"),
    # Acknowledgment / stewardship
    _ro("custom_sf_acknowledgment_date", "SF Acknowledgment Date", "Date"),
    _ro("custom_sf_acknowledgment_status", "SF Acknowledgment Status"),
    _ro("custom_sf_thanked", "SF Thanked", "Check"),
    _ro("custom_sf_thanked_by", "SF Thanked By"),
    _ro("custom_sf_new_business_vs_stewardship", "SF New Business vs Stewardship"),
    # Membership
    _ro("custom_sf_member_level", "SF Member Level"),
    _ro("custom_sf_membership_start", "SF Membership Start", "Date"),
    _ro("custom_sf_membership_end", "SF Membership End", "Date"),
    _ro("custom_sf_membership_origin", "SF Membership Origin"),
    _ro("custom_sf_recurring_donation", "SF Recurring Donation Id"),
    # Honoree / dedication
    _ro("custom_sf_honoree_name", "SF Honoree Name"),
    _ro("custom_sf_dedication_ack_type", "SF Dedication Acknowledgement Type"),
    _ro("custom_sf_dedication_personal_note", "SF Dedication Personal Note", "Small Text"),
    # Other
    _ro("custom_sf_notes", "SF Notes", "Text Editor"),
    _ro("custom_sf_package", "SF Package"),
    _ro("custom_sf_originates_from", "SF Originates From"),
    _ro("custom_sf_file_location", "SF File Location"),
    _ro("custom_sf_cheque_date", "SF Cheque Date", "Date"),
    _ro("custom_sf_external_id", "SF External ID"),
]


# ---------------------------------------------------------------------------
# CRM Task (Wave 1 + activity-type discriminator + event datetimes)
# ---------------------------------------------------------------------------
TASK_FIELDS: list[dict] = [
    SF_ID_FIELD,
    ACTIVITY_TYPE_FIELD,
    EVENT_START_FIELD,
    EVENT_END_FIELD,
    # Wave 1
    _ro("custom_sf_account", "SF Account", "Link", options="CRM Organization"),
    _ro("custom_sf_type", "SF Type"),
    _ro("custom_sf_is_closed", "SF Is Closed", "Check"),
    _ro("custom_sf_is_high_priority", "SF Is High Priority", "Check"),
    _ro("custom_sf_call_duration", "SF Call Duration (s)", "Int"),
    _ro("custom_sf_call_type", "SF Call Type"),
    _ro("custom_sf_call_disposition", "SF Call Disposition"),
    _ro("custom_sf_completed_datetime", "SF Completed Datetime", "Datetime"),
    _ro("custom_sf_reminder_datetime", "SF Reminder Datetime", "Datetime"),
    _ro("custom_sf_task_subtype", "SF Task Subtype"),
    _ro("custom_sf_record_type", "SF Record Type Id"),
    _ro("custom_sf_location", "SF Location"),
    _ro("custom_sf_is_all_day", "SF Is All Day Event", "Check"),
    _ro("custom_sf_duration_minutes", "SF Duration (min)", "Int"),
    _ro("custom_sf_is_private", "SF Is Private", "Check"),
    _ro("custom_sf_show_as", "SF Show As"),
    _ro("custom_sf_event_subtype", "SF Event Subtype"),
]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def all_custom_fields() -> dict[str, list[dict]]:
    """Return the full custom-field map for ``create_custom_fields``."""
    return {
        "CRM Organization": ORG_FIELDS,
        "Contact": CONTACT_FIELDS,
        "CRM Lead": LEAD_FIELDS,
        "CRM Deal": DEAL_FIELDS,
        "CRM Task": TASK_FIELDS,
    }


def ensure_all_custom_fields() -> None:
    """Create or update every SF mirror custom field. Idempotent."""
    create_custom_fields(all_custom_fields(), ignore_validate=True)
