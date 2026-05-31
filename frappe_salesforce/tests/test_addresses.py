"""Unit tests for the address helpers (no Frappe site required)."""

from frappe_salesforce.sync.addresses import (
    PREFIX_TO_TYPE,
    _extract_block,
    _has_any_value,
)


def test_extract_block_billing():
    rec = {
        "BillingStreet": "1 Main",
        "BillingCity": "London",
        "ShippingStreet": "2 Other",
    }
    block = _extract_block("Billing", rec)
    assert block == {
        "Street": "1 Main",
        "City": "London",
        "State": None,
        "PostalCode": None,
        "Country": None,
    }


def test_extract_block_unprefixed_for_lead():
    rec = {"Street": "1 Main", "City": "London"}
    block = _extract_block("", rec)
    assert block["Street"] == "1 Main"
    assert block["City"] == "London"
    assert block["Country"] is None


def test_has_any_value_detects_blanks():
    assert _has_any_value({"Street": "1 Main"}) is True
    assert _has_any_value({"Street": "", "City": None}) is False
    assert _has_any_value({}) is False


def test_prefix_to_type_covers_known_prefixes():
    assert PREFIX_TO_TYPE["Billing"] == "Billing"
    assert PREFIX_TO_TYPE["Shipping"] == "Shipping"
    assert PREFIX_TO_TYPE["Mailing"] == "Office"
    assert PREFIX_TO_TYPE["Other"] == "Other"
    assert PREFIX_TO_TYPE[""] == "Primary"
