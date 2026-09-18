"""Enqueue the one-off EmailMessage history import.

The new EmailMessage → Communication syncer keeps emails current from
its high-water mark onward; existing correspondence needs one full pull.
Enqueued (long queue) rather than run inline: it's a network job over
potentially thousands of records, and a migrate must never hang or fail
on Salesforce being slow — the job itself no-ops if sync is disabled and
logs a summary when done. Unlike Tasks, EmailMessage is not subject to
SF activity archival, so this brings the complete email history.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Salesforce Settings"):
        return
    frappe.enqueue(
        "frappe_salesforce.sync.emails.backfill_all_email_messages",
        queue="long",
        timeout=3600,
        job_name="sf_email_message_backfill",
    )
