"""Wire ``salutation_link`` transform onto existing Lead / Contact mapping rows.

Salesforce stores salutations with a trailing period (``"Mr."``,
``"Mrs."``, ``"Dr."``) but Frappe's standard ``Salutation`` rows are
period-less. Up to v0.1.9 the Salutation field synced as a raw passthrough,
producing ``LinkValidationError: Could not find Salutation: Mr.`` on
every Contact / Lead with a populated SF salutation. v0.1.10 ships a
``salutation_link`` transform that strips the trailing period and
auto-creates any genuinely novel salutation row.

The seed file ``setup/default_mappings.py`` is consulted only on fresh
install; existing sites need this patch to backfill the transform onto
already-installed mapping rows.

Idempotent: only rewrites rows whose ``transform`` is currently empty.
Leaves any operator-customised value (including an already-correct
``salutation_link``) untouched.
"""

from __future__ import annotations

import frappe

# (sf_object, sf_field, frappe_field, new_transform)
_REWRITES: list[tuple[str, str, str, str]] = [
    ("Contact", "Salutation", "salutation", "salutation_link"),
    ("Lead", "Salutation", "salutation", "salutation_link"),
]


def execute() -> None:
    if not frappe.db.exists("DocType", "Salesforce Field Mapping"):
        return

    by_object: dict[str, list[tuple[str, str, str]]] = {}
    for sf_object, sf_field, frappe_field, new in _REWRITES:
        by_object.setdefault(sf_object, []).append((sf_field, frappe_field, new))

    for sf_object, rules in by_object.items():
        name = frappe.db.get_value(
            "Salesforce Field Mapping", {"salesforce_object": sf_object}, "name"
        )
        if not name:
            continue
        doc = frappe.get_doc("Salesforce Field Mapping", name)
        changed = False
        for row in doc.field_mappings:
            for sf_field, frappe_field, new in rules:
                if (
                    row.sf_field == sf_field
                    and row.frappe_field == frappe_field
                    and not (row.transform or "").strip()
                ):
                    row.transform = new
                    changed = True
        if changed:
            doc.save(ignore_permissions=True)
            frappe.db.commit()
