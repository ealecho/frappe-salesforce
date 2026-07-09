"""Status tracking for the chunked retention Purge/Backfill jobs.

Mirrors the ``Salesforce Sync Log`` pattern (``tasks/incremental.py``) so the
retention workflow gets durable, browsable Running -> Success/Partial/Failed
status. The runners in ``tasks/retention_backfill.py`` execute in bounded
chunks (each chunk re-enqueues its continuation, freeing the long-queue
worker for other jobs in between), so the helpers here are chunk-shaped:
``create_log`` once up front, ``update_progress`` after every chunk (which
doubles as the run's liveness signal — see ``reap_stale_running_logs``),
then ``finalize_log`` / ``fail_log`` exactly once at the end.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime

#: A Running log whose ``modified`` is older than this is considered dead:
#: chunks update the log after every slice, so a healthy run refreshes
#: ``modified`` every few minutes. Killed workers (deploy restarts, OOM)
#: leave the log Running forever otherwise.
STALE_RUNNING_MINUTES = 30


def create_log(action: str) -> str:
    """Create a Running ``Salesforce Retention Log``; returns its name."""
    log = frappe.new_doc("Salesforce Retention Log")
    log.action = action
    log.start_time = now_datetime()
    log.status = "Running"
    log.insert(ignore_permissions=True)
    frappe.db.commit()
    return log.name


def update_progress(log_name: str, totals: dict[str, dict]) -> None:
    """Rewrite the log's items from running totals. Called after every chunk.

    Also bumps ``modified``, which is what marks the run as alive for
    ``reap_stale_running_logs``.
    """
    log = frappe.get_doc("Salesforce Retention Log", log_name)
    log.set("items", [])
    for row in _items_from_totals(totals):
        log.append("items", row)
    log.save(ignore_permissions=True)
    frappe.db.commit()


def finalize_log(log_name: str, totals: dict[str, dict]) -> None:
    """Land the log in a terminal Success/Partial/Failed status."""
    items = _items_from_totals(totals)
    total_count = sum(i["count"] for i in items)
    total_failed = sum(i["failed"] for i in items)
    if total_failed == 0:
        status = "Success"
    elif total_count == 0:
        status = "Failed"
    else:
        status = "Partial"

    log = frappe.get_doc("Salesforce Retention Log", log_name)
    log.set("items", [])
    for row in items:
        log.append("items", row)
    log.status = status
    log.end_time = now_datetime()
    log.save(ignore_permissions=True)
    frappe.db.commit()


def fail_log(log_name: str, error_summary: str, totals: dict[str, dict] | None = None) -> None:
    """Land the log in Failed with a short human-readable cause.

    Progress made before the failure (``totals``) is preserved in the items
    so the operator can see how far it got. The full traceback belongs in
    ``frappe.log_error`` at the call site.
    """
    log = frappe.get_doc("Salesforce Retention Log", log_name)
    if totals:
        log.set("items", [])
        for row in _items_from_totals(totals):
            log.append("items", row)
    log.status = "Failed"
    log.error_summary = (error_summary or "")[:500]
    log.end_time = now_datetime()
    log.save(ignore_permissions=True)
    frappe.db.commit()


def reap_stale_running_logs(action: str | None = None) -> None:
    """Mark dead Running logs Failed so they don't block new runs forever.

    Chunk continuations refresh ``modified`` every slice; a Running log
    untouched for ``STALE_RUNNING_MINUTES`` means its worker was killed
    (deploy restart, timeout, OOM) before it could finalize.
    """
    filters: dict[str, Any] = {
        "status": "Running",
        "modified": ["<", add_to_date(now_datetime(), minutes=-STALE_RUNNING_MINUTES)],
    }
    if action:
        filters["action"] = action
    for name in frappe.get_all("Salesforce Retention Log", filters=filters, pluck="name"):
        frappe.db.set_value(
            "Salesforce Retention Log",
            name,
            {
                "status": "Failed",
                "error_summary": (
                    "Aborted: no progress for "
                    f"{STALE_RUNNING_MINUTES}+ minutes — worker likely killed "
                    "(deploy restart / timeout) before the run could finish."
                ),
                "end_time": now_datetime(),
            },
            update_modified=False,
        )
    frappe.db.commit()


def has_running_log(action: str) -> bool:
    """Whether a live (non-stale) run of ``action`` is already in flight."""
    return bool(
        frappe.db.exists(
            "Salesforce Retention Log", {"status": "Running", "action": action}
        )
    )


def claim_run(action: str) -> str:
    """Atomically claim the right to start a run; returns the new log name.

    Creating the Running log *inside* the API request (rather than in the
    worker) is what makes the single-run guard effective: a check-then-
    enqueue guard alone leaves a wide race window (queue latency) where a
    second click sees no Running log because the first job hasn't started
    yet. A short Redis lock (same pattern as the incremental sync's) makes
    the reap → check → create sequence atomic across web workers too.
    Throws if a live run of ``action`` already exists.
    """
    lock_key = (
        f"frappe_salesforce:retention_claim:"
        f"{getattr(frappe.local, 'site', '') or 'default'}:{action}"
    )
    acquired = False
    try:
        acquired = bool(frappe.cache().set(lock_key, "1", nx=True, ex=30))
    except Exception:
        # Cache down: fail open on the lock, keep the DB check below.
        acquired = True
    if not acquired:
        frappe.throw(
            f"A retention {action.lower()} is already being started — "
            "check Salesforce Retention Log."
        )
    try:
        reap_stale_running_logs(action)
        if has_running_log(action):
            frappe.throw(
                f"A retention {action.lower()} is already running — track it "
                "in Salesforce Retention Log. A dead run is reaped "
                f"automatically after {STALE_RUNNING_MINUTES} minutes "
                "without progress."
            )
        return create_log(action)
    finally:
        try:
            frappe.cache().delete(lock_key)
        except Exception:
            pass  # 30s TTL reclaims it


def _items_from_totals(totals: dict[str, dict]) -> list[dict]:
    """Adapt running totals into ``Salesforce Retention Log Item`` rows.

    ``totals`` maps a label (SF object or Frappe doctype) to
    ``{"count": N, "failed": M}`` — count is deleted (Purge) or imported
    (Backfill).
    """
    return [
        {
            "label": label,
            "total": t.get("count", 0) + t.get("failed", 0),
            "count": t.get("count", 0),
            "failed": t.get("failed", 0),
        }
        for label, t in totals.items()
    ]
