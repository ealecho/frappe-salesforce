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
import datetime
import json
import time

import frappe
import jwt
import requests
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password
from frappe.utils.synchronization import filelock

from .exceptions import SalesforceAuthError, SalesforceConfigurationError

TOKEN_ENDPOINT = "/services/oauth2/token"
# Refresh the token a bit before actual expiry to avoid race conditions.
EXPIRY_SKEW_SECONDS = 60
# Default token lifetime if Salesforce does not return `expires_in`.
DEFAULT_TOKEN_LIFETIME = 3600
# Max JWT lifetime accepted by Salesforce is 3 minutes; we use slightly less.
JWT_LIFETIME_SECONDS = 180
# A valid Salesforce session token is ~100+ chars; anything materially
# shorter is almost certainly a leftover empty string / corrupted blob.
MIN_PLAUSIBLE_TOKEN_LEN = 20
# Cross-process refresh mutex name (resolves to a file lock under the
# bench's lock dir). Prevents stampedes when multiple scheduler workers
# all wake up post-expiry.
TOKEN_REFRESH_LOCK = "sf_token_refresh"
TOKEN_REFRESH_LOCK_TIMEOUT = 30


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
            instance_url = frappe.db.get_single_value(
                self.SETTINGS_DOCTYPE, "instance_url"
            )
            # Defensive shape check: an empty / truncated token would
            # produce an ``INVALID_AUTH_HEADER`` 401 on the next call.
            # If the cached value is implausible, force a refresh.
            if (
                token
                and len(token.strip()) >= MIN_PLAUSIBLE_TOKEN_LEN
                and instance_url
            ):
                return token, instance_url
        return self._fetch_new_token()

    def invalidate_cached_token(self) -> None:
        """Clear cached token so next call refreshes.

        We null out ``token_expires_at`` only — writing an empty string to
        the encrypted ``access_token`` field creates an intermediate state
        where a concurrent reader can fetch ``""`` and assemble a malformed
        ``Authorization: Bearer `` header. The expiry-null is sufficient
        to trigger a refresh on the next ``get_access_token`` call.
        """
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "token_expires_at", None)
        frappe.db.commit()

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
        """Determine whether the cached token can be safely reused.

        The token IS the source of truth: modern Salesforce session tokens
        are JWTs that embed their own ``exp`` claim. We decode that claim
        and compare against UTC wall-clock time. This is robust against
        TZ confusion (``token_expires_at`` is naive local in the DB) and
        against desync between ``access_token`` and ``token_expires_at``
        (e.g. one write succeeds, the other doesn't).

        If the token isn't a JWT (older orgs, opaque session IDs) we fall
        back to the stored ``token_expires_at`` interpreted as UTC.
        """
        token = get_decrypted_password(
            self.SETTINGS_DOCTYPE,
            self.SETTINGS_DOCTYPE,
            "access_token",
            raise_exception=False,
        )
        if not token or len(token.strip()) < MIN_PLAUSIBLE_TOKEN_LEN:
            return False

        # Primary path: trust the JWT's own exp claim.
        jwt_exp = _decode_jwt_exp(token)
        if jwt_exp is not None:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            return (jwt_exp - now_utc).total_seconds() > EXPIRY_SKEW_SECONDS

        # Fallback: opaque session ID — trust stored expiry, treated as UTC.
        expires_at = frappe.db.get_single_value(
            self.SETTINGS_DOCTYPE, "token_expires_at"
        )
        if not expires_at:
            return False
        # Stored value is naive; we now write UTC into this field, but
        # older rows may be naive-local. We accept the small risk of a
        # one-off bad cache hit during the transition — the post-401
        # refresh path will heal it. Going forward all writes are UTC.
        expires_dt = get_datetime(expires_at)
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=datetime.timezone.utc)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return (expires_dt - now_utc).total_seconds() > EXPIRY_SKEW_SECONDS

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
        # Serialize concurrent refreshes across workers. Without this,
        # two scheduler ticks waking simultaneously can both POST to
        # ``/services/oauth2/token`` and clobber each other's cached
        # token writes (the loser's response races the winner's commit,
        # producing a brief window where the persisted token is from
        # one request but the in-memory token returned by the other
        # caller comes from a different request — the asymmetry shows
        # up as ``INVALID_AUTH_HEADER`` 401s on the next REST call).
        with filelock(TOKEN_REFRESH_LOCK, timeout=TOKEN_REFRESH_LOCK_TIMEOUT):
            # Double-checked locking: another worker may have refreshed
            # while we were blocked on the mutex. If so, reuse its result.
            if self._cached_token_valid():
                token = get_decrypted_password(
                    self.SETTINGS_DOCTYPE,
                    self.SETTINGS_DOCTYPE,
                    "access_token",
                    raise_exception=False,
                )
                instance_url = frappe.db.get_single_value(
                    self.SETTINGS_DOCTYPE, "instance_url"
                )
                if (
                    token
                    and len(token.strip()) >= MIN_PLAUSIBLE_TOKEN_LEN
                    and instance_url
                ):
                    return token, instance_url
            return self._do_fetch_new_token()

    def _do_fetch_new_token(self) -> tuple[str, str]:
        private_key = self._load_private_key()
        claim = self.build_claim()

        try:
            assertion = jwt.encode(claim, private_key, algorithm="RS256")
        except Exception as e:
            raise SalesforceAuthError(f"Failed to sign JWT assertion: {e}") from e

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
        # Defensive sanitisation: even though SF returns clean values, any
        # whitespace/control char that survives into the persisted token
        # would later poison the Authorization header.
        access_token = access_token.strip()

        # Prefer the JWT's embedded exp claim if present (modern SF orgs);
        # it is the authoritative expiry. Fall back to expires_in (legacy
        # opaque session IDs).
        jwt_exp = _decode_jwt_exp(access_token)
        if jwt_exp is not None:
            # Store as naive UTC (Frappe Datetime fields are naive). We
            # always interpret this field as UTC on read.
            expires_at = jwt_exp.replace(tzinfo=None)
        else:
            expires_in = int(data.get("expires_in") or DEFAULT_TOKEN_LIFETIME)
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=expires_in)
            ).replace(tzinfo=None)

        # Persist for future calls.
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "access_token", access_token)
        frappe.db.set_single_value(self.SETTINGS_DOCTYPE, "instance_url", instance_url)
        frappe.db.set_single_value(
            self.SETTINGS_DOCTYPE, "token_expires_at", expires_at
        )
        frappe.db.commit()

        # Atomic write-verify (Plan C): immediately read back what we
        # wrote. If the encrypted-field write to access_token silently
        # failed (a class of bug we've seen on Frappe Cloud where the
        # ``__Auth`` row update doesn't actually land), we'd otherwise
        # cache a desynced (access_token, token_expires_at) pair and
        # 401 on every subsequent call until expiry. Better to fail
        # loudly than to poison the cache.
        readback = get_decrypted_password(
            self.SETTINGS_DOCTYPE,
            self.SETTINGS_DOCTYPE,
            "access_token",
            raise_exception=False,
        )
        if (readback or "").strip() != access_token:
            raise SalesforceAuthError(
                "Token persist verification failed: wrote "
                f"len={len(access_token)} but read back "
                f"len={len((readback or '').strip())}. Likely an encrypted-field "
                "write that did not commit; check site DB / __Auth table."
            )

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


def _decode_jwt_exp(token: str) -> datetime.datetime | None:
    """Return the ``exp`` claim of ``token`` as a tz-aware UTC datetime.

    Returns ``None`` if the token isn't a parseable JWT or has no ``exp``
    claim. Used as the source of truth for token expiry: the JWT is
    self-describing, so we don't have to trust separately-stored metadata
    (``token_expires_at``) that can desync from ``access_token``.

    Signature is NOT verified — we trust SF to have given us its own
    signed token, and we're only reading expiry. The signature would
    require SF's JWKS which we don't have.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Restore base64 padding stripped by JWT encoding.
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return None
        return datetime.datetime.fromtimestamp(int(exp), datetime.timezone.utc)
    except Exception:
        return None
