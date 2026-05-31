"""Static integrity checks on the custom_fields module."""

from frappe_salesforce.setup.custom_fields import (
    ALL_CUSTOM_FIELDS,
    CRM_DEAL_FIELDS,
    CRM_LEAD_FIELDS,
    CRM_ORGANIZATION_FIELDS,
    CRM_TASK_FIELDS,
    CONTACT_FIELDS,
)
from frappe_salesforce.setup.default_mappings import DEFAULT_MAPPINGS


def _names(fields: list[dict]) -> list[str]:
    return [f["fieldname"] for f in fields]


def test_no_duplicate_fieldnames_per_doctype():
    for doctype, fields in ALL_CUSTOM_FIELDS.items():
        names = _names(fields)
        assert len(names) == len(set(names)), (
            f"{doctype} has duplicate fieldnames: "
            f"{[n for n in names if names.count(n) > 1]}"
        )


def test_every_custom_sf_field_has_no_copy_flag():
    for doctype, fields in ALL_CUSTOM_FIELDS.items():
        for f in fields:
            if not f["fieldname"].startswith("custom_sf_"):
                continue
            assert f.get("no_copy") == 1, (
                f"{doctype}.{f['fieldname']} missing no_copy=1; "
                f"SF-derived fields should not propagate when a CRM doc "
                f"is duplicated."
            )


def test_every_doctype_has_custom_salesforce_id():
    for doctype, fields in ALL_CUSTOM_FIELDS.items():
        names = _names(fields)
        assert "custom_salesforce_id" in names, (
            f"{doctype} is missing custom_salesforce_id"
        )


#: Mapping ``frappe_field``s that are deliberately not real fields —
#: they're placeholders for side-effect transforms (e.g. address blocks
#: routed via ``after_upsert``).
SIDE_EFFECT_PLACEHOLDERS = {"custom_sf_address_block"}


def test_every_default_mapping_target_has_a_custom_field():
    """Every ``custom_sf_*`` referenced in DEFAULT_MAPPINGS must exist."""
    for mapping in DEFAULT_MAPPINGS:
        doctype = mapping["frappe_doctype"]
        defined = set(_names(ALL_CUSTOM_FIELDS.get(doctype, [])))
        for row in mapping["rows"]:
            ff = row["frappe_field"]
            if not ff.startswith("custom_sf_"):
                continue
            if ff in SIDE_EFFECT_PLACEHOLDERS:
                continue
            assert ff in defined, (
                f"{mapping['salesforce_object']} → {doctype}.{ff} "
                f"is in DEFAULT_MAPPINGS but missing from custom_fields.py"
            )


def test_crm_deal_has_grant_workflow_fields():
    """Spot-check that we covered the high-value NPSP grant workflow."""
    names = set(_names(CRM_DEAL_FIELDS))
    for required in [
        "custom_sf_grant_contract_number",
        "custom_sf_grant_period_start",
        "custom_sf_grant_period_end",
        "custom_sf_requested_amount",
        "custom_sf_gift_aid",
        "custom_sf_payment_method",
    ]:
        assert required in names, f"CRM Deal missing {required}"


def test_contact_has_communication_preferences():
    names = set(_names(CONTACT_FIELDS))
    for required in [
        "custom_sf_email_opt_in",
        "custom_sf_phone_opt_in",
        "custom_sf_post_opt_in",
        "custom_sf_sms_opt_in",
        "custom_sf_active_gift_aid_declaration",
    ]:
        assert required in names, f"Contact missing {required}"


def test_crm_organization_has_npsp_rollups():
    names = set(_names(CRM_ORGANIZATION_FIELDS))
    for required in [
        "custom_sf_lifetime_donation_amount",
        "custom_sf_total_opp_amount",
        "custom_sf_largest_amount",
        "custom_sf_last_close_date",
    ]:
        assert required in names, f"CRM Organization missing {required}"


def test_crm_lead_has_conversion_mirrors():
    names = set(_names(CRM_LEAD_FIELDS))
    for required in [
        "custom_sf_is_converted",
        "custom_sf_converted_account_id",
        "custom_sf_converted_contact_id",
        "custom_sf_converted_opportunity_id",
    ]:
        assert required in names, f"CRM Lead missing {required}"


def test_crm_task_keeps_existing_event_fields():
    """Backward compat: previous fields must remain available."""
    names = set(_names(CRM_TASK_FIELDS))
    for required in [
        "custom_sf_activity_type",
        "custom_sf_start_datetime",
        "custom_sf_end_datetime",
    ]:
        assert required in names, f"CRM Task lost legacy {required}"
