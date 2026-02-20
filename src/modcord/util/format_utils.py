from datetime import datetime, timezone

def humanize_timestamp(value: datetime) -> str:
    """Return a human-readable timestamp (YYYY-MM-DD HH:MM:SS) in UTC."""

    if value.tzinfo is None:
        # Assume naive datetime are already UTC
        value = value.replace(tzinfo=timezone.utc)
    else:
        # Convert any timezone to UTC
        value = value.astimezone(timezone.utc)

    return value.strftime("%Y-%m-%d %H:%M:%S UTC")