"""Unit tests for site-free helpers in ``sync.addresses``."""

from frappe_salesforce.sync.addresses import ADDRESS_TYPE_MAP, extract_block


def test_extract_block_returns_none_for_empty():
    assert extract_block({}, "Billing") is None
    assert extract_block({"BillingCity": ""}, "Billing") is None


def test_extract_block_lowercases_and_strips():
    rec = {
        "BillingStreet": "  221b Baker St  ",
        "BillingCity": "London",
        "BillingState": None,
        "BillingPostalCode": "NW1 6XE",
        "BillingCountry": "GB",
        "OtherCity": "ignored",
    }
    out = extract_block(rec, "Billing")
    assert out == {
        "street": "221b Baker St",
        "city": "London",
        "postalcode": "NW1 6XE",
        "country": "GB",
    }


def test_extract_block_independent_of_other_prefixes():
    rec = {"ShippingCity": "Paris", "BillingCity": "Berlin"}
    assert extract_block(rec, "Shipping") == {"city": "Paris"}
    assert extract_block(rec, "Billing") == {"city": "Berlin"}


def test_address_type_map_contains_all_sf_prefixes():
    for prefix in ("Billing", "Shipping", "Mailing", "Other"):
        assert prefix in ADDRESS_TYPE_MAP
