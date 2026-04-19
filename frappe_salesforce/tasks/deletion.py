"""Nightly deletion sweep using Salesforce getDeleted endpoint."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.soql import format_soql_datetime
from frappe_salesforce.sync.registry import SYNCERS

# Salesforce's getDeleted endpoint supports up to 30 days of history.
DEFAULT_WINDOW_HOURS = 26  # a little more than 24 to cover overlap


class DeletionSyncRunner:
    """Query SF for recently deleted records and remove Frappe counterparts."""

    def run(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> None:
        client = SalesforceClient()
        end = now_datetime()
        start = add_to_date(end, hours=-window_hours)
        start_s = format_soql_datetime(start)
        end_s = format_soql_datetime(end)

        for SyncerCls in SYNCERS:
            if SyncerCls.link_only:
                continue
            try:
                data = client.get_deleted(SyncerCls.salesforce_object, start_s, end_s)
            except Exception:
                frappe.log_error(
                    title=f"SF deletion fetch {SyncerCls.salesforce_object} failed",
                    message=frappe.get_traceback(),
                )
                continue
            for entry in data.get("deletedRecords", []):
                self._delete_frappe_doc(entry.get("id"), SyncerCls)

        frappe.db.commit()

    def _delete_frappe_doc(self, salesforce_id: str | None, SyncerCls) -> None:
        if not salesforce_id:
            return
        link = frappe.db.get_value(
            "Salesforce Record Link",
            {
                "salesforce_id": salesforce_id,
                "salesforce_object": SyncerCls.salesforce_object,
            },
            ["name", "frappe_doctype", "frappe_name"],
            as_dict=True,
        )
        if not link or not link.frappe_name:
            return
        try:
            if frappe.db.exists(link.frappe_doctype, link.frappe_name):
                frappe.delete_doc(
                    link.frappe_doctype,
                    link.frappe_name,
                    ignore_permissions=True,
                    delete_permanently=False,
                )
            frappe.delete_doc(
                "Salesforce Record Link",
                link.name,
                ignore_permissions=True,
            )
        except Exception:
            frappe.log_error(
                title=f"SF delete {link.frappe_doctype} {link.frappe_name}",
                message=frappe.get_traceback(),
            )
