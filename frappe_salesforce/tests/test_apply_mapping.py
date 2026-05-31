"""Test BaseSyncer._apply_mapping multi-input handling without a Frappe site.

Verifies that:
* Scalar mapping rows still work unchanged.
* Multi-input rows feed transforms a ``dict[str, Any]`` of SF fields.
* ``sf_fields`` value is parsed regardless of whitespace / blank lines.
* ``_split_sf_fields`` correctly trims and skips empty lines.
"""

from __future__ import annotations

from types import SimpleNamespace

from frappe_salesforce.sync.base import _split_sf_fields


def _row(**kw):
    """Build a fake mapping row with all fields the syncer reads."""
    return SimpleNamespace(
        sf_field=kw.get("sf_field", ""),
        sf_fields=kw.get("sf_fields", ""),
        frappe_field=kw["frappe_field"],
        transform=kw.get("transform", "none"),
        default_value=kw.get("default_value", ""),
    )


def test_split_sf_fields_strips_and_skips_blanks():
    raw = "  BillingStreet  \n\nBillingCity\n   \nBillingCountry"
    assert _split_sf_fields(raw) == [
        "BillingStreet",
        "BillingCity",
        "BillingCountry",
    ]


def test_split_sf_fields_handles_none_and_empty():
    assert _split_sf_fields(None) == []
    assert _split_sf_fields("") == []
    assert _split_sf_fields("   ") == []


def test_apply_mapping_dispatches_multi_input(monkeypatch):
    """Multi-input mapping row must feed transform a dict of SF fields."""
    from frappe_salesforce.sync import base, transforms

    received: dict = {}

    def fake_transform(name, value):
        received["name"] = name
        received["value"] = value
        return value

    monkeypatch.setattr(base, "apply_transform", fake_transform)

    syncer = base.BaseSyncer.__new__(base.BaseSyncer)
    syncer.mapping = SimpleNamespace(
        field_mappings=[
            _row(
                sf_fields="BillingStreet\nBillingCity",
                frappe_field="custom_sf_address_block",
                transform="address",
            )
        ]
    )

    rec = {"BillingStreet": "1 Main", "BillingCity": "London"}
    out = syncer._apply_mapping(rec)

    assert received["name"] == "address"
    assert received["value"] == {"BillingStreet": "1 Main", "BillingCity": "London"}
    assert "custom_sf_address_block" in out


def test_apply_mapping_scalar_unchanged(monkeypatch):
    from frappe_salesforce.sync import base

    seen: list = []

    def fake_transform(name, value):
        seen.append((name, value))
        return value

    monkeypatch.setattr(base, "apply_transform", fake_transform)

    syncer = base.BaseSyncer.__new__(base.BaseSyncer)
    syncer.mapping = SimpleNamespace(
        field_mappings=[
            _row(sf_field="Name", frappe_field="organization_name"),
        ]
    )

    out = syncer._apply_mapping({"Name": "Acme Corp"})
    assert seen == [("none", "Acme Corp")]
    assert out["organization_name"] == "Acme Corp"


def test_apply_mapping_multi_input_all_none_short_circuits(monkeypatch):
    """If every SF field in a multi-input row is strictly ``None`` and
    there's no default_value, the transform receives ``None`` (not a
    dict of None values)."""
    from frappe_salesforce.sync import base

    seen: list = []

    def fake_transform(name, value):
        seen.append((name, value))
        return None

    monkeypatch.setattr(base, "apply_transform", fake_transform)

    syncer = base.BaseSyncer.__new__(base.BaseSyncer)
    syncer.mapping = SimpleNamespace(
        field_mappings=[
            _row(
                sf_fields="BillingStreet\nBillingCity",
                frappe_field="x",
                transform="address",
            )
        ]
    )

    out = syncer._apply_mapping({"BillingStreet": None, "BillingCity": None})
    assert seen == [("address", None)]
    assert out["x"] is None


def test_apply_mapping_multi_input_partial_blank_passes_dict(monkeypatch):
    """Mixed None / empty-string still routes through as a dict; the
    transform itself decides what to do with empty values."""
    from frappe_salesforce.sync import base

    seen: list = []

    def fake_transform(name, value):
        seen.append((name, value))
        return value

    monkeypatch.setattr(base, "apply_transform", fake_transform)

    syncer = base.BaseSyncer.__new__(base.BaseSyncer)
    syncer.mapping = SimpleNamespace(
        field_mappings=[
            _row(
                sf_fields="BillingStreet\nBillingCity",
                frappe_field="x",
                transform="address",
            )
        ]
    )

    out = syncer._apply_mapping({"BillingStreet": None, "BillingCity": ""})
    assert seen == [("address", {"BillingStreet": None, "BillingCity": ""})]
    assert "x" in out


def test_soql_fields_collects_both_shapes_and_extras(monkeypatch):
    """``_soql_fields`` should union scalar sf_field, multi sf_fields, and
    ``extra_soql_fields`` declared on the syncer class."""
    from frappe_salesforce.sync import base

    syncer = base.BaseSyncer.__new__(base.BaseSyncer)
    syncer.mapping = SimpleNamespace(
        field_mappings=[
            _row(sf_field="Name", frappe_field="organization_name"),
            _row(
                sf_fields="BillingStreet\nBillingCity",
                frappe_field="custom_sf_address_block",
                transform="address",
            ),
            _row(sf_field="Industry", frappe_field="industry"),
        ]
    )
    syncer.extra_soql_fields = ("IsClosed", "WhoId")

    fields = syncer._soql_fields()
    assert "Name" in fields
    assert "BillingStreet" in fields
    assert "BillingCity" in fields
    assert "Industry" in fields
    assert "IsClosed" in fields
    assert "WhoId" in fields
