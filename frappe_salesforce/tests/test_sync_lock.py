"""The incremental sync must be serialised so runs can't collide.

Regression guard for the runaway on dev: with no concurrency lock, the
15-minute cron piled up overlapping runs that collided on Frappe's
optimistic-concurrency check (TimestampMismatchError) and left a stack of
zombie "Running" logs. Importing the runner needs Frappe, so these are
skipped in the no-site lint run.
"""

import pytest

pytest.importorskip("frappe")

from frappe_salesforce.tasks import incremental  # noqa: E402


def test_run_skips_when_lock_held(monkeypatch):
    # Simulate another run already holding the lock.
    monkeypatch.setattr(incremental, "_acquire_sync_lock", lambda: False)
    runner = incremental.IncrementalSyncRunner()
    # If the skip path is correct we never touch the DB: _create_log must
    # not be called, and run() returns None instead of a log name.
    def _boom():
        raise AssertionError("_create_log must not run when the lock is held")
    monkeypatch.setattr(runner, "_create_log", _boom)
    assert runner.run() is None


def test_sync_lock_key_is_site_namespaced(monkeypatch):
    monkeypatch.setattr(incremental.frappe.local, "site", "abc.example.com", raising=False)
    assert incremental._sync_lock_key() == f"{incremental.SYNC_LOCK_KEY}:abc.example.com"


def test_lock_released_after_run(monkeypatch):
    # Lock acquired, body runs and returns a name, lock released exactly once.
    events = []
    monkeypatch.setattr(incremental, "_acquire_sync_lock", lambda: True)
    monkeypatch.setattr(incremental, "_release_sync_lock", lambda: events.append("release"))
    runner = incremental.IncrementalSyncRunner()
    monkeypatch.setattr(runner, "_reap_stale_running_logs", lambda: None)
    monkeypatch.setattr(runner, "_run", lambda: "SF-SYNC-TEST")
    assert runner.run() == "SF-SYNC-TEST"
    assert events == ["release"]
