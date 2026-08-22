raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 4: Stakes Gate + Exact Cache.
Run from C:\\CLEVER: python step4_files.py
"""
import os

files = {}

# â”€â”€ config/intents.yaml â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["config/intents.yaml"] = """\
# Intent definitions â€” stakes level + default model tier
# stakes: read | mutate | soft_write
triage:
  stakes: read
  tier: haiku
  fields: [account, balance, days_overdue, status]

email_draft:
  stakes: read
  tier: haiku
  fields: [account, contact, balance, invoice_ids, last_contact]

inbox_check:
  stakes: read
  tier: haiku
  fields: [thread_id, account, sentiment, ask]

email_blast:
  stakes: mutate
  tier: sonnet
  fresh_data: true
  human_confirm: true

remit:
  stakes: mutate
  tier: sonnet
  fresh_data: true
  optimization: suspended

notes:
  stakes: soft_write
  tier: haiku
  fields: [account, note_text]

dispute:
  stakes: read
  tier: sonnet
  fields: [account, history, dispute_docs]
"""

# â”€â”€ config/features.yaml â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["config/features.yaml"] = """\
# Feature class definitions â€” quality floors + cache settings
collections_outreach:
  q_floor: 0.92
  default_tier: haiku
  cache: true

reconciliation:
  q_floor: 1.0
  stakes: mutate
  cache: false

customer_facing:
  q_floor: 0.98
  default_tier: sonnet
  cache: true
"""

# â”€â”€ gateway/layers/stakes_gate.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/stakes_gate.py"] = '''\
"""
Stakes Gate â€” Step 0 of every pipeline call (Â§10 of spec).
Pure function: inspects the request and decides if optimization is allowed.
STAKES_GATE_TRIP is the demo centrepiece â€” the moment CLEVER refuses to be cheap.
"""
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# Feature classes that ALWAYS suspend optimization â€” no exceptions, ever
_HIGH_STAKES_CLASSES = {"reconciliation", "ledger", "payment"}

# Intents that are always mutations regardless of feature class
_MUTATE_INTENTS = {"remit", "email_blast"}

@dataclass
class StakesResult:
    suspend_optimization: bool
    min_model: str                  # "haiku" or "sonnet"
    require_fresh: bool
    require_human_confirm: bool
    reason: Optional[str]           # populated on TRIP, None otherwise

def classify(req, intent: str) -> StakesResult:
    """
    Returns StakesResult.
    Logs STAKES_GATE_TRIP if optimization is suspended.
    Called as Step 0 before any cache lookup.
    """
    # 1. Caller explicitly declared mutate
    if req.stakes == "mutate":
        return _trip("explicit_mutate_flag")

    # 2. High-stakes feature class
    if req.feature_class in _HIGH_STAKES_CLASSES:
        return _trip(f"high_stakes_class:{req.feature_class}")

    # 3. Intent is a known mutation
    if intent in _MUTATE_INTENTS:
        return _trip(f"mutate_intent:{intent}")

    # Safe to optimize
    return StakesResult(
        suspend_optimization=False,
        min_model="haiku",
        require_fresh=False,
        require_human_confirm=False,
        reason=None,
    )

def _trip(reason: str) -> StakesResult:
    """Log the trip and return a fully locked-down StakesResult."""
    log.warning("STAKES_GATE_TRIP reason=%s", reason)
    return StakesResult(
        suspend_optimization=True,
        min_model="sonnet",
        require_fresh=True,
        require_human_confirm=True,
        reason=reason,
    )
'''

# â”€â”€ gateway/layers/cache.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/cache.py"] = '''\
"""
Cache layer â€” L4a Exact Cache (Â§5.2, Â§10 of spec).
Key format: exact:{aging_version}:{md5}
Version-namespaced so a new aging file upload NEVER serves stale data.
Degrades gracefully to no-op if Redis is down.
"""
import hashlib
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

_TTL = 3600  # 1 hour default TTL

def _key(req) -> str:
    """
    Build a deterministic, version-scoped cache key.
    Same query + same version = same key.
    New aging version = entirely different keyspace.
    """
    aging_version = req.context.get("aging_version", "none")
    payload = json.dumps({
        "q":  req.query.strip().lower(),
        "fc": req.feature_class,
        "ih": req.intent_hint,
    }, sort_keys=True)
    md5 = hashlib.md5(payload.encode()).hexdigest()
    return f"exact:{aging_version}:{md5}"

async def exact_get(redis_client, req) -> Optional[dict]:
    """
    Returns cached response dict on hit, None on miss.
    Logs result either way â€” the trace must always be honest.
    """
    try:
        k = _key(req)
        raw = await redis_client.get(k)
        if raw:
            log.info("cache.exact HIT  key=%s", k)
            return json.loads(raw)
        log.info("cache.exact MISS key=%s", k)
    except Exception as exc:
        log.warning("cache.exact_get degraded: %s", exc)
    return None

async def exact_put(redis_client, req, response_text: str, accounting: dict) -> None:
    """Store response in Redis with TTL. Non-fatal on failure."""
    try:
        k = _key(req)
        data = json.dumps({"response": response_text, "accounting": accounting})
        await redis_client.setex(k, _TTL, data)
        log.info("cache.exact SET  key=%s ttl=%ds", k, _TTL)
    except Exception as exc:
        log.warning("cache.exact_put degraded: %s", exc)
'''

# â”€â”€ gateway/telemetry/logger.py (updated â€” adds gate_fired param) â”€â”€â”€â”€â”€
files["gateway/telemetry/logger.py"] = '''\
"""
Request logger â€” writes every call to request_log (Postgres).
Fails silently so a DB hiccup never kills a user request.
"""
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

async def write_request_log(
    pool,
    req,
    trace: list,
    usage: dict,
    accounting: dict,
    latency_ms: int,
    gate_fired: Optional[str] = None,
) -> None:
    """Insert one row into request_log. Non-fatal on error."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO request_log (
                    mode, feature_class, intent, stakes,
                    gate_fired, model_used,
                    tokens_in, tokens_out,
                    cost_usd, baseline_cost_usd,
                    latency_ms, decision_trace, aging_version
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                """,
                req.mode,
                req.feature_class,
                req.intent_hint or "unknown",
                req.stakes,
                gate_fired,
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

# â”€â”€ gateway/pipeline.py (full replacement â€” real Stakes Gate + Cache) â”€
files["gateway/pipeline.py"] = '''\
"""
CLEVER pipeline orchestrator (Â§5.2).
Step 4 state: Stakes Gate + Exact Cache are now REAL.
Compressor and Classifier still stubbed (Step 5).
"""
import time
import logging

from gateway.models import RouteRequest, RouteResponse, AccountingResult, QualityResult
from gateway.providers import bedrock as provider
from gateway.layers import stakes_gate, cache
from gateway.telemetry import accounting
from gateway.telemetry import logger as telemetry

log = logging.getLogger(__name__)

_HAIKU  = "anthropic.claude-3-5-haiku-20241022-v1:0"
_SONNET = "anthropic.claude-3-5-sonnet-20241022-v2:0"

async def route(req: RouteRequest, app_state) -> RouteResponse:
    start = time.time()
    trace = []

    # â”€â”€ Step 0: Stakes Gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    intent = req.intent_hint or "triage"
    stakes = stakes_gate.classify(req, intent)

    gate_entry = {
        "layer": "stakes_gate",
        "result": "SUSPENDED" if stakes.suspend_optimization else "read",
    }
    if stakes.suspend_optimization:
        gate_entry["reason"]               = stakes.reason
        gate_entry["min_model"]            = stakes.min_model
        gate_entry["require_human_confirm"] = stakes.require_human_confirm
        gate_entry["cache"]                = "OFF"
    trace.append(gate_entry)

    # â”€â”€ MUTATION PATH (Stakes Gate tripped) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if stakes.suspend_optimization:
        ctx_tokens = max(100, len(req.query.split()) * 4)
        llm_result = await provider.invoke(
            model_id=_SONNET,
            messages=[{"role": "user", "content": req.query}],
            context_tokens=ctx_tokens,
        )
        usage = llm_result["usage"]
        acc   = accounting.build_accounting(usage)
        latency_ms = int((time.time() - start) * 1000)

        await telemetry.write_request_log(
            pool=app_state.pool, req=req, trace=trace,
            usage=usage, accounting=acc,
            latency_ms=latency_ms, gate_fired=stakes.reason,
        )

        return RouteResponse(
            response=(
                f"STAKES_GATE_TRIP â€” optimization suspended.\\n"
                f"Reason: {stakes.reason}\\n"
                f"Human confirmation required before any action fires.\\n\\n"
                f"{llm_result[\'text\']}"
            ),
            decision_trace=trace,
            accounting=AccountingResult(**acc),
            quality=QualityResult(checked=False, method="none"),
            latency_ms=latency_ms,
        )

    # â”€â”€ Step 1: Exact cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if req.mode == "clever":
        cached = await cache.exact_get(app_state.redis, req)
        if cached:
            trace.append({"layer": "cache.exact", "result": "HIT", "saved": "~$0"})
            latency_ms = int((time.time() - start) * 1000)
            return RouteResponse(
                response=cached["response"],
                decision_trace=trace,
                accounting=AccountingResult(**cached["accounting"]),
                quality=QualityResult(checked=False, method="cache"),
                latency_ms=latency_ms,
            )

    trace.append({"layer": "cache.exact", "result": "miss"})

    # â”€â”€ Step 2: Classifier (stub) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    trace.append({"layer": "classifier", "intent": intent})

    # â”€â”€ Step 3: Router (stub â€” always Haiku for read intents) â”€â”€â”€â”€â”€â”€â”€â”€
    model_id = _HAIKU
    trace.append({"layer": "router", "model": "claude-haiku"})

    # â”€â”€ Step 4: Compressor (stub â€” no compression yet) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tokens_before = max(100, len(req.query.split()) * 4)
    trace.append({
        "layer":         "compressor",
        "tokens_before": tokens_before,
        "tokens_after":  tokens_before,
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

    # â”€â”€ Step 7: Log + populate cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    await telemetry.write_request_log(
        pool=app_state.pool, req=req, trace=trace,
        usage=usage, accounting=acc, latency_ms=latency_ms,
    )

    if req.mode == "clever":
        await cache.exact_put(app_state.redis, req, llm_result["text"], acc)

    return RouteResponse(
        response=llm_result["text"],
        decision_trace=trace,
        accounting=AccountingResult(**acc),
        quality=QualityResult(checked=False, method="none"),
        latency_ms=latency_ms,
    )
'''

# â”€â”€ Write all files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for path, content in files.items():
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print(f"  created  {path}")

print("\nStep 4 files ready.")

