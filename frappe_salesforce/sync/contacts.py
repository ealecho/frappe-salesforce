"""Contact → Contact syncer."""

from .base import BaseSyncer


class ContactSyncer(BaseSyncer):
    salesforce_object = "Contact"
    frappe_doctype = "Contact"
    high_water_field = "last_sync_contact"
    order_in_sync = 30
