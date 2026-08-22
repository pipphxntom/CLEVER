"""Single load of YAML catalogs. Paths are package-root relative, not CWD."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _ROOT / "config"

_INTENTS: dict[str, Any] = {}
_FEATURES: dict[str, Any] = {}
_PRICING: dict[str, Any] = {}
_VPT: dict[str, Any] = {}


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def reload() -> None:
    global _INTENTS, _FEATURES, _PRICING, _VPT
    _INTENTS = _load_yaml(_CONFIG / "intents.yaml")
    _FEATURES = _load_yaml(_CONFIG / "features.yaml")
    _PRICING = _load_yaml(_CONFIG / "pricing.yaml")
    _VPT = _load_yaml(_CONFIG / "vpt_outcomes.yaml")


def _ensure() -> None:
    if not _INTENTS:
        reload()


def intents() -> dict[str, Any]:
    _ensure()
    return _INTENTS


def features() -> dict[str, Any]:
    _ensure()
    return _FEATURES


def pricing() -> dict[str, Any]:
    _ensure()
    return _PRICING


def vpt_outcomes() -> dict[str, Any]:
    _ensure()
    return _VPT


def intent_cfg(name: str) -> dict[str, Any]:
    return intents().get(name, {})


def feature_cfg(name: str) -> dict[str, Any]:
    return features().get(name, {})


def mutate_intents() -> set[str]:
    return {k for k, v in intents().items() if v.get("stakes") == "mutate"}


def q_floor(feature_class: str) -> float:
    return float(feature_cfg(feature_class).get("q_floor", 0.92))


def known_feature_class(name: str) -> bool:
    return name in features()


def known_intent(name: str) -> bool:
    return name in intents()


# Generate-class intents must not be answered by FAQ.
GENERATE_INTENTS = {
    "email_draft", "campaign_draft", "rfp_draft", "ticket_response_draft",
    "notes", "report_summary", "insight_query", "event_summary",
}


def is_generate_intent(name: str) -> bool:
    return name in GENERATE_INTENTS
