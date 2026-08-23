"""Sleep consolidation — maintenance, not routing.

v0.5: posterior decay, quality-gated FAQ candidates, semantic-cache prune,
consolidation_log. Does not auto-publish FAQs. Redis lock required.

Honest cache notes:
- Exact cache lives in Redis under keys `exact:{version}:{payload_hash}`.
  That hash is NOT request_log.query_hash. We do not invent Redis keys.
  Exact-cache TTL is already CACHE_TTL_S; we skip O(n) SCAN.
- Semantic cache lives in Postgres (`semantic_cache`). Zero-hit prune
  of that table is the cache this job can actually maintain.
- query_hash has been written since v0.4.0; we do not change the hash.
- vpt_daily aggregation is preserved from v0.4.0.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from gateway.config import settings

log = logging.getLogger(__name__)


def decay_alpha_beta(alpha: float, beta: float, factor: float) -> tuple[int, int]:
    """Forget evidence, keep the Beta(1,1) prior.

    Multiplying α and β themselves (handoff draft) lets integer rounding
    delete a failure from a small β and *raise* P(p>τ). Decaying (α-1)
    and (β-1) is the actual posterior-temperature step.
    """
    new_a = max(1, int(round(1.0 + (float(alpha) - 1.0) * float(factor))))
    new_b = max(1, int(round(1.0 + (float(beta) - 1.0) * float(factor))))
    return new_a, new_b


def pattern_qualifies(
    count: int,
    avg_quality: float,
    min_quality: float,
    threshold: int,
    quality_floor: float,
    min_quality_floor: float = 0.85,
) -> bool:
    return (
        count >= threshold
        and avg_quality >= quality_floor
        and min_quality >= min_quality_floor
    )


async def run(pool, redis=None, trigger: str = "scheduled") -> dict:
    job_id = str(uuid4())
    t0 = time.perf_counter()
    log.info(
        "SLEEP starting job=%s trigger=%s at %s",
        job_id,
        trigger,
        datetime.now(timezone.utc).isoformat(),
    )
    summary = {
        "job_id": job_id,
        "trigger": trigger,
        "pruned_meta": 0,
        "candidates": 0,
        "patterns_found": 0,
        "vpt_days": 0,
        "resets": 0,
        "decayed": 0,
        "cache_extended": 0,
        "cache_extend_skipped": "exact Redis keys are not query_hash",
    }

    got_lock = False
    if redis is not None:
        try:
            got = await redis.set("sleep_lock", job_id, nx=True, ex=3600)
            if not got:
                log.warning("SLEEP skipped — lock held")
                return {"job_id": job_id, "status": "skipped_lock", "trigger": trigger}
            got_lock = True
        except Exception as exc:
            log.warning("SLEEP lock error: %s", exc)

    if pool is None:
        return {**summary, "status": "no_pool"}

    window_s = int(getattr(settings, "SLEEP_INTERVAL_S", 604800) or 604800)
    decay_factor = float(getattr(settings, "SLEEP_DECAY_FACTOR", 0.80))
    decay_min_obs = int(getattr(settings, "SLEEP_DECAY_MIN_OBS", 10))
    pattern_n = int(getattr(settings, "SLEEP_PATTERN_THRESHOLD", 5))
    pattern_q = float(getattr(settings, "SLEEP_PATTERN_QUALITY_FLOOR", 0.95))
    cold_age_s = int(getattr(settings, "SLEEP_COLD_CACHE_AGE_S", 604800))

    try:
        async with pool.acquire() as conn:
            # Phase 1: decay routing confidence (n_obs unchanged — stay out of cold)
            routes = await conn.fetch(
                """
                SELECT route_class, alpha, beta, n_obs
                FROM myelination_registry
                WHERE n_obs >= $1
                """,
                decay_min_obs,
            )
            for row in routes:
                new_a, new_b = decay_alpha_beta(row["alpha"], row["beta"], decay_factor)
                if new_a != int(row["alpha"]) or new_b != int(row["beta"]):
                    await conn.execute(
                        """
                        UPDATE myelination_registry
                        SET alpha=$2, beta=$3, updated_at=now()
                        WHERE route_class=$1
                        """,
                        row["route_class"],
                        new_a,
                        new_b,
                    )
                    summary["decayed"] += 1

            # Phase 1b: hard-reset routes with high cheap→strong escalation
            degraded = await conn.fetch(
                """
                SELECT route_class,
                       COUNT(*) AS total,
                       SUM(CASE WHEN usage_legs::text LIKE '%"tier": "strong"%'
                                AND usage_legs::text LIKE '%"tier": "cheap"%'
                           THEN 1 ELSE 0 END) AS escalations
                FROM request_log
                WHERE ts > now() - ($1 * interval '1 second')
                  AND route_class IS NOT NULL
                  AND stakes_reason IS NULL
                GROUP BY route_class
                HAVING COUNT(*) >= 10
                   AND SUM(CASE WHEN usage_legs::text LIKE '%"tier": "strong"%'
                                AND usage_legs::text LIKE '%"tier": "cheap"%'
                           THEN 1 ELSE 0 END)::float / COUNT(*) > 0.30
                """,
                window_s,
            )
            for row in degraded:
                await conn.execute(
                    """
                    UPDATE myelination_registry
                    SET alpha=1, beta=1, n_obs=0, cheap_n=0, last_correction=now()
                    WHERE route_class=$1
                    """,
                    row["route_class"],
                )
                summary["resets"] += 1
                log.warning("SLEEP reset route_class=%s", row["route_class"])

            # Phase 2: quality-gated patterns → candidates (never live FAQ)
            patterns = await conn.fetch(
                """
                SELECT query_hash, intent, feature_class,
                       COUNT(*) AS frequency,
                       AVG(quality_score) AS avg_quality,
                       MIN(quality_score) AS min_quality,
                       MIN(query_text_redacted) AS representative_query
                FROM request_log
                WHERE ts > now() - ($1 * interval '1 second')
                  AND query_hash IS NOT NULL
                  AND ras_gate_fired IS NULL
                  AND stakes_reason IS NULL
                  AND quality_score IS NOT NULL
                GROUP BY query_hash, intent, feature_class
                HAVING COUNT(*) >= $2
                   AND AVG(quality_score) >= $3
                   AND MIN(quality_score) >= 0.85
                """,
                window_s,
                pattern_n,
                pattern_q,
            )
            summary["patterns_found"] = len(patterns)
            for p in patterns:
                try:
                    await conn.execute(
                        """
                        INSERT INTO faq_candidates (
                            query_hash, frequency, status, created_at,
                            intent, feature_class, representative_query,
                            avg_quality, updated_at
                        )
                        VALUES ($1, $2, 'pending', now(), $3, $4, $5, $6, now())
                        ON CONFLICT (query_hash) DO UPDATE
                        SET frequency = EXCLUDED.frequency,
                            avg_quality = EXCLUDED.avg_quality,
                            intent = COALESCE(EXCLUDED.intent, faq_candidates.intent),
                            feature_class = COALESCE(EXCLUDED.feature_class, faq_candidates.feature_class),
                            representative_query = COALESCE(
                                EXCLUDED.representative_query, faq_candidates.representative_query
                            ),
                            updated_at = now()
                        """,
                        p["query_hash"],
                        p["frequency"],
                        p["intent"],
                        p["feature_class"],
                        p["representative_query"],
                        p["avg_quality"],
                    )
                except Exception:
                    await conn.execute(
                        """
                        INSERT INTO faq_candidates (query_hash, frequency, status, created_at)
                        VALUES ($1, $2, 'pending', now())
                        ON CONFLICT (query_hash) DO UPDATE
                        SET frequency = EXCLUDED.frequency
                        """,
                        p["query_hash"],
                        p["frequency"],
                    )
                summary["candidates"] += 1

            # Phase 3: prune cold Postgres semantic_cache (the table this job owns)
            pruned = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM semantic_cache
                    WHERE hit_count = 0
                      AND created_at < now() - ($1 * interval '1 second')
                    RETURNING 1
                ) SELECT COUNT(*) FROM deleted
                """,
                cold_age_s,
            )
            summary["pruned_meta"] = pruned or 0

            # Phase 4: VpT daily (preserved)
            vpt_res = await conn.execute(
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
            try:
                summary["vpt_days"] = int(str(vpt_res).split()[-1])
            except (ValueError, IndexError):
                summary["vpt_days"] = 0

            duration_ms = int((time.perf_counter() - t0) * 1000)
            summary["duration_ms"] = duration_ms
            try:
                await conn.execute(
                    """
                    INSERT INTO consolidation_log (
                        window_start, window_end,
                        routes_decayed, routes_reset,
                        patterns_found, candidates_created,
                        cache_extended, trigger, duration_ms
                    ) VALUES (
                        now() - ($1 * interval '1 second'), now(),
                        $2, $3, $4, $5, $6, $7, $8
                    )
                    """,
                    window_s,
                    summary["decayed"],
                    summary["resets"],
                    summary["patterns_found"],
                    summary["candidates"],
                    summary["cache_extended"],
                    trigger,
                    duration_ms,
                )
            except Exception as exc:
                log.warning("SLEEP consolidation_log write skipped: %s", exc)

            summary["status"] = "ok"
    except Exception as exc:
        log.error("SLEEP error: %s", exc)
        summary["status"] = f"error:{exc}"
        summary["duration_ms"] = int((time.perf_counter() - t0) * 1000)

    if got_lock and redis is not None:
        try:
            await redis.delete("sleep_lock")
        except Exception as exc:
            log.warning("SLEEP lock release error: %s", exc)

    log.info("SLEEP complete job=%s summary=%s", job_id, summary)
    return summary
