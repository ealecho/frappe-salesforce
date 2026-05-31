"""SOQL query builder helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable


def format_soql_datetime(value: datetime | str) -> str:
    """Format a datetime value for SOQL.

    Salesforce expects ISO 8601 with a 'Z' suffix (UTC) and no microseconds.
    Accepts either a datetime instance or an ISO-like string.
    """
    if isinstance(value, str):
        value = value.strip()
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_incremental_query(
    sobject: str,
    fields: Iterable[str],
    since: datetime | str,
    order_by: str = "SystemModstamp ASC",
    extra_where: str | None = None,
) -> str:
    """Build a SOQL query for incremental (modstamp-based) sync."""
    field_list = _dedupe_fields(list(fields) + ["Id", "SystemModstamp"])
    where_parts = [f"SystemModstamp > {format_soql_datetime(since)}"]
    if extra_where:
        where_parts.append(f"({extra_where})")
    return (
        f"SELECT {', '.join(field_list)} "
        f"FROM {sobject} "
        f"WHERE {' AND '.join(where_parts)} "
        f"ORDER BY {order_by}"
    )


def _dedupe_fields(fields: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for f in fields:
        key = f.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique
