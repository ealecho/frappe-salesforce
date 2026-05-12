"""npe5__Affiliation__c → SF Contact Affiliation syncer."""

from .base import BaseSyncer


class AffiliationSyncer(BaseSyncer):
    salesforce_object = "npe5__Affiliation__c"
    frappe_doctype = "SF Contact Affiliation"
    high_water_field = "last_sync_affiliation"
    order_in_sync = 68
