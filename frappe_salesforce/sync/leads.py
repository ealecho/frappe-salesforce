"""Lead → CRM Lead syncer.

Note on conversion handling: we no longer filter out converted leads at the
SOQL level. Converted leads must still arrive so we can mark them converted
in Frappe and surface the resulting Account/Contact/Opportunity links.
"""

from __future__ import annotations

from typing import Any

from .addresses import upsert_addresses
from .base import BaseSyncer

# SF Status values that indicate a converted lead. We deliberately also key
# off the ``IsConverted`` boolean (set in enrich_values) so picklist renames
# don't break us.
_CONVERTED_FRAPPE_STATUS = "Converted"


class LeadSyncer(BaseSyncer):
    salesforce_object = "Lead"
    frappe_doctype = "CRM Lead"
    high_water_field = "last_sync_lead"
    order_in_sync = 40
    # We no longer skip converted leads — see module docstring.

    address_prefixes = ("",)  # Leads use bare Street/City/State/PostalCode/Country

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        # Frappe CRM marks first_name as mandatory, but Salesforce only
        # requires LastName. Imported / form-captured leads frequently have
        # no FirstName at all; fill in a placeholder so the doc passes
        # validation without polluting display with junk text.
        if not (values.get("first_name") or "").strip():
            values["first_name"] = "-"
        if rec.get("IsConverted"):
            values["status"] = _CONVERTED_FRAPPE_STATUS
            values["custom_sf_converted_account"] = rec.get("ConvertedAccountId")
            values["custom_sf_converted_contact"] = rec.get("ConvertedContactId")
            values["custom_sf_converted_opportunity"] = rec.get(
                "ConvertedOpportunityId"
            )
            if rec.get("ConvertedDate"):
                values["custom_sf_converted_date"] = rec["ConvertedDate"]
        return values

    def after_upsert(self, rec: dict[str, Any], frappe_name: str) -> None:
        # Lead has unprefixed address fields (Street, City, ...).
        upsert_addresses(
            self.frappe_doctype,
            frappe_name,
            rec,
            self.address_prefixes,
        )
