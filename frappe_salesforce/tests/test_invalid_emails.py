"""An invalid email address must not keep a record out of CRM.

Regression guard for 2026-10-27: Frappe refused addresses like
``joe..philp.hs@live.co.uk`` and the whole Contact / Lead failed. The
address is now dropped (and logged) and the record saves without it.
"""

import pytest

pytest.importorskip("frappe")

import frappe  # noqa: E402

from frappe_salesforce.sync.base import BaseSyncer  # noqa: E402


class _Meta:
    def get_field(self, fieldname):
        return frappe._dict(options="Email") if fieldname == "email" else frappe._dict(options="")


@pytest.fixture
def syncer(monkeypatch):
    s = BaseSyncer.__new__(BaseSyncer)
    s.salesforce_object = "Lead"
    s.frappe_doctype = "CRM Lead"
    monkeypatch.setattr(frappe, "get_meta", lambda doctype: _Meta())
    return s


@pytest.fixture
def logged(monkeypatch):
    out = []
    monkeypatch.setattr(frappe, "log_error", lambda **kw: out.append(kw))
    return out


def test_invalid_address_in_an_email_field_is_dropped_and_logged(syncer, logged):
    assert syncer._drop_invalid_emails("email", "joe..philp.hs@live.co.uk", "00QA") is None
    assert len(logged) == 1
    assert "00QA" in logged[0]["title"]


def test_valid_address_is_kept(syncer, logged):
    assert syncer._drop_invalid_emails("email", "joe.philp@live.co.uk", "00QA") == "joe.philp@live.co.uk"
    assert not logged


def test_other_text_fields_are_left_alone(syncer, logged):
    # e.g. custom_sf_work_email is plain Data: Frappe doesn't validate it.
    assert syncer._drop_invalid_emails("custom_sf_work_email", "kiingigut.@yahoo.com") == "kiingigut.@yahoo.com"
    assert not logged


def test_invalid_rows_leave_the_email_table_and_primary_moves(syncer, logged):
    rows = [
        {"email_id": "kiingigut.@yahoo.com", "is_primary": 1},
        {"email_id": "kiingi@yahoo.com", "is_primary": 0},
    ]
    assert syncer._drop_invalid_emails("email_ids", rows, "003A") == [
        {"email_id": "kiingi@yahoo.com", "is_primary": 1}
    ]
    assert len(logged) == 1


def test_email_table_with_only_invalid_addresses_becomes_empty(syncer, logged):
    rows = [{"email_id": "êinfo@pacesportsmanagement.com", "is_primary": 1}]
    assert syncer._drop_invalid_emails("email_ids", rows, "003A") is None


def test_other_child_tables_are_left_alone(syncer, logged):
    rows = [{"phone": "+44 1234", "is_primary_phone": 1}]
    assert syncer._drop_invalid_emails("phone_nos", rows) == rows
