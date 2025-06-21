from pathlib import Path
import pytest
from vea.utils.embeddings import build_index, query_index, ensure_index, INDEX_DIR

np = pytest.importorskip("numpy")
faiss = pytest.importorskip("faiss")


def test_build_and_query_index(tmp_path: Path):
    corpus = ["hello world", "goodbye moon", "hello sun"]
    index_path = tmp_path / "test.index"
    build_index(corpus, index_path)
    result = query_index("hello", index_path, k=2)
    assert result
    assert any("hello" in r for r in result)


def test_ensure_index_rebuild(tmp_path: Path):
    corpus = ["a", "b"]
    paths = []
    ensure_index(corpus, "tmp-test", paths)
    assert (INDEX_DIR / "tmp-test.index").exists()

