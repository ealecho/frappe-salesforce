"""Account → CRM Organization syncer."""

from .base import BaseSyncer


class AccountSyncer(BaseSyncer):
    salesforce_object = "Account"
    frappe_doctype = "CRM Organization"
    high_water_field = "last_sync_account"
    order_in_sync = 20
