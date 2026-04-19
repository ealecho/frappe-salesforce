"""Lead → CRM Lead syncer."""

from .base import BaseSyncer


class LeadSyncer(BaseSyncer):
    salesforce_object = "Lead"
    frappe_doctype = "CRM Lead"
    high_water_field = "last_sync_lead"
    order_in_sync = 40
    # Skip converted leads by default; they are represented via Contact+Account+Opportunity.
    extra_where = "IsConverted = false"
