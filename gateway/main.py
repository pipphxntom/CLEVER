"""CLEVER Gateway entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gateway.auth import require_admin_key, require_api_key
from gateway.security import SecurityHeadersMiddleware
from gateway.config import settings
from gateway.models import RouteRequest, RouteResponse
from gateway import catalog, pipeline
from gateway.providers.factory import build_provider
from gateway.sleep import consolidation
from gateway.telemetry import tail_cost as tail_cost_calc

logging.basicConfig(level=settings.LOG_LEVEL.upper())
log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARD = _ROOT / "superblocks" / "clever_dashboard.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("CLEVER starting env=%s provider=%s", settings.CLEVER_ENV, settings.LLM_PROVIDER)
    catalog.reload()

    app.state.provider = build_provider()
    app.state.pool = await asyncpg.create_pool(settings.POSTGRES_DSN, min_size=2, max_size=10)
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    scheduler = AsyncIOScheduler()

    async def _sleep_job():
        await consolidation.run(app.state.pool, app.state.redis, trigger="scheduled")

    if settings.SLEEP_ENABLED:
        scheduler.add_job(
            _sleep_job,
            trigger="interval",
            seconds=max(60, int(settings.SLEEP_INTERVAL_S)),
            id="sleep",
            replace_existing=True,
        )
        log.info("sleep interval_s=%s", settings.SLEEP_INTERVAL_S)
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("ready")
    yield
    scheduler.shutdown(wait=False)
    await app.state.pool.close()
    await app.state.redis.aclose()
    log.info("shutdown")


app = FastAPI(title="CLEVER Gateway", version="0.5.0", lifespan=lifespan, docs_url="/docs" if settings.CLEVER_ENV != "prod" else None)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)


class HealthResponse(BaseModel):
    status: str
    version: str
    provider: str
    db: str
    redis: str


@app.get("/health", response_model=HealthResponse)
async def health():
    db_ok, redis_ok = "ok", "ok"
    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        db_ok = "error"
    try:
        await app.state.redis.ping()
    except Exception:
        redis_ok = "error"
    overall = "ok" if db_ok == "ok" and redis_ok == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        version=app.version,
        provider=getattr(app.state.provider, "name", settings.LLM_PROVIDER),
        db=db_ok,
        redis=redis_ok,
    )


@app.get("/")
async def dashboard():
    if not _DASHBOARD.exists():
        raise HTTPException(404, "dashboard missing")
    return FileResponse(_DASHBOARD)


@app.post("/v1/route", response_model=RouteResponse)
async def route(req: RouteRequest, _auth: str = Depends(require_api_key)):
    if not catalog.known_feature_class(req.feature_class):
        raise HTTPException(422, f"unknown feature_class: {req.feature_class}")
    try:
        return await pipeline.route(req, app.state)
    except HTTPException:
        raise
    except Exception:
        log.exception("route failed")
        raise HTTPException(status_code=503, detail="upstream_error")


@app.post("/v1/admin/sleep")
async def trigger_sleep(_auth: str = Depends(require_admin_key)):
    result = await consolidation.run(app.state.pool, app.state.redis, trigger="manual")
    return result


@app.post("/v1/admin/consolidate")
async def trigger_consolidation(_auth: str = Depends(require_admin_key)):
    """Manual sleep trigger (alias of /v1/admin/sleep). Admin key required."""
    result = await consolidation.run(app.state.pool, app.state.redis, trigger="manual")
    return result


@app.get("/v1/admin/faq/candidates")
async def faq_candidates(_auth: str = Depends(require_admin_key)):
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, query_hash, frequency, status, created_at FROM faq_candidates ORDER BY frequency DESC LIMIT 50"
        )
    return {"candidates": [dict(r) for r in rows]}


@app.get("/v1/stats")
async def stats(_auth: str = Depends(require_api_key)):
    async with app.state.pool.acquire() as conn:
        totals = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_requests,
                COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                COALESCE(SUM(baseline_cost_usd), 0) AS total_baseline_usd,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                COALESCE(AVG(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    END
                ), 0) AS avg_saved_pct
            FROM request_log
            WHERE ts > now() - interval '24 hours'
            """
        )
        trips = await conn.fetch(
            """
            SELECT ts, intent, stakes_reason, feature_class
            FROM request_log
            WHERE stakes_reason IS NOT NULL
              AND ts > now() - interval '24 hours'
            ORDER BY ts DESC LIMIT 10
            """
        )
        ras_hits = await conn.fetch(
            """
            SELECT ts, intent, ras_gate_fired, feature_class
            FROM request_log
            WHERE ras_gate_fired IS NOT NULL
              AND ts > now() - interval '24 hours'
            ORDER BY ts DESC LIMIT 10
            """
        )
        models = await conn.fetch(
            """
            SELECT model_used, COUNT(*) AS calls, SUM(cost_usd) AS total_cost
            FROM request_log
            WHERE model_used IS NOT NULL AND model_used != 'none'
              AND ts > now() - interval '24 hours'
            GROUP BY model_used ORDER BY calls DESC
            """
        )
        recent = await conn.fetch(
            """
            SELECT ts, intent, feature_class, model_used,
                   tokens_in, tokens_out, cost_usd, baseline_cost_usd,
                   ROUND(
                       CASE WHEN baseline_cost_usd > 0
                       THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                       ELSE 0 END
                   ::numeric, 1) AS saved_pct,
                   latency_ms, stakes_reason, ras_gate_fired, vpt, outcome_unit, cache_hit
            FROM request_log
            WHERE ts > now() - interval '24 hours'
            ORDER BY ts DESC LIMIT 20
            """
        )
        by_class = await conn.fetch(
            """
            SELECT feature_class, COUNT(*) AS calls,
                ROUND(AVG(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    ELSE 0 END
                )::numeric, 1) AS avg_saved_pct,
                COALESCE(SUM(baseline_cost_usd - cost_usd), 0) AS total_saved_usd
            FROM request_log
            WHERE ts > now() - interval '24 hours'
            GROUP BY feature_class ORDER BY total_saved_usd DESC
            """
        )
        vpt_by_intent = await conn.fetch(
            """
            SELECT intent,
                   ROUND(AVG(vpt)::numeric, 4) AS avg_vpt,
                   ROUND(SUM(outcome_value_usd)::numeric, 2) AS total_value_usd,
                   SUM(tokens_in + tokens_out) AS total_tokens
            FROM request_log
            WHERE vpt IS NOT NULL AND ts > now() - interval '24 hours'
            GROUP BY intent ORDER BY avg_vpt DESC
            """
        )
        myelin_rows = await conn.fetch(
            """
            SELECT route_class, alpha, beta, n_obs,
                   ROUND((alpha::numeric / NULLIF(alpha + beta, 0)), 3) AS p_hat
            FROM myelination_registry
            ORDER BY n_obs DESC LIMIT 20
            """
        )
        exits = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE ras_gate_fired IS NOT NULL) AS ras,
                COUNT(*) FILTER (WHERE cache_hit IS TRUE) AS cache,
                COUNT(*) FILTER (
                    WHERE stakes_reason IS NOT NULL AND COALESCE(tokens_in,0)=0
                ) AS stakes_pending,
                COUNT(*) FILTER (WHERE COALESCE(tokens_in,0) > 0) AS llm,
                COUNT(*) AS total,
                COALESCE(AVG(
                    CASE WHEN COALESCE(tokens_in,0) > 0 AND baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    END
                ), 0) AS llm_saved_pct
            FROM request_log
            WHERE ts > now() - interval '24 hours'
            """
        )

    total_saved = float(totals["total_baseline_usd"]) - float(totals["total_cost_usd"])
    zero_exits = int(exits["ras"] or 0) + int(exits["cache"] or 0) + int(exits["stakes_pending"] or 0)
    total_n = int(exits["total"] or 0)
    short_circuit_pct = round(100.0 * zero_exits / total_n, 1) if total_n else 0.0
    tcr = await tail_cost_calc.compute(app.state.pool, window_hours=24)
    provider_name = getattr(app.state.provider, "name", settings.LLM_PROVIDER)

    def _phase(n):
        n = n or 0
        cold = settings.COLD_MIN if settings.COLD_MIN is not None else settings.N_MIN
        if n < cold:
            return "cold"
        if n < 100:
            return "warming"
        return "stable"

    return {
        "provider": provider_name,
        "window": "24h",
        "summary": {
            "total_requests": totals["total_requests"],
            "total_cost_usd": round(float(totals["total_cost_usd"]), 4),
            "total_baseline_usd": round(float(totals["total_baseline_usd"]), 4),
            "total_saved_usd": round(max(0.0, total_saved), 4),
            "avg_saved_pct": round(float(totals["avg_saved_pct"] or 0), 1),
            "avg_saved_pct_note": "MIXED: includes RAS/cache 100%. Use llm_saved_pct + short_circuit_pct.",
            "llm_saved_pct": round(float(exits["llm_saved_pct"] or 0), 1),
            "short_circuit_pct": short_circuit_pct,
            "avg_latency_ms": round(float(totals["avg_latency_ms"] or 0), 0),
        },
        "by_exit": {
            "ras": int(exits["ras"] or 0),
            "cache": int(exits["cache"] or 0),
            "stakes_pending": int(exits["stakes_pending"] or 0),
            "llm": int(exits["llm"] or 0),
            "total": total_n,
        },
        "stakes_gate_trips": [
            {"ts": str(r["ts"]), "intent": r["intent"],
             "reason": r["stakes_reason"], "feature_class": r["feature_class"]}
            for r in trips
        ],
        "short_circuits": [
            {"ts": str(r["ts"]), "intent": r["intent"],
             "gate": r["ras_gate_fired"], "feature_class": r["feature_class"]}
            for r in ras_hits
        ],
        "model_breakdown": [
            {"model": r["model_used"], "calls": r["calls"],
             "total_cost": round(float(r["total_cost"] or 0), 6)}
            for r in models
        ],
        "recent_requests": [
            {"ts": str(r["ts"]), "intent": r["intent"],
             "feature_class": r["feature_class"], "model": r["model_used"],
             "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
             "cost_usd": float(r["cost_usd"] or 0),
             "saved_pct": float(r["saved_pct"] or 0),
             "latency_ms": r["latency_ms"],
             "stakes_reason": r["stakes_reason"],
             "ras_gate": r["ras_gate_fired"],
             "cache_hit": bool(r["cache_hit"]) if r["cache_hit"] is not None else False,
             "vpt": (float(r["vpt"]) if r["vpt"] is not None else None),
             "outcome_unit": r["outcome_unit"]}
            for r in recent
        ],
        "by_feature_class": [
            {"feature_class": r["feature_class"], "calls": r["calls"],
             "avg_saved_pct": float(r["avg_saved_pct"] or 0),
             "total_saved_usd": float(r["total_saved_usd"] or 0)}
            for r in by_class
        ],
        "vpt_by_intent": [
            {"intent": r["intent"],
             "avg_vpt": float(r["avg_vpt"] or 0),
             "total_value_usd": float(r["total_value_usd"] or 0),
             "total_tokens": r["total_tokens"]}
            for r in vpt_by_intent
        ],
        "myelination": [
            {"route_class": r["route_class"], "phase": _phase(r["n_obs"]),
             "p_hat": float(r["p_hat"] or 0),
             "n_obs": r["n_obs"],
             "alpha": r["alpha"], "beta": r["beta"]}
            for r in myelin_rows
        ],
        "tail_cost": tcr,
    }
