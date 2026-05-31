"""Contact → Contact syncer."""

from __future__ import annotations

from typing import Any

import frappe

from .addresses import upsert_address_for_record
from .base import BaseSyncer


class ContactSyncer(BaseSyncer):
    salesforce_object = "Contact"
    frappe_doctype = "Contact"
    high_water_field = "last_sync_contact"
    order_in_sync = 30

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        # Frappe Contact requires either first_name or last_name; if both are
        # blank fall back to a placeholder so the record can be saved. SF
        # only requires LastName, but imported / form-captured Contacts
        # sometimes lack both.
        if not values.get("first_name") and not values.get("last_name"):
            values["last_name"] = (
                rec.get("Name") or rec.get("Email") or rec.get("Id") or "(unknown)"
            )
        return values

    def after_upsert(self, rec: dict[str, Any], doc) -> None:
        # Mailing + Other address blocks → Frappe Address docs.
        for prefix in ("Mailing", "Other"):
            upsert_address_for_record(
                parent_doctype=self.frappe_doctype,
                parent_name=doc.name,
                prefix=prefix,
                sf_record=rec,
            )
        # Link the Contact to its CRM Organization via the ``links`` table
        # (Frappe's Dynamic Link mechanism). ``company_name`` only stores
        # the org's display name; this is what makes Contact ↔ Org navigable.
        org = doc.get("company_name")
        if org and frappe.db.exists("CRM Organization", org):
            self._ensure_link(doc, "CRM Organization", org)

    def _ensure_link(self, doc, link_doctype: str, link_name: str) -> None:
        for row in doc.get("links") or []:
            if row.link_doctype == link_doctype and row.link_name == link_name:
                return
        doc.append(
            "links",
            {"link_doctype": link_doctype, "link_name": link_name},
        )
        doc.save(ignore_permissions=True)
