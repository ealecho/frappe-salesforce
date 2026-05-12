"""Contact → Contact syncer."""

from __future__ import annotations

from typing import Any

from .addresses import upsert_addresses
from .base import BaseSyncer


class ContactSyncer(BaseSyncer):
    salesforce_object = "Contact"
    frappe_doctype = "Contact"
    high_water_field = "last_sync_contact"
    order_in_sync = 30

    address_prefixes = ("Mailing", "Other")

    def after_upsert(self, rec: dict[str, Any], frappe_name: str) -> None:
        upsert_addresses(
            self.frappe_doctype,
            frappe_name,
            rec,
            self.address_prefixes,
        )
