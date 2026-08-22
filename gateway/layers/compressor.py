"""Project context to intent fields. Token counts come from the tokenizer, never constants."""
from __future__ import annotations

import json
import logging

from gateway import catalog
from gateway.tokens import count_tokens

log = logging.getLogger(__name__)


def build_context(req, intent: str) -> dict:
    icfg = catalog.intent_cfg(intent)
    fields_needed = list(icfg.get("fields") or [])
    ctx = req.context or {}

    projected = {}
    if fields_needed and ctx:
        for f in fields_needed:
            if f in ctx:
                projected[f] = ctx[f]

    full_ctx = json.dumps(ctx, sort_keys=True, default=str) if ctx else ""
    uncompressed_prompt = req.query
    if full_ctx and full_ctx not in ("{}",):
        uncompressed_prompt = f"{req.query}\n\nContext:\n{full_ctx}"

    if projected:
        ctx_block = "\n".join(f"  {k}: {v}" for k, v in projected.items())
        compressed_prompt = f"{req.query}\n\nRelevant context:\n{ctx_block}"
    else:
        compressed_prompt = req.query

    tokens_before = count_tokens(uncompressed_prompt)
    tokens_after = count_tokens(compressed_prompt)
    if tokens_before <= 0:
        reduction_pct = 0.0
    else:
        reduction_pct = round((1 - tokens_after / tokens_before) * 100, 1)

    log.info(
        "compressor intent=%s fields=%d tokens %d->%d (%.1f%%)",
        intent, len(projected), tokens_before, tokens_after, reduction_pct,
    )
    return {
        "prompt": compressed_prompt,
        "uncompressed_prompt": uncompressed_prompt,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "fields_used": list(projected.keys()),
        "fields_needed": fields_needed,
        "reduction_pct": reduction_pct,
    }
