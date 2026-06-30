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
from frappe_salesforce.tasks.deletion import DeletionSyncRunner

#: A "since" far enough back that ``SystemModstamp > since`` matches everything,
#: so the retention predicate is the only effective filter.
EPOCH = "1970-01-01 00:00:00"
_ID_BATCH = 200

#: Only objects the retention backfill re-imports may be purged. Crucially this
#: EXCLUDES Lead: the policy has no Lead KEEP rule, so the backfill never brings
#: leads back — purging them would delete the incoming pipeline for good. (User
#: is link-only and already skipped.)
PURGE_OBJECTS = {"Account", "Contact", "Opportunity", "Task", "Event"}


def purge_synced_records(dry_run: bool = True) -> dict:
    """Delete CRM records created by the sync, per ``Salesforce Record Link``.

    Skips link-only objects (e.g. User — we never delete Users). HWMs are NOT
    reset: leaving them at their current value keeps the post-purge incremental
    tick from replaying the excluded history. ``dry_run`` only counts.
    """
    by_object = {S.salesforce_object: S for S in SYNCERS}
    deleter = DeletionSyncRunner()
    links = frappe.get_all(
        "Salesforce Record Link",
        fields=["salesforce_id", "salesforce_object", "frappe_doctype", "frappe_name"],
    )

    counts: dict[str, int] = {}
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
        deleter._delete_frappe_doc(link.salesforce_id, syncer)
        deleted += 1
        if deleted % 100 == 0:
            frappe.db.commit()
    if not dry_run:
        frappe.db.commit()

    return {"dry_run": dry_run, "by_doctype": counts, "total": sum(counts.values())}


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
    """Import only records matching the KEEP rules, in dependency order."""
    client = SalesforceClient()
    summary: dict[str, int] = {}
    by_object = {S.salesforce_object: S for S in SYNCERS}

    # Account / Contact: union the kept Ids (scalar + opportunity-derived rules),
    # then import those parents by Id (semi-joins can't be OR-combined inline).
    for obj in ("Account", "Contact"):
        syncer = by_object[obj](client, frappe._dict())
        ids = sorted(kept_parent_ids(client, retention.PARENT_KEEP[obj]))
        summary[obj] = _import_by_ids(syncer, client, obj, ids, limit)

    # Opportunity: single predicate query (all scalar terms -> OR is allowed).
    opp = by_object["Opportunity"](client, frappe._dict())
    opp_soql = build_incremental_query(
        sobject="Opportunity",
        fields=opp._soql_fields(),
        since=EPOCH,
        extra_where=retention.opportunity_keep_where(),
    )
    summary["Opportunity"] = _import_query(opp, client, opp_soql, limit)

    summary.update(_backfill_activities(client, limit))
    return summary


def _import_by_ids(syncer, client, sobject, ids, limit) -> int:
    """Import ``sobject`` records for the given SF Ids, in batches of 200."""
    fields = syncer._soql_fields()
    imported = 0
    for start in range(0, len(ids), _ID_BATCH):
        batch = ids[start : start + _ID_BATCH]
        id_list = ", ".join(f"'{i}'" for i in batch)
        soql = build_incremental_query(
            sobject=sobject, fields=fields, since=EPOCH, extra_where=f"Id IN ({id_list})"
        )
        remaining = None if limit is None else max(0, limit - imported)
        imported += _import_query(syncer, client, soql, remaining)
        if limit and imported >= limit:
            break
    return imported


def _backfill_activities(client: SalesforceClient, limit: int | None) -> dict:
    """Import Tasks/Events that point at a kept Account/Contact/Opportunity.

    Activities are engagement records, not retention targets, so they are kept
    by linkage: we gather the SF ids we just imported and pull only activities
    whose ``WhoId``/``WhatId`` references one of them.
    """
    kept_ids = [
        row.salesforce_id
        for row in frappe.get_all(
            "Salesforce Record Link",
            filters={"salesforce_object": ["in", ["Account", "Contact", "Opportunity"]]},
            fields=["salesforce_id"],
        )
        if row.salesforce_id
    ]
    out: dict[str, int] = {}
    if not kept_ids:
        return out

    for syncer_cls in SYNCERS:
        if syncer_cls.salesforce_object not in ("Task", "Event"):
            continue
        syncer = syncer_cls(client, frappe._dict())
        fields = syncer._soql_fields()
        seen: set[str] = set()
        imported = 0
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
            imported += _import_query(syncer, client, soql, limit, seen=seen)
            if limit and imported >= limit:
                break
        out[syncer_cls.salesforce_object] = imported
    return out


def _import_query(syncer, client, soql, limit, seen=None) -> int:
    """Run one retention SOQL query, upserting each record. Returns count."""
    imported = 0
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
        if limit and imported >= limit:
            break
    return imported
