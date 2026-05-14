"""Unit tests for scalar / multi-input transforms.

Tests in this file deliberately avoid Frappe DB calls so they run under
plain pytest without a site context. Lookup transforms (``industry_link``,
``contact_lookup``, ``user_lookup`` …) are exercised in integration tests
that run via ``bench --site … run-tests``.
"""

from __future__ import annotations

import frappe_salesforce.sync.transforms as tfm
from frappe_salesforce.sync.transforms import (
    DEAL_STAGE_MAP,
    address_block,
    deal_lost_reason_link,
    deal_stage_link,
    email_table,
    employee_bucket,
    html_strip,
    lead_status_link,
    map_deal_lost_reason,
    map_deal_stage,
    map_lead_status,
    map_task_priority,
    map_task_status,
    phone_table,
    task_priority_link,
    task_status_link,
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
# Link-safe wrappers (auto-create parent rows)
# ----------------------------------------------------------------------
class _FakeDb:
    """Stand-in for ``frappe.db`` that pretends every DocType exists but
    no parent rows do. Used to drive ``_ensure_link`` through the
    insertion code path without touching MariaDB.
    """

    def __init__(self):
        self.existing: set[tuple[str, str]] = set()

    def exists(self, doctype, name=None):
        if name is None:
            # frappe.db.exists("DocType", "Foo") shape
            return True
        return (doctype, str(name)) in self.existing


class _FakeDoc:
    def __init__(self, payload):
        self.payload = payload

    def insert(self, **kw):  # noqa: D401, ARG002
        # Simulate successful insert; record nothing — _ensure_link only
        # cares that no exception is raised.
        return self


def _patch_link_internals(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(tfm.frappe, "db", fake_db)
    monkeypatch.setattr(tfm.frappe, "get_doc", lambda payload: _FakeDoc(payload))
    return fake_db


def test_lead_status_link_passthrough_unknown(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert lead_status_link("Custom New Status") == "Custom New Status"


def test_lead_status_link_translates_known(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert lead_status_link("Open - Not Contacted") == "New"


def test_lead_status_link_none(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert lead_status_link(None) is None
    assert lead_status_link("") is None


def test_deal_stage_link_passthrough_unknown(monkeypatch):
    _patch_link_internals(monkeypatch)
    # The original failing case: PEAS stage that maps via DEAL_STAGE_MAP →
    # "Proposal/Quotation", which must resolve through link upsert.
    assert deal_stage_link("Warm proposal to existing funder") == "Proposal/Quotation"


def test_deal_stage_link_unknown_passthrough(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert deal_stage_link("Brand New Custom Stage") == "Brand New Custom Stage"


def test_deal_lost_reason_link_returns_none_for_won(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert deal_lost_reason_link("Won") is None


def test_deal_lost_reason_link_known(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert deal_lost_reason_link("Withdrawn") == "Withdrawn"


def test_task_status_link_defaults_to_todo(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert task_status_link(None) == "Todo"
    assert task_status_link("Garbage") == "Todo"


def test_task_priority_link_defaults_to_medium(monkeypatch):
    _patch_link_internals(monkeypatch)
    assert task_priority_link(None) == "Medium"
    assert task_priority_link("Normal") == "Medium"


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
