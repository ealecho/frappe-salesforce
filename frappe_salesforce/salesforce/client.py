"""Salesforce REST + SOQL client with auto pagination and 401 refresh.

Quota-safety layers, in order:

1. **Cached preflight** — before any call, consult the last observed
   ``Sforce-Limit-Info`` stored on ``Salesforce Settings``. If it is
   recent (<5 min) and at/above the configured threshold (default 80%),
   refuse to make any call. Zero-cost circuit breaker.
2. **Per-tick budget** — hard cap on calls per ``SalesforceClient``
   instance (one instance per sync run). Prevents a single tick from
   burning through the daily quota.
3. **Per-day budget** — app-level daily counter, stored as a
   ``frappe.cache`` value keyed by UTC date. Independent of, and
   stricter than, the Salesforce org quota.
4. **Org quota abort** — reads ``Sforce-Limit-Info`` from every 2xx
   response and aborts if the Salesforce-reported usage crosses the
   fixed 90% threshold.

Diagnostic paths (``test_connection``, ``diagnose``) can set
``bypass_budget=True`` to skip layers 1–3 and surface the actual
Salesforce response even when budgets are exhausted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Generator

import frappe
import requests
from frappe.utils import get_datetime, now_datetime

from .auth import SalesforceAuth
from .exceptions import (
    SalesforceAPIError,
    SalesforceBudgetExceeded,
    SalesforceRateLimitError,
)

DEFAULT_API_VERSION = "v60.0"
DEFAULT_TIMEOUT = 60
RATE_LIMIT_ABORT_THRESHOLD = 0.9  # abort if >90% of daily org API limit used
PREFLIGHT_FRESHNESS_SECONDS = 300  # cached usage is "fresh" for 5 min
_DAILY_COUNTER_CACHE_KEY = "frappe_salesforce:api_calls:{date}"


class SalesforceClient:
    """Thin wrapper over Salesforce REST API with SOQL helpers."""

    def __init__(self, bypass_budget: bool = False):
        self.bypass_budget = bypass_budget
        self.auth = SalesforceAuth()
        self.token, self.instance_url = self.auth.get_access_token()
        self.api_version = (
            frappe.db.get_single_value("Salesforce Settings", "api_version")
            or DEFAULT_API_VERSION
        )
        self._rate_limit_info: dict[str, int] | None = None
        self._calls_this_tick: int = 0
        self._settings_cache: Any | None = None
        #: Cache of accessible-field name sets per SF object, keyed by
        #: object API name. Populated lazily by ``accessible_fields()``.
        #: One ``/sobjects/<X>/describe/`` call per object per process.
        self._field_cache: dict[str, set[str]] = {}
        if not self.bypass_budget:
            self._preflight_check()

    def accessible_fields(self, sobject: str) -> set[str]:
        """Return the case-preserved set of SF field names the integration
        user can SELECT from ``sobject``.

        Result is cached for the life of this client instance. Used by
        ``BaseSyncer._soql_fields()`` to defensively filter out fields
        that are FLS-restricted on this org — preventing
        ``INVALID_FIELD`` 400s that would abort the entire sync.
        """
        if sobject in self._field_cache:
            return self._field_cache[sobject]
        url = f"{self._base()}/sobjects/{sobject}/describe/"
        try:
            data = self._get(url).json()
        except SalesforceAPIError as e:
            # If describe fails we can't filter — return an empty set,
            # which the syncer interprets as "don't filter, send all
            # mapped fields and accept the 400 risk". This is a
            # deliberate fail-open: better to attempt the sync and log a
            # 400 than to skip the object entirely.
            frappe.log_error(
                title=f"SF describe failed for {sobject}",
                message=str(e),
            )
            self._field_cache[sobject] = set()
            return set()
        names = {f.get("name") for f in data.get("fields", []) if f.get("name")}
        self._field_cache[sobject] = names
        return names

    # ------------------------------------------------------------------
    # SOQL
    # ------------------------------------------------------------------
    def query(
        self,
        soql: str,
        include_deleted: bool = False,
    ) -> Generator[dict[str, Any], None, None]:
        """Execute a SOQL query, yielding records and auto-paginating."""
        path = "queryAll" if include_deleted else "query"
        url = f"{self._base()}/{path}"
        params: dict[str, str] | None = {"q": soql}
        while url:
            data = self._get(url, params=params).json()
            for rec in data.get("records", []):
                yield rec
            if data.get("done", True):
                break
            next_url = data.get("nextRecordsUrl")
            if not next_url:
                break
            url = f"{self.instance_url}{next_url}"
            params = None  # subsequent pages include the query in the URL

    def get_deleted(self, sobject: str, start: str, end: str) -> dict[str, Any]:
        """Return records deleted between ``start`` and ``end`` (ISO-8601 UTC)."""
        url = f"{self._base()}/sobjects/{sobject}/deleted/"
        return self._get(url, params={"start": start, "end": end}).json()

    # ------------------------------------------------------------------
    # Quota accounting
    # ------------------------------------------------------------------
    @property
    def calls_this_tick(self) -> int:
        return self._calls_this_tick

    def _settings(self):
        if self._settings_cache is None:
            self._settings_cache = frappe.get_cached_doc("Salesforce Settings")
        return self._settings_cache

    def _preflight_check(self) -> None:
        """Refuse to make any call if cached usage is high and fresh."""
        s = self._settings()
        used = s.get("last_api_usage_used") or 0
        limit = s.get("last_api_usage_limit") or 0
        observed_at = s.get("last_api_usage_at")
        threshold_pct = s.get("preflight_threshold") or 80
        if not (used and limit and observed_at):
            return
        age = (now_datetime() - get_datetime(observed_at)).total_seconds()
        if age > PREFLIGHT_FRESHNESS_SECONDS:
            return
        pct = (used / limit) * 100 if limit else 0
        if pct >= float(threshold_pct):
            raise SalesforceBudgetExceeded(
                f"Preflight: Salesforce API usage at {used}/{limit} "
                f"({pct:.1f}%, observed {int(age)}s ago) is at/above "
                f"the {threshold_pct}% skip threshold. No calls made."
            )

    def _enforce_budget(self) -> None:
        if self.bypass_budget:
            return
        s = self._settings()
        per_tick = int(s.get("max_calls_per_tick") or 500)
        per_day = int(s.get("max_calls_per_day") or 50_000)
        if self._calls_this_tick >= per_tick:
            raise SalesforceBudgetExceeded(
                f"Per-tick budget of {per_tick} calls reached; aborting sync."
            )
        day_count = _daily_counter_get()
        if day_count >= per_day:
            raise SalesforceBudgetExceeded(
                f"Per-day budget of {per_day} calls reached ({day_count} used); "
                f"aborting sync."
            )

    # ------------------------------------------------------------------
    # Raw helpers
    # ------------------------------------------------------------------
    def _base(self) -> str:
        return f"{self.instance_url}/services/data/{self.api_version}"

    def _get(self, url: str, params: dict | None = None, _retried: bool = False):
        self._enforce_budget()
        try:
            resp = requests.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise SalesforceAPIError(f"Network error calling {url}: {e}") from e

        # Count every attempted round-trip (success or failure) — they all
        # consume API quota on Salesforce's side.
        self._calls_this_tick += 1
        if not self.bypass_budget:
            _daily_counter_incr()

        if resp.status_code == 401 and not _retried:
            self.auth.invalidate_cached_token()
            self.token, self.instance_url = self.auth.get_access_token()
            return self._get(url, params=params, _retried=True)

        if resp.status_code >= 400:
            raise SalesforceAPIError(
                f"Salesforce API call failed ({resp.status_code}): {resp.text}",
                status_code=resp.status_code,
                payload=_safe_json(resp),
            )

        self._record_rate_limit(resp)
        return resp

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _record_rate_limit(self, resp: requests.Response) -> None:
        header = resp.headers.get("Sforce-Limit-Info")
        if not header:
            return
        # Format: "api-usage=123/15000"
        try:
            part = [p for p in header.split(",") if "api-usage" in p][0]
            used_str, limit_str = part.split("=")[1].split("/")
            used, limit = int(used_str), int(limit_str)
        except (IndexError, ValueError):
            return
        self._rate_limit_info = {"used": used, "limit": limit}
        # Persist for the next tick's preflight check. Best-effort — never
        # let a write failure kill a sync.
        try:
            frappe.db.set_single_value(
                "Salesforce Settings", "last_api_usage_used", used
            )
            frappe.db.set_single_value(
                "Salesforce Settings", "last_api_usage_limit", limit
            )
            frappe.db.set_single_value(
                "Salesforce Settings", "last_api_usage_at", now_datetime()
            )
        except Exception:
            frappe.log_error(
                title="SF sync: failed to persist last_api_usage",
                message=frappe.get_traceback(),
            )
        if limit and used / limit >= RATE_LIMIT_ABORT_THRESHOLD:
            raise SalesforceRateLimitError(
                f"Salesforce API usage at {used}/{limit}; aborting sync.",
                status_code=429,
            )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    @property
    def rate_limit_info(self) -> dict[str, int] | None:
        return self._rate_limit_info


# ----------------------------------------------------------------------
# Daily counter (app-level, UTC-day rollover)
# ----------------------------------------------------------------------
def _daily_counter_key() -> str:
    return _DAILY_COUNTER_CACHE_KEY.format(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )


def _daily_counter_get() -> int:
    try:
        val = frappe.cache.get_value(_daily_counter_key())
        return int(val) if val else 0
    except Exception:
        return 0


def _daily_counter_incr() -> int:
    key = _daily_counter_key()
    try:
        # 36h expiry covers the UTC rollover edge comfortably.
        new = frappe.cache.incr(key)
        if new == 1:
            frappe.cache.expire(key, 36 * 60 * 60)
        return int(new)
    except Exception:
        # Cache backends without incr — fall back to get/set.
        cur = _daily_counter_get() + 1
        try:
            frappe.cache.set_value(key, cur, expires_in_sec=36 * 60 * 60)
        except Exception:
            pass
        return cur


def _safe_json(resp: requests.Response):
    try:
        return resp.json()
    except ValueError:
        return None
