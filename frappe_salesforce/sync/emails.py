"""EmailMessage → Communication syncer.

Salesforce keeps a logged email in two places: a lightweight activity
entry (a ``Task`` with ``TaskSubtype='Email'`` — synced by ``TaskSyncer``
into the deal's Tasks tab) and the full message as an ``EmailMessage``
(sender, recipients, complete body). This syncer brings the full message
across as a Frappe ``Communication``, which is what the CRM's Emails tab
renders — so correspondence reads as email, not as a task log line.

No ``Salesforce Field Mapping`` doc is used: EmailMessage's shape is
fixed and every field feeds a computed Communication value, so the field
list lives in ``extra_soql_fields`` and the mapping happens in
``build_communication_values`` (pure, unit-testable).

Emails whose ``RelatedToId`` doesn't resolve to a synced record are
skipped (counted in the sync log): an unanchored Communication shows up
nowhere in the CRM and would only pollute the table.

Unlike Tasks/Events, EmailMessage records are NOT subject to Salesforce
activity archival — full history is queryable, which is what the one-off
``backfill_all_email_messages`` (enqueued by patch) pulls in.
"""

from __future__ import annotations

from typing import Any

import frappe

from .base import BaseSyncer
from .transforms import build_communication_values, lookup_record_link


class EmailMessageSyncer(BaseSyncer):
    salesforce_object = "EmailMessage"
    frappe_doctype = "Communication"
    high_water_field = "last_sync_email_message"
    order_in_sync = 80  # after Opportunity: references must already exist
    extra_soql_fields = (
        "Subject",
        "TextBody",
        "HtmlBody",
        "FromAddress",
        "FromName",
        "ToAddress",
        "CcAddress",
        "BccAddress",
        "MessageDate",
        "Incoming",
        "RelatedToId",
    )

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        values.update(build_communication_values(rec))
        link = lookup_record_link(rec.get("RelatedToId"))
        if link and link.get("frappe_name"):
            values["reference_doctype"] = link["frappe_doctype"]
            values["reference_name"] = link["frappe_name"]
        else:
            # Nothing in the CRM to hang this email on — skip it.
            values["__skip__"] = True
        return values


# ----------------------------------------------------------------------
# One-off history pull (enqueued by patches/v0_1_0/backfill_email_messages)
# ----------------------------------------------------------------------
def backfill_all_email_messages() -> None:
    """Import every SF EmailMessage from the beginning of time.

    Runs on the long queue; per-record failures are logged and skipped by
    ``_import_query``. Safe to re-run — records upsert by SF Id.
    """
    from frappe_salesforce.salesforce.client import SalesforceClient
    from frappe_salesforce.salesforce.soql import build_incremental_query
    from frappe_salesforce.tasks.retention_backfill import EPOCH, _import_query

    if not frappe.db.get_single_value("Salesforce Settings", "enabled"):
        return
    # The enqueuing patch runs BEFORE after_migrate seeds custom fields,
    # and the worker can pick this job up in that window — first run on
    # peasuk-dev hit exactly that: 858 upserts failed on "Unknown column
    # 'custom_salesforce_id'". Self-heal instead of racing.
    if not frappe.get_meta("Communication").get_field("custom_salesforce_id"):
        from frappe_salesforce.setup.custom_fields import ensure_all_custom_fields

        ensure_all_custom_fields()
        frappe.clear_cache(doctype="Communication")
    client = SalesforceClient()
    syncer = EmailMessageSyncer(client, frappe._dict())
    soql = build_incremental_query(
        sobject="EmailMessage", fields=syncer._soql_fields(), since=EPOCH
    )
    imported, failed = _import_query(syncer, client, soql, None)
    frappe.log_error(
        title="EmailMessage backfill finished",
        message=f"imported={imported} failed={failed}",
    )
