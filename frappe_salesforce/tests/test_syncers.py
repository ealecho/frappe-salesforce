"""Tests that syncer registry is well-formed."""

from frappe_salesforce.sync.registry import SYNCERS


def test_registry_ordering_is_monotonic():
    orders = [s.order_in_sync for s in SYNCERS]
    assert orders == sorted(orders)


def test_user_syncer_runs_first():
    assert SYNCERS[0].salesforce_object == "User"


def test_all_syncers_declare_sf_object():
    for s in SYNCERS:
        assert s.salesforce_object
        assert s.frappe_doctype


def test_all_syncers_have_unique_hwm_fields():
    hwms = [s.high_water_field for s in SYNCERS]
    assert len(hwms) == len(set(hwms))
