"""Writing the observed API usage to Salesforce Settings.

Every API call writes it, inside the caller's transaction. A deadlock there
rolls that whole transaction back, so it must reach the caller; any other
write failure is still only logged.
"""

import pytest

pytest.importorskip("frappe")

import frappe  # noqa: E402

from frappe_salesforce.salesforce.client import SalesforceClient  # noqa: E402


class _Resp:
    headers = {"Sforce-Limit-Info": "api-usage=1200/113000"}


def _client():
    client = SalesforceClient.__new__(SalesforceClient)
    client._rate_limit_info = None
    return client


def test_usage_is_one_write_without_a_modified_bump(monkeypatch):
    calls = []
    monkeypatch.setattr(
        frappe.db, "set_single_value", lambda *a, **kw: calls.append((a, kw)), raising=False
    )
    _client()._record_rate_limit(_Resp())
    assert len(calls) == 1
    (doctype, values), kwargs = calls[0]
    assert doctype == "Salesforce Settings"
    assert values["last_api_usage_used"] == 1200
    assert values["last_api_usage_limit"] == 113000
    assert kwargs == {"update_modified": False}


def test_deadlock_writing_usage_reaches_the_caller(monkeypatch):
    def deadlock(*a, **kw):
        raise frappe.QueryDeadlockError("(1213, 'Deadlock found')")

    monkeypatch.setattr(frappe.db, "set_single_value", deadlock, raising=False)
    with pytest.raises(frappe.QueryDeadlockError):
        _client()._record_rate_limit(_Resp())


def test_other_usage_write_failures_are_only_logged(monkeypatch):
    def timeout(*a, **kw):
        raise frappe.QueryTimeoutError("(1205, 'Lock wait timeout exceeded')")

    logged = []
    monkeypatch.setattr(frappe.db, "set_single_value", timeout, raising=False)
    monkeypatch.setattr(frappe, "log_error", lambda **kw: logged.append(kw))
    _client()._record_rate_limit(_Resp())
    assert len(logged) == 1
