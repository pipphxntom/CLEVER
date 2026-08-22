"""Semantic cache. Same-account isolation via context_hash. Never cross-tenant."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from gateway.config import settings
import asyncio

from gateway.embedder import embed, to_pgvector
from gateway.layers.cache import canonical_context

log = logging.getLogger(__name__)


def context_hash(req, fields_needed: list[str]) -> str:
    ctx = canonical_context(req.context or {}, fields_needed)
    raw = json.dumps({
        "fc": req.feature_class,
        "ver": str((req.context or {}).get("aging_version", "none")),
        "ctx": ctx,
    }, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _embed_text(intent: str, query: str) -> str:
    return f"{intent}\n{query.strip().lower()}"


async def semantic_get(pool, req, intent: str, fields_needed: list[str]) -> Optional[dict]:
    if pool is None or not settings.SEMANTIC_ENABLED:
        return None
    vec = await asyncio.to_thread(embed, _embed_text(intent, req.query))
    if not vec:
        return None
    ch = context_hash(req, fields_needed)
    ver = str((req.context or {}).get("aging_version", "none"))
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, response, baseline_cost_usd,
                       (1 - (embedding <=> $1::vector)) AS sim
                FROM semantic_cache
                WHERE feature_class = $2
                  AND aging_version = $3
                  AND context_hash = $4
                  AND intent = $5
                  AND created_at + (COALESCE(ttl_seconds, 3600) * interval '1 second') > now()
                ORDER BY embedding <=> $1::vector
                LIMIT 1
                """,
                to_pgvector(vec), req.feature_class, ver, ch, intent,
            )
        if not row:
            log.info("cache.semantic MISS")
            return None
        sim = float(row["sim"] or 0)
        if sim < settings.SEMANTIC_THRESHOLD:
            log.info("cache.semantic below_threshold sim=%.3f", sim)
            return None
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE semantic_cache SET hit_count = hit_count + 1, last_hit_at = now() WHERE id = $1",
                row["id"],
            )
        log.info("cache.semantic HIT sim=%.3f id=%s", sim, row["id"])
        return {
            "response": row["response"],
            "baseline_cost_usd": float(row["baseline_cost_usd"] or 0),
            "score": sim,
        }
    except Exception as exc:
        log.warning("cache.semantic_get degraded: %s", exc)
        return None


async def semantic_put(
    pool, req, intent: str, fields_needed: list[str],
    response_text: str, baseline_cost_usd: float,
) -> None:
    if pool is None or not settings.SEMANTIC_ENABLED:
        return
    vec = await asyncio.to_thread(embed, _embed_text(intent, req.query))
    if not vec:
        return
    ch = context_hash(req, fields_needed)
    ver = str((req.context or {}).get("aging_version", "none"))
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO semantic_cache (
                    embedding, query_text, response, feature_class, intent,
                    aging_version, context_hash, hit_count, ttl_seconds, baseline_cost_usd
                ) VALUES (
                    $1::vector, $2, $3, $4, $5, $6, $7, 0, $8, $9
                )
                """,
                to_pgvector(vec),
                req.query.strip()[:500],
                response_text,
                req.feature_class,
                intent,
                ver,
                ch,
                settings.CACHE_TTL_S,
                baseline_cost_usd,
            )
        log.info("cache.semantic SET intent=%s", intent)
    except Exception as exc:
        log.warning("cache.semantic_put degraded: %s", exc)
