"""Remap the SF "Closed" stage to Won and backfill missing Grants.

PEAS Salesforce uses a bare "Closed" stage for completed grants (1,689 of
1,690 such deals are IsWon=true at 100% probability), which the stage map
didn't know — so those deals linked to an auto-created "Closed" CRM Deal
Status instead of "Won". Consequences: won-deal reporting missed them, and
the grants app's status-transition hook (fires only on *change to* "Won")
never created a Grant for any of them.

1. Remap: synced deals with status "Closed" and ``custom_sf_is_won=1``
   → status "Won". Direct SQL (no hooks) so this doesn't mass-fire the
   grant hook; probability is already 100 on these, matching Won.
   The stage map now carries ``"Closed" → "Won"`` for future syncs.

2. Grant backfill: for won deals closed on/after 2024-01-01 with no Grant,
   call the grants app's ``_create_grant_from_deal`` directly (the hook
   can't be re-fired for already-won deals). Older wins stay CRM-only by
   agreed scope — the grants module tracks grants the team still manages,
   not decade-old donations. No-op on benches without the grants app.
"""

import frappe

GRANT_BACKFILL_FROM = "2024-01-01"


def execute():
    if not frappe.db.exists("DocType", "CRM Deal"):
        return
    if not frappe.get_meta("CRM Deal").get_field("custom_sf_is_won"):
        return
    _remap_closed_to_won()
    _backfill_grants()


def _remap_closed_to_won():
    if not frappe.db.exists("CRM Deal Status", "Won"):
        return
    frappe.db.sql(
        """
        UPDATE `tabCRM Deal`
        SET status = 'Won'
        WHERE status = 'Closed' AND custom_sf_is_won = 1
        """
    )


def _backfill_grants():
    try:
        from frappe_grants_budgeting.grants_budgeting.api.grant_lifecycle import (
            _create_grant_from_deal,
        )
    except ImportError:
        return  # grants app not installed on this bench
    if not frappe.db.exists("DocType", "Grant"):
        return

    deals = frappe.get_all(
        "CRM Deal",
        filters={
            "status": "Won",
            "closed_date": (">=", GRANT_BACKFILL_FROM),
        },
        pluck="name",
    )
    with_grant = {
        g.crm_deal
        for g in frappe.get_all("Grant", fields=["crm_deal"])
        if g.crm_deal
    }
    for name in deals:
        if name in with_grant:
            continue
        try:
            _create_grant_from_deal(frappe.get_doc("CRM Deal", name))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"Grant backfill failed for {name}",
                message=frappe.get_traceback(),
            )
