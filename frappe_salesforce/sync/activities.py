"""Activities syncer: Salesforce Task + Event → CRM Task.

Both SF ``Task`` and ``Event`` are upserted as CRM Tasks. A custom field
``custom_sf_activity_type`` distinguishes them. Polymorphic ``WhoId``/``WhatId``
links are resolved via Salesforce Record Link.
"""

from __future__ import annotations

from typing import Any

from .base import BaseSyncer
from .transforms import lookup_record_link


class ActivitySyncerMixin:
    """Shared polymorphic reference resolution for Task + Event."""

    def _resolve_reference(self, sf_id: str | None) -> tuple[str | None, str | None]:
        """Return ``(doctype, name)`` for a SF polymorphic reference or ``(None, None)``."""
        if not sf_id:
            return None, None
        link = lookup_record_link(sf_id)
        if not link:
            return None, None
        return link.get("frappe_doctype"), link.get("frappe_name")

    def _apply_closed_status(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> None:
        """Force ``status="Done"`` on closed Tasks/Events."""
        if rec.get("IsClosed") or rec.get("CompletedDateTime"):
            values["status"] = "Done"


class TaskSyncer(ActivitySyncerMixin, BaseSyncer):
    salesforce_object = "Task"
    frappe_doctype = "CRM Task"
    high_water_field = "last_sync_task"
    order_in_sync = 60
    extra_soql_fields = ("WhoId", "WhatId", "IsClosed", "CompletedDateTime")

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        values["custom_sf_activity_type"] = "Task"
        ref_dt, ref_name = self._resolve_reference(
            rec.get("WhatId") or rec.get("WhoId")
        )
        if ref_dt and ref_name:
            values["reference_doctype"] = ref_dt
            values["reference_docname"] = ref_name
        self._apply_closed_status(rec, values)
        return values


class EventSyncer(ActivitySyncerMixin, BaseSyncer):
    salesforce_object = "Event"
    frappe_doctype = "CRM Task"
    high_water_field = "last_sync_event"
    order_in_sync = 70
    extra_soql_fields = ("WhoId", "WhatId", "OwnerId")

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        values["custom_sf_activity_type"] = "Event"
        ref_dt, ref_name = self._resolve_reference(
            rec.get("WhatId") or rec.get("WhoId")
        )
        if ref_dt and ref_name:
            values["reference_doctype"] = ref_dt
            values["reference_docname"] = ref_name
        # SF Event has no ``Status`` field — events are always "scheduled".
        # Treat them as "In Progress" until the start datetime has passed.
        # (Defensive: only set if mapping didn't set it.)
        if not values.get("status"):
            values["status"] = "Todo"
        return values
