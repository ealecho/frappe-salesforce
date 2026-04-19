"""User syncer: link-only (maps SF Users to existing Frappe Users by email)."""

from __future__ import annotations

import frappe

from .base import BaseSyncer


class UserSyncer(BaseSyncer):
    salesforce_object = "User"
    frappe_doctype = "User"
    high_water_field = "last_sync_user"
    order_in_sync = 10
    extra_where = "IsActive = true"
    link_only = True

    def _soql_fields(self) -> list[str]:
        # Link-only syncer: fetch a fixed set of fields regardless of mapping.
        return ["Id", "Username", "Email", "FirstName", "LastName", "IsActive"]

    def _resolve_link_only(self, rec: dict, values: dict) -> str | None:
        email = (rec.get("Email") or "").strip().lower()
        if not email:
            return None
        return frappe.db.get_value("User", {"email": email}, "name")
