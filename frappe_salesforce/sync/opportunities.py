"""Opportunity → CRM Deal syncer."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import get_datetime

from .base import BaseSyncer
from .transforms import map_contact


class OpportunitySyncer(BaseSyncer):
    salesforce_object = "Opportunity"
    frappe_doctype = "CRM Deal"
    high_water_field = "last_sync_opportunity"
    order_in_sync = 50
    extra_soql_fields = ("IsClosed", "CloseDate")

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        # Derive ``closed_date`` from ``IsClosed=true`` + ``CloseDate``;
        # mapping rows already populate ``expected_closure_date``.
        if rec.get("IsClosed") and rec.get("CloseDate"):
            try:
                values["closed_date"] = str(get_datetime(rec["CloseDate"]).date())
            except (TypeError, ValueError) as e:
                frappe.log_error(
                    title="OpportunitySyncer.enrich_values",
                    message=(
                        f"Unparseable CloseDate for SF Opportunity "
                        f"{rec.get('Id') or '?'}: {rec.get('CloseDate')!r}\n{e}"
                    ),
                )

        # Fallback contact resolution: if ContactId was empty, try the
        # NPSP primary-contact link.
        if not values.get("contact"):
            primary = rec.get("npsp__Primary_Contact__c")
            if primary:
                resolved = map_contact(primary)
                if resolved:
                    values["contact"] = resolved

        return values
