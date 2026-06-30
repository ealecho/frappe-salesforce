"""SOQL predicate builders for the one-time retention backfill.

Pure string builders (no Frappe / network) so they're unit-testable. Consumed
by ``tasks/retention_backfill.py`` (the selective import) and
``api/sync.retention_backfill_report`` (dry-run counts).

Retention policy — KEEP a contact/organisation when ANY of:
  * it has had any activity in the past 5 years;
  * it is linked to a donation on a campaign created in the past 5 years;
  * it has an active grant;
  * it gave a donation in the past 10 years.
Everything else is simply not imported (that is how the "REMOVE inactive >5y
unless they have a donation" rule is satisfied — by exclusion).

Org-specific interpretation
---------------------------
This org has no clean scalar flag separating a "grant" from a "donation"
Opportunity (confirmed during discovery — only opaque ``Type``/``RecordTypeId``
text, or the structural presence of ``Income_year__c`` children). Rather than
depend on that, the predicates use neutral signals that capture the policy
intent and are valid, un-nested SOQL:
  * "active grant"   -> an OPEN opportunity (``IsClosed = false``)
  * "donation given" -> the NPSP last-donation-date rollup on the Account/Contact
  * "campaign-linked"-> any opportunity whose Campaign was created recently

If strict grant-only / donation-only semantics are wanted later, set
``ACTIVE_GRANT`` to a grant-period rule and add an ``IS_DONATION`` scalar once the
RecordType/Type values are confirmed (Phase 0 probe). Keep leaf predicates
SCALAR — Salesforce rejects a semi-join nested inside another semi-join.
"""

from __future__ import annotations

#: Retention windows as SOQL relative-date literals.
ACTIVITY_WINDOW = "LAST_N_DAYS:1825"  # 5 years
DONATION_WINDOW = "LAST_N_DAYS:3650"  # 10 years
CAMPAIGN_WINDOW = "LAST_N_DAYS:1825"  # 5 years

#: An "active grant" is modelled as an open opportunity. Override to a grant
#: period rule if preferred, e.g. "npsp__Grant_Period_End_Date__c >= TODAY".
ACTIVE_GRANT = "IsClosed = false"


def _or(*clauses: str) -> str:
    """OR-join clauses, each parenthesised so precedence is unambiguous."""
    return " OR ".join(f"({c})" for c in clauses)


def account_keep_where() -> str:
    """KEEP predicate for the Account (CRM Organization) query."""
    return _or(
        f"LastActivityDate >= {ACTIVITY_WINDOW}",
        f"npe01__LastDonationDate__c >= {DONATION_WINDOW}",
        f"Id IN (SELECT AccountId FROM Opportunity WHERE {ACTIVE_GRANT})",
        f"Id IN (SELECT AccountId FROM Opportunity "
        f"WHERE Campaign.CreatedDate >= {CAMPAIGN_WINDOW})",
    )


def contact_keep_where() -> str:
    """KEEP predicate for the Contact query.

    NB the Contact rollup field is ``npe01__Last_Donation_Date__c`` (note the
    extra underscores vs the Account field ``npe01__LastDonationDate__c``).
    """
    return _or(
        f"LastActivityDate >= {ACTIVITY_WINDOW}",
        f"npe01__Last_Donation_Date__c >= {DONATION_WINDOW}",
        f"Id IN (SELECT ContactId FROM Opportunity WHERE {ACTIVE_GRANT})",
        f"Id IN (SELECT ContactId FROM Opportunity "
        f"WHERE Campaign.CreatedDate >= {CAMPAIGN_WINDOW})",
    )


def opportunity_keep_where() -> str:
    """KEEP predicate for the Opportunity (CRM Deal) query.

    Imports the materially relevant deals of kept parties: active grants, gifts
    received in the past 10 years, and anything on a recently-created campaign.
    """
    return _or(
        ACTIVE_GRANT,
        f"IsWon = true AND CloseDate >= {DONATION_WINDOW}",
        f"Campaign.CreatedDate >= {CAMPAIGN_WINDOW}",
    )


#: salesforce_object -> KEEP predicate builder. Objects absent here (Task,
#: Event, User) are not selected by a self-predicate: activities are imported
#: by linkage to kept records (see tasks/retention_backfill), and the link-only
#: User syncer creates no docs.
KEEP_WHERE = {
    "Account": account_keep_where,
    "Contact": contact_keep_where,
    "Opportunity": opportunity_keep_where,
}
