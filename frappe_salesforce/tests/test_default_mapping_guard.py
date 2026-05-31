"""Tests for pre-sync Salesforce Field Mapping readiness checks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from frappe_salesforce.setup import default_mappings as dm


class _FakeDoc:
    def __init__(self, payload: dict, db):
        self.name = payload.get("name") or f"Mapping-{payload['salesforce_object']}"
        self.salesforce_object = payload["salesforce_object"]
        self.frappe_doctype = payload["frappe_doctype"]
        self.enabled = payload.get("enabled", 1)
        self.field_mappings = [
            SimpleNamespace(**row) for row in payload.get("field_mappings", [])
        ]
        self._db = db

    def append(self, fieldname: str, row: dict) -> None:
        assert fieldname == "field_mappings"
        self.field_mappings.append(SimpleNamespace(**row))

    def insert(self, ignore_permissions: bool = False) -> None:
        self._db.save(self)

    def save(self, ignore_permissions: bool = False) -> None:
        self._db.save(self)


class _FakeDB:
    def __init__(self):
        self.docs_by_name: dict[str, _FakeDoc] = {}
        self.names_by_object: dict[str, str] = {}

    def save(self, doc: _FakeDoc) -> None:
        self.docs_by_name[doc.name] = doc
        self.names_by_object[doc.salesforce_object] = doc.name

    def exists(self, doctype: str, filters: dict) -> bool:
        return bool(self.get_value(doctype, filters, "name"))

    def get_value(self, doctype: str, filters: dict, fieldname: str):
        assert doctype == "Salesforce Field Mapping"
        name = self.names_by_object.get(filters.get("salesforce_object"))
        if not name:
            return None
        doc = self.docs_by_name[name]
        if "enabled" in filters and doc.enabled != filters["enabled"]:
            return None
        return doc.name if fieldname == "name" else getattr(doc, fieldname)


class _FakeFrappe:
    def __init__(self):
        self.db = _FakeDB()

    def get_doc(self, *args):
        if len(args) == 1 and isinstance(args[0], dict):
            return _FakeDoc(args[0], self.db)
        doctype, name = args
        assert doctype == "Salesforce Field Mapping"
        return self.db.docs_by_name[name]


@pytest.fixture
def fake_frappe(monkeypatch):
    fake = _FakeFrappe()
    monkeypatch.setattr(dm, "frappe", fake)
    return fake


def _row_pairs(doc):
    return {
        (row.sf_field, row.frappe_field)
        for row in doc.field_mappings
        if row.sf_field
    }


def test_ensure_default_field_mappings_seeds_empty_site(fake_frappe):
    dm.ensure_default_field_mappings()

    assert set(fake_frappe.db.names_by_object) == {
        mapping["salesforce_object"] for mapping in dm.DEFAULT_MAPPINGS
    }
    task = fake_frappe.db.docs_by_name[fake_frappe.db.names_by_object["Task"]]
    assert ("Subject", "title") in _row_pairs(task)


def test_ensure_default_field_mappings_backfills_missing_rows(fake_frappe):
    task = _FakeDoc(
        {
            "salesforce_object": "Task",
            "frappe_doctype": "CRM Task",
            "enabled": 1,
            "field_mappings": [
                {
                    "sf_field": "Custom__c",
                    "sf_fields": "",
                    "frappe_field": "custom_sf_custom",
                    "transform": "none",
                }
            ],
        },
        fake_frappe.db,
    )
    task.insert(ignore_permissions=True)

    dm.ensure_default_field_mappings()

    task = fake_frappe.db.docs_by_name[fake_frappe.db.names_by_object["Task"]]
    assert ("Custom__c", "custom_sf_custom") in _row_pairs(task)
    assert ("Subject", "title") in _row_pairs(task)


def test_validate_required_field_mappings_rejects_disabled_mapping(fake_frappe):
    dm.ensure_default_field_mappings()
    task = fake_frappe.db.docs_by_name[fake_frappe.db.names_by_object["Task"]]
    task.enabled = 0

    with pytest.raises(dm.SalesforceMappingSetupError) as exc:
        dm.validate_required_field_mappings()

    assert "Task: enabled Salesforce Field Mapping" in str(exc.value)
