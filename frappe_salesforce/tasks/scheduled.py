"""Scheduler entrypoints wired from hooks.scheduler_events."""

from __future__ import annotations

import frappe


def run_incremental_sync() -> None:
    """Entrypoint for the 15-minute cron."""
    if not frappe.db.get_single_value("Salesforce Settings", "enabled"):
        return
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
