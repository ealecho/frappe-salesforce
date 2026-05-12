"""Account → CRM Organization syncer."""

from __future__ import annotations

from typing import Any

from .addresses import upsert_address_for_record
from .base import BaseSyncer


class AccountSyncer(BaseSyncer):
    salesforce_object = "Account"
    frappe_doctype = "CRM Organization"
    high_water_field = "last_sync_account"
    order_in_sync = 20
    extra_soql_fields = ()  # all SF fields supplied via mapping rows

    def after_upsert(self, rec: dict[str, Any], doc) -> None:
        # Upsert Billing + Shipping Address docs and link them back to the
        # CRM Organization. Frappe ``Address`` docs are linked via
        # ``Dynamic Link`` rows (Address → many parents), not via a Link
        # field on the parent — so this lives in ``after_upsert``, not in
        # a regular mapping row.
        for prefix in ("Billing", "Shipping"):
            upsert_address_for_record(
                parent_doctype=self.frappe_doctype,
                parent_name=doc.name,
                prefix=prefix,
                sf_record=rec,
            )
