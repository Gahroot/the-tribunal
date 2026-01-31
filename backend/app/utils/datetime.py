"""DateTime parsing utilities for campaign and test scheduling."""

from datetime import time


def parse_time_string(time_str: str | None) -> time | None:
    """Parse a time string like '09:00' into a datetime.time object.

    Args:
        time_str: Time string in HH:MM format or None

    Returns:
        time object or None if parsing fails or input is None

    Example:
        >>> parse_time_string("09:30")
        datetime.time(9, 30)
        >>> parse_time_string(None)
        None
    """
    if time_str is None:
        return None
    try:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None
