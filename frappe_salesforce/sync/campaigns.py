"""Campaign → SF Campaign syncer.

Runs before Opportunity/Recurring Donation so campaign FKs resolve in a
single pass. Campaign self-reference (``ParentId``) within the same run
is best-effort: unresolved parents fill on the next incremental sync.
"""

from .base import BaseSyncer


class CampaignSyncer(BaseSyncer):
    salesforce_object = "Campaign"
    frappe_doctype = "SF Campaign"
    high_water_field = "last_sync_campaign"
    order_in_sync = 15
