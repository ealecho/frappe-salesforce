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


def test_format_soql_datetime_from_space_separated_string():
    """Regression: ``frappe.utils.now_datetime()`` returns space-separated
    strings; SOQL rejects them with MALFORMED_QUERY."""
    assert format_soql_datetime("2026-04-19 12:30:45") == "2026-04-19T12:30:45Z"


def test_format_soql_datetime_strips_offset():
    assert format_soql_datetime("2026-04-19T12:30:45+05:30") == "2026-04-19T12:30:45Z"


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
    # Extract the field list between SELECT and FROM and verify dedupe.
    select_part = q.split("SELECT ", 1)[1].split(" FROM", 1)[0]
    fields = [f.strip() for f in select_part.split(",")]
    lowered = [f.lower() for f in fields]
    assert lowered.count("id") == 1
    assert lowered.count("name") == 1
    assert "systemmodstamp" in lowered


def test_build_incremental_query_with_extra_where():
    q = build_incremental_query(
        "Lead",
        ["Email"],
        datetime(2026, 4, 19, tzinfo=timezone.utc),
        extra_where="IsConverted = false",
    )
    assert "(IsConverted = false)" in q
