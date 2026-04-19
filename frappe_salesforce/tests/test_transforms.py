"""Unit tests for scalar transforms that don't require a Frappe site."""

from frappe_salesforce.sync.transforms import (
    DEAL_STAGE_MAP,
    html_strip,
    map_deal_stage,
    to_bool,
    to_date,
)


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
