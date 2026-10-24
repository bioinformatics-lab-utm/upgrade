"""
API timestamps.

The pipeline tables use `timestamp without time zone` columns filled with
CURRENT_TIMESTAMP on a UTC database, so the naive datetimes asyncpg returns are
UTC. Serialized without an offset ("2026-10-16T07:56:25"), browsers read them as
*local* time, which shifts every duration by the viewer's UTC offset. Always
serialize through to_iso() so the offset is explicit.
"""
from datetime import date, datetime, timezone


def to_iso(value):
    """ISO 8601 string for a date/datetime, marking naive datetimes as UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
