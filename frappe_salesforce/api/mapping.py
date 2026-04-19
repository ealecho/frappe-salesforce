"""Field mapping helpers (describe SF objects, preview, etc.)."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def describe_object(salesforce_object: str):
    """Return describe() metadata for a Salesforce object (fields + picklists)."""
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.client import SalesforceClient

    client = SalesforceClient()
    url = f"{client._base()}/sobjects/{salesforce_object}/describe/"
    resp = client._get(url)
    data = resp.json()
    return {
        "name": data.get("name"),
        "label": data.get("label"),
        "fields": [
            {
                "name": f.get("name"),
                "label": f.get("label"),
                "type": f.get("type"),
                "nillable": f.get("nillable"),
                "referenceTo": f.get("referenceTo"),
                "picklistValues": [
                    p.get("value") for p in (f.get("picklistValues") or [])
                ],
            }
            for f in data.get("fields", [])
        ],
    }
