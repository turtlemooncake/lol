from datetime import datetime, timezone


def parse_ts(value) -> datetime | None:
    """Parse a Supabase timestamptz string into an aware UTC datetime.

    Returns None on empty/unparseable input. A naive timestamp is assumed UTC.
    """
    if not value:
        return None
    try:
        # Supabase returns ISO-8601; tolerate a trailing 'Z' just in case.
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
