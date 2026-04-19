"""Ordered registry of syncers run per incremental sync."""

from __future__ import annotations

from .accounts import AccountSyncer
from .activities import EventSyncer, TaskSyncer
from .contacts import ContactSyncer
from .leads import LeadSyncer
from .opportunities import OpportunitySyncer
from .users import UserSyncer

SYNCERS = sorted(
    [
        UserSyncer,
        AccountSyncer,
        ContactSyncer,
        LeadSyncer,
        OpportunitySyncer,
        TaskSyncer,
        EventSyncer,
    ],
    key=lambda s: s.order_in_sync,
)
