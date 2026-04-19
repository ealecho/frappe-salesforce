"""Connection test and diagnostic endpoints."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def test_connection():
    """Verify Salesforce credentials by executing a trivial SOQL query."""
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.client import SalesforceClient
    from frappe_salesforce.salesforce.exceptions import SalesforceError

    try:
        client = SalesforceClient()
        rec = next(client.query("SELECT Id, Name FROM Organization LIMIT 1"))
    except StopIteration:
        return {"ok": False, "error": "No Organization record returned."}
    except SalesforceError as e:
        return {
            "ok": False,
            "error": str(e),
            "hint": (
                "See Error Log doctype for a 'Salesforce JWT Bearer auth "
                "failed' entry with the decoded claim and Salesforce's "
                "response — that's the fastest way to diagnose."
            ),
        }
    return {
        "ok": True,
        "org_id": rec.get("Id"),
        "org_name": rec.get("Name"),
        "api_limits": client.rate_limit_info,
    }


@frappe.whitelist()
def diagnose():
    """Return a redacted view of the JWT claim and token URL we would send.

    Does **not** include the signed assertion, private key, or any secret
    material. Useful for verifying the External Client App is configured
    correctly without hitting Salesforce.
    """
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.auth import SalesforceAuth
    from frappe_salesforce.salesforce.exceptions import SalesforceConfigurationError

    try:
        auth = SalesforceAuth()
        claim = auth.build_claim()
        return {
            "ok": True,
            "token_url": auth._token_url(),
            "claim": {
                "iss (Consumer Key)": claim["iss"],
                "sub (Username)": claim["sub"],
                "aud (Audience)": claim["aud"],
                "iat": claim["iat"],
                "exp": claim["exp"],
                "lifetime_seconds": claim["exp"] - claim["iat"],
            },
            "notes": [
                "iss must exactly match the External Client App's Consumer Key.",
                "sub must be the integration user's Salesforce Username (not email alias).",
                "aud must be https://login.salesforce.com (production) or https://test.salesforce.com (sandbox).",
                "The integration user must be pre-authorized on the ECA policy.",
            ],
        }
    except SalesforceConfigurationError as e:
        return {"ok": False, "error": str(e)}
