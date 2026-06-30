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


def run_retention_backfill(limit: int | None = None) -> dict:
    """Import only records matching the KEEP predicates, in dependency order."""
    client = SalesforceClient()
    summary: dict[str, int] = {}

    for syncer_cls in SYNCERS:
        builder = retention.KEEP_WHERE.get(syncer_cls.salesforce_object)
        if builder is None:
            continue  # activities + User handled separately / skipped
        syncer = syncer_cls(client, frappe._dict())
        soql = build_incremental_query(
            sobject=syncer_cls.salesforce_object,
            fields=syncer._soql_fields(),
            since=EPOCH,
            extra_where=builder(),
        )
        summary[syncer_cls.salesforce_object] = _import_query(syncer, client, soql, limit)

    summary.update(_backfill_activities(client, limit))
    return summary


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
