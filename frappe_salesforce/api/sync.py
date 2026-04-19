"""Manual sync trigger + status endpoints."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def trigger_manual_sync():
    """Enqueue an immediate incremental sync run."""
    frappe.only_for("System Manager")
    frappe.enqueue(
        "frappe_salesforce.tasks.scheduled.run_incremental_sync",
        queue="long",
        timeout=3600,
        job_name="salesforce_manual_sync",
        enqueue_after_commit=True,
    )
    return {"queued": True}


@frappe.whitelist()
def get_sync_status():
    """Return the most recent Salesforce Sync Log summary."""
    frappe.only_for("System Manager")
    logs = frappe.get_all(
        "Salesforce Sync Log",
        fields=["name", "start_time", "end_time", "status", "triggered_by"],
        order_by="start_time desc",
        limit=1,
    )
    return logs[0] if logs else None
