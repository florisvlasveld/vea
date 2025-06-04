import os
import re
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

DEFAULT_BLACKLIST = [
]

TOKEN_PATH = Path(".credentials/calendar_token.json")


def get_effective_offset(tz_name: str, dt: datetime) -> timedelta:
    try:
        tz = pytz.timezone(tz_name) if tz_name else pytz.UTC
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        return dt.utcoffset()
    except Exception as e:
        logger.warning(f"Failed to calculate offset for event: {e}")
        return timedelta(0)


def strip_google_meet_block(text: str) -> str:
    if not text:
        return ""
    return re.sub(
        r"-::~:~::~:~:.*?-::~:~::~:~:.*?-::~:~::~:~::-",
        "",
        text,
        flags=re.DOTALL,
    ).strip()


def catch_google_api_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error("Google API error: %s", e)
            return []
    return wrapper


@catch_google_api_errors
def load_events(
    target_date: date,
    my_email: Optional[str] = None,
    token_unused: Optional[str] = None,
    blacklist: Optional[List[str]] = None,
    skip_past_events: bool = False,
) -> List[dict]:
    if not my_email:
        my_email = os.getenv("GOOGLE_ACCOUNT_EMAIL", "").lower()
    else:
        my_email = my_email.lower()

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    service = build("calendar", "v3", credentials=creds)

    tz = pytz.timezone("Europe/Amsterdam")
    start = tz.localize(datetime.combine(target_date, datetime.min.time()))
    end = tz.localize(datetime.combine(target_date, datetime.max.time()))

    calendar_ids = ["primary"]
    additional_ids = os.getenv("GCAL_ADDITIONAL_CALENDARS", "")
    if additional_ids:
        calendar_ids += [cid.strip() for cid in additional_ids.split(",") if cid.strip()]

    env_blacklist = os.getenv("CALENDAR_EVENT_BLACKLIST", "")
    combined_blacklist = DEFAULT_BLACKLIST + [item.strip() for item in env_blacklist.split(",") if item.strip()]
    if blacklist:
        combined_blacklist += blacklist

    all_events = []

    for calendar_id in calendar_ids:
        try:
            events_result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            for e in events:
                summary = e.get("summary", "")
                if any(bl_item.lower() in summary.lower() for bl_item in combined_blacklist):
                    continue

                attendees = e.get("attendees", [])
                my_status = next(
                    (a.get("responseStatus") for a in attendees if a.get("email", "").lower() == my_email),
                    "accepted",
                )
                if my_status == "declined":
                    continue

                attendee_info = [
                    {
                        "email": a.get("email"),
                        "name": a.get("displayName", a.get("email")),
                    }
                    for a in attendees
                    if "email" in a and not a["email"].endswith("@resource.calendar.google.com")
                ]

                description = strip_google_meet_block(e.get("description", ""))

                all_events.append(
                    {
                        "summary": e.get("summary"),
                        "start": e["start"].get("dateTime") or e["start"].get("date"),
                        "end": e["end"].get("dateTime") or e["end"].get("date"),
                        "start_time_zone": e["start"].get("timeZone"),
                        "end_time_zone": e["end"].get("timeZone"),
                        "attendees": attendee_info,
                        "my_status": my_status,
                        "description": description,
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to fetch events from calendar '{calendar_id}': {e}")

    if skip_past_events and target_date == datetime.now(tz).date():
        now = datetime.now(tz)

        def event_is_past(ev):
            if "T" not in ev["start"]:
                return False
            try:
                dt = datetime.fromisoformat(ev["start"])
            except Exception:
                return False
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            return dt < now

        all_events = [ev for ev in all_events if not event_is_past(ev)]

    # Offset check and sort
    effective_offsets = set()
    for e in all_events:
        start_dt_str = e["start"]
        tz_name = e.get("start_time_zone") or "UTC"
        try:
            if "T" in start_dt_str:
                dt = datetime.fromisoformat(start_dt_str)
            else:
                dt = datetime.combine(datetime.fromisoformat(start_dt_str), datetime.min.time())
            offset = get_effective_offset(tz_name, dt)
            effective_offsets.add(offset)
        except Exception as ex:
            logger.warning(f"Failed to calculate offset for event '{e.get('summary', '')}': {ex}")

    if len(effective_offsets) <= 1:
        for e in all_events:
            e["start_time_zone"] = None
            e["end_time_zone"] = None

    def is_all_day(event):
        return "T" not in event["start"]

    all_events.sort(key=lambda e: (0 if is_all_day(e) else 1, e["start"]))
    return all_events