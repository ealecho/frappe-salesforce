"""Account → CRM Organization syncer."""

from __future__ import annotations

from typing import Any

from .addresses import upsert_addresses
from .base import BaseSyncer


class AccountSyncer(BaseSyncer):
    salesforce_object = "Account"
    frappe_doctype = "CRM Organization"
    high_water_field = "last_sync_account"
    order_in_sync = 20

    #: SF compound-address prefixes to materialise as Frappe Address docs.
    address_prefixes = ("Billing", "Shipping")

    def after_upsert(self, rec: dict[str, Any], frappe_name: str) -> None:
        upsert_addresses(
            self.frappe_doctype,
            frappe_name,
            rec,
            self.address_prefixes,
        )
