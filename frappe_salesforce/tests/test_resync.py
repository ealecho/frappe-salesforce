"""``resync_opportunities`` against the API budget.

A full re-sync costs ~3 calls per deal, far more than one per-tick budget,
so it must renew its client before the budget trips and report a quota
stop instead of raising. Importing the API needs Frappe, so these are
skipped in the no-site lint run.
"""

import pytest

pytest.importorskip("frappe")

import frappe  # noqa: E402

from frappe_salesforce.api import sync as api  # noqa: E402
from frappe_salesforce.salesforce import client as client_module  # noqa: E402
from frappe_salesforce.salesforce.exceptions import SalesforceBudgetExceeded  # noqa: E402
from frappe_salesforce.sync import opportunities  # noqa: E402
from frappe_salesforce.tasks import incremental  # noqa: E402

PER_TICK = 20


class _BudgetedClient:
    """Counts calls and enforces ``PER_TICK`` like the real client."""

    created = 0

    def __init__(self):
        type(self).created += 1
        self.calls_this_tick = 0

    def spend(self, n=1):
        if self.calls_this_tick + n > PER_TICK:
            raise SalesforceBudgetExceeded(f"Per-tick budget of {PER_TICK} calls reached")
        self.calls_this_tick += n

    def query(self, soql):
        self.spend()
        ids = soql.split("IN (", 1)[1].rstrip(")").split(", ")
        return iter([{"Id": i.strip("'"), "SystemModstamp": "2026-06-29T07:40:00Z"} for i in ids])


class _FakeSyncer:
    def __init__(self, client, log):
        self.client = client
        self.processed = []

    def _soql_fields(self):
        return ["Name"]

    def _process_record(self, rec):
        self.client.spend(3)  # income years, payments, budget
        self.processed.append(rec["Id"])

    def _mark_link_failed(self, sf_id, e):
        pass


@pytest.fixture
def lock(monkeypatch):
    """The scheduled sync's lock, as the re-sync sees it."""
    state = {"held": False, "refreshed": 0}

    def acquire(timeout=120, poll=5):
        if state["held"]:
            return False
        state["held"] = True
        return True

    monkeypatch.setattr(incremental, "acquire_sync_lock_waiting", acquire)
    monkeypatch.setattr(incremental, "_release_sync_lock", lambda: state.update(held=False))
    monkeypatch.setattr(
        incremental, "refresh_sync_lock", lambda: state.update(refreshed=state["refreshed"] + 1)
    )
    return state


@pytest.fixture
def site(monkeypatch, lock):
    _BudgetedClient.created = 0
    links = [
        frappe._dict(salesforce_id=f"006{i:015d}", frappe_name=f"CRM-DEAL-{i}")
        for i in range(30)
    ]
    monkeypatch.setattr(frappe, "only_for", lambda *a, **k: None)
    monkeypatch.setattr(frappe, "get_all", lambda *a, **k: links)
    monkeypatch.setattr(frappe, "log_error", lambda **kw: None)
    monkeypatch.setattr(frappe.db, "exists", lambda *a, **k: True, raising=False)
    monkeypatch.setattr(frappe.db, "commit", lambda: None, raising=False)
    monkeypatch.setattr(frappe.db, "rollback", lambda **k: None, raising=False)
    monkeypatch.setattr(
        frappe.db, "get_single_value", lambda dt, f: PER_TICK, raising=False
    )
    monkeypatch.setattr(client_module, "SalesforceClient", _BudgetedClient)
    monkeypatch.setattr(opportunities, "OpportunitySyncer", _FakeSyncer)
    return links


def test_long_resync_renews_client_instead_of_stopping(site):
    result = api.resync_opportunities()
    # 30 deals x 3 calls + 1 query = 91 calls, so it needed several clients.
    assert result["stopped"] is None
    assert result["deals_processed"] == 30
    assert _BudgetedClient.created > 1


def test_preflight_stop_is_reported_not_raised(site, monkeypatch):
    def preflight_trips():
        raise SalesforceBudgetExceeded("Preflight: SF usage at 92%")

    monkeypatch.setattr(client_module, "SalesforceClient", preflight_trips)
    result = api.resync_opportunities()
    assert result["stopped"] == "Preflight: SF usage at 92%"
    assert result["deals_processed"] == 0


def test_resync_holds_the_sync_lock_throughout(site, lock, monkeypatch):
    # Run beside a scheduled tick, both wrote Salesforce Settings on every
    # API call and the tick undid the re-sync's deal saves (2026-10-23).
    held_while_processing = []

    def process(self, rec):
        held_while_processing.append(lock["held"])

    monkeypatch.setattr(_FakeSyncer, "_process_record", process)
    result = api.resync_opportunities()
    assert result["deals_processed"] == 30
    assert all(held_while_processing)
    assert lock["refreshed"] >= 1
    assert not lock["held"]


def test_resync_stops_before_any_call_when_a_tick_holds_the_lock(site, lock):
    lock["held"] = True
    result = api.resync_opportunities()
    assert result["ok"] is False
    assert result["deals_processed"] == 0
    assert _BudgetedClient.created == 0
    assert lock["held"]  # not ours to release


def test_lock_wait_gives_up_after_timeout(monkeypatch):
    clock = iter(range(0, 1000, 5))
    monkeypatch.setattr(incremental, "_acquire_sync_lock", lambda: False)
    monkeypatch.setattr(incremental.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(incremental.time, "sleep", lambda s: None)
    assert incremental.acquire_sync_lock_waiting(timeout=20) is False


def test_lock_wait_takes_the_lock_once_the_tick_ends(monkeypatch):
    attempts = iter([False, False, True])
    monkeypatch.setattr(incremental, "_acquire_sync_lock", lambda: next(attempts))
    monkeypatch.setattr(incremental.time, "sleep", lambda s: None)
    assert incremental.acquire_sync_lock_waiting(timeout=120) is True
