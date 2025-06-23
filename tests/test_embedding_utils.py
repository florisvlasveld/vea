import json
import types
import sys
from pathlib import Path


# Create dummy faiss module
class DummyIndex:
    def __init__(self, dim):
        self.dim = dim
        self.vectors = []

    def add(self, arr):
        self.vectors.extend(arr)

    def search(self, q, k):
        def l2(v1, v2):
            return sum((a - b) ** 2 for a, b in zip(v1, v2))

        dists = [l2(q[0], vec) for vec in self.vectors]
        idx = sorted(range(len(dists)), key=lambda i: dists[i])[:k]
        return None, [idx]

def _write_index(idx, path):
    Path(path).write_text("idx")

dummy_faiss = types.SimpleNamespace(
    IndexFlatL2=lambda dim: DummyIndex(dim),
    write_index=_write_index,
    read_index=lambda path: DummyIndex(0),
)

sys.modules['faiss'] = dummy_faiss

# Dummy sentence transformer
class DummyModel:
    def __init__(self, name):
        self.name = name
    def encode(self, docs, convert_to_numpy=True):
        class Arr(list):
            @property
            def shape(self):
                return (len(self), len(self[0]) if self else 0)

        data = Arr([[float(len(d)), float(len(d) + 1)] for d in docs])
        return data

st_mod = types.ModuleType("sentence_transformers")
st_mod.SentenceTransformer = DummyModel
sys.modules['sentence_transformers'] = st_mod

import importlib
import vea.utils.embedding_utils as emb
importlib.reload(emb)
from vea.utils.embedding_utils import load_or_create_index, query_index


def test_index_and_query(tmp_path):
    docs = ["alpha", "beta", "gamma"]
    index_path = tmp_path / "test.index"
    index = load_or_create_index(index_path, docs, debug=True)
    results = query_index(index, "alpha", 2)
    assert docs[0] in results


def test_tuple_documents(tmp_path):
    docs = [("foo", {"id": 1}), ("bar", {"id": 2})]
    index = load_or_create_index(tmp_path / "tuple.index", docs, debug=True)
    res = query_index(index, "foo", 1)
    assert res == [{"id": 1}]


def test_model_name_roundtrip(tmp_path, monkeypatch):
    called = []

    def fake_get(name):
        called.append(name)
        return DummyModel(name)

    monkeypatch.setattr(emb, "_get_model", fake_get)

    doc = tmp_path / "doc.txt"
    doc.write_text("alpha")

    idx = load_or_create_index(tmp_path / "m.index", [str(doc)], model_name="special", debug=True)
    query_index(idx, "alpha", 1)

    assert called[-1] == "special"


def test_index_rebuild_on_mtime(tmp_path):
    doc = tmp_path / "f.txt"
    doc.write_text("alpha")
    idx_path = tmp_path / "mtime.index"

    idx1 = load_or_create_index(idx_path, [str(doc)], debug=True)
    meta_path = idx_path.with_suffix(".meta.json")
    ts1 = json.loads(meta_path.read_text())["timestamp"]

    idx2 = load_or_create_index(idx_path, [str(doc)], debug=True)
    ts2 = json.loads(meta_path.read_text())["timestamp"]
    assert abs(ts1 - ts2) < 1e-3  # no rebuild

    doc.write_text("alpha changed")
    load_or_create_index(idx_path, [str(doc)], debug=True)
    ts3 = json.loads(meta_path.read_text())["timestamp"]
    assert ts3 != ts2
