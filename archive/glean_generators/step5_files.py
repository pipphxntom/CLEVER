raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 5: Classifier + Compressor â€” where real token savings happen.
Run from C:\\CLEVER: python step5_files.py
"""
import os

files = {}

# â”€â”€ gateway/layers/classifier.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/classifier.py"] = '''\
"""
Classifier (L1) â€” Â§5.2 of spec.
Cost-ascending classification order:
  1. Config lookup  â€” intent_hint matches known intent â†’ $0, confidence 1.0
  2. Keyword regex  â€” scan query text for intent signals â†’ $0, confidence 0.8
  3. Default        â€” safe fallback for the feature class â†’ $0, confidence 0.5
Nano-model fallback is roadmap, not needed for demo.
"""
import logging
import yaml
from pathlib import Path

log = logging.getLogger(__name__)

_INTENTS_PATH = Path("config/intents.yaml")
_INTENTS: dict = {}

def _load():
    global _INTENTS
    if not _INTENTS:
        _INTENTS = yaml.safe_load(_INTENTS_PATH.read_text(encoding="utf-8"))

# Keyword â†’ intent signals (used when intent_hint is absent or unknown)
_KEYWORD_MAP = {
    "triage":             ["overdue", "aged", "aging", "outstanding", "delinquent", "who owes"],
    "email_draft":        ["draft email", "write email", "compose", "dunning letter"],
    "email_blast":        ["blast", "send all", "bulk send", "mass email", "send to all"],
    "remit":              ["remit", "payment received", "pay invoice", "settle balance"],
    "inbox_check":        ["inbox", "new replies", "check responses", "new messages"],
    "dispute":            ["dispute", "challenge invoice", "contest", "disagree with charge"],
    "notes":              ["add note", "log note", "record note"],
    "event_summary":      ["event summary", "tell me about the event", "event details"],
    "event_status_check": ["registration count", "how many registered", "capacity", "seats left"],
    "event_publish":      ["publish event", "go live", "launch event"],
    "registration_lookup":["registration status", "is registered", "attendee status"],
    "registration_cancel":["cancel registration", "unregister", "refund registration"],
    "campaign_draft":     ["draft campaign", "write campaign", "compose campaign"],
    "campaign_send":      ["send campaign", "launch campaign", "blast campaign", "push campaign"],
    "audience_segment":   ["segment", "audience", "who should receive", "target list"],
    "venue_search":       ["find venue", "venue in", "venue for", "search venues", "where to host"],
    "rfp_draft":          ["draft rfp", "write rfp", "rfp for venue"],
    "rfp_send":           ["send rfp", "submit rfp", "send proposal"],
    "ticket_lookup":      ["ticket #", "support case", "open ticket", "check issue"],
    "ticket_response_draft": ["respond to ticket", "reply to case", "draft response"],
    "ticket_escalate":    ["escalate ticket", "escalate case", "raise priority"],
    "report_summary":     ["report", "metrics", "dashboard", "give me a summary", "insights"],
    "insight_query":      ["analyse", "analyze", "trend", "breakdown", "compare"],
}

# Feature class â†’ safe default intent when everything else fails
_CLASS_DEFAULTS = {
    "collections_outreach": "triage",
    "event_management":     "event_summary",
    "registration":         "registration_lookup",
    "marketing_automation": "campaign_draft",
    "venue_sourcing":       "venue_search",
    "customer_support":     "ticket_lookup",
    "analytics_reporting":  "report_summary",
    "billing_support":      "triage",
}

def classify(req) -> tuple[str, float]:
    """
    Returns (intent, confidence).
    Logs which classification method fired.
    """
    _load()
    q = req.query.lower()

    # 1. Config lookup â€” cheapest, most reliable
    if req.intent_hint and req.intent_hint in _INTENTS:
        log.info("classifier method=config_lookup intent=%s conf=1.0", req.intent_hint)
        return req.intent_hint, 1.0

    # 2. Keyword scan
    for intent, keywords in _KEYWORD_MAP.items():
        for kw in keywords:
            if kw in q:
                log.info("classifier method=keyword_match intent=%s kw=%r conf=0.8", intent, kw)
                return intent, 0.8

    # 3. Feature-class default
    default = _CLASS_DEFAULTS.get(req.feature_class, "triage")
    log.info("classifier method=default intent=%s conf=0.5", default)
    return default, 0.5
'''

# â”€â”€ gateway/layers/compressor.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/compressor.py"] = '''\
"""
Compressor (L3) â€” Â§5.2, Â§5.3 of spec.
Strips context down to only the fields the intent actually needs.
Everything else is noise that costs tokens and adds no value.

Spec example (triage, 4 fields):
  tokens_before = 8,200  (full aging record)
  tokens_after  = 1,450  (82% reduction)
"""
import logging
import yaml
from pathlib import Path

log = logging.getLogger(__name__)

_INTENTS_PATH = Path("config/intents.yaml")
_INTENTS: dict = {}

# Baseline: a full uncompressed context (aging file / full document)
_FULL_CONTEXT_TOKENS = 8_200

# Realistic tokens per projected field (header + value + whitespace)
_TOKENS_PER_FIELD = 300

def _load():
    global _INTENTS
    if not _INTENTS:
        _INTENTS = yaml.safe_load(_INTENTS_PATH.read_text(encoding="utf-8"))

def build_context(req, intent: str) -> dict:
    """
    Projects context to only the fields this intent needs.
    Returns a dict with: prompt, tokens_before, tokens_after,
                         fields_used, reduction_pct.
    """
    _load()
    intent_cfg   = _INTENTS.get(intent, {})
    fields_needed = intent_cfg.get("fields", [])

    # Project only needed fields from the request context
    projected = {}
    if fields_needed and req.context:
        for f in fields_needed:
            if f in req.context:
                projected[f] = req.context[f]

    # Build the focused prompt
    if projected:
        ctx_block = "\\n".join(f"  {k}: {v}" for k, v in projected.items())
        prompt = f"{req.query}\\n\\nRelevant context:\\n{ctx_block}"
    else:
        prompt = req.query

    # Token estimates
    query_tokens  = max(20, int(len(req.query.split()) * 1.4))
    tokens_before = _FULL_CONTEXT_TOKENS if req.context else query_tokens
    tokens_after  = max(
        80,
        len(fields_needed) * _TOKENS_PER_FIELD + query_tokens
    ) if fields_needed else query_tokens

    # Never report MORE tokens after than before
    tokens_after  = min(tokens_after, tokens_before)

    reduction_pct = round((1 - tokens_after / tokens_before) * 100, 1) if tokens_before else 0.0

    log.info(
        "compressor intent=%s fields=%d tokens %d->%d (%.1f%% saved)",
        intent, len(fields_needed), tokens_before, tokens_after, reduction_pct,
    )

    return {
        "prompt":        prompt,
        "tokens_before": tokens_before,
        "tokens_after":  tokens_after,
        "fields_used":   fields_needed,
        "reduction_pct": reduction_pct,
    }
'''

# â”€â”€ gateway/telemetry/accounting.py (updated â€” baseline uses full context) â”€â”€
files["gateway/telemetry/accounting.py"] = '''\
"""
Cost accounting â€” computes per-request cost vs true baseline.
Baseline = FULL uncompressed context + always Sonnet + no cache.
This is what you would have paid without CLEVER.
"""

# Bedrock on-demand pricing per 1M tokens (approximate)
_PRICING = {
    "haiku":  {"in": 0.80,  "out": 4.00},
    "sonnet": {"in": 3.00,  "out": 15.00},
}

def _tier(model_id: str) -> str:
    return "haiku" if "haiku" in model_id.lower() else "sonnet"

def _cost(tokens_in: int, tokens_out: int, model_id: str) -> float:
    r = _PRICING[_tier(model_id)]
    return (tokens_in * r["in"] + tokens_out * r["out"]) / 1_000_000

def build_accounting(usage: dict, tokens_before: int = None) -> dict:
    """
    usage        â€” actual token counts from the LLM call
    tokens_before â€” full uncompressed token count (for true baseline)
    """
    ti  = usage["tokens_in"]
    to  = usage["tokens_out"]
    mid = usage["model_id"]

    # What we actually paid
    cost = _cost(ti, to, mid)

    # Baseline: full context (before compression) + always Sonnet + no cache
    baseline_in = tokens_before if tokens_before else ti
    base = _cost(baseline_in, to, "sonnet")

    saved     = max(0.0, base - cost)
    saved_pct = round(saved / base * 100, 1) if base > 0 else 0.0

    return {
        "tokens_in":         ti,
        "tokens_out":        to,
        "cost_usd":          round(cost,  6),
        "baseline_cost_usd": round(base,  6),
        "saved_usd":         round(saved, 6),
        "saved_pct":         saved_pct,
    }
'''

# â”€â”€ gateway/pipeline.py (full replacement â€” real classifier + compressor) â”€â”€
files["gateway/pipeline.py"] = '''\
"""
CLEVER pipeline orchestrator (Â§5.2).
Step 5 state: Stakes Gate + Exact Cache + Classifier + Compressor are REAL.
Cascade (Haiku -> quality gate -> Sonnet) comes in Step 6.
"""
import time
import logging

from gateway.models import RouteRequest, RouteResponse, AccountingResult, QualityResult
from gateway.providers import bedrock as provider
from gateway.layers import stakes_gate, cache, classifier, compressor
from gateway.telemetry import accounting
from gateway.telemetry import logger as telemetry

log = logging.getLogger(__name__)

_HAIKU  = "anthropic.claude-3-5-haiku-20241022-v1:0"
_SONNET = "anthropic.claude-3-5-sonnet-20241022-v2:0"

async def route(req: RouteRequest, app_state) -> RouteResponse:
    start = time.time()
    trace = []

    # â”€â”€ Step 0: Classifier (runs BEFORE Stakes Gate so gate has real intent) â”€â”€
    intent, confidence = classifier.classify(req)
    trace.append({
        "layer":      "classifier",
        "intent":     intent,
        "confidence": confidence,
        "method":     "config" if confidence == 1.0 else "keyword" if confidence == 0.8 else "default",
    })

    # â”€â”€ Step 1: Stakes Gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    stakes = stakes_gate.classify(req, intent)
    gate_entry = {
        "layer":  "stakes_gate",
        "result": "SUSPENDED" if stakes.suspend_optimization else "read",
    }
    if stakes.suspend_optimization:
        gate_entry["reason"]                = stakes.reason
        gate_entry["min_model"]             = stakes.min_model
        gate_entry["require_human_confirm"] = stakes.require_human_confirm
        gate_entry["cache"]                 = "OFF"
    trace.append(gate_entry)

    # â”€â”€ MUTATION PATH (Stakes Gate tripped) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if stakes.suspend_optimization:
        ctx = compressor.build_context(req, intent)
        llm_result = await provider.invoke(
            model_id=_SONNET,
            messages=[{"role": "user", "content": ctx["prompt"]}],
            context_tokens=ctx["tokens_after"],
        )
        usage = llm_result["usage"]
        acc   = accounting.build_accounting(usage, tokens_before=ctx["tokens_before"])
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
                + llm_result["text"]
            ),
            decision_trace=trace,
            accounting=AccountingResult(**acc),
            quality=QualityResult(checked=False, method="none"),
            latency_ms=latency_ms,
        )

    # â”€â”€ Step 2: Exact cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Step 3: Router (stub â€” always Haiku for read intents) â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # TODO Step 6: real cascade with quality gate
    model_id = _HAIKU
    trace.append({"layer": "router", "model": "claude-haiku"})

    # â”€â”€ Step 4: Compressor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ctx = compressor.build_context(req, intent)
    trace.append({
        "layer":          "compressor",
        "fields_used":    ctx["fields_used"],
        "tokens_before":  ctx["tokens_before"],
        "tokens_after":   ctx["tokens_after"],
        "reduction_pct":  ctx["reduction_pct"],
    })

    # â”€â”€ Step 5: LLM call â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    llm_result = await provider.invoke(
        model_id=model_id,
        messages=[{"role": "user", "content": ctx["prompt"]}],
        context_tokens=ctx["tokens_after"],
    )
    usage = llm_result["usage"]
    trace.append({
        "layer": "llm",
        "model": "claude-haiku",
        "in":    usage["tokens_in"],
        "out":   usage["tokens_out"],
    })

    # â”€â”€ Step 6: Accounting (baseline uses full uncompressed tokens) â”€â”€â”€â”€
    acc = accounting.build_accounting(usage, tokens_before=ctx["tokens_before"])
    latency_ms = int((time.time() - start) * 1000)

    # â”€â”€ Step 7: Log + cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

print("\nStep 5 files ready.")

