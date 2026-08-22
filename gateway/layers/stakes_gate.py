"""Stakes policy is YAML. Mutate requires a confirm token before any model call."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from gateway import catalog

log = logging.getLogger(__name__)


@dataclass
class StakesResult:
    suspend_optimization: bool
    min_tier: str
    require_fresh: bool
    require_human_confirm: bool
    reason: Optional[str]


def classify(req, intent: str) -> StakesResult:
    if req.stakes == "mutate":
        return _trip("explicit_mutate_flag")

    feat = catalog.feature_cfg(req.feature_class)
    if feat.get("stakes") == "mutate":
        return _trip(f"high_stakes_class:{req.feature_class}")

    icfg = catalog.intent_cfg(intent)
    if icfg.get("stakes") == "mutate":
        return _trip(f"mutate_intent:{intent}")

    return StakesResult(
        suspend_optimization=False,
        min_tier="cheap",
        require_fresh=False,
        require_human_confirm=False,
        reason=None,
    )


def _trip(reason: str) -> StakesResult:
    log.warning("STAKES_GATE_TRIP reason=%s", reason)
    return StakesResult(
        suspend_optimization=True,
        min_tier="strong",
        require_fresh=True,
        require_human_confirm=True,
        reason=reason,
    )
