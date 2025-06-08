import os
from datetime import datetime
from typing import List, Optional

from ..utils.event_utils import find_upcoming_events, find_current_events


def _find_upcoming_events(
    *,
    start: datetime,
    my_email: Optional[str],
    blacklist: Optional[List[str]],
    lookahead_minutes: Optional[int] = None,
) -> List[dict]:
    """Wrapper for :func:`find_upcoming_events` to allow easier testing."""
    if blacklist is None:
        env_bl = os.getenv("CALENDAR_EVENT_BLACKLIST", "")
        blacklist = [b.strip() for b in env_bl.split(",") if b.strip()]

    return find_upcoming_events(
        start=start,
        my_email=my_email,
        blacklist=blacklist,
        lookahead_minutes=lookahead_minutes,
    )


def _find_current_events(
    *,
    my_email: Optional[str],
    blacklist: Optional[List[str]],
) -> List[dict]:
    """Wrapper for :func:`find_current_events` to allow easier testing."""
    if blacklist is None:
        env_bl = os.getenv("CALENDAR_EVENT_BLACKLIST", "")
        blacklist = [b.strip() for b in env_bl.split(",") if b.strip()]

    return find_current_events(my_email=my_email, blacklist=blacklist)

__all__ = ["_find_upcoming_events", "_find_current_events"]
