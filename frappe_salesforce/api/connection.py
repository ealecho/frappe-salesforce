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
                "Open Error Log and find the 'Salesforce JWT Bearer auth "
                "failed' entry for the decoded claim. Also check "
                "Salesforce: Setup > Login History (filter by your "
                "integration user) — the Status column there shows the "
                "real rejection reason (e.g. 'user hasn't approved "
                "consumer', 'invalid certificate')."
            ),
        }
    return {
        "ok": True,
        "org_id": rec.get("Id"),
        "org_name": rec.get("Name"),
        "api_limits": client.rate_limit_info,
    }


@frappe.whitelist()
def diagnose(include_assertion: int | str | bool = 0):
    """Return a redacted view of the JWT claim, token URL, and the public-key
    fingerprint derived from the private key configured in Settings.

    Pass ``include_assertion=1`` to also return the signed JWT string so you
    can paste it into https://jwt.io to verify the signature against the
    .crt you uploaded to Salesforce.

    Never returns the private key itself.
    """
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.auth import SalesforceAuth
    from frappe_salesforce.salesforce.exceptions import (
        SalesforceAuthError,
        SalesforceConfigurationError,
    )

    include = str(include_assertion).lower() in {"1", "true", "yes"}

    try:
        auth = SalesforceAuth()
        claim = auth.build_claim()
        out = {
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
                "sub must be the integration user's Salesforce Username (NOT email alias).",
                "aud must be https://login.salesforce.com (production) or https://test.salesforce.com (sandbox).",
                "The integration user must be pre-authorized on the ECA Policy.",
                "The 'Issue JSON Web Token (JWT)-based access tokens' toggle must be enabled on the ECA's OAuth Settings.",
            ],
        }
        try:
            out["public_key_fingerprint"] = auth.public_key_fingerprint()
            out["fingerprint_help"] = (
                "Compare 'sha256_colon_hex' to the certificate fingerprint "
                "Salesforce shows for the uploaded cert in the ECA's Digital "
                "Signatures section. If they differ, the private key in "
                "Settings does NOT match the uploaded certificate — this "
                "will always produce 'invalid_grant: invalid assertion'."
            )
        except SalesforceConfigurationError as e:
            out["public_key_fingerprint_error"] = str(e)

        if include:
            try:
                out["signed_assertion"] = auth.sign_assertion(claim)
                out["assertion_help"] = (
                    "Paste this JWT into https://jwt.io along with your "
                    "certificate's PEM to verify the signature validates. "
                    "If jwt.io says 'Signature Verified' but Salesforce "
                    "still rejects it, the issue is on the SF side "
                    "(policy, pre-auth, user, or app config)."
                )
            except SalesforceAuthError as e:
                out["signed_assertion_error"] = str(e)

        return out
    except SalesforceConfigurationError as e:
        return {"ok": False, "error": str(e)}
