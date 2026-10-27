"""Duplicate Salesforce Record Links: which one survives the dedupe.

Shape taken from staging: the 2026-05-14 overlapping runs left a blank
link (no Frappe record) next to the real one for the same Opportunity.
Importing the helper needs Frappe, so these are skipped in the no-site
lint run.
"""

import pytest

pytest.importorskip("frappe")

import frappe  # noqa: E402

from frappe_salesforce.setup import record_links  # noqa: E402


def _link(name, sf_id, frappe_name=None, status="Synced", synced=None):
    return frappe._dict(
        name=name,
        salesforce_object="Opportunity",
        salesforce_id=sf_id,
        frappe_doctype="CRM Deal",
        frappe_name=frappe_name,
        sync_status=status,
        last_synced_at=synced,
        modified=synced,
    )


@pytest.fixture
def db(monkeypatch):
    state = {"deleted": [], "existing": set(), "errors": []}
    monkeypatch.setattr(
        frappe.db, "exists", lambda dt, name: name in state["existing"], raising=False
    )
    monkeypatch.setattr(
        frappe.db,
        "delete",
        lambda dt, filters: state["deleted"].extend(filters["name"][1]),
        raising=False,
    )
    monkeypatch.setattr(frappe, "log_error", lambda **kw: state["errors"].append(kw))
    return state


def _rows(monkeypatch, rows):
    monkeypatch.setattr(frappe.db, "sql", lambda *a, **k: rows, raising=False)


def test_blank_duplicate_is_deleted_and_real_link_kept(monkeypatch, db):
    db["existing"] = {"CRM-DEAL-2026-01441"}
    _rows(
        monkeypatch,
        [
            _link("blank", "006D000000AAAAAIA1", synced="2026-05-14 13:31:00"),
            _link("real", "006D000000AAAAAIA1", "CRM-DEAL-2026-01441", synced="2026-05-14 13:33:38"),
        ],
    )
    assert record_links.delete_duplicate_links() == 1
    assert db["deleted"] == ["blank"]
    assert not db["errors"]


def test_existing_record_beats_newer_blank_link(monkeypatch, db):
    db["existing"] = {"CRM-DEAL-2026-01441"}
    _rows(
        monkeypatch,
        [
            _link("real", "006D000000AAAAAIA1", "CRM-DEAL-2026-01441", synced="2026-05-14"),
            _link("newer-blank", "006D000000AAAAAIA1", status="Failed", synced="2026-10-01"),
        ],
    )
    record_links.delete_duplicate_links()
    assert db["deleted"] == ["newer-blank"]


def test_link_to_a_different_live_record_is_reported(monkeypatch, db):
    db["existing"] = {"Contact A", "Contact B"}
    _rows(
        monkeypatch,
        [
            _link("a", "003D000000BBBBBIA1", "Contact A", synced="2026-05-14"),
            _link("b", "003D000000BBBBBIA1", "Contact B", synced="2026-06-01"),
        ],
    )
    record_links.delete_duplicate_links()
    assert db["deleted"] == ["a"]
    assert len(db["errors"]) == 1
    assert "Contact A" in db["errors"][0]["message"]
