"""Incremental sync orchestrator."""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.exceptions import SalesforceError
from frappe_salesforce.sync.registry import SYNCERS


class IncrementalSyncRunner:
    """Run all registered syncers in order, recording a Sync Log."""

    def run(self) -> str:
        log = self._create_log()
        try:
            client = SalesforceClient()
        except SalesforceError as e:
            log.status = "Failed"
            log.error_summary = f"Auth failure: {e}"
            log.end_time = now_datetime()
            log.save(ignore_permissions=True)
            frappe.db.commit()
            return log.name

        had_failure = False
        for SyncerCls in SYNCERS:
            item = log.append(
                "items",
                {
                    "salesforce_object": SyncerCls.salesforce_object,
                    "fetched": 0,
                    "created": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                },
            )
            try:
                SyncerCls(client, item).run()
            except Exception as e:  # noqa: BLE001
                had_failure = True
                item.error_summary = str(e)[:500]
                frappe.log_error(
                    title=f"SF syncer {SyncerCls.salesforce_object} failed",
                    message=frappe.get_traceback() or str(e),
                )
                # Commit partial progress so HWM advances survive.
                frappe.db.commit()

        log.end_time = now_datetime()
        log.status = "Partial" if had_failure else "Success"
        log.save(ignore_permissions=True)
        frappe.db.commit()
        return log.name

    def _create_log(self):
        log = frappe.new_doc("Salesforce Sync Log")
        log.start_time = now_datetime()
        log.triggered_by = "Scheduler" if not frappe.flags.in_manual_sync else "Manual"
        log.status = "Running"
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log
