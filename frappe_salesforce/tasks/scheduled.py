"""Scheduler entrypoints wired from hooks.scheduler_events."""

from __future__ import annotations

import frappe

#: Wall-clock timeout for an incremental sync job. The scheduler executes
#: cron handlers on the default queue (300s RQ timeout), which is far too
#: short for a large catch-up — a killed job leaves a "Running" log and
#: holds DB row locks. So the cron handler instead *enqueues* the work on
#: the long queue with this timeout. A single run is bounded by the
#: per-tick API budget and ends well before this, but the headroom means a
#: legitimate catch-up is never guillotined mid-record.
INCREMENTAL_SYNC_TIMEOUT = 1500  # seconds (25 min)


def run_incremental_sync() -> None:
    """Entrypoint for the 15-minute cron.

    Enqueues the sync on the long queue rather than running inline, so it
    gets a proper timeout. ``IncrementalSyncRunner.run`` is itself
    serialised by a lock, so if a previous run is still going this job
    no-ops instead of colliding.
    """
    if not frappe.db.get_single_value("Salesforce Settings", "enabled"):
        return
    frappe.enqueue(
        "frappe_salesforce.tasks.scheduled._execute_incremental_sync",
        queue="long",
        timeout=INCREMENTAL_SYNC_TIMEOUT,
        job_name="frappe_salesforce_incremental_sync",
    )


def _execute_incremental_sync() -> None:
    """Long-queue worker that actually runs the incremental sync."""
    from .incremental import IncrementalSyncRunner

    IncrementalSyncRunner().run()


def run_manual_sync() -> None:
    """Entrypoint for the manual 'Sync Now' button.

    Bypasses the ``enabled`` gate so admins can trigger a sync even when
    the scheduler is paused.
    """
    from .incremental import IncrementalSyncRunner

    IncrementalSyncRunner().run()


def run_deletion_sync() -> None:
    """Entrypoint for the nightly deletion sweep."""
    if not frappe.db.get_single_value("Salesforce Settings", "enabled"):
        return
    if not frappe.db.get_single_value("Salesforce Settings", "enable_deletion_sync"):
        return
    from .deletion import DeletionSyncRunner

    DeletionSyncRunner().run()
