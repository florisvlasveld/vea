"""Utility utilities for ranking and filtering text documents.

The module exposes a pluggable architecture for determining the relevance of a
piece of text given a list of focus topics.  In previous iterations this module
only exposed the :class:`BaseRanker` class and a ``filter_documents`` function.
The API has been expanded with a more explicit ``RelevanceStrategy`` interface
and a small :class:`RelevanceFilterPipeline` for combining multiple strategies.

The original classes are kept as aliases so existing imports keep working.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

try:  # Optional dependency used for token counting
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional
    tiktoken = None

__all__ = [
    "RelevanceStrategy",
    "TFIDFStrategy",
    "KeywordMatchStrategy",
    "EmbeddingSimilarityStrategy",
    "RelevanceFilterPipeline",
    "filter_documents",
    "BaseRanker",
    "TfidfRanker",
    "KeywordRanker",
]


_TOKEN_RE = re.compile(r"\b\w+\b")

_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "if",
    "of",
    "to",
    "in",
    "for",
    "with",
    "on",
    "at",
    "by",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "this",
    "that",
    "these",
    "those",
    "i",
    "me",
    "my",
    "we",
    "our",
    "you",
    "your",
    "he",
    "she",
    "it",
    "they",
    "them",
    "their",
    "not",
}


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _preprocess(text: str) -> List[str]:
    """Tokenize and remove very common stop words."""
    return [t for t in _tokenize(text) if t not in _STOP_WORDS]


def _estimate_tokens(text: str) -> int:
    """Best-effort token count using tiktoken when available.

    Falls back to a naive heuristic of ~1.3 tokens per word when the
    ``tiktoken`` package is not installed.
    """
    if tiktoken is not None:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:  # pragma: no cover - unexpected
            pass
    # naive fallback: assume ~1.3 tokens per word
    return max(1, int(len(_tokenize(text)) * 1.3))


@dataclass
class RelevanceStrategy:
    """Base class for relevance scoring strategies."""

    preprocess: bool = True

    def _prep(self, text: str) -> List[str]:
        return _preprocess(text) if self.preprocess else _tokenize(text)

    def score(self, doc: str, topics: List[str]) -> float:  # pragma: no cover - abstract
        """Return a numeric relevance score for ``doc`` given ``topics``."""
        raise NotImplementedError

    def rank(self, docs: Iterable[str], topics: List[str]) -> List[Tuple[str, float]]:
        """Return ``docs`` sorted by descending score."""
        scored = [(doc, self.score(doc, topics)) for doc in docs]
        return sorted(scored, key=lambda x: x[1], reverse=True)


# Backwards compatible alias
BaseRanker = RelevanceStrategy


@dataclass
class TFIDFStrategy(RelevanceStrategy):
    """Rank documents based on cosine similarity using a minimal TF–IDF model."""

    def _build_idf(self, docs: Iterable[str]) -> Dict[str, float]:
        df: Dict[str, int] = defaultdict(int)
        doc_count = 0
        for doc in docs:
            tokens = set(self._prep(doc))
            for token in tokens:
                df[token] += 1
            doc_count += 1
        return {t: math.log((doc_count + 1) / (n + 1)) + 1 for t, n in df.items()}

    def _tfidf(self, tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
        if not tokens:
            return {}
        counts = Counter(tokens)
        total = len(tokens)
        return {t: (counts[t] / total) * idf.get(t, 0.0) for t in counts}

    def score(self, doc: str, topics: List[str]) -> float:
        # Build IDF from both the candidate document and the topics.
        idf = self._build_idf([doc] + topics)
        doc_vec = self._tfidf(self._prep(doc), idf)
        topic_vec = self._tfidf(self._prep(" ".join(topics)), idf)

        # Cosine similarity without numpy.
        if not doc_vec or not topic_vec:
            return 0.0
        dot = sum(doc_vec.get(t, 0.0) * topic_vec.get(t, 0.0) for t in set(doc_vec) | set(topic_vec))
        norm_doc = math.sqrt(sum(v * v for v in doc_vec.values()))
        norm_topic = math.sqrt(sum(v * v for v in topic_vec.values()))
        if norm_doc == 0 or norm_topic == 0:
            return 0.0
        return dot / (norm_doc * norm_topic)


@dataclass
class KeywordMatchStrategy(RelevanceStrategy):
    """Simpler ranker based on shared keyword count."""

    def score(self, doc: str, topics: List[str]) -> float:
        doc_tokens = set(self._prep(doc))
        topic_tokens = set(self._prep(" ".join(topics)))
        if not doc_tokens:
            return 0.0
        return len(doc_tokens & topic_tokens) / len(doc_tokens)


class EmbeddingSimilarityStrategy(RelevanceStrategy):
    """Strategy based on cosine similarity between document embeddings.

    This class requires ``sentence-transformers`` to be installed.  If the
    package is missing, an informative ImportError is raised when ``score`` is
    called.  The implementation is intentionally lightweight so tests can run
    without the optional dependency.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # pragma: no cover - optional dependency
                raise ImportError(
                    "sentence-transformers is required for EmbeddingSimilarityStrategy"
                ) from exc
            self._model = SentenceTransformer(self.model_name)

    def score(self, doc: str, topics: List[str]) -> float:
        self._ensure_model()
        embeddings = self._model.encode([doc, " ".join(topics)])
        a, b = embeddings
        # Manual cosine similarity to avoid numpy requirement
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


@dataclass
class RelevanceFilterPipeline:
    """Filter and rank document dictionaries using one or more strategies."""

    strategies: List[tuple[RelevanceStrategy, float]] | None = None
    max_documents: int | None = None
    token_budget: int | None = None

    def _normalized_strategies(self) -> List[tuple[RelevanceStrategy, float]]:
        if not self.strategies:
            return [(TFIDFStrategy(), 1.0)]
        norm = []
        for item in self.strategies:
            if isinstance(item, tuple):
                strat, weight = item
            else:
                strat, weight = item, 1.0
            norm.append((strat, weight))
        return norm

    def _rank(self, docs: List[dict], topics: List[str]):
        strats = self._normalized_strategies()
        total_weight = sum(w for _, w in strats)
        results = []
        for doc in docs:
            scores = {}
            combined = 0.0
            for strat, weight in strats:
                sc = strat.score(doc["content"], topics)
                sc = max(0.0, min(1.0, sc))
                scores[type(strat).__name__] = sc
                combined += sc * weight
            combined = combined / total_weight if strats else 0.0
            results.append((doc, combined, scores))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def filter(self, docs: List[dict], topics: List[str], *, return_scores: bool = False) -> dict:
        ranked = self._rank(docs, topics)
        selected: List[dict] = []
        tokens_used = 0
        for doc, combined, scores in ranked:
            if self.max_documents is not None and len(selected) >= self.max_documents:
                break
            doc_tokens = _estimate_tokens(doc["content"])
            if self.token_budget is not None and doc_tokens > self.token_budget - tokens_used:
                continue
            out = doc.copy()
            out["token_count"] = doc_tokens
            if return_scores:
                out["strategy_scores"] = scores
                out["combined_score"] = combined
            selected.append(out)
            tokens_used += doc_tokens
            if self.token_budget is not None and tokens_used >= self.token_budget:
                break
        return {"documents": selected, "total_tokens": tokens_used}


def run_pipeline(
    docs: List[dict],
    topics: List[str],
    *,
    strategies: List[tuple[RelevanceStrategy, float] | RelevanceStrategy] | None = None,
    max_documents: int | None = None,
    token_budget: int | None = None,
    return_scores: bool = False,
) -> dict:
    """Convenience wrapper around :class:`RelevanceFilterPipeline`."""

    pipeline = RelevanceFilterPipeline(
        strategies=strategies,
        max_documents=max_documents,
        token_budget=token_budget,
    )
    return pipeline.filter(docs, topics, return_scores=return_scores)


# Backwards compatible class names
TfidfRanker = TFIDFStrategy
KeywordRanker = KeywordMatchStrategy


def filter_documents(
    docs: List[str],
    topics: List[str],
    *,
    ranker: RelevanceStrategy | None = None,
    top_n: int | None = None,
    threshold: float | None = None,
) -> List[str]:
    """Return documents ranked most relevant to ``topics``.

    ``top_n`` limits the number of results. ``threshold`` filters by minimum
    similarity score.
    """

    ranker = ranker or TFIDFStrategy()
    ranked = ranker.rank(docs, topics)

    if threshold is not None:
        ranked = [pair for pair in ranked if pair[1] >= threshold]

    if top_n is not None:
        ranked = ranked[:top_n]

    return [doc for doc, _ in ranked]
