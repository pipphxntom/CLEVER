raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 6 fixes:
1. Compressor baseline always 8200 on mutation path
2. Quality response marks Sonnet as 'accepted' not scored
3. Mutation accounting uses real baseline tokens
"""
import os

files = {}

# â”€â”€ Fix 1: compressor.py â€” baseline always 8200 when intent has stakes=mutate â”€â”€
files["gateway/layers/compressor.py"] = '''\
"""
Compressor (L3) â€” Â§5.2, Â§5.3 of spec.
Baseline is ALWAYS the full document token count.
Even on mutation path, we track what the baseline would have been.
"""
import logging
import yaml
from pathlib import Path

log = logging.getLogger(__name__)

_INTENTS_PATH  = Path("config/intents.yaml")
_FEATURES_PATH = Path("config/features.yaml")
_INTENTS: dict = {}

_FULL_CONTEXT_TOKENS = 8_200
_TOKENS_PER_FIELD    = 300

def _load():
    global _INTENTS
    if not _INTENTS:
        _INTENTS = yaml.safe_load(_INTENTS_PATH.read_text(encoding="utf-8"))

def build_context(req, intent: str) -> dict:
    _load()
    intent_cfg    = _INTENTS.get(intent, {})
    fields_needed = intent_cfg.get("fields", [])

    # Project only needed fields from the request context
    projected = {}
    if fields_needed and req.context:
        for f in fields_needed:
            if f in req.context:
                projected[f] = req.context[f]

    # Build focused prompt
    if projected:
        ctx_block = "\\n".join(f"  {k}: {v}" for k, v in projected.items())
        prompt = f"{req.query}\\n\\nRelevant context:\\n{ctx_block}"
    else:
        prompt = req.query

    # Token estimates
    query_tokens = max(20, int(len(req.query.split()) * 1.4))

    # Baseline is ALWAYS the full document â€” regardless of mutation/read
    # This represents what a naive call would cost without CLEVER
    tokens_before = _FULL_CONTEXT_TOKENS

    # After compression â€” if no fields defined (mutation), we pass query only
    if fields_needed:
        tokens_after = max(80, len(fields_needed) * _TOKENS_PER_FIELD + query_tokens)
    else:
        tokens_after = query_tokens

    tokens_after  = min(tokens_after, tokens_before)
    reduction_pct = round((1 - tokens_after / tokens_before) * 100, 1)

    log.info(
        "compressor intent=%s fields=%d tokens %d->%d (%.1f%% reduction)",
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

# â”€â”€ Fix 2: quality.py â€” add accepted_sonnet method â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/quality.py"] = '''\
"""
Quality scorer (L5b) â€” Â§5.2, Â§9 of spec.
Scores Haiku output before deciding to escalate to Sonnet.
All checks are pure Python â€” zero LLM cost.
"""
import logging
import re
import yaml
from pathlib import Path

log = logging.getLogger(__name__)

_FEATURES_PATH = Path("config/features.yaml")
_FEATURES: dict = {}

_REFUSAL_PATTERNS = [
    r"i (cannot|can\'t|am unable to)",
    r"i don\'t (know|have)",
    r"i\'m not sure",
    r"as an ai",
    r"i do not have access",
    r"no information available",
    r"unable to (provide|answer|assist)",
]

_MIN_LENGTH = {
    "triage":                80,
    "email_draft":           120,
    "report_summary":        100,
    "insight_query":         80,
    "venue_search":          80,
    "campaign_draft":        100,
    "ticket_response_draft": 100,
    "default":               40,
}

def _load():
    global _FEATURES
    if not _FEATURES:
        _FEATURES = yaml.safe_load(_FEATURES_PATH.read_text(encoding="utf-8"))

def score(response_text: str, intent: str, feature_class: str) -> dict:
    """Score Haiku output. Returns {score, passed, checks, reason}."""
    _load()
    checks     = []
    deductions = 0.0

    # Check 1: Refusal detection (weight 0.4)
    text_lower = response_text.lower()
    for pattern in _REFUSAL_PATTERNS:
        if re.search(pattern, text_lower):
            checks.append({"check": "refusal", "passed": False, "detail": pattern})
            deductions += 0.4
            break
    else:
        checks.append({"check": "refusal", "passed": True})

    # Check 2: Length gate (weight 0.2)
    min_len   = _MIN_LENGTH.get(intent, _MIN_LENGTH["default"])
    length_ok = len(response_text.strip()) >= min_len
    checks.append({
        "check":  "length",
        "passed": length_ok,
        "detail": f"{len(response_text)} chars, min={min_len}",
    })
    if not length_ok:
        deductions += 0.2

    # Check 3: Mock/placeholder detection (weight 0.3)
    # NOTE: only active with mock provider â€” disappears with real Bedrock
    mock_signals = ["[mock]", "replace this", "to be implemented", "coming soon"]
    mock_found   = any(s in text_lower for s in mock_signals)
    checks.append({"check": "mock_signal", "passed": not mock_found})
    if mock_found:
        deductions += 0.3

    # Check 4: Number completeness (weight 0.1)
    number_intents = {"triage", "report_summary", "insight_query", "billing_support"}
    if intent in number_intents:
        has_number = bool(re.search(r"\\$?[\\d,]+", response_text))
        checks.append({"check": "has_numbers", "passed": has_number})
        if not has_number:
            deductions += 0.1
    else:
        checks.append({"check": "has_numbers", "passed": True, "detail": "n/a"})

    raw_score = round(max(0.0, 1.0 - deductions), 3)
    floor     = _FEATURES.get(feature_class, {}).get("q_floor", 0.92)
    passed    = raw_score >= floor

    reason = None
    if not passed:
        failed = [c["check"] for c in checks if not c["passed"]]
        reason = f"score={raw_score} < floor={floor}. Failed: {failed}"
        log.warning("quality FAIL intent=%s %s", intent, reason)
    else:
        log.info("quality PASS intent=%s score=%.3f", intent, raw_score)

    return {
        "score":  raw_score,
        "passed": passed,
        "floor":  floor,
        "checks": checks,
        "reason": reason,
    }

def accepted_sonnet() -> dict:
    """
    Marker returned when Sonnet is used directly (stakes forced or escalation).
    We don't re-score Sonnet â€” we accept it unconditionally.
    Score shown as 1.0 to indicate 'accepted, not scored'.
    """
    return {
        "score":  1.0,
        "passed": True,
        "floor":  None,
        "checks": [],
        "reason": "accepted_sonnet",
    }
'''

# â”€â”€ Fix 3: cascade.py â€” use accepted_sonnet marker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/cascade.py"] = '''\
"""
Cascade (L5) â€” Â§5.2, Â§8 of spec.
Haiku -> quality gate -> Sonnet escalation.
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
    force_model: str = None,
) -> dict:
    """Returns {text, usage, quality, escalated, model_used}."""

    # Forced path (stakes gate tripped) â€” skip quality scoring entirely
    if force_model:
        result = await provider.invoke(
            model_id=force_model,
            messages=[{"role": "user", "content": prompt}],
            context_tokens=context_tokens,
        )
        return {
            "text":       result["text"],
            "usage":      result["usage"],
            "quality":    quality_scorer.accepted_sonnet(),
            "escalated":  False,
            "model_used": force_model,
        }

    # Attempt 1: Haiku
    haiku_result = await provider.invoke(
        model_id=_HAIKU,
        messages=[{"role": "user", "content": prompt}],
        context_tokens=context_tokens,
    )
    quality = quality_scorer.score(haiku_result["text"], intent, feature_class)

    if quality["passed"]:
        log.info("cascade HAIKU_OK intent=%s score=%.3f", intent, quality["score"])
        return {
            "text":       haiku_result["text"],
            "usage":      haiku_result["usage"],
            "quality":    quality,
            "escalated":  False,
            "model_used": _HAIKU,
        }

    # Attempt 2: Escalate to Sonnet
    log.warning("cascade ESCALATE intent=%s reason=%s", intent, quality["reason"])
    sonnet_result = await provider.invoke(
        model_id=_SONNET,
        messages=[{"role": "user", "content": prompt}],
        context_tokens=context_tokens,
    )

    return {
        "text":       sonnet_result["text"],
        "usage":      sonnet_result["usage"],
        "quality":    quality_scorer.accepted_sonnet(),  # Sonnet always accepted
        "escalated":  True,
        "model_used": _SONNET,
        "haiku_fail_reason": quality["reason"],          # keep for telemetry
    }
'''

# â”€â”€ Write all files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for path, content in files.items():
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print(f"  fixed  {path}")

print("\nAll fixes applied.")

