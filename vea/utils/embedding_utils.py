import json
import logging
import hashlib
import time
from pathlib import Path
from typing import Any, Iterable, List, Tuple, Union

logger = logging.getLogger(__name__)

try:
    import faiss  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled in tests
    faiss = None  # pragma: no cover

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled in tests
    SentenceTransformer = None  # type: ignore

_MODEL_CACHE: dict[str, "SentenceTransformer"] = {}


def _get_model(name: str):
    if SentenceTransformer is None:  # pragma: no cover - handled in tests
        raise RuntimeError("sentence_transformers is required")
    if name not in _MODEL_CACHE:
        _MODEL_CACHE[name] = SentenceTransformer(name)
    return _MODEL_CACHE[name]

INDEX_DIR = Path("~/.vea/indexes").expanduser()
# MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_NAME = "BAAI/bge-base-en-v1.5"


def _hash_documents(docs: List[str]) -> str:
    joined = "\u0000".join(docs)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def load_or_create_index(
    index_path: Path,
    documents: Iterable[Union[str, Tuple[str, Any]]],
    model_name: str = MODEL_NAME,
    debug: bool = False,
) -> "faiss.Index":
    """Load a FAISS index from ``index_path`` or create it from ``documents``.

    ``documents`` may contain plain strings or ``(text, obj)`` tuples. Only the
    text portion is embedded and hashed, while the corresponding objects are
    attached to the index and returned by :func:`query_index`.
    """
    if faiss is None or SentenceTransformer is None:  # pragma: no cover
        raise RuntimeError("faiss and sentence_transformers are required")

    texts: List[str] = []
    objects: List[Any] = []
    for item in documents:
        if isinstance(item, tuple):
            text, obj = item
        else:
            text, obj = str(item), item
        texts.append(text)
        objects.append(obj)
    index_path = index_path.expanduser()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = index_path.with_suffix(".meta.json")
    docs_hash = _hash_documents(texts)

    if index_path.is_file() and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}
        if meta.get("hash") == docs_hash:
            index = faiss.read_index(str(index_path))
            try:
                setattr(index, "_documents", objects)
            except Exception:  # pragma: no cover - unlikely
                pass
            if debug:
                logger.debug("Loaded existing index from %s", index_path)
            return index

    if debug:
        logger.debug("Creating new index at %s", index_path)
    model = _get_model(model_name)
    embeddings = model.encode(texts, convert_to_numpy=True)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    faiss.write_index(index, str(index_path))
    meta_path.write_text(json.dumps({"hash": docs_hash, "timestamp": time.time()}))
    try:
        setattr(index, "_documents", objects)
    except Exception:  # pragma: no cover - unlikely
        pass
    return index


def query_index(index, query_text: str, top_k: int) -> List[Any]:
    """Return the stored objects for the top ``top_k`` matches to ``query_text``."""
    if SentenceTransformer is None or faiss is None:  # pragma: no cover
        raise RuntimeError("faiss and sentence_transformers are required")

    docs = getattr(index, "_documents", [])
    if not docs:
        return []

    model = _get_model(MODEL_NAME)
    query_vec = model.encode([query_text], convert_to_numpy=True)
    _, indices = index.search(query_vec, min(top_k, len(docs)))
    result = []
    for idx in indices[0]:
        if 0 <= idx < len(docs):
            result.append(docs[idx])
    return result
