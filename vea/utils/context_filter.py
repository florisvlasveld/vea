import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def _tfidf_vectors(texts: List[str]) -> List[Dict[str, float]]:
    tokens_per_doc = [_tokenize(t) for t in texts]
    df: Counter[str] = Counter()
    for tokens in tokens_per_doc:
        for token in set(tokens):
            df[token] += 1

    idf = {t: math.log((len(texts) + 1) / (df[t] + 1)) + 1 for t in df}

    vectors: List[Dict[str, float]] = []
    for tokens in tokens_per_doc:
        tf = Counter(tokens)
        vec = {t: tf[t] * idf[t] for t in tf}
        vectors.append(vec)
    return vectors


def get_embedding(text: str, *, _cache: Dict[str, Any] | None = None) -> Dict[str, float]:
    """Return a local TF-IDF embedding for ``text``."""
    if _cache is not None and text in _cache:
        return _cache[text]
    emb = _tfidf_vectors([text])[0]
    if _cache is not None:
        _cache[text] = emb
    return emb


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    numerator = sum(a.get(t, 0.0) * b.get(t, 0.0) for t in set(a) | set(b))
    denom = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    if denom == 0.0:
        return 0.0
    return numerator / denom


def filter_top_n(items: List[Dict[str, Any]], query: str, n: int, *, key: str = "content") -> List[Dict[str, Any]]:
    """Return the top ``n`` items most similar to ``query``."""
    if not items:
        return []

    q_emb = get_embedding(query)
    scored = []
    for item in items:
        text = str(item.get(key, ""))
        emb = get_embedding(text)
        score = _cosine(q_emb, emb)
        scored.append((score, item))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in scored[:n]]
