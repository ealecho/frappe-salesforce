"""Seed CRM Deal Status records that mirror the PEAS Salesforce pipeline.

In this CRM, deal *probability* is derived from the deal *status* by the
``peas_crm`` app (``deal_hooks.set_probability_and_expected_amount`` →
``_set_probability_from_status``, which does
``doc.probability = int(CRM Deal Status.probability)`` on every save). So
to make a synced Opportunity show the same probability as Salesforce, the
CRM Deal Status it lands on must carry that probability.

We therefore mirror the active Salesforce ``OpportunityStage`` ladder 1:1
as CRM Deal Status records, with the exact SF ``DefaultProbability`` and
won/lost flags. ``OpportunitySyncer``'s ``deal_stage_link`` transform then
passes each SF stage through unchanged (see ``transforms.DEAL_STAGE_MAP``)
so it links to the matching status here.

Idempotent: creates missing statuses and converges existing ones to the
spec; never touches statuses outside this set.
"""

from __future__ import annotations

import frappe

#: SF OpportunityStage (active pipeline, SortOrder 1-9) mirrored as CRM
#: Deal Status. ``position`` follows the SF sort order; ``probability`` is
#: the SF ``DefaultProbability``; ``type`` reflects IsClosed/IsWon. Colour
#: is cosmetic (a rough cool→warm→closed gradient).
PEAS_DEAL_STATUSES: list[dict] = [
    {"deal_status": "Research", "type": "Open", "position": 1, "probability": 1, "color": "gray"},
    {"deal_status": "Cold proposal or positive meeting", "type": "Open", "position": 2, "probability": 5, "color": "blue"},
    {"deal_status": "Warm proposal to new funder", "type": "Open", "position": 3, "probability": 25, "color": "cyan"},
    {"deal_status": "Warm proposal to existing funder", "type": "Open", "position": 4, "probability": 50, "color": "teal"},
    {"deal_status": "Final stage proposal", "type": "Open", "position": 5, "probability": 75, "color": "amber"},
    {"deal_status": "Finalising", "type": "Open", "position": 6, "probability": 90, "color": "orange"},
    {"deal_status": "Won", "type": "Won", "position": 7, "probability": 100, "color": "green"},
    {"deal_status": "Lost", "type": "Lost", "position": 8, "probability": 0, "color": "red"},
    {"deal_status": "Reporting Delivered", "type": "Won", "position": 9, "probability": 100, "color": "violet"},
]


def ensure_peas_deal_statuses() -> None:
    """Create/converge the PEAS-mirror CRM Deal Status records. Idempotent."""
    for spec in PEAS_DEAL_STATUSES:
        name = spec["deal_status"]
        if frappe.db.exists("CRM Deal Status", name):
            doc = frappe.get_doc("CRM Deal Status", name)
            changed = False
            for key, value in spec.items():
                if doc.get(key) != value:
                    doc.set(key, value)
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "CRM Deal Status", **spec}).insert(
                ignore_permissions=True
            )
