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

Both are invoked via the whitelisted wrappers in ``api/sync.py``. The
background execution model is **chunked**: ``run_purge_with_log`` /
``run_backfill_with_log`` process one bounded slice per RQ job, record
progress on the ``Salesforce Retention Log``, then enqueue their own
continuation at the back of the long queue — so a multi-hour run doesn't
monopolise a worker (other queued jobs interleave between chunks), a
deploy's worker restart only loses the in-flight chunk, and the log shows
live per-object progress instead of appearing hung.
"""

from __future__ import annotations

import json

import frappe

from frappe_salesforce.salesforce.client import SalesforceClient
from frappe_salesforce.salesforce.soql import build_incremental_query
from frappe_salesforce.sync import retention
from frappe_salesforce.sync.registry import SYNCERS

#: A "since" far enough back that ``SystemModstamp > since`` matches everything,
#: so the retention predicate is the only effective filter.
EPOCH = "1970-01-01 00:00:00"
_ID_BATCH = 200

#: Records processed per background chunk before the job re-enqueues its
#: continuation and frees the worker. 200 keeps a chunk to a few minutes
#: even for Opportunities (whose after_upsert fetches child grids).
CHUNK_SIZE = 200
CHUNK_QUEUE = "long"
CHUNK_TIMEOUT = 3600

#: Import order for the chunked backfill (dependencies first).
BACKFILL_PHASES = ("Account", "Contact", "Opportunity", "Task", "Event")

#: Only objects the retention backfill re-imports may be purged. Crucially this
#: EXCLUDES Lead: the policy has no Lead KEEP rule, so the backfill never brings
#: leads back — purging them would delete the incoming pipeline for good. (User
#: is link-only and already skipped.)
PURGE_OBJECTS = {"Account", "Contact", "Opportunity", "Task", "Event"}


def purge_synced_records(
    dry_run: bool = True,
    limit: int | None = None,
    skip_names: list[str] | None = None,
) -> dict:
    """Delete CRM records created by the sync, per ``Salesforce Record Link``.

    Skips link-only objects (e.g. User — we never delete Users) and objects not
    re-imported (Lead). HWMs are NOT reset: leaving them at their current value
    keeps the post-purge incremental tick from replaying the excluded history.
    ``dry_run`` only counts. ``limit`` caps *attempted* links per call (not
    just successful deletes — a call must stay bounded even when every
    remaining link is failing) so the purge can run in chunks; each call
    re-reads the remaining links, so chunked runs resume naturally.
    ``skip_names`` (Salesforce Record Link names) are ignored entirely —
    the chunked runner passes links that already failed in an earlier chunk
    so they aren't retried and re-counted every chunk.
    """
    by_object = {S.salesforce_object: S for S in SYNCERS}
    links = frappe.get_all(
        "Salesforce Record Link",
        fields=["name", "salesforce_object", "frappe_doctype", "frappe_name"],
    )
    skip = set(skip_names or ())

    counts: dict[str, int] = {}
    deleted_counts: dict[str, int] = {}
    failed_by_doctype: dict[str, list[str]] = {}
    deleted = 0
    attempted = 0
    for link in links:
        syncer = by_object.get(link.salesforce_object)
        if syncer is None or syncer.link_only:
            continue  # unknown object or link-only (User) -> never delete
        if link.salesforce_object not in PURGE_OBJECTS:
            continue  # e.g. Lead — not re-imported, so never purged
        if link.name in skip:
            continue  # failed in an earlier chunk — don't retry / recount
        # Break before counting so a limited run doesn't tally a link it
        # never processes. Guarded on ``not dry_run`` so dry-run counting
        # stays exhaustive; ``is not None`` so limit=0 ("do nothing")
        # isn't treated as "no limit".
        if not dry_run and limit is not None and attempted >= limit:
            break
        counts[link.frappe_doctype] = counts.get(link.frappe_doctype, 0) + 1
        if dry_run:
            continue
        attempted += 1
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
            failed_by_doctype.setdefault(link.frappe_doctype, []).append(link.name)
            continue
    if not dry_run:
        frappe.db.commit()

    return {
        "dry_run": dry_run,
        "by_doctype": counts,
        "deleted_by_doctype": deleted_counts,
        "failed_by_doctype": failed_by_doctype,
        "deleted": deleted,
        "total": sum(counts.values()),
    }


def run_purge_with_log(limit: int | None = None, log_name: str | None = None) -> str:
    """Chunked destructive purge, tracked on a Retention Log.

    The ``frappe.enqueue`` target for the purge — see
    ``api/sync.py::purge_synced_data``, which claims the run and creates
    the log synchronously (``log_name``) so the single-run guard has no
    queue-latency race. Runs the first chunk in this job and lets
    ``_run_purge_chunk`` re-enqueue continuations until nothing purgeable
    remains. Dry-run stays a direct synchronous call (just COUNT()s).
    """
    from frappe_salesforce.tasks import retention_log

    if log_name is None:  # direct/console invocation
        log_name = retention_log.create_log("Purge")
    _run_purge_chunk(log_name=log_name, limit=limit, totals={}, failed_by_doctype={})
    return log_name


def _run_purge_chunk(
    log_name: str,
    limit: int | None,
    totals: dict,
    failed_by_doctype: dict | None = None,
) -> None:
    """Delete one bounded slice of links, then re-enqueue the continuation.

    ``totals`` accumulates ``{doctype: {"count": deleted, "failed": n}}``
    across chunks; ``failed_by_doctype`` carries the *identities* of links
    that already failed (``{doctype: [link names]}``) so they are skipped —
    not retried and re-counted — by every later chunk. Both travel through
    the enqueue kwargs and are mirrored onto the log after every chunk.
    ``purge_synced_records`` re-reads the remaining links on every call, so
    continuation needs no cursor.
    """
    from frappe_salesforce.tasks import retention_log

    failed_by_doctype = failed_by_doctype or {}
    try:
        total_deleted = sum(t.get("count", 0) for t in totals.values())
        chunk_cap = (
            CHUNK_SIZE if limit is None else min(CHUNK_SIZE, max(0, limit - total_deleted))
        )
        if chunk_cap == 0:
            retention_log.finalize_log(log_name, totals)
            return

        skip = [name for names in failed_by_doctype.values() for name in names]
        result = purge_synced_records(dry_run=False, limit=chunk_cap, skip_names=skip)

        for doctype, names in result["failed_by_doctype"].items():
            failed_by_doctype.setdefault(doctype, []).extend(names)
        for doctype, n in result["deleted_by_doctype"].items():
            totals.setdefault(doctype, {"count": 0, "failed": 0})["count"] += n
        for doctype, names in failed_by_doctype.items():
            # Absolute (not +=): failed identities are tracked exactly once.
            totals.setdefault(doctype, {"count": 0, "failed": 0})["failed"] = len(names)
        retention_log.update_progress(log_name, totals)

        if result["total"] == 0:
            # Nothing attempted: no purgeable links left beyond the
            # known-failed set (which we don't retry) — we're done.
            retention_log.finalize_log(log_name, totals)
            return

        frappe.enqueue(
            "frappe_salesforce.tasks.retention_backfill._run_purge_chunk",
            queue=CHUNK_QUEUE,
            timeout=CHUNK_TIMEOUT,
            job_name=f"salesforce_purge_chunk_{log_name}",
            log_name=log_name,
            limit=limit,
            totals=totals,
            failed_by_doctype=failed_by_doctype,
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title=f"Salesforce Retention Log {log_name}: purge chunk failed",
            message=frappe.get_traceback(),
        )
        retention_log.fail_log(log_name, str(e), totals)


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

    ``limit`` is a **per-object** cap, not a total across the run — e.g.
    ``limit=200`` caps Account/Contact/Opportunity at up to 200 each (so up
    to ~1000 records total), not 200 combined. Intended for controlled test
    slices before a full (``limit=None``) run; confirmed via this exact
    shape during manual validation (Account 200 / Contact 200 /
    Opportunity 200 / Task 255 / Event 2).

    Note: when ``limit`` truncates an Account/Contact/Opportunity import,
    the activity backfill's parent set still includes every KEEP-matched Id
    (not just the ones actually imported before the cut-off) — a handful of
    Task/Event rows in a truncated test slice may therefore reference a
    parent that wasn't imported this run. Harmless for a full run
    (``limit=None``, the normal production path), where nothing is
    truncated.

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


def run_backfill_with_log(limit: int | None = None, log_name: str | None = None) -> str:
    """Chunked selective backfill, tracked on a Retention Log.

    The ``frappe.enqueue`` target for the backfill — see
    ``api/sync.py::start_retention_backfill``, which claims the run and
    creates the log synchronously (``log_name``) so the single-run guard
    has no queue-latency race. Runs the first chunk in this job and lets
    ``_run_backfill_chunk`` re-enqueue continuations phase by phase. Same
    KEEP semantics and per-object ``limit`` contract as
    ``run_retention_backfill`` (which remains the synchronous,
    console-friendly single-shot variant).
    """
    from frappe_salesforce.tasks import retention_log

    if log_name is None:  # direct/console invocation
        log_name = retention_log.create_log("Backfill")
    _run_backfill_chunk(
        log_name=log_name, limit=limit, phase_idx=0, offset=0, totals={}
    )
    return log_name


def _run_backfill_chunk(
    log_name: str, limit: int | None, phase_idx: int, offset: int, totals: dict
) -> None:
    """Import one bounded slice, then re-enqueue the continuation.

    State (phase index + offset into that phase's sorted KEEP-id list +
    running totals) travels through the enqueue kwargs; the id lists are
    cached per run (see ``_phase_ids``) so continuations don't recompute
    the KEEP queries every chunk.
    """
    from frappe_salesforce.tasks import retention_log

    try:
        client = SalesforceClient()
        by_object = {S.salesforce_object: S for S in SYNCERS}

        while phase_idx < len(BACKFILL_PHASES):
            phase = BACKFILL_PHASES[phase_idx]
            ids = _phase_ids(client, phase, log_name)
            t = totals.setdefault(phase, {"count": 0, "failed": 0})
            remaining = None if limit is None else max(0, limit - t["count"])
            if offset >= len(ids) or remaining == 0:
                phase_idx += 1
                offset = 0
                continue

            batch = ids[offset : offset + CHUNK_SIZE]
            id_list = ", ".join(f"'{i}'" for i in batch)
            syncer = by_object[phase](client, frappe._dict())
            if phase in ("Task", "Event"):
                # Activities are kept by linkage to a kept parent; the
                # batch here is parent ids, not activity ids. An activity
                # referencing parents in two different batches just gets
                # upserted twice (idempotent).
                extra_where = f"WhoId IN ({id_list}) OR WhatId IN ({id_list})"
            else:
                extra_where = f"Id IN ({id_list})"
            soql = build_incremental_query(
                sobject=phase,
                fields=syncer._soql_fields(),
                since=EPOCH,
                extra_where=extra_where,
            )
            imported, failed = _import_query(syncer, client, soql, remaining)
            t["count"] += imported
            t["failed"] += failed
            offset += CHUNK_SIZE
            retention_log.update_progress(log_name, totals)

            # Yield the worker: continuation goes to the back of the queue
            # so other pending jobs get a turn between chunks.
            frappe.enqueue(
                "frappe_salesforce.tasks.retention_backfill._run_backfill_chunk",
                queue=CHUNK_QUEUE,
                timeout=CHUNK_TIMEOUT,
                job_name=f"salesforce_backfill_chunk_{log_name}",
                log_name=log_name,
                limit=limit,
                phase_idx=phase_idx,
                offset=offset,
                totals=totals,
            )
            return

        retention_log.finalize_log(log_name, totals)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title=f"Salesforce Retention Log {log_name}: backfill chunk failed",
            message=frappe.get_traceback(),
        )
        retention_log.fail_log(log_name, str(e), totals)


def _phase_ids(client: SalesforceClient, phase: str, log_name: str) -> list[str]:
    """Sorted SF ids this phase should import, cached per run.

    Account/Contact: union of the KEEP rules (``kept_parent_ids``).
    Opportunity: ids matching ``opportunity_keep_where()``.
    Task/Event: the union of all three parent id sets — activities are
    kept by linkage, matching ``run_retention_backfill``'s contract of
    scoping to THIS run's KEEP set (not whatever links already exist).

    Cached in Redis keyed by the log name so continuations don't redo the
    KEEP queries every chunk; recomputed transparently if evicted.
    """
    cache_slot = "activities" if phase in ("Task", "Event") else phase
    cache_key = f"sf_retention_ids:{log_name}:{cache_slot}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return json.loads(cached)

    if phase in ("Account", "Contact"):
        ids = sorted(kept_parent_ids(client, retention.PARENT_KEEP[phase]))
    elif phase == "Opportunity":
        ids = sorted(
            rec["Id"]
            for rec in client.query(
                f"SELECT Id FROM Opportunity WHERE {retention.opportunity_keep_where()}"
            )
            if rec.get("Id")
        )
    else:
        ids = sorted(
            set(_phase_ids(client, "Account", log_name))
            | set(_phase_ids(client, "Contact", log_name))
            | set(_phase_ids(client, "Opportunity", log_name))
        )

    frappe.cache().set_value(cache_key, json.dumps(ids), expires_in_sec=6 * 3600)
    return ids


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
