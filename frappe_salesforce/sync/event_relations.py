"""EventRelation → SF Event Invitee syncer.

WARNING: ``EventRelation`` is queryable but some orgs report no
``SystemModstamp`` field on it. The base incremental SOQL builder relies
on ``SystemModstamp`` for both filtering and ordering — if the org
rejects the query, an admin must either:

  * Disable this syncer by removing the ``EventRelation`` field mapping, or
  * Subclass and override the SOQL to use ``LastModifiedDate`` instead.

Kept enabled by default because most modern orgs expose SystemModstamp.

The ``RelationId`` polymorphic reference is resolved here (not via two
duplicate mapping rows) so that the ``Salesforce Field Mapping`` validator
remains strict about unique ``sf_field`` per mapping — same approach as
``TaskSyncer`` / ``EventSyncer`` use for ``WhoId``/``WhatId``.
"""

from __future__ import annotations

from typing import Any

from .base import BaseSyncer
from .transforms import lookup_record_link


class EventRelationSyncer(BaseSyncer):
    salesforce_object = "EventRelation"
    frappe_doctype = "SF Event Invitee"
    high_water_field = "last_sync_event_relation"
    order_in_sync = 75

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        """Populate ``invitee_doctype`` from RelationId via Salesforce Record Link.

        ``invitee`` (the docname) is already set via the mapping row using
        the ``polymorphic_lookup`` transform.
        """
        link = lookup_record_link(rec.get("RelationId"))
        if link and link.get("frappe_doctype"):
            values["invitee_doctype"] = link["frappe_doctype"]
        return values
