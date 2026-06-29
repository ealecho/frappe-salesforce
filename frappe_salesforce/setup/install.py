"""after_install hook."""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from .custom_fields import SF_ID_DOCTYPES, ensure_all_custom_fields
from .deal_statuses import ensure_peas_deal_statuses
from .default_mappings import ensure_default_field_mappings, seed_default_field_mappings

#: Re-exported for backwards-compat with patches/v0_0_1.
__all__ = [
    "after_install",
    "after_migrate",
    "ensure_all_custom_fields",
    "SF_ID_DOCTYPES",
    "HWM_FIELDS",
]

# Fields on Salesforce Settings that hold per-syncer high-water marks.
# Default to install-time ``now()`` so the first tick does NOT backfill
# from 1970 — that behaviour nearly blew our API quota once already.
# Users who want a backfill run the "Backfill From Date" or "Reset HWMs
# to Epoch (Full Backfill)" actions on Salesforce Settings.
HWM_FIELDS = [
    "last_sync_user",
    "last_sync_account",
    "last_sync_contact",
    "last_sync_lead",
    "last_sync_opportunity",
    "last_sync_task",
    "last_sync_event",
]


def after_install() -> None:
    _ensure_custom_fields()
    _ensure_default_settings()
    seed_default_field_mappings()
    ensure_peas_deal_statuses()
    frappe.db.commit()


def after_migrate() -> None:
    """Self-heal default field mappings on every ``bench migrate``.

    Unlike ``after_install`` (fresh installs only) and the one-shot
    ``extend_default_mappings`` patch (Frappe runs each patch exactly once,
    so it can't re-seed a site whose ``Salesforce Field Mapping`` records
    were never created or were later deleted), this runs on *every*
    migrate. ``ensure_default_field_mappings`` is additive and idempotent:
    it creates any missing object mapping, appends missing default rows,
    and never removes admin customisations — so a deploy + migrate always
    converges a site to a complete set of mappings.

    ``validate=False`` so a migrate can never be aborted by the readiness
    guard; the per-sync path (``IncrementalSyncRunner.run``) still validates
    before each run.

    Any failure is logged and swallowed: this hook runs in the shared
    ``after_migrate`` phase of ``bench migrate``, so an exception here would
    abort migration for *every* app on the bench. A mapping-seed problem
    must never have that blast radius — it is rolled back and recorded to
    the Error Log for follow-up instead.
    """
    try:
        ensure_default_field_mappings(validate=False)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="frappe_salesforce after_migrate: mapping seed failed",
            message=frappe.get_traceback(),
        )


def _ensure_custom_fields() -> None:
    """Backwards-compatible wrapper used by ``patches.v0_0_1``."""
    ensure_all_custom_fields()


def _ensure_default_settings() -> None:
    settings = frappe.get_single("Salesforce Settings")
    changed = False
    if not settings.api_version:
        settings.api_version = "v60.0"
        changed = True
    if not settings.login_url:
        settings.login_url = "https://login.salesforce.com"
        changed = True
    if not settings.batch_size:
        settings.batch_size = 500
        changed = True
    if not settings.get("max_calls_per_tick"):
        settings.max_calls_per_tick = 500
        changed = True
    if not settings.get("max_calls_per_day"):
        settings.max_calls_per_day = 50_000
        changed = True
    if not settings.get("preflight_threshold"):
        settings.preflight_threshold = 80
        changed = True
    # Seed HWMs to install-time now() so the first run doesn't backfill
    # from epoch. Only set fields that are still empty — never clobber
    # existing progress.
    install_now = now_datetime()
    for field in HWM_FIELDS:
        if not settings.get(field):
            settings.set(field, install_now)
            changed = True
    if changed:
        settings.save(ignore_permissions=True)
