"""One-time retention purge + selective backfill.

Two background runners for the one-off "clear the synced data, re-import only
what the retention policy keeps" operation:

* ``purge_synced_records`` — delete every CRM record this sync created (tracked
  by ``Salesforce Record Link``); never touches manually-entered CRM data.
* ``run_retention_backfill`` — re-import only records matching the KEEP
  predicates in ``sync/retention.py``, reusing each syncer's full mapping via
  ``_process_record``. High-water marks are left untouched (so the normal
  incremental tick stays selective-friendly afterwards — it won't replay the
  excluded history).

Both are invoked via the whitelisted wrappers in ``api/sync.py`` and are meant
to be enqueued on the long queue.
"""

from __future__ import annotations

import frappe

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.soql import build_incremental_query
from frappe_salesforce.sync import retention
from frappe_salesforce.sync.registry import SYNCERS

#: A "since" far enough back that ``SystemModstamp > since`` matches everything,
#: so the retention predicate is the only effective filter.
EPOCH = "1970-01-01 00:00:00"
_ID_BATCH = 200

#: Only objects the retention backfill re-imports may be purged. Crucially this
#: EXCLUDES Lead: the policy has no Lead KEEP rule, so the backfill never brings
#: leads back — purging them would delete the incoming pipeline for good. (User
#: is link-only and already skipped.)
PURGE_OBJECTS = {"Account", "Contact", "Opportunity", "Task", "Event"}


def purge_synced_records(dry_run: bool = True, limit: int | None = None) -> dict:
    """Delete CRM records created by the sync, per ``Salesforce Record Link``.

    Skips link-only objects (e.g. User — we never delete Users) and objects not
    re-imported (Lead). HWMs are NOT reset: leaving them at their current value
    keeps the post-purge incremental tick from replaying the excluded history.
    ``dry_run`` only counts. ``limit`` caps deletions per call so the purge can
    be run inline in chunks (re-run until ``deleted`` is 0); each call re-reads
    the remaining links, so chunked runs resume naturally.
    """
    by_object = {S.salesforce_object: S for S in SYNCERS}
    links = frappe.get_all(
        "Salesforce Record Link",
        fields=["name", "salesforce_object", "frappe_doctype", "frappe_name"],
    )

    counts: dict[str, int] = {}
    deleted_counts: dict[str, int] = {}
    deleted = 0
    for link in links:
        syncer = by_object.get(link.salesforce_object)
        if syncer is None or syncer.link_only:
            continue  # unknown object or link-only (User) -> never delete
        if link.salesforce_object not in PURGE_OBJECTS:
            continue  # e.g. Lead — not re-imported, so never purged
        counts[link.frappe_doctype] = counts.get(link.frappe_doctype, 0) + 1
        if dry_run:
            continue
        # Checked before deleting (not ``if limit`` after, which would
        # treat limit=0 — a legitimate "delete nothing" — as falsy/"no
        # limit" and purge everything instead).
        if limit is not None and deleted >= limit:
            break
        try:
            _force_delete(link)
            deleted += 1
            deleted_counts[link.frappe_doctype] = deleted_counts.get(link.frappe_doctype, 0) + 1
            # Commit per successful delete, not every 100 — rollback on a
            # later failure only rolls back uncommitted work, so batching
            # commits would discard up to 99 already-counted deletes
            # (records survive in the DB while deleted/deleted_counts
            # claim they don't) every time any single delete in the batch
            # failed. Matches _import_query's per-record commit below.
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"SF purge {link.frappe_doctype} {link.frappe_name}",
                message=frappe.get_traceback(),
            )
            continue
    if not dry_run:
        frappe.db.commit()

    return {
        "dry_run": dry_run,
        "by_doctype": counts,
        "deleted_by_doctype": deleted_counts,
        "deleted": deleted,
        "total": sum(counts.values()),
    }


def run_purge_with_log(limit: int | None = None) -> str:
    """``purge_synced_records(dry_run=False, ...)``, tracked on a Retention Log.

    The ``frappe.enqueue`` target for the destructive purge — see
    ``api/sync.py::purge_synced_data``. Dry-run stays a direct synchronous
    call (it's just COUNT()s, no log needed).
    """
    from frappe_salesforce.tasks.retention_log import run_with_log

    return run_with_log("Purge", purge_synced_records, dry_run=False, limit=limit)


def _force_delete(link) -> None:
    """Delete a sync-created doc and its Salesforce Record Link.

    ``force=True`` bypasses Frappe's link checks — necessary because the
    Salesforce Record Link *dynamically links* the target doc (so a plain delete
    raises ``LinkExistsError``), and because the synced docs cross-reference each
    other (CRM Deal -> Contact, dynamic Org links, Addresses). Appropriate for a
    full purge, which wipes the whole synced set before re-importing.
    ``delete_permanently=True`` skips the Deleted Document trail for a clean wipe.
    """
    if link.frappe_name and frappe.db.exists(link.frappe_doctype, link.frappe_name):
        frappe.delete_doc(
            link.frappe_doctype,
            link.frappe_name,
            force=True,
            ignore_permissions=True,
            delete_permanently=True,
        )
    frappe.delete_doc("Salesforce Record Link", link.name, ignore_permissions=True)


def kept_parent_ids(client: SalesforceClient, spec: dict) -> set[str]:
    """Union the KEEP Ids for a parent object (Account/Contact).

    Salesforce forbids OR-combining semi-joins, so each rule is its own query:
    one scalar query on the parent, plus one per lookup rule on the child
    (collecting the parent lookup Id). See ``sync/retention.py``.
    """
    ids: set[str] = set()
    for rec in client.query(
        f"SELECT Id FROM {spec['object']} WHERE {spec['scalar_where']}"
    ):
        if rec.get("Id"):
            ids.add(rec["Id"])
    for child_object, lookup_field, where in spec["lookup_rules"]:
        for rec in client.query(
            f"SELECT {lookup_field} FROM {child_object} WHERE {where}"
        ):
            value = rec.get(lookup_field)
            if value:
                ids.add(value)
    return ids


def run_retention_backfill(limit: int | None = None) -> dict:
    """Import only records matching the KEEP rules, in dependency order.

    Returns ``{object: {"imported": N, "failed": M}}`` for every object —
    a consistent shape across Account/Contact/Opportunity/Task/Event so
    callers (see ``tasks/retention_log.py``) can report real partial-failure
    counts rather than just a success count.
    """
    client = SalesforceClient()
    summary: dict[str, dict] = {}
    by_object = {S.salesforce_object: S for S in SYNCERS}
    # SF Ids actually targeted by this run's KEEP predicates, threaded into
    # _backfill_activities below — NOT sourced from whatever Salesforce
    # Record Link already has lying around, which would include anything
    # from a prior sync if this run isn't immediately preceded by a purge
    # (the two are separate steps/buttons now, not an enforced pair).
    kept_sf_ids: list[str] = []

    # Account / Contact: union the kept Ids (scalar + opportunity-derived rules),
    # then import those parents by Id (semi-joins can't be OR-combined inline).
    for obj in ("Account", "Contact"):
        syncer = by_object[obj](client, frappe._dict())
        ids = sorted(kept_parent_ids(client, retention.PARENT_KEEP[obj]))
        kept_sf_ids.extend(ids)
        imported, failed = _import_by_ids(syncer, client, obj, ids, limit)
        summary[obj] = {"imported": imported, "failed": failed}

    # Opportunity: single predicate query (all scalar terms -> OR is allowed).
    opp = by_object["Opportunity"](client, frappe._dict())
    opp_where = retention.opportunity_keep_where()
    kept_sf_ids.extend(
        rec["Id"] for rec in client.query(f"SELECT Id FROM Opportunity WHERE {opp_where}") if rec.get("Id")
    )
    opp_soql = build_incremental_query(
        sobject="Opportunity",
        fields=opp._soql_fields(),
        since=EPOCH,
        extra_where=opp_where,
    )
    opp_imported, opp_failed = _import_query(opp, client, opp_soql, limit)
    summary["Opportunity"] = {"imported": opp_imported, "failed": opp_failed}

    summary.update(_backfill_activities(client, kept_sf_ids, limit))
    return summary


def run_backfill_with_log(limit: int | None = None) -> str:
    """``run_retention_backfill(...)``, tracked on a Retention Log.

    The ``frappe.enqueue`` target for the backfill — see
    ``api/sync.py::start_retention_backfill``.
    """
    from frappe_salesforce.tasks.retention_log import run_with_log

    return run_with_log("Backfill", run_retention_backfill, limit=limit)


def _import_by_ids(syncer, client, sobject, ids, limit) -> tuple[int, int]:
    """Import ``sobject`` records for the given SF Ids, in batches of 200."""
    fields = syncer._soql_fields()
    imported = 0
    failed = 0
    for start in range(0, len(ids), _ID_BATCH):
        batch = ids[start : start + _ID_BATCH]
        id_list = ", ".join(f"'{i}'" for i in batch)
        soql = build_incremental_query(
            sobject=sobject, fields=fields, since=EPOCH, extra_where=f"Id IN ({id_list})"
        )
        remaining = None if limit is None else max(0, limit - imported)
        batch_imported, batch_failed = _import_query(syncer, client, soql, remaining)
        imported += batch_imported
        failed += batch_failed
        if limit is not None and imported >= limit:
            break
    return imported, failed


def _backfill_activities(client: SalesforceClient, kept_ids: list[str], limit: int | None) -> dict:
    """Import Tasks/Events that point at a kept Account/Contact/Opportunity.

    Activities are engagement records, not retention targets, so they are kept
    by linkage: ``kept_ids`` are the SF Ids this run's KEEP predicates actually
    targeted (passed in by ``run_retention_backfill``) — not queried from
    ``Salesforce Record Link``, which could include parents from a prior sync
    that this run never touched if it isn't immediately preceded by a purge.
    """
    out: dict[str, dict] = {}
    if not kept_ids:
        return out

    for syncer_cls in SYNCERS:
        if syncer_cls.salesforce_object not in ("Task", "Event"):
            continue
        syncer = syncer_cls(client, frappe._dict())
        fields = syncer._soql_fields()
        seen: set[str] = set()
        imported = 0
        failed = 0
        for start in range(0, len(kept_ids), _ID_BATCH):
            batch = kept_ids[start : start + _ID_BATCH]
            id_list = ", ".join(f"'{i}'" for i in batch)
            where = f"WhoId IN ({id_list}) OR WhatId IN ({id_list})"
            soql = build_incremental_query(
                sobject=syncer_cls.salesforce_object,
                fields=fields,
                since=EPOCH,
                extra_where=where,
            )
            remaining = None if limit is None else max(0, limit - imported)
            batch_imported, batch_failed = _import_query(syncer, client, soql, remaining, seen=seen)
            imported += batch_imported
            failed += batch_failed
            if limit is not None and imported >= limit:
                break
        out[syncer_cls.salesforce_object] = {"imported": imported, "failed": failed}
    return out


def _import_query(syncer, client, soql, limit, seen=None) -> tuple[int, int]:
    """Run one retention SOQL query, upserting each record.

    Returns ``(imported, failed)`` so callers can report real partial-failure
    counts (see ``tasks/retention_log.py``) instead of just a success count.
    """
    imported = 0
    failed = 0
    # ``if limit`` (not ``is not None``) would treat limit=0 as falsy/"no
    # limit" and import everything instead of nothing; check upfront so a
    # zero limit never issues the query at all.
    if limit is not None and imported >= limit:
        return imported, failed
    for rec in client.query(soql):
        sf_id = rec.get("Id")
        if seen is not None:
            if sf_id in seen:
                continue
            seen.add(sf_id)
        try:
            syncer._process_record(rec)
            frappe.db.commit()
            imported += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"Retention backfill {syncer.salesforce_object} {sf_id}",
                message=frappe.get_traceback(),
            )
            failed += 1
        if limit is not None and imported >= limit:
            break
    return imported, failed
