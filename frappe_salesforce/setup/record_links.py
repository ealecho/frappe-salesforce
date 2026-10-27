"""One ``Salesforce Record Link`` per Salesforce record.

Nothing stopped two links for the same ``(salesforce_object,
salesforce_id)``. On 2026-05-14 two overlapping Opportunity runs each
created their own link for the same records (the first run never reached a
commit, so the second couldn't see its rows), leaving thousands of
Opportunities with a second, blank link. ``ensure_record_link_unique``
removes the duplicates and adds a unique key so it can't happen again.

Salesforce REST always returns 18-character ids, which are unique
case-insensitively, so the default case-insensitive collation is safe for
the key.
"""

from __future__ import annotations

import frappe

DOCTYPE = "Salesforce Record Link"
UNIQUE_FIELDS = ["salesforce_object", "salesforce_id"]
UNIQUE_CONSTRAINT = "unique_salesforce_object_id"


def ensure_record_link_unique() -> int:
    """Delete duplicate links, then add the unique key. Idempotent.

    Returns the number of duplicate links deleted.
    """
    deleted = delete_duplicate_links()
    frappe.db.add_unique(DOCTYPE, UNIQUE_FIELDS, constraint_name=UNIQUE_CONSTRAINT)
    return deleted


def delete_duplicate_links() -> int:
    """Keep the best link per Salesforce record and delete the rest.

    The keeper is the link whose Frappe record still exists, then a Synced
    one, then the most recently synced. A deleted link that pointed at a
    *different*, still-existing record is listed in an Error Log, since
    that record is no longer reachable from its Salesforce id.
    """
    rows = frappe.db.sql(
        f"""
        select l.name, l.salesforce_object, l.salesforce_id, l.frappe_doctype,
            l.frappe_name, l.sync_status, l.last_synced_at, l.modified
        from `tab{DOCTYPE}` l
        join (
            select salesforce_object, salesforce_id
            from `tab{DOCTYPE}`
            group by salesforce_object, salesforce_id
            having count(*) > 1
        ) d on d.salesforce_object = l.salesforce_object
            and d.salesforce_id = l.salesforce_id
        """,
        as_dict=True,
    )
    groups: dict[tuple[str, str], list] = {}
    for row in rows:
        key = (row.salesforce_object, row.salesforce_id.lower())
        groups.setdefault(key, []).append(row)

    to_delete: list[str] = []
    orphaned: list[str] = []
    for links in groups.values():
        for link in links:
            link.target_exists = _target_exists(link)
        keep = max(links, key=_keep_rank)
        for link in links:
            if link.name == keep.name:
                continue
            to_delete.append(link.name)
            if link.target_exists and (
                link.frappe_doctype,
                link.frappe_name,
            ) != (keep.frappe_doctype, keep.frappe_name):
                orphaned.append(
                    f"{link.salesforce_object} {link.salesforce_id}: "
                    f"{link.frappe_doctype} {link.frappe_name} "
                    f"(kept {keep.frappe_doctype} {keep.frappe_name})"
                )

    for start in range(0, len(to_delete), 1000):
        frappe.db.delete(DOCTYPE, {"name": ("in", to_delete[start : start + 1000])})

    if orphaned:
        frappe.log_error(
            title=f"SF Record Link dedupe: {len(orphaned)} records lost their link",
            message=(
                "These duplicate links pointed at a different Frappe record "
                "than the one kept. That record still exists but no link "
                "points at it any more; review it for a duplicate.\n\n"
                + "\n".join(orphaned)
            ),
        )
    return len(to_delete)


def _target_exists(link) -> bool:
    return bool(
        link.frappe_doctype
        and link.frappe_name
        and frappe.db.exists(link.frappe_doctype, link.frappe_name)
    )


def _keep_rank(link) -> tuple:
    return (
        link.target_exists,
        link.sync_status == "Synced",
        str(link.last_synced_at or ""),
        str(link.modified or ""),
    )
