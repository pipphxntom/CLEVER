"""Exact cache. Key includes classified intent + canonical projected context + data version."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from gateway.config import settings

log = logging.getLogger(__name__)


def canonical_context(context: dict, fields_needed: list[str]) -> dict:
    if not context:
        return {}
    if fields_needed:
        return {k: context[k] for k in fields_needed if k in context}
    return {k: context[k] for k in sorted(context)}


def make_key(query: str, intent: str, feature_class: str, aging_version: str, ctx: dict) -> str:
    payload = json.dumps({
        "q": query.strip().lower(),
        "intent": intent,
        "fc": feature_class,
        "ver": aging_version,
        "ctx": ctx,
    }, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"exact:{aging_version}:{digest}"


def _key(req, intent: str, fields_needed: list[str]) -> str:
    aging_version = str((req.context or {}).get("aging_version", "none"))
    ctx = canonical_context(req.context or {}, fields_needed)
    return make_key(req.query, intent, req.feature_class, aging_version, ctx)


async def exact_get(redis_client, req, intent: str, fields_needed: list[str]) -> Optional[dict]:
    if redis_client is None:
        return None
    try:
        k = _key(req, intent, fields_needed)
        raw = await redis_client.get(k)
        if raw:
            log.info("cache.exact HIT key=%s", k)
            return json.loads(raw)
        log.info("cache.exact MISS key=%s", k)
    except Exception as exc:
        log.warning("cache.exact_get degraded: %s", exc)
    return None


async def exact_put(
    redis_client,
    req,
    intent: str,
    fields_needed: list[str],
    response_text: str,
    baseline_cost_usd: float,
    original_cost_usd: float,
    original_model: str,
) -> None:
    if redis_client is None:
        return
    try:
        k = _key(req, intent, fields_needed)
        data = json.dumps({
            "response": response_text,
            "baseline_cost_usd": baseline_cost_usd,
            "original_cost_usd": original_cost_usd,
            "original_model": original_model,
        })
        await redis_client.setex(k, settings.CACHE_TTL_S, data)
        log.info("cache.exact SET key=%s ttl=%ds", k, settings.CACHE_TTL_S)
    except Exception as exc:
        log.warning("cache.exact_put degraded: %s", exc)
