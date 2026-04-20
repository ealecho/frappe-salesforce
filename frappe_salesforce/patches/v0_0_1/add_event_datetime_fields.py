"""Add custom_sf_start_datetime and custom_sf_end_datetime to CRM Task."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    create_custom_fields(
        {
            "CRM Task": [
                {
                    "fieldname": "custom_sf_start_datetime",
                    "label": "SF Event Start",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "no_copy": 1,
                },
                {
                    "fieldname": "custom_sf_end_datetime",
                    "label": "SF Event End",
                    "fieldtype": "Datetime",
                    "read_only": 1,
                    "no_copy": 1,
                },
            ]
        },
        ignore_validate=True,
    )
    frappe.db.commit()
