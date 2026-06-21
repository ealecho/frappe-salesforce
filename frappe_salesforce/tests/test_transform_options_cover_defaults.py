"""The Salesforce Field Mapping Row ``transform`` Select must list every
transform the default mappings actually use.

Regression guard for the migrate failure where ``salutation_link`` was used
by the default Contact/Lead mappings (and the ``wire_salutation_link``
patch) but was absent from the doctype's ``transform`` options, so seeding
the Contact mapping raised ``ValidationError: Transform cannot be
"salutation_link"`` and aborted ``bench migrate``. Needs no site.
"""

from __future__ import annotations

import json
from pathlib import Path

from frappe_salesforce.setup.default_mappings import DEFAULT_MAPPINGS

_DOCTYPE_JSON = (
    Path(__file__).resolve().parents[1]
    / "frappe_salesforce"
    / "doctype"
    / "salesforce_field_mapping_row"
    / "salesforce_field_mapping_row.json"
)


def _transform_options() -> set[str]:
    data = json.loads(_DOCTYPE_JSON.read_text())
    for field in data["fields"]:
        if field.get("fieldname") == "transform":
            return {line.strip() for line in field["options"].splitlines() if line.strip()}
    raise AssertionError("transform field not found in doctype JSON")


def test_default_mapping_transforms_are_valid_options():
    options = _transform_options()
    used = {
        row.get("transform")
        for mapping in DEFAULT_MAPPINGS
        for row in mapping["rows"]
        if row.get("transform")
    }
    missing = sorted(used - options)
    assert not missing, (
        f"transforms used by DEFAULT_MAPPINGS but missing from the "
        f"Salesforce Field Mapping Row 'transform' options: {missing}"
    )
