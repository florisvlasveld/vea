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
    doc_items: List[Tuple[Union[str, Path], Any]] = []
    text_docs: List[str] = []
    path_mtimes: dict[str, float] = {}
            src, obj = item
        else:
            src, obj = item, item
        doc_items.append((src, obj))
        if isinstance(src, (str, Path)) and Path(src).is_file():
            p = Path(src)
            path_mtimes[str(p)] = p.stat().st_mtime
            text_docs.append(str(src))
    text_hash = _hash_documents(text_docs) if text_docs else ""
    objects = [obj for _, obj in doc_items]

        if (
            meta.get("model_name") == model_name
            and meta.get("mtimes") == path_mtimes
            and meta.get("text_hash") == text_hash
        ):
                setattr(index, "_meta_path", str(meta_path))
    texts: List[str] = []
    for src, _ in doc_items:
        if isinstance(src, (str, Path)) and Path(src).is_file():
            texts.append(Path(src).read_text(encoding="utf-8"))
        else:
            texts.append(str(src))

    meta_path.write_text(
        json.dumps(
            {
                "model_name": model_name,
                "mtimes": path_mtimes,
                "text_hash": text_hash,
                "timestamp": time.time(),
            }
        )
    )
        setattr(index, "_meta_path", str(meta_path))
    meta_path = getattr(index, "_meta_path", None)
    model_name = MODEL_NAME
    if meta_path and Path(meta_path).is_file():
        try:
            meta = json.loads(Path(meta_path).read_text())
            model_name = meta.get("model_name", MODEL_NAME)
        except Exception:
            model_name = MODEL_NAME

    model = _get_model(model_name)
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
