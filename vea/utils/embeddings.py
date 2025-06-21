from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List

try:
    import faiss
except Exception:  # pragma: no cover - optional dependency
    faiss = None
try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None
import pickle
try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency
    SentenceTransformer = None

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_DIR = Path.home() / ".vea" / "indexes"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def load_model(model_name: str = MODEL_NAME) -> SentenceTransformer:
    """Load and return the embedding model."""
    if SentenceTransformer is None:
        raise ImportError("sentence-transformers is required for embeddings")
    logger.debug("Loading embedding model %s", model_name)
    model = SentenceTransformer(model_name)
    logger.debug("Model loaded")
    return model


def _meta_path(index_path: Path) -> Path:
    return index_path.with_suffix(".meta.json")


def build_index(text_chunks: List[str], index_path: Path, source_paths: Iterable[Path] | None = None) -> None:
    """Build a FAISS index from the given text chunks."""
    if faiss is None or np is None:
        raise ImportError("faiss and numpy are required for embedding indexes")
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("Building index %s with %d text chunks", index_path, len(text_chunks))
    model = load_model()
    vectors = model.encode(text_chunks, show_progress_bar=False)
    logger.debug("Encoded %d vectors", len(vectors))
    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(np.asarray(vectors).astype("float32"))
    with open(index_path.with_suffix(".pkl"), "wb") as f:
        pickle.dump(text_chunks, f)
    faiss.write_index(index, str(index_path))
    if source_paths:
        meta = {str(p): p.stat().st_mtime for p in source_paths}
        _meta_path(index_path).write_text(json.dumps(meta))
    logger.debug("Index written to %s", index_path)


def needs_rebuild(index_path: Path, source_paths: Iterable[Path]) -> bool:
    """Return True if any source file is newer than the stored metadata."""
    meta_file = _meta_path(index_path)
    if not index_path.exists() or not meta_file.exists():
        logger.debug("Index %s or metadata missing", index_path)
        return True
    try:
        meta = json.loads(meta_file.read_text())
    except Exception:
        logger.debug("Failed to read metadata for %s", index_path)
        return True
    for p in source_paths:
        mtime = p.stat().st_mtime
        if str(p) not in meta or meta[str(p)] != mtime:
            logger.debug("Source %s changed", p)
            return True
    return False


def query_index(query: str, index_path: Path, k: int = 5) -> List[str]:
    """Return the top-k text chunks most similar to the query."""
    if faiss is None or np is None:
        raise ImportError("faiss and numpy are required for embedding indexes")
    index_path = Path(index_path)
    if not index_path.exists():
        logger.debug("Index %s not found", index_path)
        return []
    logger.debug("Querying index %s with '%s'", index_path, query)
    model = load_model()
    query_vec = model.encode([query])
    index = faiss.read_index(str(index_path))
    _, idx = index.search(np.asarray(query_vec).astype("float32"), k)
    with open(index_path.with_suffix(".pkl"), "rb") as f:
        corpus = pickle.load(f)
    results = [corpus[i] for i in idx[0] if i < len(corpus)]
    logger.debug("Retrieved %d results", len(results))
    return results


def ensure_index(text_chunks: List[str], index_name: str, source_paths: Iterable[Path] | None = None) -> Path:
    """Build the index if it doesn't exist or source files changed."""
    if faiss is None or np is None:
        raise ImportError("faiss and numpy are required for embedding indexes")
    index_path = INDEX_DIR / f"{index_name}.index"
    logger.debug("Ensuring index %s", index_path)
    if source_paths and needs_rebuild(index_path, source_paths):
        logger.debug("Rebuilding index %s", index_path)
        build_index(text_chunks, index_path, source_paths)
    elif not index_path.exists():
        logger.debug("Creating new index %s", index_path)
        build_index(text_chunks, index_path, source_paths or [])
    return index_path
