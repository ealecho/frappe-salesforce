"""EventRelation → SF Event Invitee syncer.

WARNING: ``EventRelation`` is queryable but some orgs report no
``SystemModstamp`` field on it. The base incremental SOQL builder relies
on ``SystemModstamp`` for both filtering and ordering — if the org
rejects the query, an admin must either:

  * Disable this syncer by removing the ``EventRelation`` field mapping, or
  * Subclass and override the SOQL to use ``LastModifiedDate`` instead.

Kept enabled by default because most modern orgs expose SystemModstamp.
"""

from .base import BaseSyncer


class EventRelationSyncer(BaseSyncer):
    salesforce_object = "EventRelation"
    frappe_doctype = "SF Event Invitee"
    high_water_field = "last_sync_event_relation"
    order_in_sync = 75
