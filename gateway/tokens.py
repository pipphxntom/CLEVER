"""Token estimates for baselines. Actual billed tokens always come from the provider."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_enc = None


def _encoder():
    global _enc
    if _enc is None:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def count_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        return len(_encoder().encode(text))
    except Exception as exc:
        log.warning("tokenizer fallback: %s", exc)
        return max(1, int(len(text.split()) * 1.3))
