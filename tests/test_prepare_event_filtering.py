import sys
from types import SimpleNamespace
from datetime import datetime

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

import vea.cli.prepare_event as pe


def test_prepare_event_filters(monkeypatch):
    monkeypatch.setattr(pe.extras, "load_extras", lambda paths: [{"filename": "ex1", "content": "alpha note", "aliases": ["Alpha"]}])
    monkeypatch.setattr(pe.extras, "build_alias_map", lambda extras: {"alpha": "ex1"})
    monkeypatch.setattr(pe.journals, "load_journals", lambda *a, **k: [{"filename": "j1", "content": "alpha journal", "date": datetime(2025,4,30).date()}])
    monkeypatch.setattr(
        pe, "find_upcoming_events", lambda *a, **k: [{"summary": "Alpha Meeting", "description": "discuss", "attendees": [{"name": "Alice", "email": "alice@example.com"}], "start": "2025-05-01T10:00:00"}]
    )
    monkeypatch.setattr(pe.gmail, "load_emails", lambda *a, **k: {"inbox": [{"subject": "hello", "body": "alpha"}]})
    monkeypatch.setattr(pe.todoist, "load_tasks", lambda *a, **k: [])
    monkeypatch.setattr(pe.slack_loader, "load_slack_messages", lambda *a, **k: {"general": [{"user": "bob", "timestamp": "", "text": "alpha"}]})

    calls = []

    def fake_run_pipeline(docs, topics, **kwargs):
        calls.append({"docs": docs, "topics": topics})
        out = docs[:1]
        for d in out:
            d.setdefault("token_count", 5)
        return {"documents": out, "total_tokens": 5}

    monkeypatch.setattr(pe, "run_pipeline", fake_run_pipeline)

    captured = {}

    def fake_summary(**kwargs):
        captured.update({
            "journals": kwargs["journals"],
            "extras": kwargs["extras"],
            "emails": kwargs["emails"],
            "slack": kwargs["slack"],
        })
        return "SUM"

    monkeypatch.setattr(pe, "summarize_event_preparation", fake_summary)

    from pathlib import Path
    pe.prepare_event(
        event="next",
        include_slack=True,
        skip_path_checks=True,
        token_budget=50,
        journal_dir=Path("."),
    )

    assert len(calls) == 4
    assert any("Alpha Meeting" in t for t in calls[0]["topics"])
    assert any("alice@example.com" in t or "Alice" in t for t in calls[0]["topics"])
    assert captured["journals"][0]["filename"] == "j1"

