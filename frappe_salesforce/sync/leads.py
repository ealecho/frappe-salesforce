"""Lead → CRM Lead syncer."""

from __future__ import annotations

from typing import Any

from .base import BaseSyncer


class LeadSyncer(BaseSyncer):
    salesforce_object = "Lead"
    frappe_doctype = "CRM Lead"
    high_water_field = "last_sync_lead"
    order_in_sync = 40
    # IsConverted is intentionally NOT filtered out — converted leads are
    # synced too so historical records exist in Frappe; ``status`` is
    # forced to ``"Converted"`` via ``enrich_values``.
    extra_soql_fields = ("IsConverted",)

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        # CRM Lead requires ``first_name``; SF Lead only requires LastName.
        # Mailchimp / form-captured Leads regularly lack a FirstName.
        if not values.get("first_name"):
            values["first_name"] = "-"

        # Force status="Converted" for converted Leads regardless of the
        # SF Status picklist value, so they're filterable in Frappe CRM.
        if rec.get("IsConverted"):
            values["status"] = "Converted"
            values["converted"] = 1

        return values
