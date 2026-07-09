"""Shared status-tracking wrapper for the retention Purge/Backfill jobs.

Mirrors the ``Salesforce Sync Log`` pattern (``tasks/incremental.py``) so the
one-time retention workflow gets the same durable, browsable Running ->
Success/Partial/Failed status instead of only being observable from whatever
console session happened to trigger it.
"""

from __future__ import annotations

from typing import Any, Callable

import frappe
from frappe.utils import now_datetime


def run_with_log(action: str, fn: Callable[..., dict], **kwargs: Any) -> str:
    """Run ``fn(**kwargs)``, recording progress on a new ``Salesforce Retention Log``.

    ``fn`` is expected to return a result dict in the shape ``purge_synced_records``
    or ``run_retention_backfill`` already produce (see ``_build_items`` below).
    Always leaves the log in a terminal status (Success/Partial/Failed) — even
    if ``fn`` raises outright (budget exceeded, a DB lock timeout, an auth
    failure) — so the admin is never left guessing from a dropped console
    session. Returns the created log's name.
    """
    log = frappe.new_doc("Salesforce Retention Log")
    log.action = action
    log.start_time = now_datetime()
    log.status = "Running"
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    try:
        result = fn(**kwargs)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title=f"Salesforce Retention Log {log.name}: {action} failed",
            message=frappe.get_traceback(),
        )
        log.status = "Failed"
        log.error_summary = frappe.get_traceback(with_context=False).strip().splitlines()[-1][:500]
        log.end_time = now_datetime()
        log.save(ignore_permissions=True)
        frappe.db.commit()
        return log.name

    items = _build_items(action, result)
    total_count = sum(i["count"] for i in items)
    total_failed = sum(i["failed"] for i in items)
    if total_failed == 0:
        log.status = "Success"
    elif total_count == 0:
        log.status = "Failed"
    else:
        log.status = "Partial"

    for item in items:
        log.append("items", item)
    log.end_time = now_datetime()
    log.save(ignore_permissions=True)
    frappe.db.commit()
    return log.name


def _build_items(action: str, result: dict) -> list[dict]:
    """Adapt a Purge/Backfill result dict into ``Salesforce Retention Log Item`` rows."""
    if action == "Purge":
        by_doctype = result.get("by_doctype") or {}
        deleted_by_doctype = result.get("deleted_by_doctype") or {}
        return [
            {
                "label": doctype,
                "total": total,
                "count": deleted_by_doctype.get(doctype, 0),
                "failed": total - deleted_by_doctype.get(doctype, 0),
            }
            for doctype, total in by_doctype.items()
        ]

    # Backfill: {object: {"imported": N, "failed": M}}
    return [
        {
            "label": obj,
            "total": counts.get("imported", 0) + counts.get("failed", 0),
            "count": counts.get("imported", 0),
            "failed": counts.get("failed", 0),
        }
        for obj, counts in result.items()
    ]
