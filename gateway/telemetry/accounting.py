"""Cost vs baseline. Actual = sum of provider legs. Baseline = uncompressed prompt at strong tier."""
from __future__ import annotations

from gateway import catalog

_OUT_ESTIMATE = {"triage": 150, "email_draft": 220, "default": 180}


def cost_of(tokens_in: int, tokens_out: int, tier: str) -> float:
    table = catalog.pricing()
    rates = table.get(tier) or table["strong"]
    return (tokens_in * float(rates["in"]) + tokens_out * float(rates["out"])) / 1_000_000


def build_accounting(legs: list[dict], tokens_before: int) -> dict:
    tokens_in = sum(int(l.get("tokens_in") or 0) for l in legs)
    tokens_out = sum(int(l.get("tokens_out") or 0) for l in legs)
    actual = sum(
        cost_of(int(l.get("tokens_in") or 0), int(l.get("tokens_out") or 0), l.get("tier") or "strong")
        for l in legs
    )
    baseline = cost_of(tokens_before, tokens_out, "strong")
    saved = baseline - actual
    saved_pct = round((saved / baseline) * 100, 1) if baseline > 0 else 0.0
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(actual, 6),
        "baseline_cost_usd": round(baseline, 6),
        "saved_usd": round(saved, 6),
        "saved_pct": saved_pct,
        "cache_hit": False,
        "baseline_method": "uncompressed_prompt_strong_tier",
        "usage_legs": legs,
    }


def build_zero_cost_accounting(tokens_before: int, intent: str = "triage") -> dict:
    est_out = _OUT_ESTIMATE.get(intent, _OUT_ESTIMATE["default"])
    baseline = cost_of(tokens_before, est_out, "strong")
    return {
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "baseline_cost_usd": round(baseline, 6),
        "saved_usd": round(baseline, 6),
        "saved_pct": 100.0 if baseline > 0 else 0.0,
        "cache_hit": False,
        "baseline_method": "uncompressed_prompt_strong_tier",
        "usage_legs": [],
    }


def cache_hit_accounting(baseline_cost_usd: float) -> dict:
    base = float(baseline_cost_usd or 0)
    return {
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "baseline_cost_usd": round(base, 6),
        "saved_usd": round(base, 6),
        "saved_pct": 100.0 if base > 0 else 0.0,
        "cache_hit": True,
        "baseline_method": "uncompressed_prompt_strong_tier",
        "usage_legs": [],
    }
