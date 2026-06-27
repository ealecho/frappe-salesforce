"""Tests for the Opportunity child-table row builders.

These exercise the pure mapping helpers (no Frappe / network), using the
real Salesforce record shapes captured from the Four Acre Trust grants.
"""

from datetime import date

from frappe_salesforce.sync.opportunities import (
    budget_soql,
    build_budget_row,
    build_income_year_row,
    build_payment_row,
    derive_payment_status,
)


# Captured from SF: "Four Acre Trust - £100k Kabuta 2018 - Y1/4"
KABUTA_INCOME_YEAR = {
    "Income_year__c": "2018",
    "IY_Amount__c": 100000.0,
    "IY_TotalOpex__c": 20000.0,
    "IY_TotalCapex__c": 80000.0,
    "IY_ConfirmedOpex__c": 20000.0,
    "IY_ConfirmedCapex__c": 80000.0,
}


def test_income_year_row_maps_all_fields():
    row = build_income_year_row(KABUTA_INCOME_YEAR)
    assert row["income_year"] == "2018"
    assert row["iy_amount"] == 100000.0
    assert row["iy_opex"] == 20000.0
    assert row["iy_capex"] == 80000.0
    assert row["iy_confirmed_opex"] == 20000.0
    assert row["iy_confirmed_capex"] == 80000.0


def test_income_year_opex_percentage_is_derived():
    assert build_income_year_row(KABUTA_INCOME_YEAR)["opex_percentage"] == 20.0
    # 100% opex case (the 2019 unrestricted grant)
    full_opex = {"IY_Amount__c": 100000.0, "IY_TotalOpex__c": 100000.0}
    assert build_income_year_row(full_opex)["opex_percentage"] == 100.0


def test_income_year_opex_percentage_handles_zero_amount():
    row = build_income_year_row({"IY_Amount__c": 0.0, "IY_TotalOpex__c": 0.0})
    assert row["opex_percentage"] is None


def test_income_year_unsourced_columns_absent():
    # cost_type / country_allocation / confirmation_date have no SF source.
    row = build_income_year_row(KABUTA_INCOME_YEAR)
    assert "cost_type" not in row
    assert "confirmation_date" not in row


def test_payment_row_unpaid_scheduled_future():
    rec = {
        "npe01__Scheduled_Date__c": "2018-03-27",
        "npe01__Payment_Amount__c": 100000.0,
        "npe01__Payment_Date__c": None,
        "npe01__Paid__c": False,
        "npe01__Written_Off__c": False,
    }
    row = build_payment_row(rec, today=date(2018, 1, 1))
    assert row["expected_payment_date"] == "2018-03-27"
    assert row["amount_expected"] == 100000.0
    assert row["payment_received_date"] is None
    assert row["amount_received"] is None
    assert row["payment_status"] == "Pending"


def test_payment_row_paid():
    rec = {
        "npe01__Scheduled_Date__c": "2019-06-20",
        "npe01__Payment_Amount__c": 100000.0,
        "npe01__Payment_Date__c": "2019-06-18",
        "npe01__Paid__c": True,
        "npe01__Written_Off__c": False,
    }
    row = build_payment_row(rec, today=date(2026, 1, 1))
    assert row["payment_status"] == "Received"
    assert row["payment_received_date"] == "2019-06-18"
    assert row["amount_received"] == 100000.0


def test_payment_row_falls_back_to_payment_date_when_no_scheduled():
    # No scheduled date, but a real payment date exists -> use it for the
    # mandatory expected_payment_date rather than emitting None.
    rec = {
        "npe01__Scheduled_Date__c": None,
        "npe01__Payment_Amount__c": 5000.0,
        "npe01__Payment_Date__c": "2021-09-01",
        "npe01__Paid__c": True,
        "npe01__Written_Off__c": False,
    }
    row = build_payment_row(rec, today=date(2026, 1, 1))
    assert row is not None
    assert row["expected_payment_date"] == "2021-09-01"
    assert row["payment_status"] == "Received"


def test_payment_row_skipped_when_no_dates():
    # Neither scheduled nor payment date -> can't satisfy the mandatory
    # expected_payment_date, so the row is skipped (None) instead of
    # blowing up the whole deal save with MandatoryError.
    rec = {
        "npe01__Scheduled_Date__c": None,
        "npe01__Payment_Amount__c": 5000.0,
        "npe01__Payment_Date__c": None,
        "npe01__Paid__c": False,
        "npe01__Written_Off__c": False,
    }
    assert build_payment_row(rec, today=date(2026, 1, 1)) is None


# Captured from SF: a Funding_Allocation_Year__c budget cell for a Four
# Acre Trust grant, with the relationship hops Salesforce nests in the
# query response.
BUDGET_CELL = {
    "Amount__c": 15303.0,
    "Fiscal_Year__r": {"Name": "2026"},
    "Funding_Allocation__r": {
        "Cost_Code__r": {
            "Name_and_Description__c": "01-03 - UG / Construction (Other)",
            "Type__c": "Other",
        },
        "Support_Area__r": {"Short_Name__c": "Construction"},
    },
}


def test_budget_row_maps_nested_fields():
    row = build_budget_row(BUDGET_CELL)
    assert row["amount"] == 15303.0
    assert row["fiscal_year"] == "2026"
    assert row["cost_code"] == "01-03 - UG / Construction (Other)"
    assert row["cost_type"] == "Other"
    assert row["support_area"] == "Construction"


def test_budget_row_handles_null_support_area():
    # Support_Area__r is frequently null on the allocation (see the
    # Unrestricted/Opex cells) — must not raise on the missing hop.
    cell = {
        "Amount__c": 4697.0,
        "Fiscal_Year__r": {"Name": "2026"},
        "Funding_Allocation__r": {
            "Cost_Code__r": {
                "Name_and_Description__c": "00-01 - Unrestricted / Opex (Opex)",
                "Type__c": "Opex",
            },
            "Support_Area__r": None,
        },
    }
    row = build_budget_row(cell)
    assert row["support_area"] is None
    assert row["cost_code"] == "00-01 - Unrestricted / Opex (Opex)"


def test_budget_row_handles_fully_sparse_cell():
    # Defensive: every relationship hop missing -> all-blank row, no raise.
    row = build_budget_row({"Amount__c": 0.0})
    assert row == {
        "cost_code": None,
        "cost_type": None,
        "support_area": None,
        "fiscal_year": None,
        "amount": 0.0,
    }


def test_budget_soql_filters_by_parent_opportunity():
    soql = budget_soql("006XXENO")
    assert "FROM Funding_Allocation_Year__c" in soql
    assert "Funding_Allocation__r.Grant_Or_Donation__c = '006XXENO'" in soql
    # Traverses to the cost code + fiscal year labels.
    assert "Fiscal_Year__r.Name" in soql
    assert "Cost_Code__r.Name_and_Description__c" in soql


def test_payment_status_rules():
    today = date(2020, 1, 1)
    assert derive_payment_status(True, False, "2019-01-01", today) == "Received"
    assert derive_payment_status(False, True, "2025-01-01", today) == "Overdue"
    assert derive_payment_status(False, False, "2019-01-01", today) == "Overdue"
    assert derive_payment_status(False, False, "2025-01-01", today) == "Pending"
    assert derive_payment_status(False, False, None, today) == "Pending"
