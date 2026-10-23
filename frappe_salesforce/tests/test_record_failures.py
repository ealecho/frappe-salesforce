"""A failed record must not be half-saved, and a quota stop must end the run.

Regression guard for 2026-06-29: the per-tick budget ran out on a grid query
inside ``after_upsert``, the error was swallowed, and every remaining deal
was saved and marked Synced without its income years / payments. The HWM
then moved past them, so they were never retried. Importing the syncers
needs Frappe, so these are skipped in the no-site lint run.
"""

import pytest

pytest.importorskip("frappe")

import frappe  # noqa: E402

from frappe_salesforce.salesforce.exceptions import SalesforceBudgetExceeded  # noqa: E402
from frappe_salesforce.sync import base  # noqa: E402
from frappe_salesforce.sync.base import BaseSyncer  # noqa: E402
from frappe_salesforce.sync.opportunities import OpportunitySyncer  # noqa: E402


class _FakeClient:
    calls_this_tick = 0

    def __init__(self, records):
        self.records = records

    def query(self, soql):
        return iter(self.records)


class _FakeLink(frappe._dict):
    def save(self, **kwargs):
        self.saved = True


def _syncer(cls, monkeypatch, records=()):
    """A syncer with no DB-backed state: __init__ reads settings + mapping."""
    syncer = cls.__new__(cls)
    syncer.client = _FakeClient(list(records))
    syncer.log = frappe._dict()
    syncer.mapping = None
    monkeypatch.setattr(syncer, "_get_or_create_link", lambda sf_id: _FakeLink())
    monkeypatch.setattr(syncer, "_upsert_doc", lambda link, values, sf_id: object())
    return syncer


def _rec(sf_id, modstamp):
    return {"Id": sf_id, "SystemModstamp": modstamp}


@pytest.fixture
def errors(monkeypatch):
    logged = []
    monkeypatch.setattr(frappe, "log_error", lambda **kw: logged.append(kw))
    return logged


def _raise(exc):
    def fn(*args, **kwargs):
        raise exc

    return fn


def test_budget_error_in_after_upsert_always_propagates(monkeypatch, errors):
    syncer = _syncer(BaseSyncer, monkeypatch)
    monkeypatch.setattr(syncer, "after_upsert", _raise(SalesforceBudgetExceeded("tick")))
    with pytest.raises(SalesforceBudgetExceeded):
        syncer._process_record(_rec("006A", "2026-06-29T07:40:00Z"))


def test_optional_after_upsert_failure_is_logged_not_raised(monkeypatch, errors):
    syncer = _syncer(BaseSyncer, monkeypatch)
    monkeypatch.setattr(syncer, "after_upsert", _raise(ValueError("address")))
    syncer._process_record(_rec("001A", "2026-06-29T07:40:00Z"))
    assert len(errors) == 1


def test_opportunity_grid_failure_fails_the_record(monkeypatch, errors):
    assert OpportunitySyncer.after_upsert_required
    syncer = _syncer(OpportunitySyncer, monkeypatch)
    monkeypatch.setattr(syncer, "after_upsert", _raise(ValueError("grid save")))
    with pytest.raises(ValueError):
        syncer._process_record(_rec("006A", "2026-06-29T07:40:00Z"))


def _run_setup(monkeypatch, syncer):
    events = []
    monkeypatch.setattr(base, "build_incremental_query", lambda **kw: "SOQL")
    monkeypatch.setattr(syncer, "_soql_fields", lambda: [])
    monkeypatch.setattr(syncer, "_get_high_water_mark", lambda: "2026-06-01 00:00:00")
    monkeypatch.setattr(syncer, "_set_high_water_mark", lambda v: events.append(("hwm", str(v))))
    monkeypatch.setattr(syncer, "_mark_link_failed", lambda sf_id, e: events.append(("failed", sf_id)))
    monkeypatch.setattr(frappe.db, "savepoint", lambda name: events.append(("savepoint", name)))
    monkeypatch.setattr(base, "_rollback_record", lambda: events.append(("rollback",)))
    monkeypatch.setattr(frappe.db, "commit", lambda: None)
    return events


def test_budget_stop_rolls_back_record_and_keeps_hwm_on_last_good(monkeypatch, errors):
    records = [
        _rec("006A", "2026-06-29T07:40:00Z"),
        _rec("006B", "2026-06-29T07:41:00Z"),
        _rec("006C", "2026-06-29T07:42:00Z"),
    ]
    syncer = _syncer(BaseSyncer, monkeypatch, records)
    events = _run_setup(monkeypatch, syncer)
    seen = []

    def process(rec):
        seen.append(rec["Id"])
        if rec["Id"] == "006B":
            raise SalesforceBudgetExceeded("per-tick budget")

    monkeypatch.setattr(syncer, "_process_record", process)
    with pytest.raises(SalesforceBudgetExceeded):
        syncer.run()

    assert seen == ["006A", "006B"]  # 006C never touched
    assert ("rollback",) in events
    assert events[-1] == ("hwm", "2026-06-29 07:40:00")  # still on 006A
    assert not any(e[0] == "failed" for e in events)  # a quota stop isn't a bad record


def test_failed_record_is_rolled_back_flagged_and_run_continues(monkeypatch, errors):
    records = [
        _rec("006A", "2026-06-29T07:40:00Z"),
        _rec("006B", "2026-06-29T07:41:00Z"),
    ]
    syncer = _syncer(BaseSyncer, monkeypatch, records)
    events = _run_setup(monkeypatch, syncer)

    def process(rec):
        if rec["Id"] == "006A":
            raise ValueError("bad record")

    monkeypatch.setattr(syncer, "_process_record", process)
    syncer.run()

    assert syncer.log.failed == 1
    assert syncer.log.fetched == 1
    # Rolled back before the error was logged and the link flagged.
    assert events.index(("rollback",)) < events.index(("failed", "006A"))
    assert len(errors) == 1
