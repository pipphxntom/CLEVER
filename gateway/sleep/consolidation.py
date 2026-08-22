"""Weekly maintenance. Does not auto-publish FAQs. Redis lock required."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

log = logging.getLogger(__name__)

_ZERO_HIT_DAYS = 7
_FAQ_PROMOTE_MIN = 20


async def run(pool, redis=None) -> dict:
    job_id = str(uuid4())
    log.info("SLEEP starting job=%s at %s", job_id, datetime.now(timezone.utc).isoformat())
    summary = {"job_id": job_id, "pruned_meta": 0, "candidates": 0, "vpt_days": 0, "resets": 0}

    if redis is not None:
        try:
            got = await redis.set("sleep_lock", job_id, nx=True, ex=3600)
            if not got:
                log.warning("SLEEP skipped — lock held")
                return {"job_id": job_id, "status": "skipped_lock"}
        except Exception as exc:
            log.warning("SLEEP lock error: %s", exc)

    if pool is None:
        return {**summary, "status": "no_pool"}

    try:
        async with pool.acquire() as conn:
            pruned = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM semantic_cache
                    WHERE hit_count = 0
                      AND created_at < now() - interval '1 day' * $1
                    RETURNING 1
                ) SELECT COUNT(*) FROM deleted
                """,
                _ZERO_HIT_DAYS,
            )
            summary["pruned_meta"] = pruned or 0

            degraded = await conn.fetch(
                """
                SELECT route_class,
                       COUNT(*) AS total,
                       SUM(CASE WHEN usage_legs::text LIKE '%"tier": "strong"%'
                                AND usage_legs::text LIKE '%"tier": "cheap"%'
                           THEN 1 ELSE 0 END) AS escalations
                FROM request_log
                WHERE ts > now() - interval '7 days'
                  AND route_class IS NOT NULL
                  AND stakes_reason IS NULL
                GROUP BY route_class
                HAVING COUNT(*) >= 10
                   AND SUM(CASE WHEN usage_legs::text LIKE '%"tier": "strong"%'
                                AND usage_legs::text LIKE '%"tier": "cheap"%'
                           THEN 1 ELSE 0 END)::float / COUNT(*) > 0.30
                """
            )
            for row in degraded:
                await conn.execute(
                    """
                    UPDATE myelination_registry
                    SET alpha=1, beta=1, n_obs=0, last_correction=now()
                    WHERE route_class=$1
                    """,
                    row["route_class"],
                )
                summary["resets"] += 1
                log.warning("SLEEP reset route_class=%s", row["route_class"])

            patterns = await conn.fetch(
                """
                SELECT query_hash, COUNT(*) AS frequency
                FROM request_log
                WHERE ts > now() - interval '30 days'
                  AND query_hash IS NOT NULL
                  AND ras_gate_fired IS NULL
                  AND stakes_reason IS NULL
                GROUP BY query_hash
                HAVING COUNT(*) >= $1
                """,
                _FAQ_PROMOTE_MIN,
            )
            for p in patterns:
                await conn.execute(
                    """
                    INSERT INTO faq_candidates (query_hash, frequency, status, created_at)
                    VALUES ($1, $2, 'pending', now())
                    ON CONFLICT (query_hash) DO UPDATE
                    SET frequency = EXCLUDED.frequency
                    """,
                    p["query_hash"], p["frequency"],
                )
                summary["candidates"] += 1

            await conn.execute(
                """
                INSERT INTO vpt_daily (date, intent, avg_vpt, total_tokens, total_value)
                SELECT
                    CURRENT_DATE - 1,
                    intent,
                    AVG(vpt),
                    SUM(tokens_in + tokens_out),
                    SUM(outcome_value_usd)
                FROM request_log
                WHERE DATE(ts) = CURRENT_DATE - 1
                  AND vpt IS NOT NULL
                GROUP BY intent
                ON CONFLICT (date, intent) DO UPDATE
                SET avg_vpt = EXCLUDED.avg_vpt,
                    total_tokens = EXCLUDED.total_tokens,
                    total_value = EXCLUDED.total_value
                """
            )
            summary["status"] = "ok"
    except Exception as exc:
        log.error("SLEEP error: %s", exc)
        summary["status"] = f"error:{exc}"

    log.info("SLEEP complete job=%s summary=%s", job_id, summary)
    return summary
