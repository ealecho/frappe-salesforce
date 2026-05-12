"""Ensure custom_salesforce_id custom fields exist on target doctypes.

Idempotent; safe to run repeatedly. In v0.0.2 the install logic was
consolidated into ``setup.custom_fields.ensure_all_custom_fields`` —
calling it here is a superset of the original behaviour and still
covers the ``custom_salesforce_id`` field this patch was written for.
"""

from __future__ import annotations

from frappe_salesforce.setup.custom_fields import ensure_all_custom_fields


def execute() -> None:
    ensure_all_custom_fields()
