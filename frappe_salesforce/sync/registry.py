"""Ordered registry of syncers run per incremental sync."""

from __future__ import annotations

from .accounts import AccountSyncer
from .activities import EventSyncer, TaskSyncer
from .affiliations import AffiliationSyncer
from .campaigns import CampaignSyncer
from .contacts import ContactSyncer
from .event_relations import EventRelationSyncer
from .leads import LeadSyncer
from .opportunities import OpportunitySyncer
from .payments import PaymentSyncer
from .recurring_donations import RecurringDonationSyncer
from .relationships import RelationshipSyncer
from .users import UserSyncer

SYNCERS = sorted(
    [
        UserSyncer,
        CampaignSyncer,
        AccountSyncer,
        ContactSyncer,
        LeadSyncer,
        OpportunitySyncer,
        RecurringDonationSyncer,
        PaymentSyncer,
        TaskSyncer,
        RelationshipSyncer,
        AffiliationSyncer,
        EventSyncer,
        EventRelationSyncer,
    ],
    key=lambda s: s.order_in_sync,
)
