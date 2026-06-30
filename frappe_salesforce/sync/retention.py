"""Retention KEEP specifications for the one-time selective backfill.

Pure data/string builders (no Frappe / network) so they're unit-testable.
Consumed by ``tasks/retention_backfill.py`` (import) and
``api/sync.retention_backfill_report`` (dry-run counts).

Retention policy — KEEP a contact/organisation when ANY of:
  * it has had any activity in the past 5 years;
  * it is linked to a donation on a campaign created in the past 5 years;
  * it has an active grant;
  * it gave a donation in the past 10 years.
Everything else is simply not imported (that satisfies "REMOVE inactive >5y
unless they have a donation" by exclusion).

Why this is split into a scalar predicate + lookup rules
--------------------------------------------------------
Salesforce **forbids combining a semi-join (`Id IN (SELECT ...)`) with `OR`**
(`MALFORMED_QUERY: Semi join sub-selects are not allowed with the 'OR'
operator`). So a parent's KEEP set is computed as a UNION of separate queries:

  * ``scalar_where`` — the rules expressible as plain fields on the parent
    (activity recency + donation rollup); scalar ``OR`` is allowed, so these run
    as one query returning parent Ids.
  * ``lookup_rules`` — the rules that depend on related Opportunities (active
    grant, recent campaign); each runs as its own child query, and we collect
    the parent lookup Id (``AccountId`` / ``ContactId``) from the results.

The runner unions the Ids from all of these, then imports those parents.

Org-specific interpretation (neutral signals, no grant/donation discriminator):
  * "active grant"    -> an OPEN opportunity (``ACTIVE_GRANT``)
  * "donation given"  -> the NPSP last-donation-date rollup on the parent
  * "campaign-linked" -> any opportunity whose Campaign was created recently
"""

from __future__ import annotations

#: Retention windows as SOQL relative-date literals.
ACTIVITY_WINDOW = "LAST_N_DAYS:1825"  # 5 years
DONATION_WINDOW = "LAST_N_DAYS:3650"  # 10 years
CAMPAIGN_WINDOW = "LAST_N_DAYS:1825"  # 5 years

#: An "active grant" is modelled as an open opportunity. Override to a grant
#: period rule if preferred, e.g. "npsp__Grant_Period_End_Date__c >= TODAY".
ACTIVE_GRANT = "IsClosed = false"

#: Opportunities whose parent should be kept due to a recently-created campaign.
RECENT_CAMPAIGN = f"Campaign.CreatedDate >= {CAMPAIGN_WINDOW}"

#: KEEP spec per parent object. ``scalar_where`` is one query on the parent;
#: ``lookup_rules`` are (child_object, parent_lookup_field, child_where) tuples
#: each run separately, contributing the parent Ids they reference.
ACCOUNT_KEEP = {
    "object": "Account",
    "scalar_where": (
        f"LastActivityDate >= {ACTIVITY_WINDOW} "
        f"OR npe01__LastDonationDate__c >= {DONATION_WINDOW}"
    ),
    "lookup_rules": [
        ("Opportunity", "AccountId", ACTIVE_GRANT),
        ("Opportunity", "AccountId", RECENT_CAMPAIGN),
    ],
}

CONTACT_KEEP = {
    "object": "Contact",
    # NB the Contact rollup API name differs from the Account's.
    "scalar_where": (
        f"LastActivityDate >= {ACTIVITY_WINDOW} "
        f"OR npe01__Last_Donation_Date__c >= {DONATION_WINDOW}"
    ),
    "lookup_rules": [
        ("Opportunity", "ContactId", ACTIVE_GRANT),
        ("Opportunity", "ContactId", RECENT_CAMPAIGN),
    ],
}

#: Parent KEEP specs keyed by salesforce_object (consumed by the runner/report).
PARENT_KEEP = {"Account": ACCOUNT_KEEP, "Contact": CONTACT_KEEP}


def opportunity_keep_where() -> str:
    """KEEP predicate for the Opportunity (CRM Deal) query.

    All scalar / parent-field terms, so OR-combining is allowed (no semi-join).
    Imports active grants, gifts received in the past 10 years, and anything on
    a recently-created campaign.
    """
    return " OR ".join(
        f"({c})"
        for c in (
            ACTIVE_GRANT,
            f"IsWon = true AND CloseDate >= {DONATION_WINDOW}",
            RECENT_CAMPAIGN,
        )
    )
