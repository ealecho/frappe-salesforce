"""Backfill all Salesforce mirror custom fields on existing sites.

Idempotent — ``create_custom_fields`` upserts by ``(dt, fieldname)``.
"""

from __future__ import annotations

from frappe_salesforce.setup.custom_fields import ensure_all_custom_fields


def execute() -> None:
    ensure_all_custom_fields()
