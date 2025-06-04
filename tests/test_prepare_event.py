# ruff: noqa: E402
import sys
from datetime import datetime, tzinfo
from types import SimpleNamespace
from zoneinfo import ZoneInfo


# Provide a minimal 'typer' stub so vea.cli can be imported without the real
# dependency installed in the test environment.
class _DummyTyper:
    def __init__(self, *a, **k):
        pass

    def command(self, *a, **k):
        def decorator(func):
            return func
        return decorator

def _dummy_option(*a, **k):
    return None

sys.modules.setdefault(
    "typer",
    SimpleNamespace(
        Typer=_DummyTyper,
        Option=_dummy_option,
        Argument=_dummy_option,
        echo=lambda *a, **k: None,
        Exit=Exception,
    ),
)

sys.modules.setdefault("dotenv", SimpleNamespace(load_dotenv=lambda *a, **k: None))
sys.modules.setdefault("todoist_api_python.api", SimpleNamespace(TodoistAPI=object))
import types
_slack_module = types.ModuleType("slack_sdk")
_slack_module.WebClient = object
_slack_errors = types.ModuleType("slack_sdk.errors")
_slack_errors.SlackApiError = Exception
sys.modules.setdefault("slack_sdk", _slack_module)
sys.modules.setdefault("slack_sdk.errors", _slack_errors)
sys.modules.setdefault(
    "google_auth_oauthlib.flow", SimpleNamespace(InstalledAppFlow=None)
)
sys.modules.setdefault("openai", SimpleNamespace())
sys.modules.setdefault("anthropic", SimpleNamespace())
_google_pkg = types.ModuleType("google")
_genai = types.ModuleType("generativeai")
_genai.GenerativeModel = lambda *a, **k: None
_google_pkg.generativeai = _genai
sys.modules.setdefault("google", _google_pkg)
sys.modules.setdefault("google.generativeai", _genai)
sys.modules.setdefault("markdown", SimpleNamespace(markdown=lambda *a, **k: ""))
sys.modules.setdefault("weasyprint", SimpleNamespace(HTML=lambda *a, **k: None, CSS=lambda *a, **k: None))

# Stub out heavy dependencies used by gcal when vea.cli is imported
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

class _DummyCreds:
    pass

class _DummyDiscovery:
    @staticmethod
    def build(*args, **kwargs):
        return None

sys.modules.setdefault("google.oauth2.credentials", SimpleNamespace(Credentials=_DummyCreds))
sys.modules.setdefault("googleapiclient.discovery", SimpleNamespace(build=_DummyDiscovery.build))

import vea.cli as cli


def test_find_upcoming_events_filters(monkeypatch):
    events = [
        {"summary": "", "start": "2025-05-01T10:00:00", "end": "2025-05-01T11:00:00"},
        {"summary": " ", "start": "2025-05-01T11:00:00", "end": "2025-05-01T12:00:00"},
        {"summary": "Lunch with team", "start": "2025-05-01T12:00:00", "end": "2025-05-01T13:00:00"},
        {"summary": "Real Meeting", "start": "2025-05-01T14:00:00", "end": "2025-05-01T15:00:00"},
    ]

    def dummy_load_events(*args, **kwargs):
        return events

    monkeypatch.setattr(cli.gcal, "load_events", dummy_load_events)
    monkeypatch.setenv("CALENDAR_EVENT_BLACKLIST", "Lunch")

    start = datetime(2025, 5, 1, 9, 30)
    result = cli._find_upcoming_events(start=start, my_email=None, blacklist=None)

    assert len(result) == 1
    assert result[0]["summary"] == "Real Meeting"
