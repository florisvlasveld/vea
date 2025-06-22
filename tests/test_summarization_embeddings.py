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
    start = prompt.index(header) + len(header)
    match = re.search(r"^[\[{]", prompt[start:], re.MULTILINE)
    assert match, f"section {header} not found"
    start += match.start()
    open_ch = prompt[start]
    close_ch = ']' if open_ch == '[' else '}'
    depth = 0
    end = start
    while end < len(prompt):
        c = prompt[end]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                end += 1
                break
        end += 1
    return json.loads(prompt[start:end])


def test_embeddings_return_dicts(tmp_path):
    prompt = summ.summarize_daily(
        model='dummy',
        date=date(2025, 1, 2),
        emails={'inbox': [{'subject': 'a', 'body': 'b'}]},
        calendars=[{'summary': 'meet', 'description': 'x', 'attendees': []}],
        tasks=[{'content': 't', 'description': 'd'}],
        journals=[{'filename': 'j', 'date': '2025-01-01', 'content': '- a\n- b'}],
        extras=[{'filename': 'e', 'content': 'extra'}],
        slack={'general': [{'text': 'hi'}]},
        quiet=True,
        debug=False,
        use_embeddings=True,
        outliner_mode=True,
        topk_journals=2,
        topk_extras=1,
        topk_emails=1,
        topk_slack=1,
    )

    journals_section = _extract(prompt, "== Journals Entries (JSON) ==")
    assert isinstance(journals_section[0], dict)
    assert {j['filename'] for j in journals_section} == {"j-1", "j-2"}

    assert isinstance(_extract(prompt, "== Additional Information (JSON) ==" )[0], dict)
    assert isinstance(_extract(prompt, "== Emails (JSON) ==" )[0], dict)
    assert isinstance(_extract(prompt, "== Slack Messages (JSON) ==" )[0], dict)


def test_sorting_without_embeddings(tmp_path):
    prompt = summ.summarize_daily(
        model="dummy",
        date=date(2025, 1, 3),
        emails={
            "inbox": [
                {"subject": "b", "body": "", "date": "2025-01-03"},
                {"subject": "a", "body": "", "date": "2025-01-02"},
            ]
        },
        calendars=[],
        tasks=[],
        journals=[
            {"filename": "j2", "date": "2025-01-03", "content": "two"},
            {"filename": "j1", "date": "2025-01-02", "content": "one"},
        ],
        extras=[
            {"filename": "e2", "content": "x", "date": "2025-01-03"},
            {"filename": "e1", "content": "y", "date": "2025-01-02"},
        ],
        slack={
            "general": [
                {"text": "later", "timestamp": "2025-01-03T00:00:00"},
                {"text": "earlier", "timestamp": "2025-01-02T00:00:00"},
            ]
        },
        quiet=True,
        debug=False,
        use_embeddings=False,
    )

    journ = _extract(prompt, "== Journals Entries (JSON) ==")
    assert [j["filename"] for j in journ] == ["j1", "j2"]
    extras_s = _extract(prompt, "== Additional Information (JSON) ==")
    assert [e["filename"] for e in extras_s] == ["e1", "e2"]
    emails_s = _extract(prompt, "== Emails (JSON) ==")
    if isinstance(emails_s, dict):
        seq = emails_s["inbox"]
    else:
        seq = emails_s
    assert [m["subject"] for m in seq] == ["a", "b"]
    slack_s = _extract(prompt, "== Slack Messages (JSON) ==")
    if isinstance(slack_s, dict):
        seq = slack_s["general"]
    else:
        seq = slack_s
    assert [m["text"] for m in seq] == ["earlier", "later"]


def test_sorting_with_embeddings(tmp_path):
    prompt = summ.summarize_daily(
        model="dummy",
        date=date(2025, 1, 3),
        emails={
            "inbox": [
                {"subject": "b", "body": "", "date": "2025-01-03"},
                {"subject": "a", "body": "", "date": "2025-01-02"},
            ]
        },
        calendars=[{"summary": "meet", "description": "", "attendees": []}],
        tasks=[],
        journals=[
            {"filename": "j2", "date": "2025-01-03", "content": "two"},
            {"filename": "j1", "date": "2025-01-02", "content": "one"},
        ],
        extras=[
            {"filename": "e2", "content": "x", "date": "2025-01-03"},
            {"filename": "e1", "content": "y", "date": "2025-01-02"},
        ],
        slack={
            "general": [
                {"text": "later", "timestamp": "2025-01-03T00:00:00"},
                {"text": "earlier", "timestamp": "2025-01-02T00:00:00"},
            ]
        },
        quiet=True,
        debug=False,
        use_embeddings=True,
        outliner_mode=False,
        topk_journals=2,
        topk_extras=2,
        topk_emails=2,
        topk_slack=2,
    )

    journ = _extract(prompt, "== Journals Entries (JSON) ==")
    assert [j["filename"] for j in journ] == ["j1", "j2"]
    extras_s = _extract(prompt, "== Additional Information (JSON) ==")
    assert [e["filename"] for e in extras_s] == ["e1", "e2"]
    emails_s = _extract(prompt, "== Emails (JSON) ==")
    if isinstance(emails_s, dict):
        seq = emails_s["inbox"]
    else:
        seq = emails_s
    assert [m["subject"] for m in seq] == ["a", "b"]
    slack_s = _extract(prompt, "== Slack Messages (JSON) ==")
    if isinstance(slack_s, dict):
        seq_sl = slack_s["general"]
    else:
        seq_sl = slack_s
    assert [m["text"] for m in seq_sl] == ["earlier", "later"]
