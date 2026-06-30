"""Tests for the retention KEEP predicate builders (pure SOQL strings)."""

from frappe_salesforce.sync import retention


def test_windows_are_five_and_ten_years():
    assert retention.ACTIVITY_WINDOW == "LAST_N_DAYS:1825"
    assert retention.CAMPAIGN_WINDOW == "LAST_N_DAYS:1825"
    assert retention.DONATION_WINDOW == "LAST_N_DAYS:3650"


def test_account_keep_covers_all_four_rules():
    w = retention.account_keep_where()
    assert "LastActivityDate >= LAST_N_DAYS:1825" in w           # 5y activity
    assert "npe01__LastDonationDate__c >= LAST_N_DAYS:3650" in w  # 10y donation
    assert "SELECT AccountId FROM Opportunity WHERE IsClosed = false" in w  # active grant
    assert "Campaign.CreatedDate >= LAST_N_DAYS:1825" in w        # recent campaign
    # OR-combined, each term parenthesised
    assert w.count(" OR ") == 3
    assert w.startswith("(")


def test_contact_uses_contact_specific_rollup_field():
    w = retention.contact_keep_where()
    # Contact rollup API name differs from Account's (extra underscores).
    assert "npe01__Last_Donation_Date__c >= LAST_N_DAYS:3650" in w
    assert "npe01__LastDonationDate__c" not in w
    assert "SELECT ContactId FROM Opportunity" in w


def test_opportunity_keep_is_active_won_or_campaign():
    w = retention.opportunity_keep_where()
    assert "IsClosed = false" in w
    assert "IsWon = true AND CloseDate >= LAST_N_DAYS:3650" in w
    assert "Campaign.CreatedDate >= LAST_N_DAYS:1825" in w


def test_keep_where_registry_maps_core_objects_only():
    assert set(retention.KEEP_WHERE) == {"Account", "Contact", "Opportunity"}
    # builders are callable and return non-empty predicates
    for builder in retention.KEEP_WHERE.values():
        assert builder().strip()


def test_active_grant_predicate_is_scalar_not_nested_semijoin():
    # Leaf predicate must stay scalar: SF rejects a semi-join nested inside a
    # semi-join, and ACTIVE_GRANT is used inside `Id IN (SELECT ...)`.
    assert "SELECT" not in retention.ACTIVE_GRANT
