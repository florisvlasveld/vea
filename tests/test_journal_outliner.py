import datetime
from pathlib import Path
from vea.loaders.journals import load_journals


def test_outliner_parsing(tmp_path):
    md = "- item one\n  - child\n- item two\n  continuation"
    f = tmp_path / "2025-06-05.md"
    f.write_text(md)

    docs = load_journals(tmp_path, journal_days=10, outliner_mode=True)
    assert len(docs) == 2
    assert docs[0]["sub_index"] == 1
    assert docs[1]["sub_index"] == 2
    assert docs[0]["content"].startswith("- item one")
    assert docs[1]["content"].startswith("- item two")
    assert docs[0]["date"] == datetime.date(2025, 6, 5)
