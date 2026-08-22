raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 3 setup: creates all pipeline source files.
Run once from C:\\CLEVER: python step3_files.py
"""
import os

os.makedirs("gateway/layers", exist_ok=True)
os.makedirs("gateway/providers", exist_ok=True)
os.makedirs("gateway/telemetry", exist_ok=True)

files = {}

# â”€â”€ __init__.py files (empty, but Python needs them) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/__init__.py"] = ""
files["gateway/providers/__init__.py"] = ""
files["gateway/telemetry/__init__.py"] = ""

# â”€â”€ config.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/config.py"] = '''\
"""
Loads settings from .env via pydantic-settings.
Every config value lives here â€” nothing hardcoded elsewhere.
"""
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    CLEVER_ENV: str = "dev"
    LOG_LEVEL: str = "info"
    POSTGRES_DSN: str = "postgresql://clever:clever@localhost:5432/clever"
    REDIS_URL: str = "redis://localhost:6379/0"
    BEDROCK_MODEL_HAIKU: str = "anthropic.claude-3-5-haiku-20241022-v1:0"
    BEDROCK_MODEL_SONNET: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    BEDROCK_MODEL_EMBED: str = "amazon.titan-embed-text-v2:0"
    AWS_REGION: str = "us-east-1"

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
'''

# â”€â”€ models.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/models.py"] = '''\
"""
Pydantic models for the CLEVER API contract (Â§13 of spec).
These are the shapes of every request and response.
"""
from typing import Any, Optional
from pydantic import BaseModel

class RouteRequest(BaseModel):
    query: str
    context: dict[str, Any] = {}
    feature_class: str = "collections_outreach"
    intent_hint: Optional[str] = None
    stakes: str = "auto"   # auto | read | mutate
    mode: str = "clever"   # clever | baseline

class AccountingResult(BaseModel):
    tokens_in: int
    tokens_out: int
    cost_usd: float
    baseline_cost_usd: float
    saved_usd: float
    saved_pct: float

class QualityResult(BaseModel):
    checked: bool
    method: str
    score: Optional[float] = None

class RouteResponse(BaseModel):
    response: str
    decision_trace: list[dict[str, Any]]
    accounting: AccountingResult
    quality: QualityResult
    latency_ms: int
'''

# â”€â”€ providers/bedrock.py (MOCK) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/providers/bedrock.py"] = '''\
"""
Bedrock provider â€” MOCK version.
Swap the invoke() body when real AWS Bedrock access is confirmed.
Function signatures stay IDENTICAL â€” only the implementation changes.
"""
import asyncio
import random

HAIKU_ID = "anthropic.claude-3-5-haiku-20241022-v1:0"
SONNET_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

_MOCK_RESPONSES = {
    "triage": (
        "Top overdue accounts: Account 4021 ($12,500, 45 days overdue), "
        "Account 3887 ($8,200, 32 days overdue), Account 5541 ($3,100, 28 days overdue)."
    ),
    "email_draft": (
        "Dear Valued Customer, our records show invoice #INV-2024-089 "
        "totalling $12,500 remains outstanding. Please arrange payment at your "
        "earliest convenience or contact us to discuss options."
    ),
    "inbox_check": (
        "3 new replies. Account 4021 disputed invoice #INV-2024-089 â€” "
        "sentiment: frustrated. Requires human review."
    ),
    "default": (
        "[MOCK] CLEVER pipeline working. "
        "Replace this with real Bedrock output when access is confirmed."
    ),
}

async def invoke(
    model_id: str,
    messages: list[dict],
    context_tokens: int = 500,
) -> dict:
    """
    Call the LLM. Returns text + usage dict.

    MOCK: returns a canned response with fake token counts.
    REAL (swap in later):
        import boto3
        client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
        resp = client.invoke_model(modelId=model_id, body=json.dumps({...}))
        body = json.loads(resp["body"].read())
        return {
            "text": body["content"][0]["text"],
            "usage": {
                "tokens_in":  body["usage"]["input_tokens"],
                "tokens_out": body["usage"]["output_tokens"],
                "model_id":   model_id,
            }
        }
    """
    await asyncio.sleep(0.05)  # fake latency

    intent = "default"
    if messages:
        q = messages[-1].get("content", "").lower()
        for key in _MOCK_RESPONSES:
            if key in q:
                intent = key
                break

    return {
        "text": _MOCK_RESPONSES[intent],
        "usage": {
            "tokens_in":  context_tokens,
            "tokens_out": random.randint(120, 280),
            "model_id":   model_id,
        },
    }
'''

# â”€â”€ telemetry/accounting.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/telemetry/accounting.py"] = '''\
"""
Cost accounting â€” calculates per-request cost and savings vs baseline.
Baseline = full context + always Sonnet + no cache (worst case).
"""

# Bedrock on-demand pricing per 1M tokens (approximate â€” pin from AWS console)
_PRICING = {
    "haiku":  {"in": 0.80,  "out": 4.00},
    "sonnet": {"in": 3.00,  "out": 15.00},
}

def _tier(model_id: str) -> str:
    return "haiku" if "haiku" in model_id.lower() else "sonnet"

def _cost(tokens_in: int, tokens_out: int, model_id: str) -> float:
    r = _PRICING[_tier(model_id)]
    return (tokens_in * r["in"] + tokens_out * r["out"]) / 1_000_000

def build_accounting(usage: dict) -> dict:
    """Returns the accounting block that goes into RouteResponse."""
    ti, to, mid = usage["tokens_in"], usage["tokens_out"], usage["model_id"]
    cost = _cost(ti, to, mid)
    base = _cost(ti, to, "sonnet")          # baseline is always Sonnet
    saved = max(0.0, base - cost)
    saved_pct = round(saved / base * 100, 1) if base > 0 else 0.0

    return {
        "tokens_in":          ti,
        "tokens_out":         to,
        "cost_usd":           round(cost,  6),
        "baseline_cost_usd":  round(base,  6),
        "saved_usd":          round(saved, 6),
        "saved_pct":          saved_pct,
    }
'''

# â”€â”€ telemetry/logger.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/telemetry/logger.py"] = '''\
"""
Request logger â€” writes every call to request_log (Postgres).
Fails silently so a DB hiccup never kills a user request.
"""
import json
import logging

log = logging.getLogger(__name__)

async def write_request_log(
    pool, req, trace: list, usage: dict, accounting: dict, latency_ms: int
) -> None:
    """Insert one row into request_log. Non-fatal on error."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO request_log (
                    mode, feature_class, intent, stakes,
                    model_used, tokens_in, tokens_out,
                    cost_usd, baseline_cost_usd,
                    latency_ms, decision_trace, aging_version
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                req.mode,
                req.feature_class,
                req.intent_hint or "unknown",
                req.stakes,
                usage.get("model_id", "unknown"),
                usage["tokens_in"],
                usage["tokens_out"],
                accounting["cost_usd"],
                accounting["baseline_cost_usd"],
                latency_ms,
                json.dumps(trace),
                req.context.get("aging_version"),
            )
    except Exception as exc:
        log.warning("request_log write failed (degraded=db): %s", exc)
'''

# â”€â”€ pipeline.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/pipeline.py"] = '''\
"""
CLEVER pipeline orchestrator (Â§5.2 of spec).
Current state: all layers stubbed â€” routes through mock provider.
TODOs mark where real layers plug in (Steps 4-6).
"""
import time
import logging

from gateway.models import RouteRequest, RouteResponse, AccountingResult, QualityResult
from gateway.providers import bedrock as provider
from gateway.telemetry import accounting
from gateway.telemetry import logger as telemetry

log = logging.getLogger(__name__)

async def route(req: RouteRequest, app_state) -> RouteResponse:
    start = time.time()
    trace = []

    # â”€â”€ Step 0: Stakes Gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TODO (Step 4): replace with stakes_gate.classify(req, trace)
    trace.append({"layer": "stakes_gate", "result": "read"})

    # â”€â”€ Step 1: Exact cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TODO (Step 4): check Redis  exact:{version}:{md5}
    trace.append({"layer": "cache.exact", "result": "miss"})

    # â”€â”€ Step 2: Classifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TODO (Step 5): real classifier.classify(req, trace)
    intent = req.intent_hint or "triage"
    trace.append({"layer": "classifier", "intent": intent})

    # â”€â”€ Step 3: Router â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TODO (Step 5): router.plan(intent, req, trace)
    model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
    trace.append({"layer": "router", "model": "claude-haiku"})

    # â”€â”€ Step 4: Compressor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TODO (Step 5): compressor.build_context(req, intent, trace)
    tokens_before = max(100, len(req.query.split()) * 4)
    trace.append({
        "layer": "compressor",
        "tokens_before": tokens_before,
        "tokens_after": tokens_before,   # no compression yet
    })

    # â”€â”€ Step 5: LLM call â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    llm_result = await provider.invoke(
        model_id=model_id,
        messages=[{"role": "user", "content": req.query}],
        context_tokens=tokens_before,
    )
    usage = llm_result["usage"]
    trace.append({
        "layer": "llm",
        "model": "claude-haiku",
        "in":    usage["tokens_in"],
        "out":   usage["tokens_out"],
    })

    # â”€â”€ Step 6: Accounting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    acc = accounting.build_accounting(usage)

    latency_ms = int((time.time() - start) * 1000)

    # â”€â”€ Step 7: Log to Postgres â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    await telemetry.write_request_log(
        pool=app_state.pool,
        req=req,
        trace=trace,
        usage=usage,
        accounting=acc,
        latency_ms=latency_ms,
    )

    return RouteResponse(
        response=llm_result["text"],
        decision_trace=trace,
        accounting=AccountingResult(**acc),
        quality=QualityResult(checked=False, method="none"),
        latency_ms=latency_ms,
    )
'''

# â”€â”€ main.py (full replacement) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/main.py"] = '''\
"""
CLEVER Gateway â€” application entry point.
Manages DB + Redis pools via FastAPI lifespan.
"""
import logging
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI
from pydantic import BaseModel

from gateway.config import settings
from gateway.models import RouteRequest, RouteResponse
from gateway import pipeline

logging.basicConfig(level=settings.LOG_LEVEL.upper())
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open connection pools on startup, close cleanly on shutdown."""
    log.info("CLEVER starting â€” env=%s", settings.CLEVER_ENV)

    app.state.pool = await asyncpg.create_pool(
        settings.POSTGRES_DSN, min_size=2, max_size=10
    )
    log.info("Postgres pool ready")

    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    log.info("Redis ready")

    yield   # â† app is live here

    await app.state.pool.close()
    await app.state.redis.aclose()
    log.info("CLEVER shut down cleanly")

app = FastAPI(title="CLEVER Gateway", version="0.1.0", lifespan=lifespan)

# â”€â”€ Health endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str

@app.get("/health", response_model=HealthResponse)
async def health():
    """Checks gateway + Postgres + Redis are all alive."""
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

# â”€â”€ Main pipeline endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.post("/v1/route", response_model=RouteResponse)
async def route(req: RouteRequest):
    """The CLEVER pipeline: classify â†’ compress â†’ cache â†’ LLM â†’ log."""
    return await pipeline.route(req, app.state)
'''

# â”€â”€ Write all files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print(f"  created  {path}")

print("\nAll files created. Run: python -m uvicorn gateway.main:app --reload --port 8080")

