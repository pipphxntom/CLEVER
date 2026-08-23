"""Write every pipeline exit to request_log. Classified intent, not the hint."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger(__name__)


def query_hash(query: str, intent: str, version: str) -> str:
    raw = f"{query.strip().lower()}|{intent}|{version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class LogRecord:
    request_id: str
    req: Any
    intent: str
    trace: list
    usage_legs: list
    accounting: dict
    latency_ms: int
    route_class: Optional[str] = None
    cache_hit: bool = False
    ras_gate: Optional[str] = None
    stakes_reason: Optional[str] = None
    quality_score: Optional[float] = None
    model_used: Optional[str] = None
    vpt: Optional[float] = None
    outcome_unit: Optional[str] = None
    outcome_value_usd: Optional[float] = None


async def write_request_log(pool, rec: LogRecord) -> None:
    if pool is None:
        return
    try:
        version = (rec.req.context or {}).get("aging_version")
        qh = query_hash(rec.req.query, rec.intent, str(version or "none"))
        query_snip = (getattr(rec.req, "query", None) or "").strip()[:200]
        tokens_in = rec.accounting.get("tokens_in", 0)
        tokens_out = rec.accounting.get("tokens_out", 0)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO request_log (
                    request_id, mode, feature_class, intent, stakes,
                    gate_fired, ras_gate_fired, stakes_reason,
                    model_used, tokens_in, tokens_out,
                    cost_usd, baseline_cost_usd, quality_score,
                    latency_ms, decision_trace, query_hash, aging_version,
                    vpt, outcome_unit, outcome_value_usd, route_class,
                    cache_hit, usage_legs, query_text_redacted
                ) VALUES (
                    $1,$2,$3,$4,$5,
                    $6,$7,$8,
                    $9,$10,$11,
                    $12,$13,$14,
                    $15,$16,$17,$18,
                    $19,$20,$21,$22,
                    $23,$24,$25
                )
                """,
                rec.request_id,
                rec.req.mode,
                rec.req.feature_class,
                rec.intent,
                rec.req.stakes,
                rec.stakes_reason or rec.ras_gate,
                rec.ras_gate,
                rec.stakes_reason,
                rec.model_used or "none",
                tokens_in,
                tokens_out,
                rec.accounting.get("cost_usd"),
                rec.accounting.get("baseline_cost_usd"),
                rec.quality_score,
                rec.latency_ms,
                json.dumps(rec.trace, default=str),
                qh,
                version,
                rec.vpt,
                rec.outcome_unit,
                rec.outcome_value_usd,
                rec.route_class,
                rec.cache_hit,
                json.dumps(rec.usage_legs, default=str),
                query_snip or None,
            )
    except Exception as exc:
        log.warning("request_log write failed: %s", exc)
