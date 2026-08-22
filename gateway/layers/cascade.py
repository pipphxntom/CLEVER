"""Cheap tier first, escalate to strong if quality fails. Strong is also scored. Both legs billed."""
from __future__ import annotations

import logging

from gateway.layers import quality as quality_scorer
from gateway.providers.base import Completion

log = logging.getLogger(__name__)


async def run(
    *,
    provider,
    intent: str,
    feature_class: str,
    prompt: str,
    force_strong: bool,
    context: dict | None = None,
) -> dict:
    messages = [{"role": "user", "content": prompt}]

    if force_strong:
        result = await provider.complete(tier="strong", messages=messages)
        quality = quality_scorer.score(result.text, intent, feature_class, context)
        quality["method"] = "heuristic_strong"
        return {
            "text": result.text,
            "legs": [_leg(result)],
            "quality": quality,
            "escalated": False,
            "cheap_tried": False,
            "tier_used": "strong",
            "forced": True,
        }

    cheap = await provider.complete(tier="cheap", messages=messages)
    quality = quality_scorer.score(cheap.text, intent, feature_class, context)
    if quality["passed"]:
        log.info("cascade CHEAP_OK intent=%s score=%s", intent, quality["score"])
        return {
            "text": cheap.text,
            "legs": [_leg(cheap)],
            "quality": quality,
            "escalated": False,
            "cheap_tried": True,
            "tier_used": "cheap",
            "forced": False,
        }

    log.warning("cascade ESCALATE intent=%s reason=%s", intent, quality["reason"])
    strong = await provider.complete(tier="strong", messages=messages)
    sq = quality_scorer.score(strong.text, intent, feature_class, context)
    sq["method"] = "heuristic_strong"
    return {
        "text": strong.text,
        "legs": [_leg(cheap), _leg(strong)],
        "quality": sq,
        "escalated": True,
        "cheap_tried": True,
        "tier_used": "strong",
        "forced": False,
        "cheap_fail_reason": quality["reason"],
        "cheap_quality": quality,
    }


def _leg(c: Completion) -> dict:
    return {
        "tier": c.tier,
        "model_id": c.model_id,
        "tokens_in": c.tokens_in,
        "tokens_out": c.tokens_out,
        "latency_ms": c.latency_ms,
    }
