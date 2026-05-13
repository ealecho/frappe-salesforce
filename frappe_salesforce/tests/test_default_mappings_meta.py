"""Static checks on DEFAULT_MAPPINGS that don't require a Frappe site.

These would have caught the v0.0.x bugs:

* ``Opportunity.Amount → annual_revenue`` (wrong target field).
* ``Opportunity.CloseDate → close_date`` (target field doesn't exist).
* Multiple rows with identical ``(sf_field, frappe_field)`` keys.

Each row is also validated for required fields and that ``transform`` is
one of the dispatcher's known names.
"""

from __future__ import annotations

import pytest

from frappe_salesforce.setup.default_mappings import DEFAULT_MAPPINGS, _serialise_row
from frappe_salesforce.sync.transforms import TRANSFORMS

#: Native Frappe CRM target fields per DocType (excluding our ``custom_sf_*``).
#: These are spot-checks; full meta validation needs a Frappe site (covered
#: by the in-site syncer integration tests).
KNOWN_NATIVE_FIELDS: dict[str, set[str]] = {
    "CRM Organization": {
        "organization_name",
        "website",
        "organization_logo",
        "no_of_employees",
        "annual_revenue",
        "industry",
        "territory",
        "currency",
        "address",
        "exchange_rate",
    },
    "Contact": {
        "first_name",
        "middle_name",
        "last_name",
        "full_name",
        "email_id",
        "phone",
        "mobile_no",
        "salutation",
        "designation",
        "gender",
        "department",
        "company_name",
        "address",
        "user",
        "image",
        "status",
        "unsubscribed",
        # child tables
        "email_ids",
        "phone_nos",
        "links",
    },
    "CRM Lead": {
        "salutation",
        "first_name",
        "middle_name",
        "last_name",
        "lead_name",
        "email",
        "mobile_no",
        "phone",
        "website",
        "gender",
        "status",
        "organization",
        "no_of_employees",
        "annual_revenue",
        "industry",
        "job_title",
        "lead_owner",
        "source",
        "territory",
        "converted",
        "lost_reason",
        "lost_notes",
        "image",
    },
    "CRM Deal": {
        "organization",
        "organization_name",
        "lead",
        "contact",
        "contacts",
        "email",
        "mobile_no",
        "phone",
        "status",
        "probability",
        "deal_value",
        "expected_deal_value",
        "expected_closure_date",
        "closed_date",
        "currency",
        "exchange_rate",
        "next_step",
        "deal_owner",
        "industry",
        "source",
        "territory",
        "annual_revenue",
        "salutation",
        "first_name",
        "last_name",
        "lead_name",
        "job_title",
        "website",
        "lost_reason",
        "lost_notes",
        "products",
    },
    "CRM Task": {
        "title",
        "priority",
        "start_date",
        "reference_doctype",
        "reference_docname",
        "assigned_to",
        "status",
        "due_date",
        "description",
    },
}


#: Frappe-field placeholders used by ``after_upsert`` side effects (e.g.
#: address blocks) that don't correspond to a real column on the parent
#: doctype. They're allowed in mapping rows so SOQL pulls the SF inputs.
SIDE_EFFECT_PLACEHOLDERS = {
    "custom_sf_address_block",  # address upsert in after_upsert
}


def _is_known_field(doctype: str, field: str) -> bool:
    """A field is allowed if it's native, a placeholder, or a real custom field."""
    if field in SIDE_EFFECT_PLACEHOLDERS:
        return True
    if field.startswith("custom_sf_") or field == "custom_salesforce_id":
        return True
    return field in KNOWN_NATIVE_FIELDS.get(doctype, set())


@pytest.mark.parametrize(
    "mapping",
    DEFAULT_MAPPINGS,
    ids=lambda m: f"{m['salesforce_object']}->{m['frappe_doctype']}",
)
def test_every_row_targets_a_known_field(mapping):
    doctype = mapping["frappe_doctype"]
    for row in mapping["rows"]:
        ff = row["frappe_field"]
        assert _is_known_field(doctype, ff), (
            f"{mapping['salesforce_object']}: row targets unknown "
            f"{doctype}.{ff} — either the field doesn't exist or it's a "
            f"custom field that's missing from setup/custom_fields.py"
        )


@pytest.mark.parametrize(
    "mapping",
    DEFAULT_MAPPINGS,
    ids=lambda m: m["salesforce_object"],
)
def test_every_transform_is_registered(mapping):
    for row in mapping["rows"]:
        transform = row.get("transform") or "none"
        assert transform in TRANSFORMS, (
            f"{mapping['salesforce_object']}/{row['frappe_field']}: "
            f"transform {transform!r} is not registered in transforms.TRANSFORMS"
        )


@pytest.mark.parametrize(
    "mapping",
    DEFAULT_MAPPINGS,
    ids=lambda m: m["salesforce_object"],
)
def test_no_duplicate_rows(mapping):
    seen: set[tuple[str, str]] = set()
    dups: list[tuple[str, str]] = []
    for row in mapping["rows"]:
        sf = row.get("sf_field") or ""
        if not sf and isinstance(row.get("sf_fields"), list):
            sf = "\n".join(row["sf_fields"])
        key = (sf, row["frappe_field"])
        if key in seen:
            dups.append(key)
        else:
            seen.add(key)
    assert not dups, (
        f"{mapping['salesforce_object']}: duplicate (sf_field,frappe_field) "
        f"rows: {dups}"
    )


@pytest.mark.parametrize(
    "mapping",
    DEFAULT_MAPPINGS,
    ids=lambda m: m["salesforce_object"],
)
def test_each_row_has_input(mapping):
    """Every row must specify either ``sf_field`` or ``sf_fields``."""
    for row in mapping["rows"]:
        sf_field = row.get("sf_field")
        sf_fields = row.get("sf_fields")
        has_input = bool(sf_field) or (
            isinstance(sf_fields, list) and len(sf_fields) > 0
        )
        assert has_input, (
            f"{mapping['salesforce_object']}/{row['frappe_field']}: "
            f"row has neither sf_field nor sf_fields"
        )


def test_serialise_row_collapses_sf_fields_list():
    out = _serialise_row(
        {
            "sf_fields": ["BillingStreet", "BillingCity"],
            "frappe_field": "address",
            "transform": "address",
        }
    )
    assert out["sf_fields"] == "BillingStreet\nBillingCity"
    assert out["sf_field"] == ""
    assert out["transform"] == "address"


def test_serialise_row_handles_scalar_row():
    out = _serialise_row({"sf_field": "Name", "frappe_field": "organization_name"})
    assert out["sf_field"] == "Name"
    assert out["sf_fields"] == ""
    assert out["transform"] == "none"


def test_opportunity_amount_targets_deal_value():
    """Regression: v0.0.x mapped Amount → annual_revenue (wrong field)."""
    opp = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Opportunity")
    amount_rows = [r for r in opp["rows"] if r.get("sf_field") == "Amount"]
    assert len(amount_rows) == 1
    assert amount_rows[0]["frappe_field"] == "deal_value"


def test_opportunity_close_date_targets_expected_closure_date():
    """Regression: v0.0.x mapped CloseDate → close_date (field doesn't exist)."""
    opp = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Opportunity")
    rows = [r for r in opp["rows"] if r.get("sf_field") == "CloseDate"]
    assert len(rows) == 1
    assert rows[0]["frappe_field"] == "expected_closure_date"
    assert rows[0].get("transform") == "date"


def test_account_employee_count_uses_bucket_transform():
    """Regression: int → Select bucket needs the employee_bucket transform."""
    acc = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Account")
    rows = [r for r in acc["rows"] if r.get("sf_field") == "NumberOfEmployees"]
    assert len(rows) == 1
    assert rows[0].get("transform") == "employee_bucket"


def test_account_industry_uses_link_transform():
    acc = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Account")
    rows = [
        r
        for r in acc["rows"]
        if r.get("sf_field") == "Industry" and r["frappe_field"] == "industry"
    ]
    assert len(rows) == 1
    assert rows[0].get("transform") == "industry_link"


def test_task_due_date_uses_datetime_transform():
    """Regression: due_date is Datetime, not Date."""
    task = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Task")
    rows = [
        r
        for r in task["rows"]
        if r.get("sf_field") == "ActivityDate" and r["frappe_field"] == "due_date"
    ]
    assert len(rows) == 1
    assert rows[0].get("transform") == "datetime"


def test_contact_record_type_id_omitted_by_default():
    """Regression: Contact.RecordTypeId is FLS-blocked on most NPSP orgs.

    v0.0.2 had to ship a prune patch after default_mappings reintroduced
    it; v0.1.0 must keep it out of defaults to avoid blocking syncs on
    fresh installs.
    """
    contact = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Contact")
    rows = [r for r in contact["rows"] if r.get("sf_field") == "RecordTypeId"]
    assert not rows, (
        "Contact.RecordTypeId is FLS-blocked on common NPSP orgs and "
        "must NOT be in default mappings. Re-add it via the UI on orgs "
        "that expose it."
    )


def test_contact_email_uses_email_table_transform():
    """Regression: Email/Phone/MobilePhone are read-only on Contact;
    sync writes the email_ids/phone_nos child tables instead."""
    contact = next(m for m in DEFAULT_MAPPINGS if m["salesforce_object"] == "Contact")
    # No row should target read-only email_id/phone/mobile_no.
    bad = [
        r
        for r in contact["rows"]
        if r.get("sf_field") in ("Email", "Phone", "MobilePhone")
        and r["frappe_field"] in ("email_id", "phone", "mobile_no")
    ]
    assert not bad, f"Contact rows still target read-only flat fields: {bad}"

    # Multi-input rows must exist for email_ids and phone_nos.
    email_rows = [r for r in contact["rows"] if r["frappe_field"] == "email_ids"]
    phone_rows = [r for r in contact["rows"] if r["frappe_field"] == "phone_nos"]
    assert len(email_rows) == 1 and email_rows[0]["transform"] == "email_table"
    assert len(phone_rows) == 1 and phone_rows[0]["transform"] == "phone_table"
    assert "Email" in email_rows[0]["sf_fields"]
    assert "Phone" in phone_rows[0]["sf_fields"]
