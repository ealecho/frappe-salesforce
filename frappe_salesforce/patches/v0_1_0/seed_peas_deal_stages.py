"""Seed the PEAS-mirror CRM Deal Status records on existing sites.

Creates a CRM Deal Status per active Salesforce stage (Research … Reporting
Delivered) with the exact SF probability, so synced deals show the same
probability as Salesforce once ``peas_crm`` derives it from the status.
Runs before the Opportunity re-sync that moves deals onto these statuses.
"""

from __future__ import annotations

from frappe_salesforce.setup.deal_statuses import ensure_peas_deal_statuses


def execute() -> None:
    ensure_peas_deal_statuses()
