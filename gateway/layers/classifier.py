"""Intent classification. YAML is the source of truth. Mutate keywords fail closed."""
from __future__ import annotations

import logging

from gateway import catalog

log = logging.getLogger(__name__)


def classify(req) -> tuple[str, float, str]:
    """Returns (intent, confidence, method)."""
    q = req.query.lower()
    mutate = catalog.mutate_intents()
    intents = catalog.intents()

    mutate_hit = _first_keyword_match(q, {k: intents[k] for k in mutate if k in intents})
    if mutate_hit:
        log.info("classifier method=keyword_mutate intent=%s", mutate_hit)
        return mutate_hit, 0.8, "keyword_mutate"

    if req.intent_hint and catalog.known_intent(req.intent_hint):
        if req.intent_hint in mutate:
            log.info("classifier method=hint_mutate intent=%s", req.intent_hint)
            return req.intent_hint, 1.0, "config"
        log.info("classifier method=config_lookup intent=%s", req.intent_hint)
        return req.intent_hint, 1.0, "config"

    read_intents = {k: v for k, v in intents.items() if k not in mutate}
    kw_hit = _first_keyword_match(q, read_intents)
    if kw_hit:
        log.info("classifier method=keyword_match intent=%s", kw_hit)
        return kw_hit, 0.8, "keyword"

    feat = catalog.feature_cfg(req.feature_class)
    default = feat.get("default_intent", "triage")
    if not catalog.known_intent(default):
        default = "triage"
    log.info("classifier method=default intent=%s", default)
    return default, 0.5, "default"


def _first_keyword_match(q: str, subset: dict) -> str | None:
    for intent, cfg in subset.items():
        for kw in cfg.get("keywords") or []:
            if kw.lower() in q:
                return intent
    return None
