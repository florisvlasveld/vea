from datetime import datetime, timedelta
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from datetime import tzinfo

class _FakeTZ(tzinfo):
    def __init__(self, name):
        self._zone = ZoneInfo(name)

    def localize(self, dt):
        return dt.replace(tzinfo=self)

    def utcoffset(self, dt):
        return self._zone.utcoffset(dt)

    def dst(self, dt):
        return self._zone.dst(dt)

    def tzname(self, dt):
        return self._zone.tzname(dt)

sys.modules.setdefault(
    "pytz",
    SimpleNamespace(timezone=lambda name: _FakeTZ(name), UTC=_FakeTZ("UTC")),
)

# Stub google credentials and discovery modules if missing
class _DummyCreds:
    pass

class _DummyDiscovery:
    @staticmethod
    def build(*args, **kwargs):
        return None

sys.modules.setdefault("google.oauth2.credentials", SimpleNamespace(Credentials=_DummyCreds))
sys.modules.setdefault("googleapiclient.discovery", SimpleNamespace(build=_DummyDiscovery.build))

import pytz

import vea.loaders.gcal as gcal

class DummyCreds:
    pass

class DummyService:
    def __init__(self, items):
        self._items = items
    def events(self):
        return self
    def list(self, **kwargs):
        return self
    def execute(self):
        return {"items": self._items}

def make_event(summary, start, end, all_day=False):
    if all_day:
        return {"summary": summary, "start": {"date": start}, "end": {"date": end}}
    return {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}


def test_skip_past_events(monkeypatch):
    tz = pytz.timezone("Europe/Amsterdam")
    now = datetime.now(tz).replace(microsecond=0)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    items = [
        make_event("Past", past.isoformat(), past.isoformat()),
        make_event("Future", future.isoformat(), future.isoformat()),
        make_event("AllDay", now.date().isoformat(), now.date().isoformat(), all_day=True),
    ]

    monkeypatch.setattr(
        gcal,
        "Credentials",
        SimpleNamespace(from_authorized_user_file=lambda *a, **k: DummyCreds()),
    )
    monkeypatch.setattr(gcal, "build", lambda *a, **k: DummyService(items))

    events = gcal.load_events(now.date(), my_email="me@example.com", skip_past_events=True)
    summaries = [e["summary"] for e in events]
    assert "Past" not in summaries
    assert "Future" in summaries
    assert "AllDay" in summaries


def test_no_skip_past_events(monkeypatch):
    tz = pytz.timezone("Europe/Amsterdam")
    now = datetime.now(tz).replace(microsecond=0)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    items = [
        make_event("Past", past.isoformat(), past.isoformat()),
        make_event("Future", future.isoformat(), future.isoformat()),
    ]

    monkeypatch.setattr(
        gcal,
        "Credentials",
        SimpleNamespace(from_authorized_user_file=lambda *a, **k: DummyCreds()),
    )
    monkeypatch.setattr(gcal, "build", lambda *a, **k: DummyService(items))

    events = gcal.load_events(now.date(), my_email="me@example.com", skip_past_events=False)
    summaries = [e["summary"] for e in events]
    assert "Past" in summaries
    assert "Future" in summaries
