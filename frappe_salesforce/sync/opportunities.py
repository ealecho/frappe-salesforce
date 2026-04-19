"""Opportunity → CRM Deal syncer."""

from .base import BaseSyncer


class OpportunitySyncer(BaseSyncer):
    salesforce_object = "Opportunity"
    frappe_doctype = "CRM Deal"
    high_water_field = "last_sync_opportunity"
    order_in_sync = 50
