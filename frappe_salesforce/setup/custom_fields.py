"""Single source of truth for every Frappe Salesforce custom field.

Used by:

* ``setup.install._ensure_custom_fields`` on fresh install.
* ``patches.v0_1_0.add_custom_fields`` to roll forward existing sites.
* ``hooks.fixtures`` (filtered by ``custom_sf%`` + ``custom_salesforce_id``)
  so a packaged install reproduces them.

Conventions:

* Every field name starts with ``custom_sf_`` so provenance is obvious
  (Salesforce-derived) and so the fixtures filter is one glob.
* The exception is ``custom_salesforce_id`` — present on every target
  doctype, used as the upsert key, and predates this module.
* Every NPSP / SF-rollup field is ``read_only=1`` since it's computed in
  Salesforce and shouldn't be edited locally.
* Every field is ``no_copy=1`` (we don't want SF-derived values to clone
  when a user duplicates a CRM doc).

Adding a new field: append to the appropriate ``DOCTYPE_FIELDS`` list,
then either reinstall the app *or* write a migration patch under
``patches/`` that calls ``ensure_all_custom_fields()``.
"""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

#: Doctypes that get the universal ``custom_salesforce_id`` Data field.
SF_ID_DOCTYPES = [
    "CRM Organization",
    "Contact",
    "CRM Lead",
    "CRM Deal",
    "CRM Task",
]

# ----------------------------------------------------------------------
# Universal: custom_salesforce_id (the upsert key)
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# CRM Task universal additions (Task / Event coexistence + activity metadata)
# ----------------------------------------------------------------------
TASK_BASE_FIELDS = [
    SF_ID_FIELD,
    {
        "fieldname": "custom_sf_activity_type",
        "label": "Salesforce Activity Type",
        "fieldtype": "Select",
        "options": "\nTask\nEvent",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "custom_sf_start_datetime",
        "label": "SF Event Start",
        "fieldtype": "Datetime",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "custom_sf_end_datetime",
        "label": "SF Event End",
        "fieldtype": "Datetime",
        "read_only": 1,
        "no_copy": 1,
    },
]


# ----------------------------------------------------------------------
# CRM Organization (Account mirror)
# ----------------------------------------------------------------------
def _ro(spec: dict) -> dict:
    """Mark a field read-only + no_copy (NPSP rollups, computed fields)."""
    return {**spec, "read_only": 1, "no_copy": 1}


def _data(name: str, label: str, **kw) -> dict:
    return {"fieldname": name, "label": label, "fieldtype": "Data", "no_copy": 1, **kw}


def _check(name: str, label: str, **kw) -> dict:
    return {
        "fieldname": name,
        "label": label,
        "fieldtype": "Check",
        "default": "0",
        "no_copy": 1,
        **kw,
    }


def _date(name: str, label: str, **kw) -> dict:
    return {"fieldname": name, "label": label, "fieldtype": "Date", "no_copy": 1, **kw}


def _datetime(name: str, label: str, **kw) -> dict:
    return {
        "fieldname": name,
        "label": label,
        "fieldtype": "Datetime",
        "no_copy": 1,
        **kw,
    }


def _currency(name: str, label: str, **kw) -> dict:
    return {
        "fieldname": name,
        "label": label,
        "fieldtype": "Currency",
        "no_copy": 1,
        **kw,
    }


def _int(name: str, label: str, **kw) -> dict:
    return {"fieldname": name, "label": label, "fieldtype": "Int", "no_copy": 1, **kw}


def _long_text(name: str, label: str, **kw) -> dict:
    return {
        "fieldname": name,
        "label": label,
        "fieldtype": "Long Text",
        "no_copy": 1,
        **kw,
    }


def _small_text(name: str, label: str, **kw) -> dict:
    """Use for fields converted from Data — Frappe only allows
    Data <-> Small Text and Data <-> Text fieldtype changes on existing
    Custom Fields (see ALLOWED_FIELDTYPE_CHANGE in customize_form.py).
    """
    return {
        "fieldname": name,
        "label": label,
        "fieldtype": "Small Text",
        "no_copy": 1,
        **kw,
    }


CRM_ORGANIZATION_FIELDS: list[dict] = [
    SF_ID_FIELD,
    # ---- Standard SF Account fields ----
    _data("custom_sf_phone", "SF Phone"),
    _data("custom_sf_fax", "SF Fax"),
    _long_text("custom_sf_description", "SF Description"),
    _data("custom_sf_account_number", "SF Account Number"),
    _data("custom_sf_type", "SF Account Type"),
    _data("custom_sf_rating", "SF Rating"),
    _data("custom_sf_site", "SF Site"),
    _data("custom_sf_account_source", "SF Account Source"),
    _data("custom_sf_ownership", "SF Ownership"),
    _data("custom_sf_ticker", "SF Ticker Symbol"),
    _data("custom_sf_sic", "SF SIC"),
    _data("custom_sf_sic_desc", "SF SIC Description"),
    _data("custom_sf_record_type", "SF Record Type ID"),
    _data("custom_sf_jigsaw", "SF Jigsaw"),
    _data("custom_sf_jigsaw_company_id", "SF Jigsaw Company ID"),
    _data("custom_sf_external_id", "SF External ID"),
    # ---- npe01__ rollups (read-only) ----
    _ro(_data("custom_sf_one2one_contact", "SF One2One Contact")),
    _ro(_check("custom_sf_system_is_individual", "SF System Is Individual")),
    _ro(_date("custom_sf_first_donation_date", "SF First Donation Date")),
    _ro(_date("custom_sf_last_donation_date", "SF Last Donation Date")),
    _ro(_currency("custom_sf_lifetime_donation_amount", "SF Lifetime Donation Amount")),
    _ro(_int("custom_sf_lifetime_donation_number", "SF Lifetime Donation Number")),
    _ro(_data("custom_sf_system_account_type", "SF System Account Type")),
    # ---- npo02__ rollups (read-only) ----
    _ro(_currency("custom_sf_average_amount", "SF Average Donation")),
    _ro(_date("custom_sf_first_close_date", "SF First Close Date")),
    _ro(_currency("custom_sf_largest_amount", "SF Largest Donation")),
    _ro(_date("custom_sf_last_close_date", "SF Last Close Date")),
    _ro(_currency("custom_sf_last_membership_amount", "SF Last Membership Amount")),
    _ro(_date("custom_sf_last_membership_date", "SF Last Membership Date")),
    _ro(_data("custom_sf_last_membership_level", "SF Last Membership Level")),
    _ro(_data("custom_sf_last_membership_origin", "SF Last Membership Origin")),
    _ro(_currency("custom_sf_last_opp_amount", "SF Last Opp Amount")),
    _ro(_date("custom_sf_membership_end_date", "SF Membership End Date")),
    _ro(_date("custom_sf_membership_join_date", "SF Membership Join Date")),
    _ro(_int("custom_sf_number_of_closed_opps", "SF # Closed Opps")),
    _ro(_int("custom_sf_number_of_membership_opps", "SF # Membership Opps")),
    _ro(_currency("custom_sf_opp_amount_2_years_ago", "SF Opp Amount 2yrs Ago")),
    _ro(_currency("custom_sf_opp_amount_last_n_days", "SF Opp Amount Last N Days")),
    _ro(_currency("custom_sf_opp_amount_last_year", "SF Opp Amount Last Year")),
    _ro(_currency("custom_sf_opp_amount_this_year", "SF Opp Amount This Year")),
    _ro(_int("custom_sf_opps_closed_2_years_ago", "SF Opps Closed 2yrs Ago")),
    _ro(_int("custom_sf_opps_closed_last_n_days", "SF Opps Closed Last N Days")),
    _ro(_int("custom_sf_opps_closed_last_year", "SF Opps Closed Last Year")),
    _ro(_int("custom_sf_opps_closed_this_year", "SF Opps Closed This Year")),
    _ro(_currency("custom_sf_smallest_amount", "SF Smallest Donation")),
    _ro(_currency("custom_sf_total_membership_opp_amount", "SF Total Membership Opp Amount")),
    _ro(_currency("custom_sf_total_opp_amount", "SF Total Opp Amount")),
    _ro(_currency("custom_sf_best_gift_year_total", "SF Best Gift Year Total")),
    _ro(_data("custom_sf_best_gift_year", "SF Best Gift Year")),
    _ro(_data("custom_sf_formal_greeting", "SF Formal Greeting")),
    _ro(_data("custom_sf_household_phone", "SF Household Phone")),
    _ro(_data("custom_sf_informal_greeting", "SF Informal Greeting")),
    _ro(_data("custom_sf_system_custom_naming", "SF System Custom Naming")),
    # ---- npsp__ ----
    _data("custom_sf_npsp_batch", "SF NPSP Batch"),
    _data("custom_sf_funding_focus", "SF Funding Focus"),
    _ro(_check("custom_sf_grantmaker", "SF Grantmaker")),
    _data("custom_sf_membership_span", "SF Membership Span"),
    _data("custom_sf_membership_status", "SF Membership Status"),
    _ro(_int("custom_sf_number_of_household_members", "SF # Household Members")),
    # ---- bde / SF_Account_ID__c ----
    _data("custom_sf_bde_batch", "SF BDE Batch"),
    _data("custom_sf_account_legacy_id", "SF Legacy Account ID"),
    _data("custom_sf_old_one2one_contact", "SF Old One2One Contact"),
    # ---- PEAS custom__c ----
    _data("custom_sf_director", "Director"),
    _long_text("custom_sf_address_text", "Address (text)"),
    _data("custom_sf_general_enquiries_email", "General Enquiries Email"),
    _data("custom_sf_org_type", "Org Type"),
    _data("custom_sf_org_sub_type", "Org Sub-Type"),
    _data("custom_sf_capacity_to_give", "Capacity to Give"),
    _data("custom_sf_thematic_areas", "Thematic Areas"),
    _data("custom_sf_country_of_origin", "Country of Origin"),
    _data("custom_sf_country_of_interest", "Country of Interest"),
    _data("custom_sf_interests", "Interests"),
    _check("custom_sf_active_gift_aid_declaration", "Active Gift Aid Declaration"),
    _data("custom_sf_comms_opt_in", "Comms Opt-In"),
    _data("custom_sf_comms_options", "Comms Options"),
    _data("custom_sf_contact_eligibility", "Contact Eligibility"),
]


# ----------------------------------------------------------------------
# Contact
# ----------------------------------------------------------------------
CONTACT_FIELDS: list[dict] = [
    SF_ID_FIELD,
    # ---- Standard SF Contact ----
    _data("custom_sf_home_phone", "SF Home Phone"),
    _data("custom_sf_other_phone", "SF Other Phone"),
    _data("custom_sf_assistant_phone", "SF Assistant Phone"),
    _data("custom_sf_assistant_name", "SF Assistant Name"),
    _data("custom_sf_assistant_email", "SF Assistant Email"),
    _data("custom_sf_fax", "SF Fax"),
    _date("custom_sf_birthdate", "SF Birthdate"),
    _data("custom_sf_lead_source", "SF Lead Source"),
    _long_text("custom_sf_description", "SF Description"),
    _data("custom_sf_record_type", "SF Record Type ID"),
    _data("custom_sf_reports_to", "SF Reports To (Contact ID)"),
    _check("custom_sf_do_not_call", "SF Do Not Call"),
    _check("custom_sf_opted_out_email", "SF Opted Out of Email"),
    _check("custom_sf_opted_out_fax", "SF Opted Out of Fax"),
    _data("custom_sf_email_bounced_reason", "SF Email Bounced Reason"),
    _datetime("custom_sf_email_bounced_date", "SF Email Bounced Date"),
    _check("custom_sf_is_email_bounced", "SF Is Email Bounced"),
    _data("custom_sf_jigsaw", "SF Jigsaw"),
    _data("custom_sf_jigsaw_contact_id", "SF Jigsaw Contact ID"),
    _data("custom_sf_individual_id", "SF Individual ID"),
    _data("custom_sf_external_id", "SF External ID"),
    # ---- npe01 ----
    _ro(_data("custom_sf_alternate_email", "SF Alternate Email")),
    _ro(_data("custom_sf_home_email", "SF Home Email")),
    _ro(_data("custom_sf_work_email", "SF Work Email")),
    _ro(_long_text("custom_sf_home_address", "SF Home Address")),
    _ro(_long_text("custom_sf_other_address", "SF Other Address")),
    _ro(_long_text("custom_sf_work_address", "SF Work Address")),
    _ro(_date("custom_sf_last_donation_date", "SF Last Donation Date")),
    _ro(_currency("custom_sf_lifetime_giving_amount", "SF Lifetime Giving Amount")),
    _data("custom_sf_organization_type", "SF Organization Type"),
    _data("custom_sf_preferred_phone", "SF Preferred Phone"),
    _data("custom_sf_preferred_email", "SF Preferred Email"),
    _data("custom_sf_primary_address_type", "SF Primary Address Type"),
    _data("custom_sf_secondary_address_type", "SF Secondary Address Type"),
    _check("custom_sf_private", "SF Private"),
    _data("custom_sf_system_account_processor", "SF System Account Processor"),
    _data("custom_sf_type_of_account", "SF Type of Account"),
    _data("custom_sf_work_phone", "SF Work Phone"),
    # ---- npo02 (read-only rollups) ----
    _ro(_currency("custom_sf_average_amount", "SF Average Donation")),
    _ro(_date("custom_sf_first_close_date", "SF First Close Date")),
    _ro(_currency("custom_sf_largest_amount", "SF Largest Donation")),
    _ro(_date("custom_sf_last_close_date_hh", "SF Last Close Date (HH)")),
    _ro(_date("custom_sf_last_close_date", "SF Last Close Date")),
    _ro(_currency("custom_sf_last_opp_amount", "SF Last Opp Amount")),
    _ro(_int("custom_sf_number_of_closed_opps", "SF # Closed Opps")),
    _ro(_currency("custom_sf_opp_amount_2_years_ago", "SF Opp Amount 2yrs Ago")),
    _ro(_currency("custom_sf_opp_amount_last_n_days", "SF Opp Amount Last N Days")),
    _ro(_currency("custom_sf_opp_amount_last_year_hh", "SF Opp Amount Last Year (HH)")),
    _ro(_currency("custom_sf_opp_amount_last_year", "SF Opp Amount Last Year")),
    _ro(_currency("custom_sf_opp_amount_this_year_hh", "SF Opp Amount This Year (HH)")),
    _ro(_currency("custom_sf_opp_amount_this_year", "SF Opp Amount This Year")),
    _ro(_int("custom_sf_opps_closed_2_years_ago", "SF Opps Closed 2yrs Ago")),
    _ro(_int("custom_sf_opps_closed_last_n_days", "SF Opps Closed Last N Days")),
    _ro(_int("custom_sf_opps_closed_last_year", "SF Opps Closed Last Year")),
    _ro(_int("custom_sf_opps_closed_this_year", "SF Opps Closed This Year")),
    _ro(_currency("custom_sf_smallest_amount", "SF Smallest Donation")),
    _ro(_currency("custom_sf_total_membership_opp_amount", "SF Total Membership Opp Amount")),
    _ro(_currency("custom_sf_total_opp_amount", "SF Total Opp Amount")),
    _ro(_currency("custom_sf_total_household_gifts", "SF Total Household Gifts")),
    _ro(_data("custom_sf_naming_exclusions", "SF Naming Exclusions")),
    _ro(_currency("custom_sf_best_gift_year_total", "SF Best Gift Year Total")),
    _ro(_data("custom_sf_best_gift_year", "SF Best Gift Year")),
    _ro(_data("custom_sf_household_naming_order", "SF Household Naming Order")),
    _ro(_currency("custom_sf_soft_credit_last_year", "SF Soft Credit Last Year")),
    _ro(_currency("custom_sf_soft_credit_this_year", "SF Soft Credit This Year")),
    _ro(_currency("custom_sf_soft_credit_total", "SF Soft Credit Total")),
    _ro(_currency("custom_sf_soft_credit_two_years_ago", "SF Soft Credit Two Years Ago")),
    _data("custom_sf_household", "SF Household (npo02)"),
    _data("custom_sf_household_phone", "SF Household Phone"),
    _data("custom_sf_household_address_text", "SF Formula Household Mailing Address"),
    _data("custom_sf_system_household_processor", "SF System Household Processor"),
    # ---- npsp ----
    _data("custom_sf_address_verification_status", "SF Address Verification Status"),
    _data("custom_sf_current_address", "SF Current Address"),
    _check("custom_sf_deceased", "SF Deceased"),
    _check("custom_sf_do_not_contact", "SF Do Not Contact"),
    _check("custom_sf_exclude_from_household_formal_greeting", "Exclude from HH Formal Greeting"),
    _check("custom_sf_exclude_from_household_informal_greeting", "Exclude from HH Informal Greeting"),
    _check("custom_sf_exclude_from_household_name", "Exclude from HH Name"),
    _data("custom_sf_hh_id", "SF HH Id"),
    _data("custom_sf_primary_affiliation", "SF Primary Affiliation"),
    _check("custom_sf_primary_contact", "SF Primary Contact"),
    _ro(_currency("custom_sf_soft_credit_last_n_days", "SF Soft Credit Last N Days")),
    _check("custom_sf_is_address_override", "SF Is Address Override"),
    _data("custom_sf_npsp_batch", "SF NPSP Batch"),
    _data("custom_sf_bde_batch", "SF BDE Batch"),
    _data("custom_sf_legacy_id", "SF Legacy Contact ID"),
    _data("custom_sf_mc_subscriber", "MailChimp Subscriber"),
    # ---- PEAS custom__c ----
    _check("custom_sf_active_gift_aid_declaration", "Active Gift Aid Declaration"),
    _check("custom_sf_invite_to_events", "Invite to Events"),
    _data("custom_sf_comms_options", "Comms Options"),
    _check("custom_sf_email_opt_in", "Email Opt-In"),
    _check("custom_sf_phone_opt_in", "Phone Opt-In"),
    _check("custom_sf_post_opt_in", "Post Opt-In"),
    _check("custom_sf_sms_opt_in", "SMS Opt-In"),
    _data("custom_sf_comms_opt_in", "Comms Opt-In"),
    _data("custom_sf_how_heard", "How Heard"),
    _data("custom_sf_originates_from", "Originates From"),
    _data("custom_sf_pipeline_stage", "Pipeline Stage"),
    _data("custom_sf_household_head_education", "Household Head Education"),
    _data("custom_sf_maiden_name", "Maiden Name"),
    _data("custom_sf_bio_type", "Bio Type"),
    _data("custom_sf_employer", "Employer"),
    _data("custom_sf_skype_id", "Skype ID"),
    _data("custom_sf_job_title", "Job Title (custom)"),
    _data("custom_sf_preferred_contact_method", "Preferred Contact Method"),
    _long_text("custom_sf_notes", "Notes"),
    _check("custom_sf_add_to_partner_mailing_list", "Add to Partner Mailing List"),
    _data("custom_sf_interests", "Interests"),
]


# ----------------------------------------------------------------------
# CRM Lead
# ----------------------------------------------------------------------
CRM_LEAD_FIELDS: list[dict] = [
    SF_ID_FIELD,
    _data("custom_sf_fax", "SF Fax"),
    _long_text("custom_sf_description", "SF Description"),
    _data("custom_sf_rating", "SF Rating"),
    _data("custom_sf_record_type", "SF Record Type ID"),
    _data("custom_sf_jigsaw", "SF Jigsaw"),
    _data("custom_sf_jigsaw_contact_id", "SF Jigsaw Contact ID"),
    _data("custom_sf_email_bounced_reason", "SF Email Bounced Reason"),
    _datetime("custom_sf_email_bounced_date", "SF Email Bounced Date"),
    _data("custom_sf_individual_id", "SF Individual ID"),
    _data("custom_sf_preferred_email", "SF Preferred Email"),
    _data("custom_sf_preferred_phone", "SF Preferred Phone"),
    _currency("custom_sf_donation_amount", "Donation Amount"),
    _date("custom_sf_donation_close_date", "Donation Close Date"),
    _data("custom_sf_mc_subscriber", "MailChimp Subscriber"),
    _data("custom_sf_bde_batch", "SF BDE Batch"),
    _data("custom_sf_npsp_batch", "SF NPSP Batch"),
    _data("custom_sf_legacy_id", "SF Legacy Lead ID"),
    _data("custom_sf_external_id", "SF External ID"),
    # ---- Lead conversion mirrors ----
    _ro(_check("custom_sf_is_converted", "SF Is Converted")),
    _ro(_date("custom_sf_converted_date", "SF Converted Date")),
    _ro(_data("custom_sf_converted_account_id", "SF Converted Account ID")),
    _ro(_data("custom_sf_converted_contact_id", "SF Converted Contact ID")),
    _ro(_data("custom_sf_converted_opportunity_id", "SF Converted Opportunity ID")),
]


# ----------------------------------------------------------------------
# CRM Deal (this is where most NPSP grant data lives)
# ----------------------------------------------------------------------
CRM_DEAL_FIELDS: list[dict] = [
    SF_ID_FIELD,
    _data("custom_sf_opportunity_name", "SF Opportunity Name"),
    _long_text("custom_sf_description", "SF Description"),
    _data("custom_sf_type", "SF Opportunity Type"),
    _data("custom_sf_record_type", "SF Record Type ID"),
    _data("custom_sf_forecast_category", "SF Forecast Category"),
    _data("custom_sf_forecast_category_name", "SF Forecast Category Name"),
    _check("custom_sf_is_closed", "SF Is Closed"),
    _check("custom_sf_is_won", "SF Is Won"),
    _check("custom_sf_is_private", "SF Is Private"),
    _data("custom_sf_total_opportunity_quantity", "SF Total Quantity"),
    _data("custom_sf_pricebook_id", "SF Pricebook ID"),
    _data("custom_sf_fiscal", "SF Fiscal"),
    _data("custom_sf_campaign", "SF Campaign ID"),
    _data("custom_sf_primary_contact", "SF Primary Contact"),
    _check("custom_sf_has_opportunity_line_item", "SF Has Line Items"),
    _currency("custom_sf_expected_revenue", "SF Expected Revenue"),
    _data("custom_sf_lead_source", "SF Lead Source"),
    _data("custom_sf_next_step", "SF Next Step"),
    _data("custom_sf_external_id", "SF External ID"),
    # ---- npe01 ----
    _currency("custom_sf_amount_outstanding", "SF Amount Outstanding"),
    _currency("custom_sf_amount_written_off", "SF Amount Written Off"),
    _int("custom_sf_number_of_payments", "SF # Payments"),
    _int("custom_sf_payments_made", "SF Payments Made"),
    _check("custom_sf_do_not_auto_create_payment", "SF Do Not Auto-Create Payment"),
    _data("custom_sf_member_level", "SF Member Level"),
    _data("custom_sf_membership_origin", "SF Membership Origin"),
    _date("custom_sf_membership_start_date", "SF Membership Start Date"),
    _date("custom_sf_membership_end_date", "SF Membership End Date"),
    _data("custom_sf_contact_id_for_role", "SF Contact ID for Role"),
    _check("custom_sf_is_opp_from_individual", "SF Is From Individual"),
    # ---- npo02 ----
    _data("custom_sf_combined_rollup_fieldset", "SF Combined Rollup Fieldset"),
    _data("custom_sf_system_household_processor", "SF System Household Processor"),
    # ---- npe03 ----
    _data("custom_sf_recurring_donation", "SF Recurring Donation ID"),
    # ---- npsp grant ----
    _data("custom_sf_grant_contract_number", "SF Grant Contract Number"),
    _date("custom_sf_grant_contract_date", "SF Grant Contract Date"),
    _date("custom_sf_grant_period_start", "SF Grant Period Start"),
    _date("custom_sf_grant_period_end", "SF Grant Period End"),
    _data("custom_sf_grant_program_areas", "SF Grant Program Areas"),
    _data("custom_sf_grant_requirements_website", "SF Grant Requirements Website"),
    _check("custom_sf_is_grant_renewal", "SF Is Grant Renewal"),
    _data("custom_sf_previous_grant_opp", "SF Previous Grant Opp"),
    _date("custom_sf_next_grant_deadline", "SF Next Grant Deadline"),
    _currency("custom_sf_requested_amount", "SF Requested Amount"),
    _date("custom_sf_acknowledgment_date", "SF Acknowledgment Date"),
    _data("custom_sf_acknowledgment_status", "SF Acknowledgment Status"),
    _data("custom_sf_recurring_donation_installment_name", "SF Recurring Installment Name"),
    _int("custom_sf_recurring_donation_installment_number", "SF Recurring Installment #"),
    _data("custom_sf_npsp_batch", "SF NPSP Batch"),
    # ---- PEAS gift aid ----
    _check("custom_sf_gift_aid", "Gift Aid"),
    _data("custom_sf_gift_aid_applicable", "Gift Aid Applicable"),
    _check("custom_sf_gift_aid_claimed", "Gift Aid Claimed"),
    _date("custom_sf_gift_aid_claimed_date", "Gift Aid Claimed Date"),
    _data("custom_sf_gift_aid_declaration", "Gift Aid Declaration"),
    _check("custom_sf_is_payment_method_gift_aid_eligible", "Payment Method Gift Aid Eligible"),
    _check("custom_sf_is_gift_type_gift_aid_eligible", "Gift Type Gift Aid Eligible"),
    _check("custom_sf_thanked", "Thanked"),
    _data("custom_sf_thanked_by", "Thanked By"),
    _check("custom_sf_declaration_active_within_dated_range", "Declaration Active in Date Range"),
    _long_text("custom_sf_address_text", "Address (text)"),
    _data("custom_sf_first_name", "First Name (custom)"),
    _data("custom_sf_last_name", "Last Name (custom)"),
    _data("custom_sf_postcode", "Postcode (custom)"),
    _data("custom_sf_title", "Title (custom)"),
    # ---- PEAS payment ----
    _data("custom_sf_payment_method", "Payment Method"),
    _currency("custom_sf_payment_amount", "Payment Amount"),
    _date("custom_sf_date_of_payment", "Date of Payment"),
    _date("custom_sf_cheque_date", "Cheque Date"),
    _check("custom_sf_invoice_sent", "Invoice Sent"),
    _data("custom_sf_text_amount", "Text Amount"),
    # ---- PEAS application / grant workflow ----
    _data("custom_sf_application_name", "Application Name"),
    _date("custom_sf_application_date", "Application Date"),
    _data("custom_sf_submitted_to", "Submitted To"),
    _data("custom_sf_submitted_by", "Submitted By"),
    _date("custom_sf_date_of_expected_decision", "Date of Expected Decision"),
    _long_text("custom_sf_reply_details", "Reply Details"),
    _data("custom_sf_relates_to_application", "Relates to Application"),
    _data("custom_sf_alternative_gift", "Alternative Gift"),
    _check("custom_sf_alternative_gift_bought", "Alternative Gift Bought"),
    _data("custom_sf_alternative_g", "Alternative G"),
    _data("custom_sf_dedication_acknowledgement_type", "Dedication Acknowledgement Type"),
    _long_text("custom_sf_dedication_personal_note", "Dedication Personal Note"),
    _data("custom_sf_honoree_name", "Honoree Name"),
    _data("custom_sf_prospecting_stage", "Prospecting Stage"),
    _data("custom_sf_new_business_vs_stewardship", "New Business vs Stewardship"),
    # ---- PEAS fund / destination ----
    _data("custom_sf_fund_new", "Fund (New)"),
    _data("custom_sf_fund_destination", "Fund Destination"),
    _data("custom_sf_destination_country", "Destination Country"),
    _data("custom_sf_operating_country", "Operating Country"),
    _currency("custom_sf_amount_sent_to_field", "Amount Sent to Field"),
    _data("custom_sf_income_stream", "Income Stream"),
    # ---- PEAS capex / opex ----
    _currency("custom_sf_capex", "Capex"),
    _currency("custom_sf_opex", "Opex"),
    _currency("custom_sf_total_capex", "Total Capex"),
    _currency("custom_sf_total_opex", "Total Opex"),
    _currency("custom_sf_expected_capex", "Expected Capex"),
    _currency("custom_sf_expected_opex", "Expected Opex"),
    _currency("custom_sf_confirmed_capex", "Confirmed Capex"),
    _currency("custom_sf_confirmed_opex", "Confirmed Opex"),
    _currency("custom_sf_total_payments", "Total Payments"),
    _data("custom_sf_total_income_years", "Total Income Years"),
    _data("custom_sf_sort_column_for_grant_view", "Sort Column for Grant View"),
    _int("custom_sf_probability_integer_for_reports_only", "Probability (int, reports)"),
    _int("custom_sf_opex_integer_for_reports_only", "Opex (int, reports)"),
    # ---- PEAS project ----
    _date("custom_sf_project_start", "Project Start"),
    _date("custom_sf_project_end", "Project End"),
    _check("custom_sf_restricted", "Restricted"),
    _data("custom_sf_originates_from", "Originates From"),
    _long_text("custom_sf_notes", "Notes"),
    # SF stores long file paths (often deep network shares wrapped in HTML);
    # 140-char Data overflows. Small Text avoids the cap.
    _small_text("custom_sf_file_location", "File Location"),
    _int("custom_sf_installment_number", "Installment Number"),
    _date("custom_sf_due_date_of_installment", "Due Date of Installment"),
    _data("custom_sf_package", "Package"),
    _data("custom_sf_bde_batch", "SF BDE Batch"),
    _data("custom_sf_legacy_id", "SF Legacy Opportunity ID"),
    _data("custom_sf_cheque_number", "Cheque Reference"),
]


# ----------------------------------------------------------------------
# CRM Task (Task + Event)
# ----------------------------------------------------------------------
CRM_TASK_FIELDS: list[dict] = TASK_BASE_FIELDS + [
    _data("custom_sf_type", "SF Activity Type (Type field)"),
    _data("custom_sf_record_type", "SF Record Type ID"),
    {
        "fieldname": "custom_sf_account",
        "label": "SF Account (Org)",
        "fieldtype": "Link",
        "options": "CRM Organization",
        "no_copy": 1,
    },
    _int("custom_sf_call_duration", "SF Call Duration (s)"),
    _data("custom_sf_call_type", "SF Call Type"),
    _data("custom_sf_call_disposition", "SF Call Disposition"),
    _datetime("custom_sf_completed_datetime", "SF Completed At"),
    _datetime("custom_sf_reminder_datetime", "SF Reminder"),
    _data("custom_sf_task_subtype", "SF Task Subtype"),
    _data("custom_sf_event_subtype", "SF Event Subtype"),
    _data("custom_sf_location", "SF Event Location"),
    _check("custom_sf_is_all_day", "SF Is All-Day Event"),
    _check("custom_sf_is_private", "SF Is Private"),
    _data("custom_sf_show_as", "SF Show As"),
    _int("custom_sf_duration_minutes", "SF Duration (min)"),
    _check("custom_sf_is_closed", "SF Is Closed"),
    _check("custom_sf_is_high_priority", "SF Is High Priority"),
    _data("custom_sf_engagement_plan_task", "SF Engagement Plan Task"),
    _data("custom_sf_engagement_plan", "SF Engagement Plan"),
    _data("custom_sf_payment", "SF Payment"),
    _data("custom_sf_report_contents", "SF Report Contents"),
    _long_text("custom_sf_report_notes", "SF Report Notes"),
    _data("custom_sf_delegated_to", "SF Delegated To"),
]

# ----------------------------------------------------------------------
# Aggregate
# ----------------------------------------------------------------------
ALL_CUSTOM_FIELDS: dict[str, list[dict]] = {
    "CRM Organization": CRM_ORGANIZATION_FIELDS,
    "Contact": CONTACT_FIELDS,
    "CRM Lead": CRM_LEAD_FIELDS,
    "CRM Deal": CRM_DEAL_FIELDS,
    "CRM Task": CRM_TASK_FIELDS,
}


def ensure_all_custom_fields() -> None:
    """Idempotently create every Salesforce-related custom field.

    Safe to call multiple times (Frappe's ``create_custom_fields`` is
    idempotent). Used by ``after_install`` and by migration patches.
    """
    create_custom_fields(ALL_CUSTOM_FIELDS, ignore_validate=True)
