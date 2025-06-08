import re
from typing import List

try:
    from sumy.nlp.tokenizers import Tokenizer  # type: ignore
    from sumy.parsers.plaintext import PlaintextParser  # type: ignore
    from sumy.summarizers.text_rank import TextRankSummarizer  # type: ignore
except Exception:  # pragma: no cover - optional
    PlaintextParser = None

try:  # optional dependency
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional
    tiktoken = None

TOKEN_RE = re.compile(r"\b\w+\b")


def estimate_tokens(text: str) -> int:
    """Return a best-effort token count for ``text``."""
    if tiktoken is not None:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:  # pragma: no cover - unexpected
            pass
    return max(1, int(len(TOKEN_RE.findall(text)) * 1.3))


def summarize_text(text: str, max_sentences: int = 2) -> str:
    """Extract a brief summary of ``text``.

    Uses TextRank from ``sumy`` when available. If not, chooses the most
    information-dense sentences based on token uniqueness and length.
    """
    if PlaintextParser is not None:  # pragma: no cover - optional
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = TextRankSummarizer()
        sentences = summarizer(parser.document, max_sentences)
        out = " ".join(str(s) for s in sentences)
        if out:
            return out

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    words = TOKEN_RE.findall(text.lower())
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    def score(sentence: str) -> float:
        tokens = TOKEN_RE.findall(sentence.lower())
        if re.match(r"^(hi|hello|hey)\b", sentence.lower()):
            return 0.0
        uniq = sum(1.0 / freq.get(t, 1) for t in tokens)
        length = len(tokens)
        return uniq + 0.1 * length

    ranked = sorted(sentences, key=score, reverse=True)
    return " ".join(ranked[:max_sentences])
