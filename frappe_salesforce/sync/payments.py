"""npe01__OppPayment__c → SF Opportunity Payment syncer.

Runs after OpportunitySyncer so ``npe01__Opportunity__c`` resolves to a
``CRM Deal`` via the polymorphic_lookup transform.
"""

from .base import BaseSyncer


class PaymentSyncer(BaseSyncer):
    salesforce_object = "npe01__OppPayment__c"
    frappe_doctype = "SF Opportunity Payment"
    high_water_field = "last_sync_payment"
    order_in_sync = 58
