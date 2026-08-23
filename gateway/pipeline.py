"""CLEVER pipeline. Every exit is logged. Mutate does not call a model without confirm_token."""
from __future__ import annotations

import logging
import time
import uuid

from gateway.layers import cache, cascade, classifier, compressor, myelination, ras_gate, stakes_gate
from gateway.layers import semantic as semantic_cache
from gateway.models import AccountingResult, QualityResult, RouteRequest, RouteResponse
from gateway.telemetry import accounting, vpt as vpt_calc
from gateway.telemetry import logger as telemetry
from gateway.telemetry.logger import LogRecord
from gateway.config import settings

log = logging.getLogger(__name__)


async def route(req: RouteRequest, app_state) -> RouteResponse:
    start = time.time()
    request_id = str(uuid.uuid4())
    trace: list = [{"layer": "request", "request_id": request_id, "mode": req.mode}]

    intent, confidence, method = classifier.classify(req)
    trace.append({
        "layer": "classifier",
        "intent": intent,
        "confidence": confidence,
        "method": method,
    })

    ctx = compressor.build_context(req, intent)
    fields_needed = ctx["fields_needed"]

    stakes = stakes_gate.classify(req, intent)
    gate_entry = {
        "layer": "stakes_gate",
        "result": "SUSPENDED" if stakes.suspend_optimization else "read",
    }
    if stakes.suspend_optimization:
        gate_entry.update({
            "reason": stakes.reason,
            "min_tier": stakes.min_tier,
            "require_human_confirm": stakes.require_human_confirm,
            "cache": "OFF",
        })
    trace.append(gate_entry)

    if req.mode == "baseline":
        return await _baseline(req, app_state, request_id, intent, confidence, ctx, trace, start)

    if stakes.suspend_optimization and stakes.require_human_confirm:
        ok = await _confirm_ok(app_state.redis, req.confirm_token, intent)
        if not ok:
            cid = await _issue_confirm(app_state.redis, intent, request_id)
            acc = accounting.build_zero_cost_accounting(ctx["tokens_before"], intent)
            latency_ms = int((time.time() - start) * 1000)
            vpt = vpt_calc.compute(intent, 0, req.outcome_count)
            await _log(app_state.pool, LogRecord(
                request_id=request_id, req=req, intent=intent, trace=trace,
                usage_legs=[], accounting=acc, latency_ms=latency_ms,
                stakes_reason=stakes.reason, model_used="none",
                vpt=vpt["vpt"], outcome_unit=vpt["outcome_unit"],
                outcome_value_usd=vpt["outcome_value_usd"],
            ))
            return RouteResponse(
                request_id=request_id,
                status="pending_confirmation",
                confirmation_id=cid,
                response=(
                    "This intent is classified as a mutation. "
                    "Resubmit with confirm_token to proceed. No model was called."
                ),
                decision_trace=trace,
                accounting=AccountingResult(**_acc_fields(acc)),
                quality=QualityResult(checked=False, method="stakes_pending"),
                latency_ms=latency_ms,
                intent=intent,
                model_tier=None,
            )

    if not stakes.suspend_optimization:
        ras_result = await ras_gate.attempt(
            req, app_state.pool, app_state.redis, trace, intent=intent
        )
        if ras_result:
            acc = accounting.build_zero_cost_accounting(ctx["tokens_before"], intent)
            acc["cache_hit"] = False
            latency_ms = int((time.time() - start) * 1000)
            vpt = vpt_calc.compute(intent, 0, req.outcome_count)
            await _log(app_state.pool, LogRecord(
                request_id=request_id, req=req, intent=intent, trace=trace,
                usage_legs=[], accounting=acc, latency_ms=latency_ms,
                ras_gate=ras_result["gate"], model_used="none",
                vpt=vpt["vpt"], outcome_unit=vpt["outcome_unit"],
                outcome_value_usd=vpt["outcome_value_usd"],
            ))
            return RouteResponse(
                request_id=request_id,
                status="ok",
                response=ras_result["response"],
                decision_trace=trace,
                accounting=AccountingResult(**_acc_fields(acc)),
                quality=QualityResult(checked=False, method="ras"),
                latency_ms=latency_ms,
                intent=intent,
                model_tier=None,
            )

        cached = await cache.exact_get(app_state.redis, req, intent, fields_needed)
        if cached:
            trace.append({"layer": "cache.exact", "result": "HIT"})
            acc = accounting.cache_hit_accounting(cached.get("baseline_cost_usd") or 0)
            latency_ms = int((time.time() - start) * 1000)
            vpt = vpt_calc.compute(intent, 0, req.outcome_count)
            await _log(app_state.pool, LogRecord(
                request_id=request_id, req=req, intent=intent, trace=trace,
                usage_legs=[], accounting=acc, latency_ms=latency_ms,
                cache_hit=True, model_used="cache",
                vpt=vpt["vpt"], outcome_unit=vpt["outcome_unit"],
                outcome_value_usd=vpt["outcome_value_usd"],
            ))
            return RouteResponse(
                request_id=request_id,
                status="ok",
                response=cached["response"],
                decision_trace=trace,
                accounting=AccountingResult(**_acc_fields(acc)),
                quality=QualityResult(checked=True, method="cache", score=None),
                latency_ms=latency_ms,
                intent=intent,
                model_tier=None,
            )
        trace.append({"layer": "cache.exact", "result": "miss"})
        sem = await semantic_cache.semantic_get(
            app_state.pool, req, intent, fields_needed
        )
        if sem:
            trace.append({
                "layer": "cache.semantic",
                "result": "HIT",
                "score": round(sem.get("score") or 0, 3),
            })
            acc = accounting.cache_hit_accounting(sem.get("baseline_cost_usd") or 0)
            latency_ms = int((time.time() - start) * 1000)
            vpt = vpt_calc.compute(intent, 0, req.outcome_count)
            await _log(app_state.pool, LogRecord(
                request_id=request_id, req=req, intent=intent, trace=trace,
                usage_legs=[], accounting=acc, latency_ms=latency_ms,
                cache_hit=True, model_used="cache.semantic",
                vpt=vpt["vpt"], outcome_unit=vpt["outcome_unit"],
                outcome_value_usd=vpt["outcome_value_usd"],
            ))
            return RouteResponse(
                request_id=request_id,
                status="ok",
                response=sem["response"],
                decision_trace=trace,
                accounting=AccountingResult(**_acc_fields(acc)),
                quality=QualityResult(checked=True, method="cache.semantic", score=sem.get("score")),
                latency_ms=latency_ms,
                intent=intent,
                model_tier=None,
            )
        trace.append({"layer": "cache.semantic", "result": "miss"})
    else:
        trace.append({"layer": "cache.exact", "result": "OFF"})
        trace.append({"layer": "cache.semantic", "result": "OFF"})

    route_class = myelination.route_class_from(intent, confidence)
    myelin = await myelination.check(route_class, req.feature_class, app_state.pool)
    trace.append({
        "layer": "myelination",
        "route_class": route_class,
        "phase": myelin.phase,
        "p_hat": myelin.p_hat,
        "n_obs": myelin.n_obs,
        "lcb": myelin.lcb,
        "credible": myelin.credible,
        "decision": myelin.decision,
        "alpha": myelin.alpha,
        "beta": myelin.beta,
        "thompson_sample": myelin.thompson_sample,
        "tau": myelin.tau,
    })

    force_strong = stakes.suspend_optimization or (not myelin.eligible)
    router_reason = (
        "stakes_gate_forced" if stakes.suspend_optimization
        else f"myelination_{myelin.decision}"
    )
    trace.append({
        "layer": "router",
        "tier": "strong" if force_strong else "cheap",
        "reason": router_reason,
    })

    trace.append({
        "layer": "compressor",
        "fields_used": ctx["fields_used"],
        "tokens_before": ctx["tokens_before"],
        "tokens_after": ctx["tokens_after"],
        "reduction_pct": ctx["reduction_pct"],
    })

    result = await cascade.run(
        provider=app_state.provider,
        intent=intent,
        feature_class=req.feature_class,
        prompt=ctx["prompt"],
        force_strong=force_strong,
        context=req.context or {},
    )
    q = result["quality"]
    trace.append({
        "layer": "cascade",
        "cheap_tried": result["cheap_tried"],
        "escalated": result["escalated"],
        "tier_used": result["tier_used"],
        "forced": result["forced"],
        "quality": {
            "score": q.get("score"),
            "passed": q.get("passed"),
            "method": q.get("method"),
            "reason": q.get("reason"),
        },
        "legs": result["legs"],
    })

    acc = accounting.build_accounting(result["legs"], tokens_before=ctx["tokens_before"])
    total_tokens = acc["tokens_in"] + acc["tokens_out"]
    vpt = vpt_calc.compute(intent, total_tokens, req.outcome_count)
    acc["vpt"] = vpt["vpt"]
    acc["outcome_unit"] = vpt["outcome_unit"]
    acc["outcome_value_usd"] = vpt["outcome_value_usd"]
    latency_ms = int((time.time() - start) * 1000)

    last_leg = result["legs"][-1] if result["legs"] else {}
    await _log(app_state.pool, LogRecord(
        request_id=request_id, req=req, intent=intent, trace=trace,
        usage_legs=result["legs"], accounting=acc, latency_ms=latency_ms,
        route_class=route_class,
        stakes_reason=stakes.reason,
        quality_score=q.get("score"),
        model_used=last_leg.get("model_id") or result["tier_used"],
        vpt=vpt["vpt"], outcome_unit=vpt["outcome_unit"],
        outcome_value_usd=vpt["outcome_value_usd"],
    ))

    cheap_success = result["cheap_tried"] and (not result["escalated"])
    severity = "wrong" if (result["cheap_tried"] and result["escalated"]) else "none"
    if not stakes.suspend_optimization:
        await myelination.update(
            route_class,
            cheap_tried=result["cheap_tried"],
            success=cheap_success,
            severity=severity,
            pool=app_state.pool,
            count_strong_obs=not result["cheap_tried"],
        )

    if not stakes.suspend_optimization and req.mode == "clever" and q.get("passed"):
        await cache.exact_put(
            app_state.redis, req, intent, fields_needed, result["text"],
            baseline_cost_usd=acc["baseline_cost_usd"],
            original_cost_usd=acc["cost_usd"],
            original_model=last_leg.get("model_id") or "",
        )
        await semantic_cache.semantic_put(
            app_state.pool, req, intent, fields_needed,
            result["text"], acc["baseline_cost_usd"],
        )

    return RouteResponse(
        request_id=request_id,
        status="ok",
        response=result["text"],
        decision_trace=trace,
        accounting=AccountingResult(**_acc_fields(acc)),
        quality=QualityResult(
            checked=q.get("method") != "unchecked_strong",
            method=q.get("method") or "cascade",
            score=q.get("score"),
            passed=q.get("passed"),
            reason=q.get("reason"),
        ),
        latency_ms=latency_ms,
        intent=intent,
        model_tier=result["tier_used"],
    )


async def _baseline(req, app_state, request_id, intent, confidence, ctx, trace, start):
    trace.append({"layer": "baseline", "result": "strong_uncompressed"})
    result = await cascade.run(
        provider=app_state.provider,
        intent=intent,
        feature_class=req.feature_class,
        prompt=ctx["uncompressed_prompt"],
        force_strong=True,
        context=req.context or {},
    )
    acc = accounting.build_accounting(result["legs"], tokens_before=ctx["tokens_before"])
    # baseline mode: actual should equal baseline (strong on uncompressed)
    latency_ms = int((time.time() - start) * 1000)
    vpt = vpt_calc.compute(intent, acc["tokens_in"] + acc["tokens_out"], req.outcome_count)
    last_leg = result["legs"][-1] if result["legs"] else {}
    await _log(app_state.pool, LogRecord(
        request_id=request_id, req=req, intent=intent, trace=trace,
        usage_legs=result["legs"], accounting=acc, latency_ms=latency_ms,
        model_used=last_leg.get("model_id") or "strong",
        vpt=vpt["vpt"], outcome_unit=vpt["outcome_unit"],
        outcome_value_usd=vpt["outcome_value_usd"],
    ))
    q = result["quality"]
    return RouteResponse(
        request_id=request_id,
        status="ok",
        response=result["text"],
        decision_trace=trace,
        accounting=AccountingResult(**_acc_fields(acc)),
        quality=QualityResult(
            checked=False, method=q.get("method") or "unchecked_strong",
            score=q.get("score"),
        ),
        latency_ms=latency_ms,
        intent=intent,
        model_tier="strong",
    )


def _acc_fields(acc: dict) -> dict:
    return {
        "tokens_in": acc["tokens_in"],
        "tokens_out": acc["tokens_out"],
        "cost_usd": acc["cost_usd"],
        "baseline_cost_usd": acc["baseline_cost_usd"],
        "saved_usd": acc["saved_usd"],
        "saved_pct": acc["saved_pct"],
        "cache_hit": acc.get("cache_hit", False),
        "baseline_method": acc.get("baseline_method", "uncompressed_prompt_strong_tier"),
    }


async def _log(pool, rec: LogRecord) -> None:
    await telemetry.write_request_log(pool, rec)


async def _issue_confirm(redis, intent: str, request_id: str) -> str:
    cid = str(uuid.uuid4())
    if redis is None:
        return cid
    import json
    payload = json.dumps({"intent": intent, "request_id": request_id})
    try:
        await redis.setex(f"confirm:{cid}", settings.CONFIRM_TTL_S, payload)
    except Exception as exc:
        log.warning("confirm token store failed: %s", exc)
    return cid


async def _confirm_ok(redis, token: str | None, intent: str) -> bool:
    if not token:
        return False
    if redis is None:
        return False
    try:
        key = f"confirm:{token}"
        raw = await redis.get(key)
        if not raw:
            return False
        await redis.delete(key)
        return True
    except Exception as exc:
        log.warning("confirm token check failed: %s", exc)
        return False
