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

import vea.cli.weekly as weekly


def test_weekly_compression(monkeypatch):
    monkeypatch.setattr(weekly, "load_extras", lambda paths: [{"filename": "ex1", "content": "alpha note", "aliases": ["Alpha"]}])
    monkeypatch.setattr(weekly.extras, "build_alias_map", lambda extras: {"alpha": "ex1"})
    monkeypatch.setattr(
        weekly, "load_journals", lambda *a, **k: [
            {"filename": "j1", "content": "alpha journal" * 20, "date": datetime(2025,5,3).date()},
            {"filename": "j2", "content": "beta journal" * 20, "date": datetime(2025,4,20).date()},
        ]
    )
    monkeypatch.setattr(weekly, "parse_week_input", lambda w: (datetime(2025,5,1).date(), datetime(2025,5,7).date()))

    calls = []
    def fake_summary(**kwargs):
        calls.append(kwargs)
        return "SUM"
    monkeypatch.setattr(weekly, "summarize_weekly", fake_summary)

    s_calls = []
    monkeypatch.setattr(weekly, "summarize_text", lambda txt, max_sentences=2: s_calls.append(txt) or "SUM")
    monkeypatch.setattr(weekly, "estimate_tokens", lambda txt: 50)

    from pathlib import Path
    weekly.generate_weekly_summary(
        week="2025-W18",
        skip_path_checks=True,
        token_budget=80,
        journal_dir=Path("."),
    )

    assert len(s_calls) >= 1
    assert len(calls) == 1
    assert len(calls[0]["journals_in_week"]) == 1
    journal = calls[0]["journals_in_week"][0]
    assert journal["filename"] == "j1"
    assert journal.get("token_count") == 50
