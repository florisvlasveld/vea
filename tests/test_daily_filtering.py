import sys
from types import SimpleNamespace
from datetime import datetime

# Minimal typer stub
class _DummyTyper:
    def __init__(self, *a, **k):
        pass
    def command(self, *a, **k):
        def dec(f):
            return f
        return dec

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

sys.modules.setdefault(
    "dotenv",
    SimpleNamespace(load_dotenv=lambda *a, **k: None, find_dotenv=lambda *a, **k: ""),
)

# Stub heavy deps
sys.modules.setdefault("todoist_api_python.api", SimpleNamespace(TodoistAPI=object))
sys.modules.setdefault("slack_sdk", SimpleNamespace(WebClient=object))
sys.modules.setdefault("slack_sdk.errors", SimpleNamespace(SlackApiError=Exception))
sys.modules.setdefault("google.oauth2.credentials", SimpleNamespace(Credentials=object))
sys.modules.setdefault("googleapiclient.discovery", SimpleNamespace(build=lambda *a, **k: None))
sys.modules.setdefault("google_auth_oauthlib.flow", SimpleNamespace(InstalledAppFlow=None))
sys.modules.setdefault("openai", SimpleNamespace())
sys.modules.setdefault("anthropic", SimpleNamespace())
_google_pkg = SimpleNamespace(generativeai=SimpleNamespace(GenerativeModel=lambda *a, **k: None))
sys.modules.setdefault("google", _google_pkg)
sys.modules.setdefault("google.generativeai", _google_pkg.generativeai)
sys.modules.setdefault("markdown", SimpleNamespace(markdown=lambda *a, **k: ""))
sys.modules.setdefault("weasyprint", SimpleNamespace(HTML=lambda *a, **k: None, CSS=lambda *a, **k: None))

import vea.cli.daily as daily


def test_daily_generate_global_budget(monkeypatch):
    # Patch loader functions to return sample data
    monkeypatch.setattr(daily.extras, "load_extras", lambda paths: [{"filename": "ex1", "content": "alpha note", "aliases": ["Alpha"]}])
    monkeypatch.setattr(daily.extras, "build_alias_map", lambda extras: {"alpha": "ex1"})
    monkeypatch.setattr(daily.journals, "load_journals", lambda *a, **k: [{"filename": "j1", "content": "alpha journal", "date": datetime(2025,4,30).date()}])
    monkeypatch.setattr(daily.gcal, "load_events", lambda *a, **k: [{"summary": "Alpha Meeting", "description": "discuss", "attendees": [{"name": "Alice", "email": "alice@example.com"}]}])
    monkeypatch.setattr(daily.todoist, "load_tasks", lambda *a, **k: [{"content": "Finish alpha", "description": ""}])
    monkeypatch.setattr(daily.gmail, "load_emails", lambda *a, **k: {"inbox": [{"subject": "hello", "from": "alice", "date": "", "body": "alpha"}]})
    monkeypatch.setattr(daily.slack_loader, "load_slack_messages", lambda *a, **k: {"general": [{"user": "bob", "timestamp": "", "text": "alpha"}]})

    monkeypatch.setattr(daily, "parse_date", lambda x: datetime(2025,5,1).date())

    calls = []

    def fake_run_pipeline(docs, topics, **kwargs):
        calls.append({"docs": docs, "topics": topics})
        out = docs[:1]
        for d in out:
            d.setdefault("token_count", 5)
        return {"documents": out, "total_tokens": 5}

    monkeypatch.setattr(daily, "run_pipeline", fake_run_pipeline)

    captured = {}
    def fake_summary(**kwargs):
        captured.update({"journals": kwargs["journals"], "extras": kwargs["extras"], "emails": kwargs["emails"], "slack": kwargs["slack"]})
        return "SUM"

    monkeypatch.setattr(daily, "summarize_daily", fake_summary)

    from pathlib import Path
    daily.generate(
        date="2025-05-01",
        include_slack=True,
        skip_path_checks=True,
        token_budget=50,
        budget_scope="global",
        journal_dir=Path("."),
    )

    assert len(calls) == 1
    assert any("Alpha Meeting" in t for t in calls[0]["topics"])
    assert captured["journals"][0]["filename"] == "j1"


def test_daily_generate_group_budget(monkeypatch):
    monkeypatch.setattr(daily.extras, "load_extras", lambda paths: [{"filename": "ex1", "content": "alpha note", "aliases": ["Alpha"]}])
    monkeypatch.setattr(daily.extras, "build_alias_map", lambda extras: {"alpha": "ex1"})
    monkeypatch.setattr(daily.journals, "load_journals", lambda *a, **k: [{"filename": "j1", "content": "alpha journal", "date": datetime(2025,4,30).date()}])
    monkeypatch.setattr(daily.gcal, "load_events", lambda *a, **k: [{"summary": "Alpha Meeting"}])
    monkeypatch.setattr(daily.todoist, "load_tasks", lambda *a, **k: [])
    monkeypatch.setattr(daily.gmail, "load_emails", lambda *a, **k: {"inbox": [{"subject": "hello", "body": "alpha"}]})
    monkeypatch.setattr(daily.slack_loader, "load_slack_messages", lambda *a, **k: {})
    monkeypatch.setattr(daily, "parse_date", lambda x: datetime(2025,5,1).date())

    calls = []

    def fake_run_pipeline(docs, topics, **kwargs):
        calls.append((docs, topics))
        out = docs[:1]
        for d in out:
            d.setdefault("token_count", 5)
        return {"documents": out, "total_tokens": 5}

    monkeypatch.setattr(daily, "run_pipeline", fake_run_pipeline)

    def fake_summary(**kwargs):
        return "SUM"

    monkeypatch.setattr(daily, "summarize_daily", fake_summary)

    from pathlib import Path
    daily.generate(
        date="2025-05-01",
        include_slack=False,
        skip_path_checks=True,
        token_budget=50,
        budget_scope="group",
        journal_dir=Path("."),
    )

    assert len(calls) == 3  # journal, extra, email; slack skipped
