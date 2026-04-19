"""Salesforce JWT Bearer OAuth 2.0 authentication.

Uses the OAuth 2.0 JWT Bearer flow for server-to-server integration with a
Salesforce **External Client App** (ECA). Connected Apps also work with this
code since the wire protocol is identical, but new integrations should use
External Client Apps.

Docs:
- https://help.salesforce.com/s/articleView?id=xcloud.remoteaccess_oauth_jwt_flow.htm
- https://help.salesforce.com/s/articleView?id=xcloud.external_client_apps_overview.htm
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

import frappe
import jwt
import requests
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password

from .exceptions import SalesforceAuthError, SalesforceConfigurationError

TOKEN_ENDPOINT = "/services/oauth2/token"
# Refresh the token a bit before actual expiry to avoid race conditions.
EXPIRY_SKEW_SECONDS = 60
# Default token lifetime if Salesforce does not return `expires_in`.
DEFAULT_TOKEN_LIFETIME = 3600
# Max JWT lifetime accepted by Salesforce is 3 minutes; we use slightly less.
JWT_LIFETIME_SECONDS = 180


class SalesforceAuth:
    """Fetches and caches a Salesforce access token via JWT Bearer flow."""

    SETTINGS_DOCTYPE = "Salesforce Settings"

    def __init__(self):
        self.settings = frappe.get_single(self.SETTINGS_DOCTYPE)
        self._validate_settings()

    def _validate_settings(self) -> None:
        required = ["client_id", "username", "login_url"]
        missing = [f for f in required if not self.settings.get(f)]
        if missing:
            raise SalesforceConfigurationError(
                f"Salesforce Settings missing required fields: {', '.join(missing)}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_access_token(self) -> tuple[str, str]:
        """Return a tuple of ``(access_token, instance_url)``.

        Returns the cached token if still valid; otherwise fetches a new one.
        """
        if self._cached_token_valid():
            token = get_decrypted_password(
                self.SETTINGS_DOCTYPE,
                self.SETTINGS_DOCTYPE,
                "access_token",
                raise_exception=False,
            )
            if token and self.settings.instance_url:
                return token, self.settings.instance_url
        return self._fetch_new_token()

    def invalidate_cached_token(self) -> None:
        """Clear cached token so next call refreshes."""
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "access_token", "")
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "token_expires_at", None)

    def build_claim(self, issued_at: int | None = None) -> dict:
        """Build the JWT claim set. Exposed for diagnostics."""
        if issued_at is None:
            issued_at = int(time.time())
        return {
            "iss": (self.settings.client_id or "").strip(),
            "sub": (self.settings.username or "").strip(),
            "aud": self._audience(),
            "exp": issued_at + JWT_LIFETIME_SECONDS,
            "iat": issued_at,
        }

    def sign_assertion(self, claim: dict | None = None) -> str:
        """Return a signed JWT assertion. Exposed for diagnostics.

        Use jwt.io (paste the token + your .crt) to verify the signature
        independently of Salesforce.
        """
        if claim is None:
            claim = self.build_claim()
        private_key = self._load_private_key()
        try:
            return jwt.encode(claim, private_key, algorithm="RS256")
        except Exception as e:
            raise SalesforceAuthError(f"Failed to sign JWT assertion: {e}") from e

    def public_key_fingerprint(self) -> dict:
        """Derive the public key from the configured private key and return
        SHA-256 fingerprints in several formats.

        Compare one of these against the fingerprint Salesforce shows for
        the certificate you uploaded to the External Client App. If they
        differ, the private key in Settings does NOT match the uploaded
        cert and JWT signing will always fail with ``invalid_grant``.
        """
        try:
            from cryptography.hazmat.primitives import serialization
        except ImportError as e:
            raise SalesforceConfigurationError(
                "cryptography package is required for fingerprint diagnostics"
            ) from e

        pem = self._load_private_key().encode("utf-8")
        private = serialization.load_pem_private_key(pem, password=None)
        public_der = private.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashlib.sha256(public_der).digest()
        return {
            "sha256_hex": digest.hex(),
            "sha256_colon_hex": ":".join(f"{b:02x}" for b in digest),
            "sha256_base64": base64.b64encode(digest).decode("ascii"),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _audience(self) -> str:
        """Audience claim per Salesforce ECA JWT spec.

        Salesforce accepts the login host (``https://login.salesforce.com`` or
        ``https://test.salesforce.com``). We normalize to the host root, no
        trailing slash, no path — this is what the docs require.
        """
        login = (self.settings.login_url or "").strip().rstrip("/")
        if not login:
            raise SalesforceConfigurationError("login_url is not configured")
        # If a full token URL was pasted, strip the path back to the origin.
        if "/services/" in login:
            login = login.split("/services/", 1)[0]
        return login

    def _token_url(self) -> str:
        return f"{self._audience()}{TOKEN_ENDPOINT}"

    def _cached_token_valid(self) -> bool:
        expires_at = self.settings.token_expires_at
        if not expires_at:
            return False
        expires_dt = get_datetime(expires_at)
        now = get_datetime(now_datetime())
        return (expires_dt - now).total_seconds() > EXPIRY_SKEW_SECONDS

    def _load_private_key(self) -> str:
        raw = get_decrypted_password(
            self.SETTINGS_DOCTYPE,
            self.SETTINGS_DOCTYPE,
            "private_key",
            raise_exception=False,
        )
        if not raw:
            raise SalesforceConfigurationError(
                "Salesforce Settings: private_key is not set"
            )
        # Textarea/password-field paste can introduce literal "\n" sequences
        # instead of real newlines. Normalize so PyJWT/cryptography can parse.
        key = raw.strip()
        if "\\n" in key and "\n" not in key:
            key = key.replace("\\n", "\n")
        # Ensure the PEM headers are present; otherwise cryptography raises
        # a cryptic error and the JWT library wraps it unhelpfully.
        if "-----BEGIN" not in key:
            raise SalesforceConfigurationError(
                "private_key does not look like a PEM file "
                "(expected '-----BEGIN PRIVATE KEY-----' or "
                "'-----BEGIN RSA PRIVATE KEY-----')"
            )
        return key

    def _fetch_new_token(self) -> tuple[str, str]:
        claim = self.build_claim()
        assertion = self.sign_assertion(claim)

        url = self._token_url()
        try:
            resp = requests.post(
                url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as e:
            raise SalesforceAuthError(f"Network error during token request: {e}") from e

        if resp.status_code != 200:
            self._log_token_failure(claim, url, resp)
            raise SalesforceAuthError(
                f"Token request failed ({resp.status_code}): {resp.text}"
            )

        data = resp.json()
        access_token = data.get("access_token")
        instance_url = data.get("instance_url") or self.settings.instance_url
        if not access_token:
            raise SalesforceAuthError(f"Token response missing access_token: {data}")

        expires_in = int(data.get("expires_in") or DEFAULT_TOKEN_LIFETIME)
        expires_at = frappe.utils.add_to_date(now_datetime(), seconds=expires_in)

        # Persist for future calls.
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "access_token", access_token)
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "instance_url", instance_url)
        frappe.db.set_single_value(
            self.SETTINGS_DOCTYPE, "token_expires_at", expires_at
        )
        frappe.db.commit()

        return access_token, instance_url

    def _log_token_failure(
        self, claim: dict, url: str, resp: requests.Response
    ) -> None:
        """Write a diagnostic Error Log entry when SF rejects the JWT.

        Salesforce's ``invalid_grant / invalid assertion`` response is opaque.
        Logging the claim (safe fields only) plus the token URL makes
        troubleshooting dramatically faster. The private key and signed JWT
        are never logged.
        """
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        diagnostic = {
            "token_url": url,
            "http_status": resp.status_code,
            "response": body,
            "claim": {
                "iss": claim.get("iss"),
                "sub": claim.get("sub"),
                "aud": claim.get("aud"),
                "iat": claim.get("iat"),
                "exp": claim.get("exp"),
                "lifetime_seconds": claim.get("exp", 0) - claim.get("iat", 0),
            },
            "hint": _invalid_grant_hint(body),
        }
        try:
            frappe.log_error(
                title="Salesforce JWT Bearer auth failed",
                message=json.dumps(diagnostic, indent=2, default=str),
            )
        except Exception:
            # Never let logging mask the original error.
            pass


def _invalid_grant_hint(body: dict) -> str:
    """Map common Salesforce token-endpoint errors to actionable hints."""
    err = (body or {}).get("error", "")
    desc = (body or {}).get("error_description", "") or ""
    d = desc.lower()
    if err == "invalid_grant" and "invalid assertion" in d:
        return (
            "Common causes: (1) the integration user is not pre-authorized on "
            "the External Client App's policy (assign their Profile or a "
            "Permission Set); (2) the Consumer Key does not match the app that "
            "holds the uploaded certificate; (3) the private key in Settings "
            "does not match the certificate uploaded to the app; (4) the "
            "username does not match a real Salesforce user; (5) the login_url "
            "is wrong for this org (production vs sandbox)."
        )
    if err == "invalid_client_id":
        return "The Consumer Key is wrong or the app is not yet active."
    if err == "invalid_app_access":
        return (
            "The user does not have access to this External Client App. "
            "Check app policy 'Permitted Users' and pre-authorization."
        )
    if err == "inactive_user":
        return "The integration user is inactive in Salesforce."
    if err == "user_hasnt_approved":
        return (
            "Set the ECA policy 'Permitted Users' to "
            "'Admin approved users are pre-authorized' and assign the user's "
            "Profile or a Permission Set to the app."
        )
    return ""
