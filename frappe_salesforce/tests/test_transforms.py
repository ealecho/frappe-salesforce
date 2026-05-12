"""Unit tests for scalar transforms that don't require a Frappe site."""

from frappe_salesforce.sync.transforms import (
    DEAL_STAGE_MAP,
    LEAD_STATUS_MAP,
    TASK_PRIORITY_MAP,
    TASK_STATUS_MAP,
    html_strip,
    map_deal_lost_reason,
    map_deal_stage,
    map_lead_status,
    map_task_priority,
    map_task_status,
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


def test_map_lead_status_known():
    assert map_lead_status("Open - Not Contacted") == "New"
    assert map_lead_status("Closed - Converted") == "Converted"


def test_map_lead_status_passthrough_and_none():
    assert map_lead_status("Some Custom Status") == "Some Custom Status"
    assert map_lead_status(None) is None
    assert map_lead_status("") is None


def test_lead_status_map_covers_standard_sf_statuses():
    for status in [
        "Open - Not Contacted",
        "Working - Contacted",
        "Closed - Converted",
        "Closed - Not Converted",
    ]:
        assert status in LEAD_STATUS_MAP


def test_map_deal_lost_reason_only_for_lost_stages():
    assert map_deal_lost_reason("Lost") == "Lost"
    assert map_deal_lost_reason("Withdrawn") == "Withdrawn"
    assert map_deal_lost_reason("Closed Lost") == "Lost"
    # Non-lost stages must return None so _upsert_doc strips the value.
    assert map_deal_lost_reason("Prospecting") is None
    assert map_deal_lost_reason("Won") is None
    assert map_deal_lost_reason(None) is None


def test_map_task_status_defaults_to_todo():
    assert map_task_status(None) == "Todo"
    assert map_task_status("") == "Todo"
    assert map_task_status("Unknown Picklist Value") == "Todo"


def test_map_task_status_known():
    assert map_task_status("Not Started") == "Todo"
    assert map_task_status("In Progress") == "In Progress"
    assert map_task_status("Completed") == "Done"
    assert map_task_status("Deferred") == "Backlog"


def test_task_status_map_covers_standard_sf_values():
    for status in ["Not Started", "In Progress", "Completed", "Deferred"]:
        assert status in TASK_STATUS_MAP


def test_map_task_priority_defaults_to_medium():
    assert map_task_priority(None) == "Medium"
    assert map_task_priority("") == "Medium"
    assert map_task_priority("Unknown") == "Medium"


def test_map_task_priority_known():
    assert map_task_priority("Normal") == "Medium"
    assert map_task_priority("High") == "High"
    assert map_task_priority("Low") == "Low"


def test_task_priority_map_covers_standard_sf_values():
    for prio in ["Normal", "High", "Low"]:
        assert prio in TASK_PRIORITY_MAP
