"""Test BaseSyncer's FLS field filter (Strategy B).

Verifies that ``_filter_fls_blocked`` drops fields not returned by the
SF describe response, while always preserving the bookkeeping fields
(``Id``, ``SystemModstamp``). Failure modes (describe errored, empty
set returned) fail open — the original field list is returned and the
sync attempts SOQL anyway.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _make_syncer():
    from frappe_salesforce.sync import base

    syncer = base.BaseSyncer.__new__(base.BaseSyncer)
    syncer.salesforce_object = "Contact"
    syncer.client = SimpleNamespace(accessible_fields=lambda _: set())
    return syncer


def test_filter_drops_unknown_fields_keeps_required():
    syncer = _make_syncer()
    syncer.client = SimpleNamespace(
        accessible_fields=lambda _: {"FirstName", "Email", "Phone"}
    )
    # ``RecordTypeId`` is not accessible; ``Id`` is required.
    out = syncer._filter_fls_blocked(
        ["FirstName", "RecordTypeId", "Email", "Id"],
        always_required={"Id", "SystemModstamp"},
    )
    assert "RecordTypeId" not in out
    assert "FirstName" in out
    assert "Email" in out
    assert "Id" in out


def test_filter_keeps_required_even_when_describe_omits_them():
    syncer = _make_syncer()
    syncer.client = SimpleNamespace(
        accessible_fields=lambda _: {"FirstName"},  # describe doesn't list Id
    )
    out = syncer._filter_fls_blocked(
        ["FirstName", "Id", "SystemModstamp"],
        always_required={"Id", "SystemModstamp"},
    )
    assert "Id" in out
    assert "SystemModstamp" in out
    assert "FirstName" in out


def test_filter_fails_open_on_empty_describe():
    """Empty accessible_fields means describe failed; pass everything
    through and let the SOQL 400 surface naturally."""
    syncer = _make_syncer()
    syncer.client = SimpleNamespace(accessible_fields=lambda _: set())
    out = syncer._filter_fls_blocked(
        ["FirstName", "RecordTypeId"],
        always_required={"Id"},
    )
    assert out == ["FirstName", "RecordTypeId"]


def test_filter_fails_open_on_describe_exception(monkeypatch):
    """If accessible_fields() itself raises, return the input unchanged."""
    from frappe_salesforce.sync import base

    syncer = _make_syncer()

    def boom(_):
        raise RuntimeError("describe blew up")

    syncer.client = SimpleNamespace(accessible_fields=boom)
    out = syncer._filter_fls_blocked(
        ["FirstName", "RecordTypeId"], always_required={"Id"}
    )
    assert out == ["FirstName", "RecordTypeId"]


def test_filter_preserves_input_order():
    syncer = _make_syncer()
    syncer.client = SimpleNamespace(
        accessible_fields=lambda _: {"A", "B", "C", "D"}
    )
    out = syncer._filter_fls_blocked(
        ["D", "B", "X", "A", "C"], always_required={"Id"}
    )
    assert out == ["D", "B", "A", "C"]
