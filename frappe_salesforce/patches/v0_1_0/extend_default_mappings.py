"""Additively backfill v0.1.0 default mapping rows on existing sites.

Existing ``Salesforce Field Mapping`` records get new rows from
``DEFAULT_MAPPINGS`` that aren't already present. Existing rows are
matched by ``(sf_field, frappe_field)`` and left untouched — this patch
NEVER overwrites or deletes user-customised mappings.

For Salesforce objects that have no mapping at all yet, the full default
is created.
"""

from __future__ import annotations

from frappe_salesforce.setup.default_mappings import ensure_default_field_mappings


def execute() -> None:
    ensure_default_field_mappings(validate=False)
