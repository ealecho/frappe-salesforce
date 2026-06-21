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

#: Redis key (namespaced per site) guarding against concurrent sync runs.
SYNC_LOCK_KEY = "frappe_salesforce:incremental_sync_lock"
#: Lock TTL in seconds. Auto-releases if a worker is killed mid-run (e.g.
#: RQ job timeout) so a crash can never wedge the scheduler permanently.
#: Must comfortably exceed a single run's wall time (a run is bounded by
#: the per-tick API budget, so it ends well before this).
SYNC_LOCK_TTL = 3600


def _sync_lock_key() -> str:
    # Namespace by site: a shared Redis backs multiple sites on one bench.
    return f"{SYNC_LOCK_KEY}:{getattr(frappe.local, 'site', '') or 'default'}"


def _acquire_sync_lock() -> bool:
    """Atomically claim the sync lock. Returns False if already held.

    Fails open (returns True) if the cache backend is unreachable — a
    missing lock should never prevent syncing entirely, only guard the
    common case.
    """
    try:
        # redis SET NX EX — atomic claim with auto-expiry.
        return bool(
            frappe.cache().set(
                _sync_lock_key(), str(now_datetime()), nx=True, ex=SYNC_LOCK_TTL
            )
        )
    except Exception:
        frappe.log_error(
            title="frappe_salesforce: sync lock acquire failed (failing open)",
            message=frappe.get_traceback(),
        )
        return True


def _release_sync_lock() -> None:
    try:
        frappe.cache().delete(_sync_lock_key())
    except Exception:
        # TTL will reclaim it; nothing to do.
        pass


class IncrementalSyncRunner:
    """Run all registered syncers in order, recording a Sync Log."""

    def run(self) -> str | None:
        """Entry point. Serialised: only one run proceeds at a time.

        If another run holds the lock, this trigger is skipped (returns
        ``None``) rather than running concurrently — concurrent writers
        collide on Frappe's optimistic-concurrency check
        (``TimestampMismatchError``) and pile up zombie "Running" logs.
        """
        if not _acquire_sync_lock():
            frappe.logger("frappe_salesforce").info(
                "Incremental sync already in progress; skipping this trigger."
            )
            return None
        try:
            self._reap_stale_running_logs()
            return self._run()
        finally:
            _release_sync_lock()

    def _run(self) -> str:
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

    def _reap_stale_running_logs(self) -> None:
        """Close out logs left "Running" by a previous killed worker.

        We only get here holding the lock, so no run is genuinely active —
        any "Running" log is a corpse from a worker that was killed (e.g.
        RQ job timeout) before it could finalise its status. Mark them
        Failed so the log history reflects reality.
        """
        stale = frappe.get_all(
            "Salesforce Sync Log", filters={"status": "Running"}, pluck="name"
        )
        if not stale:
            return
        for name in stale:
            frappe.db.set_value(
                "Salesforce Sync Log",
                name,
                {
                    "status": "Failed",
                    "error_summary": (
                        "Aborted: superseded by a new run (previous run did "
                        "not finish — likely worker timeout)."
                    ),
                    "end_time": now_datetime(),
                },
                update_modified=False,
            )
        frappe.db.commit()

    def _create_log(self):
        log = frappe.new_doc("Salesforce Sync Log")
        log.start_time = now_datetime()
        log.triggered_by = "Scheduler" if not frappe.flags.in_manual_sync else "Manual"
        log.status = "Running"
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log
