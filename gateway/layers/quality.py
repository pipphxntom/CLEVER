"""Cheap-tier output checks. Strong-tier answers are unscored, not pretended 1.0."""
from __future__ import annotations

import logging
import re

from gateway import catalog

log = logging.getLogger(__name__)

_REFUSAL_PATTERNS = [
    r"i (cannot|can't|am unable to)",
    r"i don't (know|have)",
    r"i'm not sure",
    r"as an ai",
    r"i do not have access",
    r"no information available",
    r"unable to (provide|answer|assist)",
]

_MIN_LENGTH = {
    "triage": 80,
    "email_draft": 120,
    "report_summary": 100,
    "insight_query": 80,
    "venue_search": 80,
    "campaign_draft": 100,
    "ticket_response_draft": 100,
    "default": 40,
}


def score(response_text: str, intent: str, feature_class: str, context: dict | None = None) -> dict:
    checks = []
    deductions = 0.0
    text_lower = (response_text or "").lower()

    refused = False
    for pattern in _REFUSAL_PATTERNS:
        if re.search(pattern, text_lower):
            checks.append({"check": "refusal", "passed": False, "detail": pattern})
            deductions += 0.4
            refused = True
            break
    if not refused:
        checks.append({"check": "refusal", "passed": True})

    min_len = _MIN_LENGTH.get(intent, _MIN_LENGTH["default"])
    length_ok = len((response_text or "").strip()) >= min_len
    checks.append({
        "check": "length",
        "passed": length_ok,
        "detail": f"{len(response_text or '')} chars, min={min_len}",
    })
    if not length_ok:
        deductions += 0.2

    number_intents = {"triage", "report_summary", "insight_query"}
    if intent in number_intents:
        has_number = bool(re.search(r"\$?[\d,]+", response_text or ""))
        checks.append({"check": "has_numbers", "passed": has_number})
        if not has_number:
            deductions += 0.1
    else:
        checks.append({"check": "has_numbers", "passed": True, "detail": "n/a"})

    if context:
        grounded = _grounded(response_text or "", context)
        checks.append({"check": "grounded", "passed": grounded})
        if not grounded:
            deductions += 0.2
        fields_ok, missing = _required_fields_present(response_text or "", context)
        checks.append({"check": "required_fields", "passed": fields_ok, "detail": missing or "ok"})
        if not fields_ok:
            deductions += 0.25
    else:
        checks.append({"check": "grounded", "passed": True, "detail": "no_context"})
        checks.append({"check": "required_fields", "passed": True, "detail": "no_context"})

    raw_score = round(max(0.0, 1.0 - deductions), 3)
    floor = catalog.q_floor(feature_class)
    passed = raw_score >= floor
    reason = None
    if not passed:
        failed = [c["check"] for c in checks if not c["passed"]]
        reason = f"score={raw_score} < floor={floor}. Failed: {failed}"
        log.warning("quality FAIL intent=%s %s", intent, reason)
    else:
        log.info("quality PASS intent=%s score=%.3f", intent, raw_score)

    return {
        "score": raw_score,
        "passed": passed,
        "floor": floor,
        "checks": checks,
        "reason": reason,
        "method": "heuristic",
    }


def unchecked_strong() -> dict:
    return {
        "score": None,
        "passed": True,
        "floor": None,
        "checks": [],
        "reason": "unchecked_strong",
        "method": "unchecked_strong",
    }


def _canonical_amount(s: str) -> str:
    cleaned = str(s).replace(",", "").replace("$", "").strip()
    try:
        return str(int(round(float(cleaned))))
    except ValueError:
        digits = re.sub(r"\D", "", str(s))
        return digits.lstrip("0") or "0"


def _grounded(text: str, context: dict) -> bool:
    """Cited $ amounts must match context numbers, ignoring commas and cents."""
    amounts = re.findall(r"\$[\d,]+(?:\.\d{2})?", text)
    if not amounts:
        return True
    ctx_vals = [_canonical_amount(v) for v in context.values()]
    ctx_vals += re.findall(r"\d+", " ".join(str(v) for v in context.values()))
    allowed = set(ctx_vals)
    for amt in amounts:
        if _canonical_amount(amt) not in allowed:
            return False
    return True


def _required_fields_present(text: str, context: dict) -> tuple[bool, list[str]]:
    """Identifiers supplied in context must appear in the answer (case-insensitive)."""
    blob = (text or "").lower()
    missing: list[str] = []
    for key in ("account", "account_id", "contact"):
        val = context.get(key)
        if val is None or val == "" or val == []:
            continue
        token = str(val).strip()
        if len(token) < 2:
            continue
        if token.lower() not in blob:
            missing.append(key)
    inv = context.get("invoice_ids")
    if isinstance(inv, list) and inv:
        if not any(str(i).lower() in blob for i in inv if i):
            missing.append("invoice_ids")
    elif isinstance(inv, str) and inv.strip():
        if inv.lower() not in blob:
            missing.append("invoice_ids")
    bal = context.get("balance")
    if bal is not None and str(bal) != "":
        want = _canonical_amount(bal)
        cited = [_canonical_amount(x) for x in re.findall(r"\$?[\d,]+(?:\.\d{2})?", text)]
        cited += re.findall(r"\d+", text)
        if want not in set(cited):
            missing.append("balance")
    return (len(missing) == 0), missing


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
