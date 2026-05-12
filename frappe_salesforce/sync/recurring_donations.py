"""npe03__Recurring_Donation__c → SF Recurring Donation syncer.

Depends on Account, Contact, and Campaign syncers having already linked
their records this tick — otherwise FK transforms resolve to None and the
links populate on the next run.
"""

from .base import BaseSyncer


class RecurringDonationSyncer(BaseSyncer):
    salesforce_object = "npe03__Recurring_Donation__c"
    frappe_doctype = "SF Recurring Donation"
    high_water_field = "last_sync_recurring_donation"
    order_in_sync = 55
