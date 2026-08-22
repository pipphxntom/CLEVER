"""Pre-LLM short-circuit: structured lookup, then FAQ, then templates."""
from __future__ import annotations

import logging

from gateway.layers.ras import faq_match, structured_lookup, structured_resolver, template_resolver

log = logging.getLogger(__name__)


async def attempt(req, pool, redis_client, trace: list, intent: str | None = None) -> dict | None:
    from gateway import catalog

    hint = structured_lookup.attempt(req.query, pool)
    if hint:
        answer = await structured_resolver.resolve(hint, pool)
        if answer:
            trace.append({
                "layer": "ras.structured_lookup",
                "result": "HIT",
                "entity": hint["entity_value"],
                "field": hint["field_ask"],
                "cost": 0,
            })
            log.info("short_circuit structured_lookup entity=%s", hint["entity_value"])
            return {"response": answer, "gate": "ras.structured_lookup"}
    trace.append({"layer": "ras.structured_lookup", "result": "miss"})

    if intent and catalog.is_generate_intent(intent):
        trace.append({"layer": "ras.faq", "result": "skip_generate_intent", "intent": intent})
    else:
        faq_hit = await faq_match.attempt(req.query, pool)
        if faq_hit:
            trace.append({
                "layer": "ras.faq",
                "result": "HIT",
                "score": round(faq_hit["score"], 3),
                "faq_id": faq_hit["faq_id"],
                "cost": 0,
            })
            log.info("short_circuit faq faq_id=%s", faq_hit["faq_id"])
            return {"response": faq_hit["response"], "gate": "ras.faq"}
        trace.append({"layer": "ras.faq", "result": "miss"})

    tmpl_hit = template_resolver.attempt(req.query)
    if tmpl_hit:
        trace.append({
            "layer": "ras.template",
            "result": "HIT",
            "resolver": tmpl_hit["resolver"][:40],
            "cost": 0,
        })
        log.info("short_circuit template")
        return {"response": tmpl_hit["response"], "gate": "ras.template"}
    trace.append({"layer": "ras.template", "result": "miss"})
    return None
