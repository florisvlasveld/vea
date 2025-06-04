"""Utility functions for event-based operations."""

import os
from datetime import datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from vea.loaders import gcal


def parse_event_dt(dt_str: str) -> datetime:
    """Parse an event start time string in ``YYYY-MM-DD HH:MM`` format."""
    tz = ZoneInfo(os.getenv("TIMEZONE", "Europe/Amsterdam"))
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=tz)


def find_upcoming_events(
    *,
    start: datetime,
    my_email: Optional[str],
    blacklist: Optional[List[str]],
    lookahead_minutes: Optional[int] = None,
) -> List[dict]:
    """Find upcoming events starting from ``start``.

    Searches day by day and returns the earliest events beginning on or after
    ``start``. If ``lookahead_minutes`` is provided, only events starting within
    that window are considered.
    """
    tz = ZoneInfo(os.getenv("TIMEZONE", "Europe/Amsterdam"))
    current = start.astimezone(tz)
    end_limit = (
        current + timedelta(minutes=lookahead_minutes)
        if lookahead_minutes is not None
        else current + timedelta(days=7)
    )

    days_to_check = min((end_limit.date() - current.date()).days + 1, 7)

    for offset in range(days_to_check):
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
                dt_val = dt_val.replace(tzinfo=tz)
            return dt_val

        def _matches_blacklist(ev: dict) -> bool:
            if not blacklist:
                return False
            summary = ev.get("summary", "").lower()
            return any(bl.lower() in summary for bl in blacklist)

        eligible = [
            e
            for e in timed
            if current <= _dt(e) <= end_limit
            and (e.get("summary") or "").strip()
            and not _matches_blacklist(e)
        ]

        if not eligible:
            continue

        start_times = [_dt(e) for e in eligible]
        earliest = min(start_times)
        return [e for e, dt_val in zip(eligible, start_times) if dt_val == earliest]
        
    return []
