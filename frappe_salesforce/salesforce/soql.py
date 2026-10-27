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
    order_by: str = "SystemModstamp ASC, Id ASC",
    extra_where: str | None = None,
    after_id: str | None = None,
) -> str:
    """Build a SOQL query for incremental (modstamp-based) sync.

    ``after_id`` resumes part-way through the records sharing ``since``:
    those with an Id after it are included again. Salesforce gives every
    record in a bulk update the same SystemModstamp, so a plain
    ``> since`` would skip whatever of that group a stopped run hadn't
    reached. The default ordering sorts by Id within a timestamp to match.
    """
    field_list = _dedupe_fields(list(fields) + ["Id", "SystemModstamp"])
    stamp = format_soql_datetime(since)
    if after_id:
        where_parts = [
            f"(SystemModstamp > {stamp} OR "
            f"(SystemModstamp = {stamp} AND Id > '{after_id}'))"
        ]
    else:
        where_parts = [f"SystemModstamp > {stamp}"]
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
