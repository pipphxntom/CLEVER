"""Value-per-token using assumed YAML dollars. NULL when no tokens were used."""
from __future__ import annotations

import logging

from gateway import catalog

log = logging.getLogger(__name__)


def compute(intent: str, tokens_total: int, outcome_count: int = 1) -> dict:
    cfg = catalog.vpt_outcomes().get(intent, {"unit": "calls", "assumed_value_usd": 0.10})
    value = float(cfg.get("assumed_value_usd", cfg.get("default_value_usd", 0.10))) * outcome_count
    if tokens_total <= 0:
        return {
            "vpt": None,
            "outcome_unit": cfg.get("unit", "calls"),
            "outcome_value_usd": round(value, 4),
            "total_tokens": 0,
        }
    vpt = round(value / tokens_total * 1000, 6)
    log.info("vpt intent=%s tokens=%d assumed=%.2f vpt=%.4f", intent, tokens_total, value, vpt)
    return {
        "vpt": vpt,
        "outcome_unit": cfg.get("unit", "calls"),
        "outcome_value_usd": round(value, 4),
        "total_tokens": tokens_total,
    }
