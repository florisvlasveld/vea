"""Utility functions for event-based operations."""

from datetime import datetime, timedelta
from typing import List, Optional

import pytz

from vea.loaders import gcal


def parse_event_dt(dt_str: str) -> datetime:
    """Parse an event start time string in ``YYYY-MM-DD HH:MM`` format."""
    tz = pytz.timezone("Europe/Amsterdam")
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    return tz.localize(dt)


def find_upcoming_events(
    *,
    start: datetime,
    my_email: Optional[str],
    blacklist: Optional[List[str]],
) -> List[dict]:
    """Find upcoming events starting from ``start`` within the next 7 days."""
    tz = pytz.timezone("Europe/Amsterdam")
    current = start.astimezone(tz)
    for offset in range(7):
        day = current.date() + timedelta(days=offset)
        events = gcal.load_events(
            day,
            my_email=my_email,
            blacklist=blacklist,
            skip_past_events=(offset == 0),
        )
        timed = [e for e in events if "T" in e.get("start", "")]
        if not timed:
            continue

        def _dt(ev: dict) -> datetime:
            dt_val = datetime.fromisoformat(ev["start"])
            if dt_val.tzinfo is None:
                dt_val = tz.localize(dt_val)
            return dt_val

        starts = [_dt(e) for e in timed]
        eligible = [e for e, dt_val in zip(timed, starts) if dt_val >= current]
        if not eligible:
            continue
        start_times = [_dt(e) for e in eligible]
        earliest = min(start_times)
        return [e for e, dt_val in zip(eligible, start_times) if dt_val == earliest]
    return []
