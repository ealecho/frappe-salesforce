"""Frappe ``Address`` upsert helpers for SF address blocks.

Frappe stores addresses in a separate ``Address`` doctype linked back to
the parent (``CRM Organization``, ``Contact``, ``CRM Lead``) via a
``Dynamic Link`` row in ``Address.links``.

The convention here:

* One ``Address`` doc per ``(parent_doctype, parent_name, address_type)``.
* ``address_type`` is the SF prefix capitalised (``Billing``, ``Mailing``,
  ``Other``, ``Shipping``); a Lead's flat ``Street/City/...`` block uses
  ``"Primary"``.
* The Address ``address_title`` is ``f"{parent_name} - {address_type}"``
  (Frappe enforces uniqueness of address_title per address_type otherwise).
* Idempotent: re-running with identical data is a no-op; mutated SF fields
  trigger an in-place update.

Empty blocks (every SF field None/blank) are skipped.
"""

from __future__ import annotations

from typing import Any

import frappe

#: SF prefix → Frappe address_type label.
PREFIX_TO_TYPE = {
    "Billing": "Billing",
    "Shipping": "Shipping",
    "Mailing": "Office",  # closest Frappe Address Type for Contact mailing
    "Other": "Other",
    "": "Primary",
}

#: Some SF records use a UK constituent country, informal name, or
#: alternate form in the Country field rather than Frappe's ISO
#: ``Country`` doctype entry, which fails ``LinkValidationError`` on
#: insert. Normalise the common ones (found via retention backfill error
#: log analysis: US/USA and "The Netherlands" alongside the UK synonyms).
COUNTRY_SYNONYMS = {
    "uk": "United Kingdom",
    "wales": "United Kingdom",
    "scotland": "United Kingdom",
    "england": "United Kingdom",
    "northern ireland": "United Kingdom",
    "great britain": "United Kingdom",
    "us": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.": "United States",
    "the netherlands": "Netherlands",
}


def _normalise_country(country: Any) -> Any:
    if not isinstance(country, str):
        return country
    return COUNTRY_SYNONYMS.get(country.strip().lower(), country)


def upsert_address_for_record(
    parent_doctype: str,
    parent_name: str,
    prefix: str,
    sf_record: dict[str, Any],
) -> str | None:
    """Upsert an Address doc derived from ``<prefix>Street/City/...``.

    ``prefix`` is one of ``Billing``, ``Shipping``, ``Mailing``, ``Other``,
    or ``""`` (Lead's flat block). Returns the docname of the upserted
    Address, or ``None`` if every relevant SF field was empty.
    """
    block = _extract_block(prefix, sf_record)
    if not _has_any_value(block):
        return None

    address_type = PREFIX_TO_TYPE.get(prefix, "Other")
    title = f"{parent_name} - {address_type}"

    existing = _find_existing_address(
        parent_doctype, parent_name, address_type, title
    )

    payload = {
        "address_title": title,
        "address_type": address_type,
        "address_line1": block.get("Street") or "(none)",
        # ``city`` is mandatory on Address; a fair number of SF records
        # have every other field but this one, so fall back like Street
        # rather than failing the whole insert.
        "city": block.get("City") or "(none)",
        "state": block.get("State"),
        "pincode": block.get("PostalCode"),
        "country": _normalise_country(block.get("Country")),
    }
    # Strip None to avoid clobbering preset values.
    payload = {k: v for k, v in payload.items() if v is not None}

    if existing:
        doc = frappe.get_doc("Address", existing)
        doc.update(payload)
        if not _has_link(doc, parent_doctype, parent_name):
            doc.append(
                "links",
                {"link_doctype": parent_doctype, "link_name": parent_name},
            )
        doc.save(ignore_permissions=True)
        return doc.name

    doc = frappe.get_doc(
        {
            "doctype": "Address",
            **payload,
            "links": [
                {"link_doctype": parent_doctype, "link_name": parent_name}
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------
def _extract_block(prefix: str, sf_record: dict[str, Any]) -> dict[str, Any]:
    """Pull ``<prefix>Street/City/State/PostalCode/Country`` from ``sf_record``."""
    return {
        suffix: sf_record.get(f"{prefix}{suffix}")
        for suffix in ("Street", "City", "State", "PostalCode", "Country")
    }


def _has_any_value(block: dict[str, Any]) -> bool:
    return any(v not in (None, "") for v in block.values())


def _find_existing_address(
    parent_doctype: str,
    parent_name: str,
    address_type: str,
    title: str,
) -> str | None:
    """Find an existing Address linked to this parent of the given type.

    Search strategy:
    1. Address with matching ``address_title`` (our naming convention).
    2. Any Address whose ``links`` row matches this parent and whose
       ``address_type`` matches.
    """
    by_title = frappe.db.get_value(
        "Address", {"address_title": title, "address_type": address_type}, "name"
    )
    if by_title:
        return by_title

    rows = frappe.db.sql(
        """
        SELECT a.name
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl
          ON dl.parent = a.name AND dl.parenttype = 'Address'
        WHERE dl.link_doctype = %s
          AND dl.link_name = %s
          AND a.address_type = %s
        LIMIT 1
        """,
        (parent_doctype, parent_name, address_type),
    )
    if rows:
        return rows[0][0]
    return None


def _has_link(addr_doc, parent_doctype: str, parent_name: str) -> bool:
    for row in addr_doc.get("links") or []:
        if row.link_doctype == parent_doctype and row.link_name == parent_name:
            return True
    return False
