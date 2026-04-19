"""Salesforce REST + SOQL client with auto pagination and 401 refresh."""

from __future__ import annotations

from typing import Any, Generator

import frappe
import requests

from .auth import SalesforceAuth
from .exceptions import (
    SalesforceAPIError,
    SalesforceAuthError,
    SalesforceRateLimitError,
)

DEFAULT_API_VERSION = "v60.0"
DEFAULT_TIMEOUT = 60
RATE_LIMIT_ABORT_THRESHOLD = 0.9  # abort if >90% of daily API limit used


class SalesforceClient:
    """Thin wrapper over Salesforce REST API with SOQL helpers."""

    def __init__(self):
        self.auth = SalesforceAuth()
        self.token, self.instance_url = self.auth.get_access_token()
        self.api_version = (
            frappe.db.get_single_value("Salesforce Settings", "api_version")
            or DEFAULT_API_VERSION
        )
        self._rate_limit_info: dict[str, int] | None = None

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
    # Raw helpers
    # ------------------------------------------------------------------
    def _base(self) -> str:
        return f"{self.instance_url}/services/data/{self.api_version}"

    def _get(self, url: str, params: dict | None = None, _retried: bool = False):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise SalesforceAPIError(f"Network error calling {url}: {e}") from e

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


def _safe_json(resp: requests.Response):
    try:
        return resp.json()
    except ValueError:
        return None
