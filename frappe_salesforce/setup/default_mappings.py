"""Seed default Salesforce → Frappe field mappings.

Idempotent: a mapping is only created if one does not already exist for
the Salesforce object. To backfill rows onto an existing install use the
patch ``frappe_salesforce.patches.v0_1_0.extend_default_mappings``.

Mapping row shape:

    {"sf_field": "Name", "frappe_field": "organization_name"}
    {"sf_field": "Industry", "frappe_field": "industry",
     "transform": "industry_link"}
    {"sf_fields": ["BillingStreet", "BillingCity", "BillingState",
                   "BillingPostalCode", "BillingCountry"],
     "frappe_field": "address",       # cosmetic; address is upserted
                                      # via after_upsert, not doc.update
     "transform": "address"}

``sf_fields`` is the multi-input form. When set, the transform receives
a ``dict[str, Any]`` of ``{sf_field: value}``. See ``sync.transforms``.
"""

from __future__ import annotations

from typing import Any

try:
    import frappe
except ModuleNotFoundError:  # pragma: no cover - supports no-site static tests
    frappe = None

REQUIRED_DEFAULT_MAPPING_ROWS: dict[str, tuple[dict[str, str], ...]] = {
    "Task": ({"sf_field": "Subject", "frappe_field": "title"},),
    "Event": ({"sf_field": "Subject", "frappe_field": "title"},),
}


class SalesforceMappingSetupError(Exception):
    """Raised when required Salesforce field mappings are missing."""


DEFAULT_MAPPINGS: list[dict] = [
    # ------------------------------------------------------------------
    # Account → CRM Organization
    # ------------------------------------------------------------------
    {
        "salesforce_object": "Account",
        "frappe_doctype": "CRM Organization",
        "rows": [
            {"sf_field": "Name", "frappe_field": "organization_name"},
            {"sf_field": "Website", "frappe_field": "website"},
            {
                "sf_field": "Industry",
                "frappe_field": "industry",
                "transform": "industry_link",
            },
            {"sf_field": "AnnualRevenue", "frappe_field": "annual_revenue"},
            {
                "sf_field": "NumberOfEmployees",
                "frappe_field": "no_of_employees",
                "transform": "employee_bucket",
            },
            {"sf_field": "PhotoUrl", "frappe_field": "organization_logo"},
            # Owner → no native field on CRM Organization (deal_owner lives
            # on CRM Deal). Stored as custom_sf_* mirror only.
            # ----- standard SF mirrors -----
            {"sf_field": "Phone", "frappe_field": "custom_sf_phone"},
            {"sf_field": "Fax", "frappe_field": "custom_sf_fax"},
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {"sf_field": "AccountNumber", "frappe_field": "custom_sf_account_number"},
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {"sf_field": "Rating", "frappe_field": "custom_sf_rating"},
            {"sf_field": "Site", "frappe_field": "custom_sf_site"},
            {"sf_field": "AccountSource", "frappe_field": "custom_sf_account_source"},
            {"sf_field": "Ownership", "frappe_field": "custom_sf_ownership"},
            {"sf_field": "TickerSymbol", "frappe_field": "custom_sf_ticker"},
            {"sf_field": "Sic", "frappe_field": "custom_sf_sic"},
            {"sf_field": "SicDesc", "frappe_field": "custom_sf_sic_desc"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
            {"sf_field": "Jigsaw", "frappe_field": "custom_sf_jigsaw"},
            {"sf_field": "JigsawCompanyId", "frappe_field": "custom_sf_jigsaw_company_id"},
            {"sf_field": "ExternalID__c", "frappe_field": "custom_sf_external_id"},
            # ----- npe01__ rollups -----
            {
                "sf_field": "npe01__One2OneContact__c",
                "frappe_field": "custom_sf_one2one_contact",
            },
            {
                "sf_field": "npe01__SYSTEMIsIndividual__c",
                "frappe_field": "custom_sf_system_is_individual",
                "transform": "boolean",
            },
            {
                "sf_field": "npe01__FirstDonationDate__c",
                "frappe_field": "custom_sf_first_donation_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__LastDonationDate__c",
                "frappe_field": "custom_sf_last_donation_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__LifetimeDonationHistory_Amount__c",
                "frappe_field": "custom_sf_lifetime_donation_amount",
            },
            {
                "sf_field": "npe01__LifetimeDonationHistory_Number__c",
                "frappe_field": "custom_sf_lifetime_donation_number",
            },
            {
                "sf_field": "npe01__SYSTEM_AccountType__c",
                "frappe_field": "custom_sf_system_account_type",
            },
            # ----- npo02__ rollups -----
            {"sf_field": "npo02__AverageAmount__c", "frappe_field": "custom_sf_average_amount"},
            {
                "sf_field": "npo02__FirstCloseDate__c",
                "frappe_field": "custom_sf_first_close_date",
                "transform": "date",
            },
            {"sf_field": "npo02__LargestAmount__c", "frappe_field": "custom_sf_largest_amount"},
            {
                "sf_field": "npo02__LastCloseDate__c",
                "frappe_field": "custom_sf_last_close_date",
                "transform": "date",
            },
            {
                "sf_field": "npo02__LastMembershipAmount__c",
                "frappe_field": "custom_sf_last_membership_amount",
            },
            {
                "sf_field": "npo02__LastMembershipDate__c",
                "frappe_field": "custom_sf_last_membership_date",
                "transform": "date",
            },
            {
                "sf_field": "npo02__LastMembershipLevel__c",
                "frappe_field": "custom_sf_last_membership_level",
            },
            {
                "sf_field": "npo02__LastMembershipOrigin__c",
                "frappe_field": "custom_sf_last_membership_origin",
            },
            {
                "sf_field": "npo02__LastOppAmount__c",
                "frappe_field": "custom_sf_last_opp_amount",
            },
            {
                "sf_field": "npo02__MembershipEndDate__c",
                "frappe_field": "custom_sf_membership_end_date",
                "transform": "date",
            },
            {
                "sf_field": "npo02__MembershipJoinDate__c",
                "frappe_field": "custom_sf_membership_join_date",
                "transform": "date",
            },
            {
                "sf_field": "npo02__NumberOfClosedOpps__c",
                "frappe_field": "custom_sf_number_of_closed_opps",
            },
            {
                "sf_field": "npo02__NumberOfMembershipOpps__c",
                "frappe_field": "custom_sf_number_of_membership_opps",
            },
            {
                "sf_field": "npo02__OppAmount2YearsAgo__c",
                "frappe_field": "custom_sf_opp_amount_2_years_ago",
            },
            {
                "sf_field": "npo02__OppAmountLastNDays__c",
                "frappe_field": "custom_sf_opp_amount_last_n_days",
            },
            {
                "sf_field": "npo02__OppAmountLastYear__c",
                "frappe_field": "custom_sf_opp_amount_last_year",
            },
            {
                "sf_field": "npo02__OppAmountThisYear__c",
                "frappe_field": "custom_sf_opp_amount_this_year",
            },
            {
                "sf_field": "npo02__OppsClosed2YearsAgo__c",
                "frappe_field": "custom_sf_opps_closed_2_years_ago",
            },
            {
                "sf_field": "npo02__OppsClosedLastNDays__c",
                "frappe_field": "custom_sf_opps_closed_last_n_days",
            },
            {
                "sf_field": "npo02__OppsClosedLastYear__c",
                "frappe_field": "custom_sf_opps_closed_last_year",
            },
            {
                "sf_field": "npo02__OppsClosedThisYear__c",
                "frappe_field": "custom_sf_opps_closed_this_year",
            },
            {
                "sf_field": "npo02__SmallestAmount__c",
                "frappe_field": "custom_sf_smallest_amount",
            },
            {
                "sf_field": "npo02__TotalMembershipOppAmount__c",
                "frappe_field": "custom_sf_total_membership_opp_amount",
            },
            {
                "sf_field": "npo02__TotalOppAmount__c",
                "frappe_field": "custom_sf_total_opp_amount",
            },
            {
                "sf_field": "npo02__Best_Gift_Year_Total__c",
                "frappe_field": "custom_sf_best_gift_year_total",
            },
            {
                "sf_field": "npo02__Best_Gift_Year__c",
                "frappe_field": "custom_sf_best_gift_year",
            },
            {
                "sf_field": "npo02__Formal_Greeting__c",
                "frappe_field": "custom_sf_formal_greeting",
            },
            {
                "sf_field": "npo02__HouseholdPhone__c",
                "frappe_field": "custom_sf_household_phone",
            },
            {
                "sf_field": "npo02__Informal_Greeting__c",
                "frappe_field": "custom_sf_informal_greeting",
            },
            {
                "sf_field": "npo02__SYSTEM_CUSTOM_NAMING__c",
                "frappe_field": "custom_sf_system_custom_naming",
            },
            # ----- npsp__ -----
            {"sf_field": "npsp__Batch__c", "frappe_field": "custom_sf_npsp_batch"},
            {"sf_field": "npsp__Funding_Focus__c", "frappe_field": "custom_sf_funding_focus"},
            {
                "sf_field": "npsp__Grantmaker__c",
                "frappe_field": "custom_sf_grantmaker",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Membership_Span__c",
                "frappe_field": "custom_sf_membership_span",
            },
            {
                "sf_field": "npsp__Membership_Status__c",
                "frappe_field": "custom_sf_membership_status",
            },
            {
                "sf_field": "npsp__Number_of_Household_Members__c",
                "frappe_field": "custom_sf_number_of_household_members",
            },
            # ----- bde / SF_Account_ID__c -----
            {"sf_field": "bde__Batch__c", "frappe_field": "custom_sf_bde_batch"},
            {
                "sf_field": "SF_Account_ID__c",
                "frappe_field": "custom_sf_account_legacy_id",
            },
            {
                "sf_field": "SFOldOne2OneContact__c",
                "frappe_field": "custom_sf_old_one2one_contact",
            },
            # ----- PEAS custom__c -----
            {"sf_field": "Director__c", "frappe_field": "custom_sf_director"},
            {"sf_field": "Address__c", "frappe_field": "custom_sf_address_text"},
            {
                "sf_field": "General_enquiries_email__c",
                "frappe_field": "custom_sf_general_enquiries_email",
            },
            {"sf_field": "Org_Type__c", "frappe_field": "custom_sf_org_type"},
            {"sf_field": "Org_Sub_Type__c", "frappe_field": "custom_sf_org_sub_type"},
            {
                "sf_field": "Capacity_to_give__c",
                "frappe_field": "custom_sf_capacity_to_give",
            },
            {"sf_field": "Thematic_Areas__c", "frappe_field": "custom_sf_thematic_areas"},
            {
                "sf_field": "Country_of_Origin__c",
                "frappe_field": "custom_sf_country_of_origin",
            },
            {
                "sf_field": "Country_of_Interest__c",
                "frappe_field": "custom_sf_country_of_interest",
            },
            {"sf_field": "Interests__c", "frappe_field": "custom_sf_interests"},
            {
                "sf_field": "Active_Gift_Aid_Declaration__c",
                "frappe_field": "custom_sf_active_gift_aid_declaration",
                "transform": "boolean",
            },
            {"sf_field": "Comms_Opt_In__c", "frappe_field": "custom_sf_comms_opt_in"},
            {"sf_field": "Comms_Options__c", "frappe_field": "custom_sf_comms_options"},
            {
                "sf_field": "Contact_Eligibility__c",
                "frappe_field": "custom_sf_contact_eligibility",
            },
            # ----- Address (multi-input) -----
            # Address upsert is performed in AccountSyncer.after_upsert; the
            # mapping row is here so SOQL pulls the SF fields. The transform
            # returns a dict that the syncer ignores (uses raw SF block).
            {
                "sf_fields": [
                    "BillingStreet",
                    "BillingCity",
                    "BillingState",
                    "BillingPostalCode",
                    "BillingCountry",
                    "ShippingStreet",
                    "ShippingCity",
                    "ShippingState",
                    "ShippingPostalCode",
                    "ShippingCountry",
                ],
                "frappe_field": "custom_sf_address_block",
                "transform": "address",
            },
        ],
    },
    # ------------------------------------------------------------------
    # Contact → Contact (Frappe framework)
    # ------------------------------------------------------------------
    {
        "salesforce_object": "Contact",
        "frappe_doctype": "Contact",
        "rows": [
            {"sf_field": "FirstName", "frappe_field": "first_name"},
            {"sf_field": "LastName", "frappe_field": "last_name"},
            {
                "sf_field": "Salutation",
                "frappe_field": "salutation",
                "transform": "salutation_link",
            },
            {"sf_field": "Title", "frappe_field": "designation"},
            {"sf_field": "Department", "frappe_field": "department"},
            {"sf_field": "PhotoUrl", "frappe_field": "image"},
            {
                "sf_field": "HasOptedOutOfEmail",
                "frappe_field": "unsubscribed",
                "transform": "boolean",
            },
            {
                "sf_field": "AccountId",
                "frappe_field": "company_name",
                "transform": "account_lookup",
            },
            # ----- multi-input: emails to email_ids child table -----
            {
                "sf_fields": [
                    "Email",
                    "npe01__WorkEmail__c",
                    "npe01__HomeEmail__c",
                    "npe01__AlternateEmail__c",
                ],
                "frappe_field": "email_ids",
                "transform": "email_table",
            },
            # ----- multi-input: phones to phone_nos child table -----
            {
                "sf_fields": [
                    "Phone",
                    "MobilePhone",
                    "HomePhone",
                    "OtherPhone",
                    "AssistantPhone",
                    "Fax",
                ],
                "frappe_field": "phone_nos",
                "transform": "phone_table",
            },
            # ----- standard SF mirrors -----
            {"sf_field": "AssistantName", "frappe_field": "custom_sf_assistant_name"},
            {
                "sf_field": "Birthdate",
                "frappe_field": "custom_sf_birthdate",
                "transform": "date",
            },
            {"sf_field": "LeadSource", "frappe_field": "custom_sf_lead_source"},
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            # NOTE: ``Contact.RecordTypeId`` omitted by default — many NPSP
            # orgs FLS-restrict it for the integration user, causing
            # ``INVALID_FIELD`` 400s that abort the entire Contact sync. If
            # your org exposes it, re-add the row in the UI:
            #   sf_field=RecordTypeId, frappe_field=custom_sf_record_type.
            {
                "sf_field": "ReportsToId",
                "frappe_field": "custom_sf_reports_to",
            },
            {
                "sf_field": "DoNotCall",
                "frappe_field": "custom_sf_do_not_call",
                "transform": "boolean",
            },
            {
                "sf_field": "HasOptedOutOfFax",
                "frappe_field": "custom_sf_opted_out_fax",
                "transform": "boolean",
            },
            {
                "sf_field": "EmailBouncedReason",
                "frappe_field": "custom_sf_email_bounced_reason",
            },
            {
                "sf_field": "EmailBouncedDate",
                "frappe_field": "custom_sf_email_bounced_date",
                "transform": "datetime",
            },
            {
                "sf_field": "IsEmailBounced",
                "frappe_field": "custom_sf_is_email_bounced",
                "transform": "boolean",
            },
            {"sf_field": "Jigsaw", "frappe_field": "custom_sf_jigsaw"},
            {"sf_field": "JigsawContactId", "frappe_field": "custom_sf_jigsaw_contact_id"},
            {"sf_field": "IndividualId", "frappe_field": "custom_sf_individual_id"},
            {"sf_field": "ExternalID__c", "frappe_field": "custom_sf_external_id"},
            {"sf_field": "SF_ContactId__c", "frappe_field": "custom_sf_legacy_id"},
            # ----- npe01 rollups (text mirrors) -----
            {
                "sf_field": "npe01__AlternateEmail__c",
                "frappe_field": "custom_sf_alternate_email",
            },
            {"sf_field": "npe01__HomeEmail__c", "frappe_field": "custom_sf_home_email"},
            {"sf_field": "npe01__WorkEmail__c", "frappe_field": "custom_sf_work_email"},
            {"sf_field": "npe01__Home_Address__c", "frappe_field": "custom_sf_home_address"},
            {"sf_field": "npe01__Other_Address__c", "frappe_field": "custom_sf_other_address"},
            {"sf_field": "npe01__Work_Address__c", "frappe_field": "custom_sf_work_address"},
            {
                "sf_field": "npe01__Last_Donation_Date__c",
                "frappe_field": "custom_sf_last_donation_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__Lifetime_Giving_History_Amount__c",
                "frappe_field": "custom_sf_lifetime_giving_amount",
            },
            {
                "sf_field": "npe01__Organization_Type__c",
                "frappe_field": "custom_sf_organization_type",
            },
            {
                "sf_field": "npe01__PreferredPhone__c",
                "frappe_field": "custom_sf_preferred_phone",
            },
            {
                "sf_field": "npe01__Preferred_Email__c",
                "frappe_field": "custom_sf_preferred_email",
            },
            {
                "sf_field": "npe01__Primary_Address_Type__c",
                "frappe_field": "custom_sf_primary_address_type",
            },
            {
                "sf_field": "npe01__Secondary_Address_Type__c",
                "frappe_field": "custom_sf_secondary_address_type",
            },
            {
                "sf_field": "npe01__Private__c",
                "frappe_field": "custom_sf_private",
                "transform": "boolean",
            },
            {
                "sf_field": "npe01__SystemAccountProcessor__c",
                "frappe_field": "custom_sf_system_account_processor",
            },
            {
                "sf_field": "npe01__Type_of_Account__c",
                "frappe_field": "custom_sf_type_of_account",
            },
            {"sf_field": "npe01__WorkPhone__c", "frappe_field": "custom_sf_work_phone"},
            # ----- npo02 rollups -----
            {"sf_field": "npo02__AverageAmount__c", "frappe_field": "custom_sf_average_amount"},
            {
                "sf_field": "npo02__FirstCloseDate__c",
                "frappe_field": "custom_sf_first_close_date",
                "transform": "date",
            },
            {"sf_field": "npo02__LargestAmount__c", "frappe_field": "custom_sf_largest_amount"},
            {
                "sf_field": "npo02__LastCloseDateHH__c",
                "frappe_field": "custom_sf_last_close_date_hh",
                "transform": "date",
            },
            {
                "sf_field": "npo02__LastCloseDate__c",
                "frappe_field": "custom_sf_last_close_date",
                "transform": "date",
            },
            {"sf_field": "npo02__LastOppAmount__c", "frappe_field": "custom_sf_last_opp_amount"},
            {
                "sf_field": "npo02__NumberOfClosedOpps__c",
                "frappe_field": "custom_sf_number_of_closed_opps",
            },
            {
                "sf_field": "npo02__OppAmount2YearsAgo__c",
                "frappe_field": "custom_sf_opp_amount_2_years_ago",
            },
            {
                "sf_field": "npo02__OppAmountLastNDays__c",
                "frappe_field": "custom_sf_opp_amount_last_n_days",
            },
            {
                "sf_field": "npo02__OppAmountLastYearHH__c",
                "frappe_field": "custom_sf_opp_amount_last_year_hh",
            },
            {
                "sf_field": "npo02__OppAmountLastYear__c",
                "frappe_field": "custom_sf_opp_amount_last_year",
            },
            {
                "sf_field": "npo02__OppAmountThisYearHH__c",
                "frappe_field": "custom_sf_opp_amount_this_year_hh",
            },
            {
                "sf_field": "npo02__OppAmountThisYear__c",
                "frappe_field": "custom_sf_opp_amount_this_year",
            },
            {
                "sf_field": "npo02__OppsClosed2YearsAgo__c",
                "frappe_field": "custom_sf_opps_closed_2_years_ago",
            },
            {
                "sf_field": "npo02__OppsClosedLastNDays__c",
                "frappe_field": "custom_sf_opps_closed_last_n_days",
            },
            {
                "sf_field": "npo02__OppsClosedLastYear__c",
                "frappe_field": "custom_sf_opps_closed_last_year",
            },
            {
                "sf_field": "npo02__OppsClosedThisYear__c",
                "frappe_field": "custom_sf_opps_closed_this_year",
            },
            {"sf_field": "npo02__SmallestAmount__c", "frappe_field": "custom_sf_smallest_amount"},
            {
                "sf_field": "npo02__TotalMembershipOppAmount__c",
                "frappe_field": "custom_sf_total_membership_opp_amount",
            },
            {
                "sf_field": "npo02__TotalOppAmount__c",
                "frappe_field": "custom_sf_total_opp_amount",
            },
            {
                "sf_field": "npo02__Total_Household_Gifts__c",
                "frappe_field": "custom_sf_total_household_gifts",
            },
            {
                "sf_field": "npo02__Naming_Exclusions__c",
                "frappe_field": "custom_sf_naming_exclusions",
            },
            {
                "sf_field": "npo02__Best_Gift_Year_Total__c",
                "frappe_field": "custom_sf_best_gift_year_total",
            },
            {
                "sf_field": "npo02__Best_Gift_Year__c",
                "frappe_field": "custom_sf_best_gift_year",
            },
            {
                "sf_field": "npo02__Household_Naming_Order__c",
                "frappe_field": "custom_sf_household_naming_order",
            },
            {
                "sf_field": "npo02__Soft_Credit_Last_Year__c",
                "frappe_field": "custom_sf_soft_credit_last_year",
            },
            {
                "sf_field": "npo02__Soft_Credit_This_Year__c",
                "frappe_field": "custom_sf_soft_credit_this_year",
            },
            {
                "sf_field": "npo02__Soft_Credit_Total__c",
                "frappe_field": "custom_sf_soft_credit_total",
            },
            {
                "sf_field": "npo02__Soft_Credit_Two_Years_Ago__c",
                "frappe_field": "custom_sf_soft_credit_two_years_ago",
            },
            {
                "sf_field": "npo02__Household__c",
                "frappe_field": "custom_sf_household",
            },
            {
                "sf_field": "npo02__Formula_HouseholdPhone__c",
                "frappe_field": "custom_sf_household_phone",
            },
            {
                "sf_field": "npo02__Formula_HouseholdMailingAddress__c",
                "frappe_field": "custom_sf_household_address_text",
            },
            {
                "sf_field": "npo02__SystemHouseholdProcessor__c",
                "frappe_field": "custom_sf_system_household_processor",
            },
            # ----- npsp__ -----
            {
                "sf_field": "npsp__Address_Verification_Status__c",
                "frappe_field": "custom_sf_address_verification_status",
            },
            {
                "sf_field": "npsp__Current_Address__c",
                "frappe_field": "custom_sf_current_address",
            },
            {
                "sf_field": "npsp__Deceased__c",
                "frappe_field": "custom_sf_deceased",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Do_Not_Contact__c",
                "frappe_field": "custom_sf_do_not_contact",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Exclude_from_Household_Formal_Greeting__c",
                "frappe_field": "custom_sf_exclude_from_household_formal_greeting",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Exclude_from_Household_Informal_Greeting__c",
                "frappe_field": "custom_sf_exclude_from_household_informal_greeting",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Exclude_from_Household_Name__c",
                "frappe_field": "custom_sf_exclude_from_household_name",
                "transform": "boolean",
            },
            {"sf_field": "npsp__HHId__c", "frappe_field": "custom_sf_hh_id"},
            {
                "sf_field": "npsp__Primary_Affiliation__c",
                "frappe_field": "custom_sf_primary_affiliation",
            },
            {
                "sf_field": "npsp__Primary_Contact__c",
                "frappe_field": "custom_sf_primary_contact",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Soft_Credit_Last_N_Days__c",
                "frappe_field": "custom_sf_soft_credit_last_n_days",
            },
            {
                "sf_field": "npsp__is_Address_Override__c",
                "frappe_field": "custom_sf_is_address_override",
                "transform": "boolean",
            },
            {"sf_field": "npsp__Batch__c", "frappe_field": "custom_sf_npsp_batch"},
            {"sf_field": "bde__Batch__c", "frappe_field": "custom_sf_bde_batch"},
            {"sf_field": "MC4SF__MC_Subscriber__c", "frappe_field": "custom_sf_mc_subscriber"},
            # ----- PEAS custom__c -----
            {
                "sf_field": "Active_Gift_Aid_Declaration__c",
                "frappe_field": "custom_sf_active_gift_aid_declaration",
                "transform": "boolean",
            },
            {
                "sf_field": "Invite_to_events__c",
                "frappe_field": "custom_sf_invite_to_events",
                "transform": "boolean",
            },
            {"sf_field": "Comms_Options__c", "frappe_field": "custom_sf_comms_options"},
            {
                "sf_field": "Email_Opt_In__c",
                "frappe_field": "custom_sf_email_opt_in",
                "transform": "boolean",
            },
            {
                "sf_field": "Phone_Opt_In__c",
                "frappe_field": "custom_sf_phone_opt_in",
                "transform": "boolean",
            },
            {
                "sf_field": "Post_Opt_In__c",
                "frappe_field": "custom_sf_post_opt_in",
                "transform": "boolean",
            },
            {
                "sf_field": "SMS_Opt_In__c",
                "frappe_field": "custom_sf_sms_opt_in",
                "transform": "boolean",
            },
            {"sf_field": "Comms_Opt_In__c", "frappe_field": "custom_sf_comms_opt_in"},
            {"sf_field": "How_Heard__c", "frappe_field": "custom_sf_how_heard"},
            {"sf_field": "Originates_From__c", "frappe_field": "custom_sf_originates_from"},
            {"sf_field": "Pipeline_Stage__c", "frappe_field": "custom_sf_pipeline_stage"},
            {
                "sf_field": "Household_head_level_of_education__c",
                "frappe_field": "custom_sf_household_head_education",
            },
            {"sf_field": "Maiden_name__c", "frappe_field": "custom_sf_maiden_name"},
            {"sf_field": "Bio_Type__c", "frappe_field": "custom_sf_bio_type"},
            {"sf_field": "Employer__c", "frappe_field": "custom_sf_employer"},
            {"sf_field": "Skype_ID__c", "frappe_field": "custom_sf_skype_id"},
            {"sf_field": "Job_Title__c", "frappe_field": "custom_sf_job_title"},
            {
                "sf_field": "Preferred_contact_method__c",
                "frappe_field": "custom_sf_preferred_contact_method",
            },
            {
                "sf_field": "Notes__c",
                "frappe_field": "custom_sf_notes",
                "transform": "html_strip",
            },
            {
                "sf_field": "Add_to_Partner_Mailing_List__c",
                "frappe_field": "custom_sf_add_to_partner_mailing_list",
                "transform": "boolean",
            },
            {"sf_field": "Assistant_Email__c", "frappe_field": "custom_sf_assistant_email"},
            {"sf_field": "Interests__c", "frappe_field": "custom_sf_interests"},
            # ----- Address (multi-input) -----
            {
                "sf_fields": [
                    "MailingStreet",
                    "MailingCity",
                    "MailingState",
                    "MailingPostalCode",
                    "MailingCountry",
                    "OtherStreet",
                    "OtherCity",
                    "OtherState",
                    "OtherPostalCode",
                    "OtherCountry",
                ],
                "frappe_field": "custom_sf_address_block",
                "transform": "address",
            },
        ],
    },
    # ------------------------------------------------------------------
    # Lead → CRM Lead
    # ------------------------------------------------------------------
    {
        "salesforce_object": "Lead",
        "frappe_doctype": "CRM Lead",
        "rows": [
            {"sf_field": "FirstName", "frappe_field": "first_name"},
            {"sf_field": "LastName", "frappe_field": "last_name"},
            {
                "sf_field": "Salutation",
                "frappe_field": "salutation",
                "transform": "salutation_link",
            },
            {"sf_field": "Company", "frappe_field": "organization"},
            {"sf_field": "Email", "frappe_field": "email"},
            {"sf_field": "Phone", "frappe_field": "phone"},
            {"sf_field": "MobilePhone", "frappe_field": "mobile_no"},
            {"sf_field": "Title", "frappe_field": "job_title"},
            {"sf_field": "Website", "frappe_field": "website"},
            {
                "sf_field": "Industry",
                "frappe_field": "industry",
                "transform": "industry_link",
            },
            {"sf_field": "AnnualRevenue", "frappe_field": "annual_revenue"},
            {
                "sf_field": "NumberOfEmployees",
                "frappe_field": "no_of_employees",
                "transform": "employee_bucket",
            },
            {"sf_field": "PhotoUrl", "frappe_field": "image"},
            {
                "sf_field": "LeadSource",
                "frappe_field": "source",
                "transform": "lead_source",
            },
            {
                "sf_field": "Status",
                "frappe_field": "status",
                "transform": "lead_status_link",
            },
            {
                "sf_field": "OwnerId",
                "frappe_field": "lead_owner",
                "transform": "user_lookup",
            },
            # ----- standard SF mirrors -----
            {"sf_field": "Fax", "frappe_field": "custom_sf_fax"},
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {"sf_field": "Rating", "frappe_field": "custom_sf_rating"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
            {"sf_field": "Jigsaw", "frappe_field": "custom_sf_jigsaw"},
            {"sf_field": "JigsawContactId", "frappe_field": "custom_sf_jigsaw_contact_id"},
            {
                "sf_field": "EmailBouncedReason",
                "frappe_field": "custom_sf_email_bounced_reason",
            },
            {
                "sf_field": "EmailBouncedDate",
                "frappe_field": "custom_sf_email_bounced_date",
                "transform": "datetime",
            },
            {"sf_field": "IndividualId", "frappe_field": "custom_sf_individual_id"},
            {
                "sf_field": "npe01__Preferred_Email__c",
                "frappe_field": "custom_sf_preferred_email",
            },
            {
                "sf_field": "npe01__Preferred_Phone__c",
                "frappe_field": "custom_sf_preferred_phone",
            },
            {"sf_field": "Donation_Amount__c", "frappe_field": "custom_sf_donation_amount"},
            {
                "sf_field": "Donation_Close_Date__c",
                "frappe_field": "custom_sf_donation_close_date",
                "transform": "date",
            },
            {"sf_field": "MC4SF__MC_Subscriber__c", "frappe_field": "custom_sf_mc_subscriber"},
            {"sf_field": "bde__Batch__c", "frappe_field": "custom_sf_bde_batch"},
            {"sf_field": "npsp__Batch__c", "frappe_field": "custom_sf_npsp_batch"},
            {"sf_field": "SF_LeadId__c", "frappe_field": "custom_sf_legacy_id"},
            # ----- Lead conversion mirrors -----
            {
                "sf_field": "IsConverted",
                "frappe_field": "custom_sf_is_converted",
                "transform": "boolean",
            },
            {
                "sf_field": "ConvertedDate",
                "frappe_field": "custom_sf_converted_date",
                "transform": "date",
            },
            {
                "sf_field": "ConvertedAccountId",
                "frappe_field": "custom_sf_converted_account_id",
            },
            {
                "sf_field": "ConvertedContactId",
                "frappe_field": "custom_sf_converted_contact_id",
            },
            {
                "sf_field": "ConvertedOpportunityId",
                "frappe_field": "custom_sf_converted_opportunity_id",
            },
        ],
    },
    # ------------------------------------------------------------------
    # Opportunity → CRM Deal
    # ------------------------------------------------------------------
    {
        "salesforce_object": "Opportunity",
        "frappe_doctype": "CRM Deal",
        "rows": [
            # CRM Deal has no native deal-name field (title_field is
            # ``organization``). We mirror SF Name into a custom field so
            # it's still visible / searchable.
            {"sf_field": "Name", "frappe_field": "custom_sf_opportunity_name"},
            {
                "sf_field": "AccountId",
                "frappe_field": "organization",
                "transform": "account_lookup",
            },
            {"sf_field": "Amount", "frappe_field": "deal_value"},
            {"sf_field": "ExpectedRevenue", "frappe_field": "expected_deal_value"},
            {
                "sf_field": "CloseDate",
                "frappe_field": "expected_closure_date",
                "transform": "date",
            },
            {
                "sf_field": "StageName",
                "frappe_field": "status",
                "transform": "deal_stage_link",
            },
            {
                "sf_field": "StageName",
                "frappe_field": "lost_reason",
                "transform": "deal_lost_reason_link",
            },
            # NOTE: SF ``Probability`` is intentionally NOT mapped. In this
            # CRM the ``peas_crm`` validate hook derives ``probability`` from
            # the CRM Deal Status, overwriting any value we set — so the SF
            # number flows via the stage→status mapping (StageName below +
            # setup/deal_statuses.py), not a direct field map.
            {"sf_field": "NextStep", "frappe_field": "custom_sf_next_step"},
            {
                "sf_field": "ContactId",
                "frappe_field": "contact",
                "transform": "contact_lookup",
            },
            {
                "sf_field": "OwnerId",
                "frappe_field": "deal_owner",
                "transform": "user_lookup",
            },
            # ----- standard SF mirrors -----
            {
                "sf_field": "Description",
                "frappe_field": "custom_sf_description",
                "transform": "html_strip",
            },
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
            {"sf_field": "ForecastCategory", "frappe_field": "custom_sf_forecast_category"},
            {
                "sf_field": "ForecastCategoryName",
                "frappe_field": "custom_sf_forecast_category_name",
            },
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
            {
                "sf_field": "IsPrivate",
                "frappe_field": "custom_sf_is_private",
                "transform": "boolean",
            },
            {
                "sf_field": "TotalOpportunityQuantity",
                "frappe_field": "custom_sf_total_opportunity_quantity",
            },
            {"sf_field": "Pricebook2Id", "frappe_field": "custom_sf_pricebook_id"},
            {"sf_field": "Fiscal", "frappe_field": "custom_sf_fiscal"},
            {
                "sf_field": "CampaignId",
                "frappe_field": "custom_sf_campaign",
                "transform": "campaign_lookup",
            },
            {
                "sf_field": "HasOpportunityLineItem",
                "frappe_field": "custom_sf_has_opportunity_line_item",
                "transform": "boolean",
            },
            {"sf_field": "LeadSource", "frappe_field": "custom_sf_lead_source"},
            {"sf_field": "ExternalID__c", "frappe_field": "custom_sf_external_id"},
            {"sf_field": "SF_OpportunityId__c", "frappe_field": "custom_sf_legacy_id"},
            # ----- npe01 -----
            {
                "sf_field": "npe01__Amount_Outstanding__c",
                "frappe_field": "custom_sf_amount_outstanding",
            },
            {
                "sf_field": "npe01__Amount_Written_Off__c",
                "frappe_field": "custom_sf_amount_written_off",
            },
            {
                "sf_field": "npe01__Number_of_Payments__c",
                "frappe_field": "custom_sf_number_of_payments",
            },
            {
                "sf_field": "npe01__Payments_Made__c",
                "frappe_field": "custom_sf_payments_made",
            },
            {
                "sf_field": "npe01__Do_Not_Automatically_Create_Payment__c",
                "frappe_field": "custom_sf_do_not_auto_create_payment",
                "transform": "boolean",
            },
            {"sf_field": "npe01__Member_Level__c", "frappe_field": "custom_sf_member_level"},
            {
                "sf_field": "npe01__Membership_Origin__c",
                "frappe_field": "custom_sf_membership_origin",
            },
            {
                "sf_field": "npe01__Membership_Start_Date__c",
                "frappe_field": "custom_sf_membership_start_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__Membership_End_Date__c",
                "frappe_field": "custom_sf_membership_end_date",
                "transform": "date",
            },
            {
                "sf_field": "npe01__Contact_Id_for_Role__c",
                "frappe_field": "custom_sf_contact_id_for_role",
            },
            {
                "sf_field": "npe01__Is_Opp_From_Individual__c",
                "frappe_field": "custom_sf_is_opp_from_individual",
                "transform": "boolean",
            },
            # ----- npo02 -----
            {
                "sf_field": "npo02__CombinedRollupFieldset__c",
                "frappe_field": "custom_sf_combined_rollup_fieldset",
            },
            {
                "sf_field": "npo02__systemHouseholdContactRoleProcessor__c",
                "frappe_field": "custom_sf_system_household_processor",
            },
            # ----- npe03 -----
            {
                "sf_field": "npe03__Recurring_Donation__c",
                "frappe_field": "custom_sf_recurring_donation",
            },
            # ----- npsp grant -----
            {
                "sf_field": "npsp__Grant_Contract_Number__c",
                "frappe_field": "custom_sf_grant_contract_number",
            },
            {
                "sf_field": "npsp__Grant_Contract_Date__c",
                "frappe_field": "custom_sf_grant_contract_date",
                "transform": "date",
            },
            {
                "sf_field": "npsp__Grant_Period_Start_Date__c",
                "frappe_field": "custom_sf_grant_period_start",
                "transform": "date",
            },
            {
                "sf_field": "npsp__Grant_Period_End_Date__c",
                "frappe_field": "custom_sf_grant_period_end",
                "transform": "date",
            },
            {
                "sf_field": "npsp__Grant_Program_Area_s__c",
                "frappe_field": "custom_sf_grant_program_areas",
            },
            {
                "sf_field": "npsp__Grant_Requirements_Website__c",
                "frappe_field": "custom_sf_grant_requirements_website",
            },
            {
                "sf_field": "npsp__Is_Grant_Renewal__c",
                "frappe_field": "custom_sf_is_grant_renewal",
                "transform": "boolean",
            },
            {
                "sf_field": "npsp__Previous_Grant_Opportunity__c",
                "frappe_field": "custom_sf_previous_grant_opp",
            },
            {
                "sf_field": "npsp__Next_Grant_Deadline_Due_Date__c",
                "frappe_field": "custom_sf_next_grant_deadline",
                "transform": "date",
            },
            {
                "sf_field": "npsp__Requested_Amount__c",
                "frappe_field": "custom_sf_requested_amount",
            },
            {
                "sf_field": "npsp__Acknowledgment_Date__c",
                "frappe_field": "custom_sf_acknowledgment_date",
                "transform": "date",
            },
            {
                "sf_field": "npsp__Acknowledgment_Status__c",
                "frappe_field": "custom_sf_acknowledgment_status",
            },
            {
                "sf_field": "npsp__Recurring_Donation_Installment_Name__c",
                "frappe_field": "custom_sf_recurring_donation_installment_name",
            },
            {
                "sf_field": "npsp__Recurring_Donation_Installment_Number__c",
                "frappe_field": "custom_sf_recurring_donation_installment_number",
            },
            {"sf_field": "npsp__Batch__c", "frappe_field": "custom_sf_npsp_batch"},
            {
                "sf_field": "npsp__Primary_Contact__c",
                "frappe_field": "custom_sf_primary_contact",
                "transform": "contact_lookup",
            },
            # ----- PEAS gift aid -----
            {
                "sf_field": "Gift_Aid__c",
                "frappe_field": "custom_sf_gift_aid",
                "transform": "boolean",
            },
            {
                "sf_field": "Gift_Aid_Applicable__c",
                "frappe_field": "custom_sf_gift_aid_applicable",
            },
            {
                "sf_field": "Gift_Aid_Claimed__c",
                "frappe_field": "custom_sf_gift_aid_claimed",
                "transform": "boolean",
            },
            {
                "sf_field": "Gift_Aid_Claimed_Date__c",
                "frappe_field": "custom_sf_gift_aid_claimed_date",
                "transform": "date",
            },
            {
                "sf_field": "Gift_Aid_Declaration__c",
                "frappe_field": "custom_sf_gift_aid_declaration",
            },
            {
                "sf_field": "Is_Payment_Method_Gift_Aid_Eligible__c",
                "frappe_field": "custom_sf_is_payment_method_gift_aid_eligible",
                "transform": "boolean",
            },
            {
                "sf_field": "Is_Gift_Type_Gift_Aid_Eligible__c",
                "frappe_field": "custom_sf_is_gift_type_gift_aid_eligible",
                "transform": "boolean",
            },
            {
                "sf_field": "Thanked__c",
                "frappe_field": "custom_sf_thanked",
                "transform": "boolean",
            },
            {"sf_field": "Thanked_By__c", "frappe_field": "custom_sf_thanked_by"},
            {
                "sf_field": "Declaration_Active_within_Dated_Range__c",
                "frappe_field": "custom_sf_declaration_active_within_dated_range",
                "transform": "boolean",
            },
            {"sf_field": "Address__c", "frappe_field": "custom_sf_address_text"},
            {"sf_field": "First_Name__c", "frappe_field": "custom_sf_first_name"},
            {"sf_field": "Last_Name__c", "frappe_field": "custom_sf_last_name"},
            {"sf_field": "Postcode__c", "frappe_field": "custom_sf_postcode"},
            {"sf_field": "Title__c", "frappe_field": "custom_sf_title"},
            # ----- PEAS payment -----
            {"sf_field": "Payment_Method__c", "frappe_field": "custom_sf_payment_method"},
            {"sf_field": "Payment_amount__c", "frappe_field": "custom_sf_payment_amount"},
            {
                "sf_field": "Date_of_Payment__c",
                "frappe_field": "custom_sf_date_of_payment",
                "transform": "date",
            },
            {
                "sf_field": "Cheque_Date__c",
                "frappe_field": "custom_sf_cheque_date",
                "transform": "date",
            },
            {
                "sf_field": "Invoice_sent__c",
                "frappe_field": "custom_sf_invoice_sent",
                "transform": "boolean",
            },
            {"sf_field": "Text_Amount__c", "frappe_field": "custom_sf_text_amount"},
            # ----- PEAS application / grant workflow -----
            {"sf_field": "Application_name__c", "frappe_field": "custom_sf_application_name"},
            {
                "sf_field": "Application_Date__c",
                "frappe_field": "custom_sf_application_date",
                "transform": "date",
            },
            {"sf_field": "Submitted_to__c", "frappe_field": "custom_sf_submitted_to"},
            {"sf_field": "Submitted_by__c", "frappe_field": "custom_sf_submitted_by"},
            {
                "sf_field": "Date_of_Expected_Decision__c",
                "frappe_field": "custom_sf_date_of_expected_decision",
                "transform": "date",
            },
            {
                "sf_field": "Reply_details__c",
                "frappe_field": "custom_sf_reply_details",
                "transform": "html_strip",
            },
            {
                "sf_field": "Relates_to_Application__c",
                "frappe_field": "custom_sf_relates_to_application",
            },
            {"sf_field": "Alternative_gift__c", "frappe_field": "custom_sf_alternative_gift"},
            {
                "sf_field": "Alternative_gift_bought__c",
                "frappe_field": "custom_sf_alternative_gift_bought",
                "transform": "boolean",
            },
            {"sf_field": "Alternative_G__c", "frappe_field": "custom_sf_alternative_g"},
            {
                "sf_field": "Dedication_Acknowledgement_Type__c",
                "frappe_field": "custom_sf_dedication_acknowledgement_type",
            },
            {
                "sf_field": "Dedication_Personal_Note__c",
                "frappe_field": "custom_sf_dedication_personal_note",
                "transform": "html_strip",
            },
            {"sf_field": "Honoree_Name__c", "frappe_field": "custom_sf_honoree_name"},
            {
                "sf_field": "Prospecting_stage__c",
                "frappe_field": "custom_sf_prospecting_stage",
            },
            {
                "sf_field": "New_Business_vs_Stewardship__c",
                "frappe_field": "custom_sf_new_business_vs_stewardship",
            },
            # ----- PEAS fund / destination -----
            {"sf_field": "Fund_New__c", "frappe_field": "custom_sf_fund_new"},
            {"sf_field": "Fund_destination__c", "frappe_field": "custom_sf_fund_destination"},
            {
                "sf_field": "Destination_of_Funding_Country__c",
                "frappe_field": "custom_sf_destination_country",
            },
            {
                "sf_field": "Operating_country__c",
                "frappe_field": "custom_sf_operating_country",
            },
            {
                "sf_field": "Amount_sent_to_field__c",
                "frappe_field": "custom_sf_amount_sent_to_field",
            },
            {"sf_field": "Income_Stream__c", "frappe_field": "custom_sf_income_stream"},
            # ----- PEAS capex / opex -----
            {"sf_field": "Opex__c", "frappe_field": "custom_sf_opex"},
            {"sf_field": "Total_Opex__c", "frappe_field": "custom_sf_total_opex"},
            {"sf_field": "Total_Capex__c", "frappe_field": "custom_sf_total_capex"},
            {"sf_field": "Expected_Capex__c", "frappe_field": "custom_sf_expected_capex"},
            {"sf_field": "Expected_Opex__c", "frappe_field": "custom_sf_expected_opex"},
            {"sf_field": "Confirmed_Opex__c", "frappe_field": "custom_sf_confirmed_opex"},
            {"sf_field": "Confirmed_Capex__c", "frappe_field": "custom_sf_confirmed_capex"},
            {"sf_field": "Total_Payments__c", "frappe_field": "custom_sf_total_payments"},
            {"sf_field": "Total_Income_Years__c", "frappe_field": "custom_sf_total_income_years"},
            {
                "sf_field": "Sort_column_for_Grant_view__c",
                "frappe_field": "custom_sf_sort_column_for_grant_view",
            },
            {
                "sf_field": "Probability_integer_for_reports_only__c",
                "frappe_field": "custom_sf_probability_integer_for_reports_only",
            },
            {
                "sf_field": "opex_integer_for_reports_only__c",
                "frappe_field": "custom_sf_opex_integer_for_reports_only",
            },
            # ----- PEAS project -----
            {
                "sf_field": "Project_Start__c",
                "frappe_field": "custom_sf_project_start",
                "transform": "date",
            },
            {
                "sf_field": "Project_End__c",
                "frappe_field": "custom_sf_project_end",
                "transform": "date",
            },
            {
                "sf_field": "Restricted__c",
                "frappe_field": "custom_sf_restricted",
                "transform": "boolean",
            },
            {"sf_field": "Originates_From__c", "frappe_field": "custom_sf_originates_from"},
            {
                "sf_field": "Notes__c",
                "frappe_field": "custom_sf_notes",
                "transform": "html_strip",
            },
            {
                "sf_field": "File_location__c",
                "frappe_field": "custom_sf_file_location",
                "transform": "html_strip",
            },
            {
                "sf_field": "Installment_number__c",
                "frappe_field": "custom_sf_installment_number",
            },
            {
                "sf_field": "Due_Date_of_Installment__c",
                "frappe_field": "custom_sf_due_date_of_installment",
                "transform": "date",
            },
            {"sf_field": "Package__c", "frappe_field": "custom_sf_package"},
            {"sf_field": "bde__Batch__c", "frappe_field": "custom_sf_bde_batch"},
        ],
    },
    # ------------------------------------------------------------------
    # Task → CRM Task
    # ------------------------------------------------------------------
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
                "transform": "datetime",
            },
            {
                "sf_field": "Status",
                "frappe_field": "status",
                "transform": "task_status_link",
            },
            {
                "sf_field": "Priority",
                "frappe_field": "priority",
                "transform": "task_priority_link",
            },
            {
                "sf_field": "OwnerId",
                "frappe_field": "assigned_to",
                "transform": "user_lookup",
            },
            # ----- standard SF mirrors -----
            {
                "sf_field": "AccountId",
                "frappe_field": "custom_sf_account",
                "transform": "account_lookup",
            },
            {"sf_field": "Type", "frappe_field": "custom_sf_type"},
            {"sf_field": "RecordTypeId", "frappe_field": "custom_sf_record_type"},
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
            {
                "sf_field": "CallDurationInSeconds",
                "frappe_field": "custom_sf_call_duration",
            },
            {"sf_field": "CallType", "frappe_field": "custom_sf_call_type"},
            {
                "sf_field": "CallDisposition",
                "frappe_field": "custom_sf_call_disposition",
            },
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
            {
                "sf_field": "npsp__Engagement_Plan_Task__c",
                "frappe_field": "custom_sf_engagement_plan_task",
            },
            {
                "sf_field": "npsp__Engagement_Plan__c",
                "frappe_field": "custom_sf_engagement_plan",
            },
            {"sf_field": "Payment__c", "frappe_field": "custom_sf_payment"},
            {"sf_field": "Report_Contents__c", "frappe_field": "custom_sf_report_contents"},
            {
                "sf_field": "Report_Notes__c",
                "frappe_field": "custom_sf_report_notes",
                "transform": "html_strip",
            },
            {"sf_field": "Delegated_To__c", "frappe_field": "custom_sf_delegated_to"},
        ],
    },
    # ------------------------------------------------------------------
    # Event → CRM Task
    # ------------------------------------------------------------------
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
                "transform": "datetime",
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
            # OwnerId not on Event by default; supplied via owner_id alias if needed.
            # ----- standard SF mirrors -----
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
            {
                "sf_field": "DurationInMinutes",
                "frappe_field": "custom_sf_duration_minutes",
            },
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
            {
                "sf_field": "npsp__Engagement_Plan_Task__c",
                "frappe_field": "custom_sf_engagement_plan_task",
            },
            {
                "sf_field": "npsp__Engagement_Plan__c",
                "frappe_field": "custom_sf_engagement_plan",
            },
            {"sf_field": "Payment__c", "frappe_field": "custom_sf_payment"},
            {"sf_field": "Report_Contents__c", "frappe_field": "custom_sf_report_contents"},
            {
                "sf_field": "Report_Notes__c",
                "frappe_field": "custom_sf_report_notes",
                "transform": "html_strip",
            },
            {"sf_field": "Delegated_To__c", "frappe_field": "custom_sf_delegated_to"},
        ],
    },
]


def seed_default_field_mappings() -> None:
    _require_frappe()
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
                "field_mappings": [_serialise_row(row) for row in mapping["rows"]],
            }
        )
        doc.insert(ignore_permissions=True)


def ensure_default_field_mappings(validate: bool = True) -> None:
    """Create/backfill default mappings and optionally validate sync readiness.

    This is intentionally additive: existing mapping rows are left untouched,
    and missing default rows are appended. Admin customisations therefore
    survive, but an old/broken install with an empty mapping table can heal
    itself before sync starts.

    One narrow exception to "untouched": rows listed in
    ``_TRANSFORM_CONVERGENCES`` whose transform is inert (empty / "none")
    are converged to the required transform — see that list's docstring.
    """
    _require_frappe()
    for mapping in DEFAULT_MAPPINGS:
        _ensure_default_mapping(mapping)
    _converge_known_broken_transforms()
    if validate:
        validate_required_field_mappings()


#: Rows where an inert transform (empty / "none") is known-broken: the raw
#: SF value can never satisfy the target Frappe field, so every populated
#: record fails to save. SF salutations carry a trailing period ("Mr.")
#: that Frappe's period-less Salutation Link rows never match.
#:
#: Why converge continuously instead of a one-shot patch: "none" is the
#: transform Select field's DEFAULT, so any row an admin adds (or
#: re-adds) through the UI lands on "none" automatically — the broken
#: state regenerates itself. The one-shot ``wire_salutation_link`` patch
#: only rewrote EMPTY transforms and skipped rows already at "none"
#: (exactly the state found on staging 2026-07-09: 141 contacts failing
#: "Could not find Salutation: Mr."), and a patch never runs twice. Any
#: non-inert transform value is a deliberate admin customisation and is
#: left untouched.
_TRANSFORM_CONVERGENCES: list[tuple[str, str, str, str]] = [
    ("Contact", "Salutation", "salutation", "salutation_link"),
    ("Lead", "Salutation", "salutation", "salutation_link"),
]


def _converge_known_broken_transforms() -> None:
    # Per-object try/except: this runs inside every migrate AND every
    # incremental sync tick (IncrementalSyncRunner calls
    # ensure_default_field_mappings each run) — one object's save failing
    # must not block the other objects, abort the tick, or prevent
    # validate_required_field_mappings from running.
    for sf_object, sf_field, frappe_field, transform in _TRANSFORM_CONVERGENCES:
        try:
            name = frappe.db.get_value(
                "Salesforce Field Mapping", {"salesforce_object": sf_object}, "name"
            )
            if not name:
                continue
            doc = frappe.get_doc("Salesforce Field Mapping", name)
            changed = False
            for row in doc.field_mappings or []:
                if (
                    row.sf_field == sf_field
                    and row.frappe_field == frappe_field
                    and (row.transform or "").strip().lower() in ("", "none")
                ):
                    row.transform = transform
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title=f"SF transform convergence failed: {sf_object}",
                message=frappe.get_traceback(),
            )


def validate_required_field_mappings() -> None:
    """Fail clearly if required mappings are not enabled and complete."""
    _require_frappe()
    required_objects = _required_salesforce_objects()
    missing: list[str] = []
    for sf_object in required_objects:
        mapping_name = frappe.db.get_value(
            "Salesforce Field Mapping",
            {"salesforce_object": sf_object, "enabled": 1},
            "name",
        )
        if not mapping_name:
            missing.append(f"{sf_object}: enabled Salesforce Field Mapping")
            continue
        doc = frappe.get_doc("Salesforce Field Mapping", mapping_name)
        rows = {_row_key(row) for row in doc.field_mappings or []}
        for required in REQUIRED_DEFAULT_MAPPING_ROWS.get(sf_object, ()):
            if _row_key(required) not in rows:
                missing.append(
                    f"{sf_object}: {required['sf_field']} -> "
                    f"{required['frappe_field']}"
                )

    if missing:
        raise SalesforceMappingSetupError(
            "Salesforce Field Mapping setup incomplete. Missing: "
            + "; ".join(missing)
        )


def _ensure_default_mapping(mapping: dict[str, Any]) -> None:
    sf_object = mapping["salesforce_object"]
    existing_name = frappe.db.get_value(
        "Salesforce Field Mapping",
        {"salesforce_object": sf_object},
        "name",
    )
    if not existing_name:
        doc = frappe.get_doc(
            {
                "doctype": "Salesforce Field Mapping",
                "salesforce_object": sf_object,
                "frappe_doctype": mapping["frappe_doctype"],
                "enabled": 1,
                "field_mappings": [_serialise_row(row) for row in mapping["rows"]],
            }
        )
        doc.insert(ignore_permissions=True)
        return

    doc = frappe.get_doc("Salesforce Field Mapping", existing_name)
    existing_rows = {_row_key(row) for row in doc.field_mappings or []}
    added = 0
    for row in mapping["rows"]:
        serialised = _serialise_row(row)
        key = _row_key(serialised)
        if key in existing_rows:
            continue
        doc.append("field_mappings", serialised)
        existing_rows.add(key)
        added += 1
    if added:
        doc.save(ignore_permissions=True)


def _required_salesforce_objects() -> set[str]:
    """Return SF objects that must have enabled mappings before sync."""
    return set(REQUIRED_DEFAULT_MAPPING_ROWS)


def _row_key(row) -> tuple[str, str]:
    sf_field = _row_value(row, "sf_field")
    sf_fields = _row_value(row, "sf_fields")
    frappe_field = _row_value(row, "frappe_field")
    sf_input = sf_field or sf_fields
    return (str(sf_input).strip().lower(), str(frappe_field).strip().lower())


def _row_value(row, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key) or ""
    return getattr(row, key, "") or ""


def _serialise_row(row: dict) -> dict:
    """Convert a DEFAULT_MAPPINGS row to a Salesforce Field Mapping Row dict.

    Handles the multi-input form (``sf_fields`` list → newline-separated
    Long Text) and applies the ``transform`` default of ``"none"``.
    """
    sf_fields = row.get("sf_fields")
    if isinstance(sf_fields, list):
        sf_fields_value = "\n".join(sf_fields)
    else:
        sf_fields_value = sf_fields or ""
    return {
        "sf_field": row.get("sf_field") or "",
        "sf_fields": sf_fields_value,
        "frappe_field": row["frappe_field"],
        "transform": row.get("transform") or "none",
    }


def _require_frappe() -> None:
    if frappe is None:
        raise RuntimeError("Frappe is required to manage Salesforce Field Mapping")
