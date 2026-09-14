"""Repair sync data clobbered/omitted by earlier runs.

1. ``closed_date``: Frappe CRM core's validate stamps ``closed_date =
   nowdate()`` when a deal is inserted in a Won-type status, so every deal
   imported by the backfill carries the *sync run date* instead of the SF
   CloseDate (1,046 of 1,700 won deals on the PEAS dev site were stamped
   with the backfill day). The true SF CloseDate lives in
   ``expected_closure_date`` (direct mapping row), so restore from there
   for every synced, closed deal. The syncer now re-asserts the date via
   ``db_set`` after each save, keeping this fixed going forward.

2. ``address`` Link fields: addresses were synced as Address docs with
   Dynamic Links only; the native ``address`` field on CRM Organization /
   Contact — the one the CRM UI displays — was never set. Point it at the
   already-linked Address (skipping records where a user set one manually).
"""

import frappe


def execute():
    _repair_closed_dates()
    for doctype in ("CRM Organization", "Contact"):
        _repair_address_links(doctype)


def _repair_closed_dates():
    if not frappe.db.exists("DocType", "CRM Deal"):
        return
    meta = frappe.get_meta("CRM Deal")
    if not (
        meta.get_field("custom_salesforce_id")
        and meta.get_field("custom_sf_is_closed")
    ):
        return
    frappe.db.sql(
        """
        UPDATE `tabCRM Deal`
        SET closed_date = expected_closure_date
        WHERE IFNULL(custom_salesforce_id, '') != ''
          AND custom_sf_is_closed = 1
          AND expected_closure_date IS NOT NULL
          AND (closed_date IS NULL OR closed_date != expected_closure_date)
        """
    )


def _repair_address_links(doctype):
    if not frappe.db.exists("DocType", doctype):
        return
    df = frappe.get_meta(doctype).get_field("address")
    if not df or df.fieldtype != "Link" or df.options != "Address":
        return
    # One arbitrary-but-stable linked Address per parent (min address name);
    # only parents whose address field is still empty.
    frappe.db.sql(
        """
        UPDATE `tab{doctype}` p
        JOIN (
            SELECT dl.link_name AS parent_name, MIN(dl.parent) AS address_name
            FROM `tabDynamic Link` dl
            WHERE dl.parenttype = 'Address' AND dl.link_doctype = %s
            GROUP BY dl.link_name
        ) a ON a.parent_name = p.name
        SET p.address = a.address_name
        WHERE IFNULL(p.address, '') = ''
        """.format(doctype=doctype),
        (doctype,),
    )
