"""Unit tests for the SOQL builder helpers."""

from datetime import datetime, timezone

from frappe_salesforce.salesforce.soql import (
    build_incremental_query,
    format_soql_datetime,
)


def test_format_soql_datetime_from_datetime():
    dt = datetime(2026, 4, 19, 12, 30, 45, tzinfo=timezone.utc)
    assert format_soql_datetime(dt) == "2026-04-19T12:30:45Z"


def test_format_soql_datetime_naive_assumes_utc():
    dt = datetime(2026, 4, 19, 12, 30, 45)
    assert format_soql_datetime(dt) == "2026-04-19T12:30:45Z"


def test_format_soql_datetime_from_string():
    assert format_soql_datetime("2026-04-19T12:30:45.123Z") == "2026-04-19T12:30:45Z"


def test_build_incremental_query_includes_modstamp():
    q = build_incremental_query(
        "Account",
        ["Name", "Website"],
        datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    assert "FROM Account" in q
    assert "SystemModstamp > 2026-04-19T00:00:00Z" in q
    assert "ORDER BY SystemModstamp ASC" in q
    assert "Id" in q


def test_build_incremental_query_dedupes_fields():
    q = build_incremental_query(
        "Account",
        ["Id", "Name", "name"],
        datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    # Only one "Id" and one "Name" (case-insensitive dedupe).
    assert q.count(" Id,") + q.count("SELECT Id,") == 1
    assert q.lower().count(" name,") + q.lower().count("select name,") <= 1
