raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 7: Dashboard stats endpoint + CORS for Superblocks.
Run from C:\\CLEVER: python step7_files.py
"""
import os

files = {}

# â”€â”€ gateway/main.py (add CORS + /v1/stats endpoint) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/main.py"] = '''\
"""
CLEVER Gateway â€” Step 7: added CORS + /v1/stats for Superblocks dashboard.
"""
import logging
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from gateway.config import settings
from gateway.models import RouteRequest, RouteResponse
from gateway import pipeline

logging.basicConfig(level=settings.LOG_LEVEL.upper())
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("CLEVER starting â€” env=%s", settings.CLEVER_ENV)
    app.state.pool = await asyncpg.create_pool(
        settings.POSTGRES_DSN, min_size=2, max_size=10
    )
    log.info("Postgres pool ready")
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    log.info("Redis ready")
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()
    log.info("CLEVER shut down cleanly")

app = FastAPI(title="CLEVER Gateway", version="0.1.0", lifespan=lifespan)

# CORS â€” required for Superblocks browser calls and local HTML dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to Superblocks domain in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

# â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str

@app.get("/health", response_model=HealthResponse)
async def health():
    db_ok, redis_ok = "ok", "ok"
    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        db_ok = f"error: {e}"
    try:
        await app.state.redis.ping()
    except Exception as e:
        redis_ok = f"error: {e}"
    overall = "ok" if db_ok == "ok" and redis_ok == "ok" else "degraded"
    return HealthResponse(status=overall, version=app.version, db=db_ok, redis=redis_ok)

# â”€â”€ Main pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.post("/v1/route", response_model=RouteResponse)
async def route(req: RouteRequest):
    """The CLEVER pipeline: classify -> compress -> cascade -> log."""
    return await pipeline.route(req, app.state)

# â”€â”€ Dashboard stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.get("/v1/stats")
async def stats():
    """
    Aggregated stats for the Superblocks dashboard.
    Single endpoint â€” Superblocks polls this every 5 seconds.
    """
    async with app.state.pool.acquire() as conn:

        # Overall totals
        totals = await conn.fetchrow("""
            SELECT
                COUNT(*)                              AS total_requests,
                COALESCE(SUM(cost_usd), 0)            AS total_cost_usd,
                COALESCE(SUM(baseline_cost_usd), 0)   AS total_baseline_usd,
                COALESCE(AVG(latency_ms), 0)          AS avg_latency_ms,
                COALESCE(AVG(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    END
                ), 0)                                 AS avg_saved_pct
            FROM request_log
        """)

        # Stakes Gate trips
        trips = await conn.fetch("""
            SELECT ts, intent, gate_fired, feature_class
            FROM request_log
            WHERE gate_fired IS NOT NULL
            ORDER BY ts DESC
            LIMIT 10
        """)

        # Model usage breakdown
        models = await conn.fetch("""
            SELECT
                model_used,
                COUNT(*)             AS calls,
                SUM(cost_usd)        AS total_cost
            FROM request_log
            WHERE model_used IS NOT NULL
            GROUP BY model_used
            ORDER BY calls DESC
        """)

        # Last 20 requests for live feed
        recent = await conn.fetch("""
            SELECT
                ts, intent, feature_class,
                model_used, tokens_in, tokens_out,
                cost_usd, baseline_cost_usd,
                ROUND(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    ELSE 0 END
                , 1)             AS saved_pct,
                latency_ms, gate_fired
            FROM request_log
            ORDER BY ts DESC
            LIMIT 20
        """)

        # Savings by feature class
        by_class = await conn.fetch("""
            SELECT
                feature_class,
                COUNT(*)                                AS calls,
                ROUND(AVG(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    ELSE 0 END
                )::numeric, 1)                          AS avg_saved_pct,
                COALESCE(SUM(baseline_cost_usd - cost_usd), 0) AS total_saved_usd
            FROM request_log
            GROUP BY feature_class
            ORDER BY total_saved_usd DESC
        """)

    total_saved = float(totals["total_baseline_usd"]) - float(totals["total_cost_usd"])

    return {
        "summary": {
            "total_requests":   totals["total_requests"],
            "total_cost_usd":   round(float(totals["total_cost_usd"]),    4),
            "total_baseline_usd": round(float(totals["total_baseline_usd"]), 4),
            "total_saved_usd":  round(max(0.0, total_saved),              4),
            "avg_saved_pct":    round(float(totals["avg_saved_pct"]),     1),
            "avg_latency_ms":   round(float(totals["avg_latency_ms"]),    0),
        },
        "stakes_gate_trips": [
            {
                "ts":            str(r["ts"]),
                "intent":        r["intent"],
                "reason":        r["gate_fired"],
                "feature_class": r["feature_class"],
            }
            for r in trips
        ],
        "model_breakdown": [
            {
                "model":      r["model_used"],
                "calls":      r["calls"],
                "total_cost": round(float(r["total_cost"] or 0), 6),
            }
            for r in models
        ],
        "recent_requests": [
            {
                "ts":            str(r["ts"]),
                "intent":        r["intent"],
                "feature_class": r["feature_class"],
                "model":         r["model_used"],
                "tokens_in":     r["tokens_in"],
                "tokens_out":    r["tokens_out"],
                "cost_usd":      float(r["cost_usd"] or 0),
                "saved_pct":     float(r["saved_pct"] or 0),
                "latency_ms":    r["latency_ms"],
                "gate_fired":    r["gate_fired"],
            }
            for r in recent
        ],
        "by_feature_class": [
            {
                "feature_class":  r["feature_class"],
                "calls":          r["calls"],
                "avg_saved_pct":  float(r["avg_saved_pct"] or 0),
                "total_saved_usd": float(r["total_saved_usd"] or 0),
            }
            for r in by_class
        ],
    }
'''

# â”€â”€ Write all files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for path, content in files.items():
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print(f"  created  {path}")

print("\nStep 7 gateway files ready.")

