"""Frappe Address creation/update from Salesforce compound address blocks.

Salesforce stores compound addresses as a flat group of fields:
``BillingStreet``, ``BillingCity``, ``BillingState``, ``BillingPostalCode``,
``BillingCountry`` (plus ``Shipping*`` / ``Mailing*`` / ``Other*`` variants).

Frappe represents addresses as a separate ``Address`` DocType linked back to
the parent doc via a ``Dynamic Link`` child row. This helper bridges the two:
given a parent ``(doctype, name)`` and a SF block prefix, ensure an Address
exists, fields match, and a Dynamic Link points at the parent.

Idempotent: subsequent runs with the same prefix on the same parent will
update the existing Address rather than create duplicates.
"""

from __future__ import annotations

from typing import Iterable

import frappe

# SF prefix -> ("Billing"/"Shipping"/...) -> Frappe address_type Select
ADDRESS_TYPE_MAP = {
    "Billing": "Billing",
    "Shipping": "Shipping",
    "Mailing": "Billing",
    "Other": "Other",
}

# SF compound fields per prefix. SF uses both flat (BillingStreet) and
# nested (BillingAddress.street) forms; we accept the flat form.
_SUFFIXES = ("Street", "City", "State", "PostalCode", "Country")


def extract_block(rec: dict, prefix: str) -> dict | None:
    """Return a dict of address fields, or None if the block is fully empty."""
    block = {}
    for suffix in _SUFFIXES:
        val = rec.get(f"{prefix}{suffix}")
        if val:
            block[suffix.lower()] = str(val).strip()
    return block or None


def upsert_address(
    parent_doctype: str,
    parent_name: str,
    prefix: str,
    block: dict,
) -> str | None:
    """Create or update an ``Address`` doc and Dynamic Link for the parent.

    Returns the Address docname, or ``None`` if nothing was written.
    """
    if not block or not parent_name:
        return None

    address_type = ADDRESS_TYPE_MAP.get(prefix, "Other")

    # Find an existing Address linked to this parent with this address_type.
    existing = frappe.db.sql(
        """
        SELECT a.name
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent = a.name
        WHERE dl.parenttype = 'Address'
          AND dl.link_doctype = %s
          AND dl.link_name = %s
          AND a.address_type = %s
        LIMIT 1
        """,
        (parent_doctype, parent_name, address_type),
    )

    values = {
        "address_line1": block.get("street") or "",
        "city": block.get("city") or "",
        "state": block.get("state") or "",
        "pincode": block.get("postalcode") or "",
        "country": _resolve_country(block.get("country")),
        "address_type": address_type,
    }

    if existing:
        addr = frappe.get_doc("Address", existing[0][0])
        addr.update(values)
        addr.save(ignore_permissions=True)
        return addr.name

    # Create a new Address with a single Dynamic Link to the parent.
    title = block.get("city") or parent_name
    addr = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": title,
            **values,
            "links": [
                {
                    "link_doctype": parent_doctype,
                    "link_name": parent_name,
                }
            ],
        }
    )
    addr.insert(ignore_permissions=True)
    return addr.name


def upsert_addresses(
    parent_doctype: str,
    parent_name: str,
    rec: dict,
    prefixes: Iterable[str],
) -> None:
    """Convenience wrapper: upsert each prefix that has data on ``rec``."""
    for prefix in prefixes:
        block = extract_block(rec, prefix)
        if block:
            upsert_address(parent_doctype, parent_name, prefix, block)


def _resolve_country(name: str | None) -> str:
    """Return a Country docname or empty string if the value isn't recognised.

    Frappe's Country DocType uses the country name as its primary key (e.g.
    ``"United States"``). Salesforce often stores ISO codes (``"US"``) or
    abbreviations — we do a best-effort exact match and fall back to empty.
    """
    if not name:
        return ""
    name = name.strip()
    if frappe.db.exists("Country", name):
        return name
    # Try by code (2-letter) which Frappe Country stores in ``code``.
    if len(name) <= 3:
        match = frappe.db.get_value("Country", {"code": name.lower()}, "name")
        if match:
            return match
    return ""
