"""before_uninstall hook."""

from __future__ import annotations

import frappe


def before_uninstall() -> None:
    """Best-effort cleanup before uninstall."""
    # Intentionally do NOT delete linked CRM data. Only clean up app-owned docs.
    for doctype in [
        "Salesforce Sync Log",
        "Salesforce Record Link",
        "Salesforce Field Mapping",
    ]:
        try:
            frappe.db.delete(doctype)
        except Exception:
            pass
    frappe.db.commit()
