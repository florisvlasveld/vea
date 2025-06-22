import json
import types
import sys
import importlib
import re
from datetime import date

# Setup dummy faiss and sentence_transformers
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

faiss_mod = types.SimpleNamespace(
    IndexFlatL2=lambda dim: DummyIndex(dim),
    write_index=lambda idx, path: None,
    read_index=lambda path: DummyIndex(0),
)
sys.modules['faiss'] = faiss_mod

class DummyModel:
    def __init__(self, name):
        self.name = name
    def encode(self, docs, convert_to_numpy=True):
        class Arr(list):
            @property
            def shape(self):
                return (len(self), len(self[0]) if self else 0)
        return Arr([[float(len(d)), float(len(d))+1] for d in docs])

st_mod = types.ModuleType('sentence_transformers')
st_mod.SentenceTransformer = DummyModel
sys.modules['sentence_transformers'] = st_mod

import vea.utils.embedding_utils as emb
importlib.reload(emb)
sys.modules['vea.utils.embedding_utils'] = emb

import vea.utils.summarization as summ
importlib.reload(summ)

summ.run_llm_prompt = lambda prompt, *a, **k: prompt

def _extract(prompt: str, header: str):
    pattern = rf"{re.escape(header)}.*?\n(\[.*?\])"
    m = re.search(pattern, prompt, re.S)
    assert m, f"section {header} not found"
    return json.loads(m.group(1))


def test_embeddings_return_dicts(tmp_path):
    prompt = summ.summarize_daily(
        model='dummy',
        date=date(2025, 1, 2),
        emails={'inbox': [{'subject': 'a', 'body': 'b'}]},
        calendars=[{'summary': 'meet', 'description': 'x', 'attendees': []}],
        tasks=[{'content': 't', 'description': 'd'}],
        journals=[{'filename': 'j', 'date': '2025-01-01', 'content': '- bullet'}],
        extras=[{'filename': 'e', 'content': 'extra'}],
        slack={'general': [{'text': 'hi'}]},
        quiet=True,
        debug=False,
        use_embeddings=True,
        outliner_mode=True,
        topk_journals=1,
        topk_extras=1,
        topk_emails=1,
        topk_slack=1,
    )

    assert isinstance(_extract(prompt, "== Journals Entries (JSON) ==" )[0], dict)
    assert isinstance(_extract(prompt, "== Additional Information (JSON) ==" )[0], dict)
    assert isinstance(_extract(prompt, "== Emails (JSON) ==" )[0], dict)
    assert isinstance(_extract(prompt, "== Slack Messages (JSON) ==" )[0], dict)
