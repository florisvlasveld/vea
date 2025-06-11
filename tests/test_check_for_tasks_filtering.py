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

import vea.cli.check_for_tasks as cft


def test_check_for_tasks_filtering(monkeypatch):
    monkeypatch.setattr(cft.extras, "load_extras", lambda paths: [{"filename": "ex1", "content": "alpha note", "aliases": ["Alpha"]}])
    monkeypatch.setattr(cft.extras, "build_alias_map", lambda extras: {"alpha": "ex1"})
    monkeypatch.setattr(
        cft.journals,
        "load_journals",
        lambda *a, **k: [
            {"filename": "j1", "content": "remember to ping Alpha", "date": datetime(2025,5,1).date()},
            {"filename": "j2", "content": "random note", "date": datetime(2025,5,1).date()},
        ],
    )
    monkeypatch.setattr(
        cft.gmail,
        "load_emails",
        lambda *a, **k: {"inbox": [{"subject": "hi", "body": "follow up with Alpha", "from": "alice"}]},
    )
    monkeypatch.setattr(
        cft.slack_loader,
        "load_slack_messages",
        lambda *a, **k: {"general": [{"user": "bob", "timestamp": "", "text": "- [ ] call Alpha", "replies": []}]},
    )
    monkeypatch.setattr(cft.todoist, "load_completed_tasks", lambda *a, **k: [])
    monkeypatch.setattr(cft.todoist, "load_open_tasks", lambda *a, **k: [])

    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return "SUM"

    monkeypatch.setattr(cft, "summarize_check_for_tasks", fake_summary)
    monkeypatch.setattr(cft, "summarize_text", lambda txt, max_sentences=2: "SUM")
    monkeypatch.setattr(cft, "estimate_tokens", lambda txt: 5)

    from pathlib import Path
    cft.check_for_tasks(
        journal_dir=Path("."),
        extras_dir=Path("."),
        token_budget=25,
        include_slack=True,
        skip_path_checks=True,
    )

    assert captured["journals"][0]["filename"] == "j1"
    assert list(captured["emails"].values())[0][0]["body"] == "SUM"
    assert list(captured["slack"].values())[0][0]["text"] == "SUM"

