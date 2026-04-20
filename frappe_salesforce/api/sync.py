"""Manual sync trigger + status endpoints."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def trigger_manual_sync():
    """Enqueue an immediate incremental sync run."""
    frappe.only_for("System Manager")
    frappe.enqueue(
        "frappe_salesforce.tasks.scheduled.run_manual_sync",
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


@frappe.whitelist()
def backfill_from_date(since: str):
    """Reset all high-water marks to ``since`` so the next tick backfills.

    ``since`` must be an ISO-8601 datetime. This is the *only* supported way
    to sync historical data; default HWMs are seeded to install-time to
    prevent accidental full-history backfills (see PR #Phase-B).
    """
    frappe.only_for("System Manager")
    from frappe.utils import get_datetime

    from frappe_salesforce.setup.install import HWM_FIELDS

    try:
        dt = get_datetime(since)
    except Exception as e:
        frappe.throw(f"Invalid datetime: {e}")

    settings = frappe.get_single("Salesforce Settings")
    for field in HWM_FIELDS:
        settings.set(field, dt)
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "reset_to": str(dt), "fields": HWM_FIELDS}


@frappe.whitelist()
def get_api_usage():
    """Return last-observed Salesforce API usage + today's app-level count."""
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.client import _daily_counter_get

    s = frappe.get_cached_doc("Salesforce Settings")
    return {
        "sf_used": s.get("last_api_usage_used") or 0,
        "sf_limit": s.get("last_api_usage_limit") or 0,
        "sf_observed_at": s.get("last_api_usage_at"),
        "app_calls_today": _daily_counter_get(),
        "per_day_budget": s.get("max_calls_per_day") or 0,
        "per_tick_budget": s.get("max_calls_per_tick") or 0,
    }
