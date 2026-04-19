"""Salesforce JWT Bearer OAuth 2.0 authentication.

Uses the JWT Bearer flow for server-to-server integration:
https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_jwt_flow.htm
"""

from __future__ import annotations

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


class SalesforceAuth:
    """Fetches and caches a Salesforce access token via JWT Bearer flow."""

    SETTINGS_DOCTYPE = "Salesforce Settings"

    def __init__(self):
        self.settings = frappe.get_single(self.SETTINGS_DOCTYPE)
        self._validate_settings()

    def _validate_settings(self) -> None:
        required = ["client_id", "username", "login_url", "instance_url"]
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
            if token:
                return token, self.settings.instance_url
        return self._fetch_new_token()

    def invalidate_cached_token(self) -> None:
        """Clear cached token so next call refreshes."""
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "access_token", "")
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "token_expires_at", None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _cached_token_valid(self) -> bool:
        expires_at = self.settings.token_expires_at
        if not expires_at:
            return False
        expires_dt = get_datetime(expires_at)
        now = get_datetime(now_datetime())
        return (expires_dt - now).total_seconds() > EXPIRY_SKEW_SECONDS

    def _fetch_new_token(self) -> tuple[str, str]:
        private_key = get_decrypted_password(
            self.SETTINGS_DOCTYPE,
            self.SETTINGS_DOCTYPE,
            "private_key",
            raise_exception=False,
        )
        if not private_key:
            raise SalesforceConfigurationError(
                "Salesforce Settings: private_key is not set"
            )

        issued_at = int(time.time())
        claim = {
            "iss": self.settings.client_id,
            "sub": self.settings.username,
            "aud": self.settings.login_url,
            "exp": issued_at + 300,
            "iat": issued_at,
        }
        try:
            assertion = jwt.encode(claim, private_key, algorithm="RS256")
        except Exception as e:
            raise SalesforceAuthError(f"Failed to sign JWT assertion: {e}") from e

        url = f"{self.settings.login_url.rstrip('/')}{TOKEN_ENDPOINT}"
        try:
            resp = requests.post(
                url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise SalesforceAuthError(f"Network error during token request: {e}") from e

        if resp.status_code != 200:
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
