"""Opportunity → CRM Deal syncer."""

from __future__ import annotations

from typing import Any

from .base import BaseSyncer
from .transforms import map_deal_lost_reason


class OpportunitySyncer(BaseSyncer):
    salesforce_object = "Opportunity"
    frappe_doctype = "CRM Deal"
    high_water_field = "last_sync_opportunity"
    order_in_sync = 50

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        """Derive ``lost_reason`` from ``StageName``.

        ``StageName`` already feeds ``status`` via the ``deal_stage`` mapping
        row. The Salesforce Field Mapping validator forbids duplicate
        ``sf_field`` per mapping, so we derive ``lost_reason`` here rather
        than via a second mapping row — same approach as TaskSyncer /
        EventSyncer / EventRelationSyncer.
        """
        reason = map_deal_lost_reason(rec.get("StageName"))
        if reason is not None:
            values["lost_reason"] = reason
        return values
