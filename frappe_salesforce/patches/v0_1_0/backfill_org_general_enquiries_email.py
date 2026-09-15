"""One-shot pull of Account.General_enquiries_email__c for synced orgs.

The field was never mapped, so already-synced organizations have no org
email and won't get one until their SF Account is next modified (org
emails are static, so effectively never). One paginated SOQL query
fills them in; the new mapping row keeps them current afterwards.

Network access inside a migrate patch must never abort the migrate (a
failed patch rolls the whole deploy back — learned the hard way on this
site), so any failure is logged and swallowed. If it does fail, rerun
manually from a console:

    from frappe_salesforce.patches.v0_1_0.backfill_org_general_enquiries_email import execute
    execute()
"""

import frappe

SF_FIELD = "General_enquiries_email__c"
TARGET_FIELD = "custom_sf_general_enquiries_email"


def execute():
    if not frappe.db.exists("DocType", "CRM Organization"):
        return
    # ensure_all_custom_fields (after_migrate) may not have run yet on
    # this migrate — create the target field now so the writes land.
    if not frappe.get_meta("CRM Organization").get_field(TARGET_FIELD):
        from frappe_salesforce.setup.custom_fields import ensure_all_custom_fields

        ensure_all_custom_fields()
        frappe.clear_cache(doctype="CRM Organization")
    if not frappe.db.get_single_value("Salesforce Settings", "enabled"):
        return
    try:
        from frappe_salesforce.salesforce.client import SalesforceClient

        client = SalesforceClient()
        for rec in client.query(
            f"SELECT Id, {SF_FIELD} FROM Account WHERE {SF_FIELD} != null"
        ):
            name = frappe.db.get_value(
                "CRM Organization", {"custom_salesforce_id": rec.get("Id")}, "name"
            )
            if name:
                frappe.db.set_value(
                    "CRM Organization",
                    name,
                    TARGET_FIELD,
                    rec.get(SF_FIELD),
                    update_modified=False,
                )
    except Exception:
        frappe.log_error(
            title="backfill_org_general_enquiries_email failed",
            message=frappe.get_traceback(),
        )
