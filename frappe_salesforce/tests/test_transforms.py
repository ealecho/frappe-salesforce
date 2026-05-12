"""Unit tests for scalar / multi-input transforms.

Tests in this file deliberately avoid Frappe DB calls so they run under
plain pytest without a site context. Lookup transforms (``industry_link``,
``contact_lookup``, ``user_lookup`` …) are exercised in integration tests
that run via ``bench --site … run-tests``.
"""

from __future__ import annotations

from frappe_salesforce.sync.transforms import (
    DEAL_STAGE_MAP,
    address_block,
    email_table,
    employee_bucket,
    html_strip,
    map_deal_lost_reason,
    map_deal_stage,
    map_lead_status,
    map_task_priority,
    map_task_status,
    phone_table,
    to_bool,
    to_date,
)


# ----------------------------------------------------------------------
# Scalar transforms
# ----------------------------------------------------------------------
def test_to_bool_truthy_strings():
    assert to_bool("true") == 1
    assert to_bool("True") == 1
    assert to_bool("1") == 1
    assert to_bool("yes") == 1


def test_to_bool_falsy():
    assert to_bool(None) == 0
    assert to_bool("false") == 0
    assert to_bool("") == 0
    assert to_bool(0) == 0


def test_to_date_handles_none():
    assert to_date(None) is None
    assert to_date("") is None


def test_html_strip_removes_tags():
    assert html_strip("<p>Hello <b>world</b></p>") == "Hello world"


def test_html_strip_unescapes_entities():
    assert html_strip("Tom &amp; Jerry") == "Tom & Jerry"


# ----------------------------------------------------------------------
# Picklist mappers
# ----------------------------------------------------------------------
def test_map_deal_stage_known():
    assert map_deal_stage("Closed Won") == "Won"
    assert map_deal_stage("Closed Lost") == "Lost"


def test_map_deal_stage_passthrough_unknown():
    assert map_deal_stage("Custom Stage") == "Custom Stage"


def test_map_deal_stage_none():
    assert map_deal_stage(None) is None


def test_all_standard_sf_stages_covered():
    for stage in [
        "Prospecting",
        "Qualification",
        "Needs Analysis",
        "Proposal/Price Quote",
        "Negotiation/Review",
        "Closed Won",
        "Closed Lost",
    ]:
        assert stage in DEAL_STAGE_MAP


def test_map_deal_lost_reason_returns_none_for_won():
    assert map_deal_lost_reason("Won") is None
    assert map_deal_lost_reason("Closed Won") is None


def test_map_deal_lost_reason_known():
    assert map_deal_lost_reason("Lost") == "Lost"
    assert map_deal_lost_reason("Withdrawn") == "Withdrawn"


def test_map_lead_status_translates_known():
    assert map_lead_status("Open - Not Contacted") == "New"
    assert map_lead_status("Closed - Converted") == "Converted"


def test_map_task_status_defaults_to_todo():
    assert map_task_status(None) == "Todo"
    assert map_task_status("Garbage") == "Todo"


def test_map_task_priority_defaults_to_medium():
    assert map_task_priority(None) == "Medium"
    assert map_task_priority("Normal") == "Medium"


# ----------------------------------------------------------------------
# Bucketing
# ----------------------------------------------------------------------
def test_employee_bucket_boundaries():
    assert employee_bucket(None) is None
    assert employee_bucket("") is None
    assert employee_bucket(0) is None
    assert employee_bucket(1) == "1-10"
    assert employee_bucket(10) == "1-10"
    assert employee_bucket(11) == "11-50"
    assert employee_bucket(50) == "11-50"
    assert employee_bucket(51) == "51-200"
    assert employee_bucket(200) == "51-200"
    assert employee_bucket(201) == "201-500"
    assert employee_bucket(500) == "201-500"
    assert employee_bucket(501) == "501-1000"
    assert employee_bucket(1000) == "501-1000"
    assert employee_bucket(1001) == "1000+"
    assert employee_bucket(50_000) == "1000+"


def test_employee_bucket_handles_non_numeric():
    assert employee_bucket("not-a-number") is None
    assert employee_bucket("42") == "11-50"  # SF int often arrives as string


# ----------------------------------------------------------------------
# Multi-input: address
# ----------------------------------------------------------------------
def test_address_block_billing():
    block = address_block(
        {
            "BillingStreet": "1 Main St",
            "BillingCity": "London",
            "BillingState": "Greater London",
            "BillingPostalCode": "EC1A 1AA",
            "BillingCountry": "United Kingdom",
        }
    )
    assert block == {
        "address_line1": "1 Main St",
        "city": "London",
        "state": "Greater London",
        "pincode": "EC1A 1AA",
        "country": "United Kingdom",
    }


def test_address_block_unprefixed():
    """Lead has flat ``Street/City/...`` (no prefix)."""
    block = address_block(
        {"Street": "1 Main", "City": "London", "Country": "UK"}
    )
    assert block["address_line1"] == "1 Main"
    assert block["city"] == "London"
    assert block["country"] == "UK"
    assert block["state"] is None
    assert block["pincode"] is None


def test_address_block_empty():
    assert address_block({}) is None
    assert address_block({"BillingStreet": None, "BillingCity": ""}) is None


def test_address_block_partial():
    """Only city present → still produces a block."""
    block = address_block({"BillingCity": "London"})
    assert block == {
        "address_line1": None,
        "city": "London",
        "state": None,
        "pincode": None,
        "country": None,
    }


def test_address_block_rejects_non_dict():
    assert address_block(None) is None
    assert address_block("not a dict") is None


# ----------------------------------------------------------------------
# Multi-input: emails
# ----------------------------------------------------------------------
def test_email_table_marks_first_primary():
    rows = email_table(
        {
            "Email": "a@example.com",
            "npe01__WorkEmail__c": "work@example.com",
            "npe01__HomeEmail__c": "home@example.com",
        }
    )
    assert rows == [
        {"email_id": "a@example.com", "is_primary": 1},
        {"email_id": "work@example.com", "is_primary": 0},
        {"email_id": "home@example.com", "is_primary": 0},
    ]


def test_email_table_skips_empty():
    rows = email_table(
        {
            "Email": "",
            "npe01__HomeEmail__c": None,
            "npe01__WorkEmail__c": "work@example.com",
        }
    )
    assert rows == [{"email_id": "work@example.com", "is_primary": 1}]


def test_email_table_dedupes_case_insensitive():
    rows = email_table(
        {
            "Email": "Foo@EXAMPLE.com",
            "npe01__HomeEmail__c": "foo@example.com",
        }
    )
    assert len(rows) == 1
    assert rows[0]["email_id"] == "Foo@EXAMPLE.com"


def test_email_table_returns_none_when_all_empty():
    assert email_table({"Email": "", "npe01__HomeEmail__c": None}) is None


# ----------------------------------------------------------------------
# Multi-input: phones
# ----------------------------------------------------------------------
def test_phone_table_flags_primary_phone_and_mobile():
    rows = phone_table(
        {
            "Phone": "020 1234 5678",
            "MobilePhone": "+44 7700 900000",
            "HomePhone": "020 9999 0000",
        }
    )
    assert rows[0] == {"phone": "020 1234 5678", "is_primary_phone": 1}
    assert rows[1] == {"phone": "+44 7700 900000", "is_primary_mobile_no": 1}
    assert rows[2] == {"phone": "020 9999 0000"}


def test_phone_table_skips_blank_and_dedupes_exact_string():
    rows = phone_table(
        {
            "Phone": "020 1234 5678",
            "MobilePhone": "020 1234 5678",  # duplicate
            "HomePhone": "",
        }
    )
    assert len(rows) == 1


def test_phone_table_returns_none_when_all_empty():
    assert phone_table({"Phone": None, "MobilePhone": ""}) is None
