from daily_brief.loaders.journals import load_journals
from pathlib import Path


def test_load_journals(tmp_path: Path):
    journal = tmp_path / "entry.md"
    journal.write_text("Sample journal entry")
    result = load_journals(tmp_path)
    assert result == ["Sample journal entry"]