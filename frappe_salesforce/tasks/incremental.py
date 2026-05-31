"""Incremental sync orchestrator."""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.exceptions import (
    SalesforceBudgetExceeded,
    SalesforceError,
    SalesforceRateLimitError,
)
from frappe_salesforce.setup.default_mappings import (
    SalesforceMappingSetupError,
    ensure_default_field_mappings,
)
from frappe_salesforce.sync.registry import SYNCERS


class IncrementalSyncRunner:
    """Run all registered syncers in order, recording a Sync Log."""

    def run(self) -> str:
        log = self._create_log()
        try:
            ensure_default_field_mappings()
        except SalesforceMappingSetupError as e:
            log.status = "Failed"
            log.error_summary = str(e)[:500]
            log.end_time = now_datetime()
            log.save(ignore_permissions=True)
            frappe.db.commit()
            return log.name
        try:
            client = SalesforceClient()
        except SalesforceBudgetExceeded as e:
            # Preflight tripped: cached SF usage is hot. Log cleanly and
            # bail without making any API call.
            log.status = "Skipped"
            log.error_summary = f"Preflight skip: {e}"
            log.end_time = now_datetime()
            log.save(ignore_permissions=True)
            frappe.db.commit()
            return log.name
        except SalesforceError as e:
            log.status = "Failed"
            log.error_summary = f"Auth failure: {e}"
            log.end_time = now_datetime()
            log.save(ignore_permissions=True)
            frappe.db.commit()
            return log.name

        had_failure = False
        budget_stop: str | None = None
        for SyncerCls in SYNCERS:
            if budget_stop:
                # Budget tripped earlier in this tick; skip remaining
                # syncers so the next tick can pick up where we left off.
                break
            item = log.append(
                "items",
                {
                    "salesforce_object": SyncerCls.salesforce_object,
                    "fetched": 0,
                    "created": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "api_calls_used": 0,
                },
            )
            try:
                SyncerCls(client, item).run()
            except (SalesforceBudgetExceeded, SalesforceRateLimitError) as e:
                budget_stop = str(e)
                item.error_summary = str(e)[:500]
                # Not a "failure" in the data sense — quota guardrail
                # fired. Mark the log Partial but don't alarm.
                had_failure = True
                frappe.db.commit()
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
        if budget_stop:
            log.status = "Partial"
            log.error_summary = f"Budget/quota guard: {budget_stop}"
        else:
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
