"""Ensure custom_salesforce_id custom fields exist on target doctypes.

Idempotent; safe to run repeatedly.
"""

from __future__ import annotations

from frappe_salesforce.setup.install import _ensure_custom_fields


def execute() -> None:
    _ensure_custom_fields()
