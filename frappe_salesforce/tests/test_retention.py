"""Tests for the retention KEEP specs (pure SOQL strings / specs)."""

from frappe_salesforce.sync import retention


def test_windows_are_five_and_ten_years():
    assert retention.ACTIVITY_WINDOW == "LAST_N_DAYS:1825"
    assert retention.CAMPAIGN_WINDOW == "LAST_N_DAYS:1825"
    assert retention.DONATION_WINDOW == "LAST_N_DAYS:3650"


def test_account_scalar_keep_is_pure_scalar_or():
    spec = retention.ACCOUNT_KEEP
    assert spec["object"] == "Account"
    w = spec["scalar_where"]
    assert "LastActivityDate >= LAST_N_DAYS:1825" in w
    assert "npe01__LastDonationDate__c >= LAST_N_DAYS:3650" in w
    # Scalar OR only — no semi-join in the OR'd predicate (SF forbids that mix).
    assert "SELECT" not in w


def test_account_lookup_rules_collect_accountid():
    rules = retention.ACCOUNT_KEEP["lookup_rules"]
    assert ("Opportunity", "AccountId", "IsClosed = false") in rules
    assert ("Opportunity", "AccountId", retention.RECENT_CAMPAIGN) in rules


def test_contact_uses_contact_specific_rollup_and_contactid():
    spec = retention.CONTACT_KEEP
    assert "npe01__Last_Donation_Date__c >= LAST_N_DAYS:3650" in spec["scalar_where"]
    assert "npe01__LastDonationDate__c" not in spec["scalar_where"]
    assert all(lr[1] == "ContactId" for lr in spec["lookup_rules"])


def test_opportunity_keep_is_scalar_or_no_semijoin():
    w = retention.opportunity_keep_where()
    assert "IsClosed = false" in w
    assert "IsWon = true AND CloseDate >= LAST_N_DAYS:3650" in w
    assert "Campaign.CreatedDate >= LAST_N_DAYS:1825" in w
    assert "SELECT" not in w  # all scalar -> safe to OR


def test_parent_keep_registry_covers_account_and_contact():
    assert set(retention.PARENT_KEEP) == {"Account", "Contact"}
    for spec in retention.PARENT_KEEP.values():
        assert spec["scalar_where"] and spec["lookup_rules"]


def test_recent_campaign_uses_parent_traversal_not_semijoin():
    # Parent-field traversal (Campaign.CreatedDate) is allowed in OR; a
    # semi-join would not be.
    assert retention.RECENT_CAMPAIGN == "Campaign.CreatedDate >= LAST_N_DAYS:1825"
