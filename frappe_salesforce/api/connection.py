"""Connection test endpoint."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def test_connection():
    """Verify Salesforce credentials by executing a trivial SOQL query."""
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.client import SalesforceClient

    client = SalesforceClient()
    try:
        rec = next(client.query("SELECT Id, Name FROM Organization LIMIT 1"))
    except StopIteration:
        return {"ok": False, "error": "No Organization record returned."}
    return {
        "ok": True,
        "org_id": rec.get("Id"),
        "org_name": rec.get("Name"),
        "api_limits": client.rate_limit_info,
    }
