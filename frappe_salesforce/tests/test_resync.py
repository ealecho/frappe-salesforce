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
def site(monkeypatch):
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
