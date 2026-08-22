raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 6: Cascade â€” Haiku -> quality gate -> Sonnet escalation.
Run from C:\\CLEVER: python step6_files.py
"""
import os

files = {}

# â”€â”€ gateway/layers/quality.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/quality.py"] = '''\
"""
Quality scorer (L5b) â€” Â§5.2, Â§9 of spec.
Scores Haiku output BEFORE deciding to escalate to Sonnet.
All checks are pure Python â€” zero LLM cost.
Returns a score 0.0-1.0. Floor per feature class is in features.yaml.
"""
import logging
import re
import yaml
from pathlib import Path

log = logging.getLogger(__name__)

_FEATURES_PATH = Path("config/features.yaml")
_FEATURES: dict = {}

# Phrases that signal the model gave up or hallucinated
_REFUSAL_PATTERNS = [
    r"i (cannot|can\'t|am unable to)",
    r"i don\'t (know|have)",
    r"i\'m not sure",
    r"as an ai",
    r"i do not have access",
    r"no information available",
    r"unable to (provide|answer|assist)",
]

# Minimum meaningful response length (chars) per intent
_MIN_LENGTH = {
    "triage":             80,
    "email_draft":        120,
    "report_summary":     100,
    "insight_query":      80,
    "venue_search":       80,
    "campaign_draft":     100,
    "ticket_response_draft": 100,
    "default":            40,
}

def _load():
    global _FEATURES
    if not _FEATURES:
        _FEATURES = yaml.safe_load(_FEATURES_PATH.read_text(encoding="utf-8"))

def score(response_text: str, intent: str, feature_class: str) -> dict:
    """
    Returns {score, passed, checks, reason}.
    score  â€” float 0.0-1.0
    passed â€” bool: True if score >= feature class floor
    checks â€” list of individual check results
    reason â€” plain-English escalation reason if failed
    """
    _load()
    checks = []
    deductions = 0.0

    # â”€â”€ Check 1: Refusal detection (weight 0.4) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    text_lower = response_text.lower()
    for pattern in _REFUSAL_PATTERNS:
        if re.search(pattern, text_lower):
            checks.append({"check": "refusal", "passed": False, "detail": pattern})
            deductions += 0.4
            break
    else:
        checks.append({"check": "refusal", "passed": True})

    # â”€â”€ Check 2: Length gate (weight 0.2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    min_len = _MIN_LENGTH.get(intent, _MIN_LENGTH["default"])
    length_ok = len(response_text.strip()) >= min_len
    checks.append({
        "check":  "length",
        "passed": length_ok,
        "detail": f"{len(response_text)} chars, min={min_len}",
    })
    if not length_ok:
        deductions += 0.2

    # â”€â”€ Check 3: Mock/placeholder detection (weight 0.3) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    mock_signals = ["[mock]", "replace this", "to be implemented", "coming soon"]
    mock_found = any(s in text_lower for s in mock_signals)
    checks.append({"check": "mock_signal", "passed": not mock_found})
    if mock_found:
        deductions += 0.3

    # â”€â”€ Check 4: Completeness hint (weight 0.1) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # For triage/report intents, expect at least one number in the response
    number_intents = {"triage", "report_summary", "insight_query", "billing_support"}
    if intent in number_intents:
        has_number = bool(re.search(r"\\$?[\\d,]+", response_text))
        checks.append({"check": "has_numbers", "passed": has_number})
        if not has_number:
            deductions += 0.1
    else:
        checks.append({"check": "has_numbers", "passed": True, "detail": "n/a"})

    raw_score = round(max(0.0, 1.0 - deductions), 3)

    # Get quality floor for this feature class
    floor = _FEATURES.get(feature_class, {}).get("q_floor", 0.92)
    passed = raw_score >= floor

    reason = None
    if not passed:
        failed = [c["check"] for c in checks if not c["passed"]]
        reason = f"score={raw_score} < floor={floor}. Failed: {failed}"
        log.warning("quality FAIL intent=%s class=%s %s", intent, feature_class, reason)
    else:
        log.info("quality PASS intent=%s score=%.3f floor=%.2f", intent, raw_score, floor)

    return {
        "score":   raw_score,
        "passed":  passed,
        "floor":   floor,
        "checks":  checks,
        "reason":  reason,
    }
'''

# â”€â”€ gateway/layers/cascade.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/cascade.py"] = '''\
"""
Cascade (L5) â€” Â§5.2, Â§8 of spec.
Tries the cheap model (Haiku) first.
If quality score fails the floor, escalates to Sonnet.
Logs every escalation â€” this is how we learn which routes need Sonnet.
"""
import logging

from gateway.providers import bedrock as provider
from gateway.layers import quality as quality_scorer

log = logging.getLogger(__name__)

_HAIKU  = "anthropic.claude-3-5-haiku-20241022-v1:0"
_SONNET = "anthropic.claude-3-5-sonnet-20241022-v2:0"

async def run(
    intent: str,
    feature_class: str,
    prompt: str,
    context_tokens: int,
    force_model: str = None,   # pass _SONNET to skip cascade (stakes tripped)
) -> dict:
    """
    Returns {text, usage, quality, escalated, model_used}.
    escalated=True means Haiku failed and Sonnet was called.
    """
    if force_model:
        result = await provider.invoke(
            model_id=force_model,
            messages=[{"role": "user", "content": prompt}],
            context_tokens=context_tokens,
        )
        return {
            "text":      result["text"],
            "usage":     result["usage"],
            "quality":   {"score": None, "passed": True, "checks": [], "reason": "skipped_forced_model"},
            "escalated": False,
            "model_used": force_model,
        }

    # â”€â”€ Attempt 1: Haiku â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    haiku_result = await provider.invoke(
        model_id=_HAIKU,
        messages=[{"role": "user", "content": prompt}],
        context_tokens=context_tokens,
    )

    quality = quality_scorer.score(
        response_text=haiku_result["text"],
        intent=intent,
        feature_class=feature_class,
    )

    if quality["passed"]:
        log.info("cascade HAIKU_OK intent=%s score=%.3f", intent, quality["score"])
        return {
            "text":       haiku_result["text"],
            "usage":      haiku_result["usage"],
            "quality":    quality,
            "escalated":  False,
            "model_used": _HAIKU,
        }

    # â”€â”€ Attempt 2: Escalate to Sonnet â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    log.warning(
        "cascade ESCALATE intent=%s reason=%s",
        intent, quality["reason"]
    )

    sonnet_result = await provider.invoke(
        model_id=_SONNET,
        messages=[{"role": "user", "content": prompt}],
        context_tokens=context_tokens,
    )

    # Re-score Sonnet output (for telemetry â€” we accept it regardless)
    sonnet_quality = quality_scorer.score(
        response_text=sonnet_result["text"],
        intent=intent,
        feature_class=feature_class,
    )

    return {
        "text":       sonnet_result["text"],
        "usage":      sonnet_result["usage"],
        "quality":    sonnet_quality,
        "escalated":  True,
        "model_used": _SONNET,
    }
'''

# â”€â”€ gateway/pipeline.py (full replacement â€” cascade wired in) â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/pipeline.py"] = '''\
"""
CLEVER pipeline orchestrator (Â§5.2).
Step 6 state: ALL core layers real.
Classifier -> Stakes Gate -> Exact Cache -> Compressor -> Cascade -> Log
"""
import time
import logging

from gateway.models import RouteRequest, RouteResponse, AccountingResult, QualityResult
from gateway.layers import stakes_gate, cache, classifier, compressor, cascade
from gateway.telemetry import accounting
from gateway.telemetry import logger as telemetry

log = logging.getLogger(__name__)

_SONNET = "anthropic.claude-3-5-sonnet-20241022-v2:0"

async def route(req: RouteRequest, app_state) -> RouteResponse:
    start = time.time()
    trace = []

    # â”€â”€ Layer 1: Classifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    intent, confidence = classifier.classify(req)
    trace.append({
        "layer":      "classifier",
        "intent":     intent,
        "confidence": confidence,
        "method":     (
            "config"   if confidence == 1.0 else
            "keyword"  if confidence == 0.8 else
            "default"
        ),
    })

    # â”€â”€ Layer 2: Stakes Gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    stakes = stakes_gate.classify(req, intent)
    gate_entry = {
        "layer":  "stakes_gate",
        "result": "SUSPENDED" if stakes.suspend_optimization else "read",
    }
    if stakes.suspend_optimization:
        gate_entry.update({
            "reason":                stakes.reason,
            "min_model":             stakes.min_model,
            "require_human_confirm": stakes.require_human_confirm,
            "cache":                 "OFF",
        })
    trace.append(gate_entry)

    # â”€â”€ Layer 3: Exact cache (skip if stakes suspended) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not stakes.suspend_optimization and req.mode == "clever":
        cached = await cache.exact_get(app_state.redis, req)
        if cached:
            trace.append({"layer": "cache.exact", "result": "HIT", "saved": "~$0"})
            latency_ms = int((time.time() - start) * 1000)
            return RouteResponse(
                response=cached["response"],
                decision_trace=trace,
                accounting=AccountingResult(**cached["accounting"]),
                quality=QualityResult(checked=True, method="cache", score=1.0),
                latency_ms=latency_ms,
            )
    trace.append({
        "layer":  "cache.exact",
        "result": "OFF" if stakes.suspend_optimization else "miss",
    })

    # â”€â”€ Layer 4: Compressor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ctx = compressor.build_context(req, intent)
    trace.append({
        "layer":         "compressor",
        "fields_used":   ctx["fields_used"],
        "tokens_before": ctx["tokens_before"],
        "tokens_after":  ctx["tokens_after"],
        "reduction_pct": ctx["reduction_pct"],
    })

    # â”€â”€ Layer 5: Cascade (Haiku -> quality gate -> Sonnet) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    force = _SONNET if stakes.suspend_optimization else None
    result = await cascade.run(
        intent=intent,
        feature_class=req.feature_class,
        prompt=ctx["prompt"],
        context_tokens=ctx["tokens_after"],
        force_model=force,
    )

    q = result["quality"]
    trace.append({
        "layer":     "cascade",
        "model_tried": "claude-haiku" if not force else "claude-sonnet (forced)",
        "escalated": result["escalated"],
        "model_used": "claude-sonnet" if result["escalated"] or force else "claude-haiku",
        "quality": {
            "score":  q["score"],
            "passed": q["passed"],
            "reason": q["reason"],
        },
        "tokens_in":  result["usage"]["tokens_in"],
        "tokens_out": result["usage"]["tokens_out"],
    })

    # â”€â”€ Layer 6: Accounting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    acc = accounting.build_accounting(
        result["usage"],
        tokens_before=ctx["tokens_before"],
    )
    latency_ms = int((time.time() - start) * 1000)

    # â”€â”€ Layer 7: Log + cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    await telemetry.write_request_log(
        pool=app_state.pool,
        req=req,
        trace=trace,
        usage=result["usage"],
        accounting=acc,
        latency_ms=latency_ms,
        gate_fired=stakes.reason,
    )

    if not stakes.suspend_optimization and req.mode == "clever":
        await cache.exact_put(
            app_state.redis, req, result["text"], acc
        )

    # Build response text â€” prepend gate warning if stakes tripped
    response_text = result["text"]
    if stakes.suspend_optimization:
        response_text = (
            f"STAKES_GATE_TRIP â€” optimization suspended.\\n"
            f"Reason: {stakes.reason}\\n"
            f"Human confirmation required before any action fires.\\n\\n"
            + response_text
        )

    return RouteResponse(
        response=response_text,
        decision_trace=trace,
        accounting=AccountingResult(**acc),
        quality=QualityResult(
            checked=True,
            method="cascade",
            score=q["score"],
        ),
        latency_ms=latency_ms,
    )
'''

# â”€â”€ Write all files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for path, content in files.items():
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print(f"  created  {path}")

print("\nStep 6 files ready.")

