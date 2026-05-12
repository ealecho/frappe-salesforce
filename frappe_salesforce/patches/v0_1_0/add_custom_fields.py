"""Create the v0.1.0 custom_sf_* fields on existing sites."""

from __future__ import annotations

from frappe_salesforce.setup.custom_fields import ensure_all_custom_fields


def execute() -> None:
    ensure_all_custom_fields()
