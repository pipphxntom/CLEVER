"""Tail cost ratio on a time window. Ignores zero-cost rows."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

TCR_ALERT_THRESHOLD = 1.0


async def compute(pool, intent: str = None, window_hours: int = 24) -> dict:
    empty = {
        "tcr": 0.0, "tail_cost_usd": 0.0, "body_cost_usd": 0.0,
        "total_requests": 0, "alert": False, "message": "no_data",
    }
    if pool is None:
        return empty
    intent_filter = "AND intent = $2" if intent else ""
    params: list = [window_hours]
    if intent:
        params.append(intent)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                WITH ranked AS (
                    SELECT
                        cost_usd,
                        NTILE(10) OVER (ORDER BY cost_usd DESC) AS decile
                    FROM request_log
                    WHERE ts > now() - interval '1 hour' * $1
                    {intent_filter}
                    AND cost_usd IS NOT NULL
                    AND cost_usd > 0
                )
                SELECT
                    COALESCE(SUM(CASE WHEN decile = 1 THEN cost_usd ELSE 0 END), 0) AS tail_cost,
                    COALESCE(SUM(CASE WHEN decile > 1 THEN cost_usd ELSE 0 END), 0) AS body_cost,
                    COUNT(*) AS total_requests
                FROM ranked
                """,
                *params,
            )
    except Exception as exc:
        log.warning("tail_cost.compute error: %s", exc)
        return {**empty, "message": "error"}

    tail = float(row["tail_cost"] or 0)
    body = float(row["body_cost"] or 0)
    total = row["total_requests"]
    tcr = round(tail / body, 4) if body > 0 else 0.0
    alert = tcr > TCR_ALERT_THRESHOLD
    return {
        "tcr": tcr,
        "tail_cost_usd": round(tail, 4),
        "body_cost_usd": round(body, 4),
        "total_requests": total,
        "alert": alert,
        "message": (
            f"TCR={tcr:.2f}: top 10% costs more than the rest"
            if alert else f"TCR={tcr:.2f}: healthy"
        ),
    }
