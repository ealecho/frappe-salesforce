"""npe4__Relationship__c → SF Contact Relationship syncer."""

from .base import BaseSyncer


class RelationshipSyncer(BaseSyncer):
    salesforce_object = "npe4__Relationship__c"
    frappe_doctype = "SF Contact Relationship"
    high_water_field = "last_sync_relationship"
    order_in_sync = 65
