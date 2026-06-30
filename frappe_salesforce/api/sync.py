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
        budget_soql,
        build_budget_row,
        build_income_year_row,
        build_payment_row,
        INCOME_YEAR_FIELDS,
        PAYMENT_FIELDS,
    )

    if limit is not None:
        limit = int(limit)

    # The grant child tables are owned by a separate app; on a bench that
    # lacks them there's nowhere to write, so bail before spending any
    # Salesforce API calls.
    meta = frappe.get_meta("CRM Deal")
    has_income_years = bool(meta.get_field("custom_income_years"))
    has_payments = bool(meta.get_field("custom_payment_schedule"))
    has_budget = bool(meta.get_field("custom_grant_budget"))
    if not (has_income_years or has_payments or has_budget):
        return {
            "ok": False,
            "reason": (
                "CRM Deal has none of custom_income_years, "
                "custom_payment_schedule or custom_grant_budget; the grant "
                "child tables are not installed on this bench."
            ),
        }

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
            if has_income_years:
                iy_soql = (
                    f"SELECT {', '.join(INCOME_YEAR_FIELDS)} FROM Income_year__c "
                    f"WHERE Grant_Or_Donation__c = '{sf_id}'"
                )
                doc.set(
                    "custom_income_years",
                    [build_income_year_row(r) for r in client.query(iy_soql)],
                )
            if has_payments:
                pay_soql = (
                    f"SELECT {', '.join(PAYMENT_FIELDS)} FROM npe01__OppPayment__c "
                    f"WHERE npe01__Opportunity__c = '{sf_id}'"
                )
                doc.set(
                    "custom_payment_schedule",
                    [
                        row
                        for row in (
                            build_payment_row(r, today) for r in client.query(pay_soql)
                        )
                        if row is not None
                    ],
                )
            if has_budget:
                doc.set(
                    "custom_grant_budget",
                    [build_budget_row(r) for r in client.query(budget_soql(sf_id))],
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
def resync_opportunities(account_name: str | None = None, limit: int | None = None):
    """Re-pull Opportunities through the full mapping to refresh scalar fields.

    Unlike ``backfill_deal_child_tables`` (which only rebuilds the grids),
    this re-runs the complete ``OpportunitySyncer`` mapping for each deal —
    so it picks up corrected field mappings (e.g. the stage→status change
    that drives ``probability`` via ``peas_crm``) without resetting the
    Opportunity high-water mark and replaying all of history.

    Each record is re-fetched and re-upserted exactly as a normal sync
    would, including ``after_upsert`` (income year / payment / budget
    grids). The Opportunity HWM is left untouched.

    Args:
        account_name: Optional CRM Organization name to restrict to one
            account's deals (e.g. ``"John Bothamley"``).
        limit: Optional cap on the number of deals processed.
    """
    frappe.only_for("System Manager")

    from frappe_salesforce.salesforce.client import SalesforceClient
    from frappe_salesforce.sync.opportunities import OpportunitySyncer

    if limit is not None:
        limit = int(limit)

    links = frappe.get_all(
        "Salesforce Record Link",
        filters={"salesforce_object": "Opportunity", "frappe_doctype": "CRM Deal"},
        fields=["salesforce_id", "frappe_name"],
    )

    # Restrict to one account's deals if requested.
    sf_ids: list[str] = []
    for link in links:
        deal_name = link.get("frappe_name")
        sf_id = link.get("salesforce_id")
        if not deal_name or not sf_id:
            continue
        if not frappe.db.exists("CRM Deal", deal_name):
            continue
        if account_name:
            org = frappe.db.get_value("CRM Deal", deal_name, "organization")
            if org != account_name:
                continue
        sf_ids.append(sf_id)
        if limit and len(sf_ids) >= limit:
            break

    client = SalesforceClient()
    syncer = OpportunitySyncer(client, frappe._dict())
    fields = list(dict.fromkeys(["Id", "SystemModstamp", *syncer._soql_fields()]))
    select = ", ".join(fields)

    processed = failed = 0
    # Batch the SF re-fetch (200 ids/query) to keep API calls down; the
    # per-record after_upsert grid queries still cost the usual ~3 each.
    for start in range(0, len(sf_ids), 200):
        chunk = sf_ids[start : start + 200]
        id_list = ", ".join(f"'{i}'" for i in chunk)
        soql = f"SELECT {select} FROM Opportunity WHERE Id IN ({id_list})"
        for rec in client.query(soql):
            try:
                syncer._process_record(rec)
                frappe.db.commit()
                processed += 1
            except Exception as e:
                failed += 1
                frappe.db.rollback()
                frappe.log_error(
                    title=f"SF resync Opportunity {rec.get('Id')}",
                    message=frappe.get_traceback() or str(e),
                )

    return {
        "ok": True,
        "deals_matched": len(sf_ids),
        "deals_processed": processed,
        "failed": failed,
        "account_name": account_name,
    }


def _count(client, sobject: str, where: str | None = None) -> int:
    """Run a SOQL ``COUNT()`` and return totalSize."""
    soql = f"SELECT COUNT() FROM {sobject}"
    if where:
        soql += f" WHERE {where}"
    data = client._get(f"{client._base()}/query", params={"q": soql}).json()
    return int(data.get("totalSize", 0))


@frappe.whitelist()
def retention_backfill_report():
    """Dry-run: how many records each object KEEPs vs drops under the policy.

    Non-destructive — just SOQL COUNT()s. Run this first to validate the
    retention rules (see ``sync/retention.py``) before any purge / backfill.
    """
    frappe.only_for("System Manager")
    from frappe_salesforce.salesforce.client import SalesforceClient
    from frappe_salesforce.sync import retention
    from frappe_salesforce.tasks.retention_backfill import kept_parent_ids

    client = SalesforceClient(bypass_budget=True)
    out: dict[str, Any] = {}
    # Account / Contact: KEEP is a UNION of separate queries (SF forbids
    # OR-combining semi-joins), so count distinct kept Ids rather than COUNT().
    for obj in ("Account", "Contact"):
        total = _count(client, obj)
        keep = len(kept_parent_ids(client, retention.PARENT_KEEP[obj]))
        out[obj] = {"total": total, "keep": keep, "drop": total - keep}
    # Opportunity: scalar predicate, COUNT() works directly.
    opp_total = _count(client, "Opportunity")
    opp_keep = _count(client, "Opportunity", retention.opportunity_keep_where())
    out["Opportunity"] = {"total": opp_total, "keep": opp_keep, "drop": opp_total - opp_keep}
    return out


@frappe.whitelist()
def purge_synced_data(dry_run: str = "true", limit: int | None = None):
    """Delete CRM records the sync created (tracked by Salesforce Record Link).

    ``dry_run`` defaults to "true" (counts only). Pass ``dry_run=false`` to
    actually delete — enqueued on the long queue because of volume and the
    other apps' delete hooks. Only sync-created records are touched. ``limit``
    caps deletions for a chunked run.
    """
    frappe.only_for("System Manager")
    from frappe_salesforce.tasks.retention_backfill import purge_synced_records

    if limit is not None:
        limit = int(limit)
    dry = str(dry_run).lower() != "false"
    if dry:
        return purge_synced_records(dry_run=True, limit=limit)
    frappe.enqueue(
        "frappe_salesforce.tasks.retention_backfill.purge_synced_records",
        queue="long",
        timeout=36000,
        job_name="salesforce_purge_synced_records",
        dry_run=False,
        limit=limit,
    )
    return {"queued": True, "job": "salesforce_purge_synced_records"}


@frappe.whitelist()
def start_retention_backfill(limit: int | None = None):
    """Import only records matching the retention KEEP rules. Enqueued."""
    frappe.only_for("System Manager")
    if limit is not None:
        limit = int(limit)
    frappe.enqueue(
        "frappe_salesforce.tasks.retention_backfill.run_retention_backfill",
        queue="long",
        timeout=36000,
        job_name="salesforce_retention_backfill",
        limit=limit,
    )
    return {"queued": True, "job": "salesforce_retention_backfill"}


@frappe.whitelist()
def dedup_contacts(dry_run: str = "true"):
    """Merge Frappe Contacts sharing first name + last name + email.

    ``dry_run`` defaults to "true" (reports the duplicate groups). Pass
    ``dry_run=false`` to merge: the first contact in each group is the survivor
    and the rest are merged into it via ``frappe.rename_doc(merge=True)``.

    CAUTION — sync-identity reconciliation: the survivor keeps a single unique
    ``custom_salesforce_id``. Each merged-away contact's ``Salesforce Record
    Link`` is re-pointed at the survivor so a future incremental sync updates
    the survivor instead of re-creating the duplicate. The survivor's
    ``custom_salesforce_id`` will then reflect whichever SF contact synced most
    recently (the records collapse to one Frappe doc, by design). Review the
    dry-run output before enabling.
    """
    frappe.only_for("System Manager")
    dry = str(dry_run).lower() != "false"

    rows = frappe.get_all(
        "Contact", fields=["name", "first_name", "last_name", "email_id"]
    )
    groups: dict[tuple, list[str]] = {}
    for r in rows:
        email = (r.email_id or "").strip().lower()
        if not email:
            continue  # require an email to consider two contacts the same
        key = ((r.first_name or "").strip().lower(), (r.last_name or "").strip().lower(), email)
        groups.setdefault(key, []).append(r.name)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}

    if dry:
        return {
            "dry_run": True,
            "duplicate_groups": len(dupes),
            "records_to_merge": sum(len(v) - 1 for v in dupes.values()),
            "sample": [
                {"first": k[0], "last": k[1], "email": k[2], "names": v}
                for k, v in list(dupes.items())[:25]
            ],
        }

    merged = failed = 0
    for names in dupes.values():
        survivor, *rest = names
        for dup in rest:
            try:
                _merge_contact_into(dup, survivor)
                merged += 1
            except Exception:
                failed += 1
                frappe.db.rollback()
                frappe.log_error(
                    title=f"Contact dedup merge {dup} -> {survivor}",
                    message=frappe.get_traceback(),
                )
    return {"dry_run": False, "merged": merged, "failed": failed, "groups": len(dupes)}


def _merge_contact_into(dup: str, survivor: str) -> None:
    """Merge ``dup`` into ``survivor`` and re-point its SF link at survivor."""
    # Re-point the duplicate's Salesforce Record Link(s) before the merge
    # removes the duplicate doc, so future syncs update the survivor.
    for link in frappe.get_all(
        "Salesforce Record Link",
        filters={"frappe_doctype": "Contact", "frappe_name": dup},
        fields=["name"],
    ):
        frappe.db.set_value("Salesforce Record Link", link.name, "frappe_name", survivor)
    frappe.rename_doc("Contact", dup, survivor, merge=True, ignore_permissions=True)
    frappe.db.commit()


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
