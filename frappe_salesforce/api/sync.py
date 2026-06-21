"""Manual sync trigger + status endpoints."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime


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
def reset_all_high_water_marks():
    """Reset every per-syncer HWM to epoch (1970-01-01) for a full backfill.

    Use after deploying mapping fixes that require existing records to be
    re-fetched from Salesforce. The next scheduler tick (or manual
    ``Sync Now``) will start replaying records from the beginning of time;
    the per-day API budget guards against quota exhaustion.

    Returns the list of fields that were reset.
    """
    frappe.only_for("System Manager")
    from frappe_salesforce.setup.install import HWM_FIELDS

    epoch = "1970-01-01 00:00:00"
    settings = frappe.get_single("Salesforce Settings")
    for field in HWM_FIELDS:
        settings.set(field, epoch)
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.log_error(
        title="Salesforce HWMs reset to epoch",
        message=(
            "Operator triggered a full backfill via "
            "frappe_salesforce.api.sync.reset_all_high_water_marks. "
            f"Fields reset: {', '.join(HWM_FIELDS)}."
        ),
    )
    return {"ok": True, "reset_to": epoch, "fields": HWM_FIELDS}


@frappe.whitelist()
def backfill_deal_child_tables(account_name: str | None = None, limit: int | None = None):
    """Repopulate the Income Year Breakdown + Payment Schedule grids.

    Walks existing ``Salesforce Record Link`` rows for Opportunities and,
    for each linked CRM Deal, re-queries the related ``Income_year__c`` and
    ``npe01__OppPayment__c`` records and rebuilds the two child tables.

    This is the one-off / on-demand counterpart to the automatic refresh
    that ``OpportunitySyncer.after_upsert`` performs during incremental
    sync — useful to seed existing deals or to reconcile after a child
    record changed in Salesforce without bumping the parent Opportunity.

    Args:
        account_name: Optional CRM Organization name to restrict the
            backfill to a single account's deals (e.g. ``"Four Acre Trust"``
            to test on John Bothamley's grants first).
        limit: Optional cap on the number of deals processed.

    Returns a per-run summary; details (failures) are written to the Error
    Log. Each deal costs ~2 Salesforce API calls, governed by the same
    per-tick / per-day budgets as a normal sync.
    """
    frappe.only_for("System Manager")

    from frappe_salesforce.salesforce.client import SalesforceClient
    from frappe_salesforce.sync.opportunities import (
        build_income_year_row,
        build_payment_row,
        INCOME_YEAR_FIELDS,
        PAYMENT_FIELDS,
    )

    if limit is not None:
        limit = int(limit)

    filters: dict[str, Any] = {
        "salesforce_object": "Opportunity",
        "frappe_doctype": "CRM Deal",
    }
    links = frappe.get_all(
        "Salesforce Record Link",
        filters=filters,
        fields=["salesforce_id", "frappe_name"],
    )

    client = SalesforceClient()
    today = now_datetime().date()
    processed = skipped = failed = 0

    for link in links:
        deal_name = link.get("frappe_name")
        sf_id = link.get("salesforce_id")
        if not deal_name or not sf_id:
            skipped += 1
            continue
        if not frappe.db.exists("CRM Deal", deal_name):
            skipped += 1
            continue
        if account_name:
            org = frappe.db.get_value("CRM Deal", deal_name, "organization")
            if org != account_name:
                skipped += 1
                continue
        try:
            doc = frappe.get_doc("CRM Deal", deal_name)
            iy_soql = (
                f"SELECT {', '.join(INCOME_YEAR_FIELDS)} FROM Income_year__c "
                f"WHERE Grant_Or_Donation__c = '{sf_id}'"
            )
            doc.set(
                "custom_income_years",
                [build_income_year_row(r) for r in client.query(iy_soql)],
            )
            pay_soql = (
                f"SELECT {', '.join(PAYMENT_FIELDS)} FROM npe01__OppPayment__c "
                f"WHERE npe01__Opportunity__c = '{sf_id}'"
            )
            doc.set(
                "custom_payment_schedule",
                [build_payment_row(r, today) for r in client.query(pay_soql)],
            )
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            processed += 1
        except Exception as e:
            failed += 1
            frappe.db.rollback()
            frappe.log_error(
                title=f"SF backfill child tables: deal {deal_name}",
                message=frappe.get_traceback() or str(e),
            )
        if limit and processed >= limit:
            break

    return {
        "ok": True,
        "deals_processed": processed,
        "skipped": skipped,
        "failed": failed,
        "account_name": account_name,
    }


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
