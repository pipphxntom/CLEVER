"""Local embeddings for semantic cache. Fails closed (returns None) if model missing."""
from __future__ import annotations

import logging
import threading

from gateway.config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_failed = False
DIM = 384


def available() -> bool:
    if _failed:
        return False
    try:
        _load()
        return _model is not None
    except Exception:
        return False


def _load():
    global _model, _failed
    if _model is not None or _failed:
        return
    with _lock:
        if _model is not None or _failed:
            return
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(settings.SEMANTIC_MODEL)
            log.info("embedder loaded model=%s", settings.SEMANTIC_MODEL)
        except Exception as exc:
            _failed = True
            log.warning("embedder unavailable: %s", exc)


def embed(text: str) -> list[float] | None:
    if not settings.SEMANTIC_ENABLED:
        return None
    _load()
    if _model is None:
        return None
    vec = _model.encode([text], normalize_embeddings=True)[0]
    return [float(x) for x in vec.tolist()]


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
