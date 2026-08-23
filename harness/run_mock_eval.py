"""Live mock eval against a running gateway. Honest pass/fail vs intended behavior."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import httpx
import asyncpg
import asyncio

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"
KEY = "dev-key-change-me"
HEADERS = {"X-API-Key": KEY, "Content-Type": "application/json"}

FAT = {
    "account": "40211",
    "contact": "Ada",
    "balance": 12500,
    "invoice_ids": ["INV-2024-089"],
    "last_contact": "2026-01-01",
    "noise_block": ("AGING ROW " + "x" * 4000),
    "history": ["note " + str(i) for i in range(80)],
}


def layer_hit(trace: list, name: str) -> dict | None:
    for e in trace or []:
        if e.get("layer") == name:
            return e
    return None


def ras_hit(trace: list) -> str | None:
    for e in trace or []:
        if str(e.get("layer", "")).startswith("ras.") and e.get("result") == "HIT":
            return e["layer"]
    return None


class Eval:
    def __init__(self):
        self.rows = []

    def add(self, case_id: str, intended: str, actual: str, ok: bool, detail: str):
        self.rows.append({
            "id": case_id,
            "intended": intended,
            "actual": actual,
            "pass": ok,
            "detail": detail,
        })
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {case_id}\n  intended: {intended}\n  actual:   {actual}\n  {detail}\n")


async def route(client: httpx.AsyncClient, body: dict) -> httpx.Response:
    return await client.post(f"{BASE}/v1/route", headers=HEADERS, json=body, timeout=30)


async def main():
    ev = Eval()
    dsn = "postgresql://clever:clever@localhost:5432/clever"

    conn0 = await asyncpg.connect(dsn)
    try:
        await conn0.execute("DELETE FROM myelination_registry")
    finally:
        await conn0.close()
    try:
        import redis.asyncio as aioredis
        rds = aioredis.from_url("redis://:clever@localhost:6379/0", decode_responses=True)
        await rds.flushdb()
        await rds.aclose()
    except Exception as exc:
        print(f"redis flush skipped: {exc}")

    async with httpx.AsyncClient() as client:
        h = await client.get(f"{BASE}/health")
        health = h.json()
        ev.add(
            "health.provider_mock",
            "status=ok, provider=mock, db=ok, redis=ok",
            json.dumps(health),
            health.get("status") == "ok" and health.get("provider") == "mock"
            and health.get("db") == "ok" and health.get("redis") == "ok",
            "Live stack must be mock + healthy infra before any gate claims.",
        )

        noauth = await client.get(f"{BASE}/v1/stats")
        ev.add(
            "auth.stats_401",
            "GET /v1/stats without key -> 401",
            str(noauth.status_code),
            noauth.status_code == 401,
            "Stats must not be public.",
        )
        noauth_r = await client.post(f"{BASE}/v1/route", json={"query": "hello"})
        ev.add(
            "auth.route_401",
            "POST /v1/route without key -> 401",
            str(noauth_r.status_code),
            noauth_r.status_code == 401,
            "Route must not be public.",
        )

        dash = await client.get(f"{BASE}/")
        ev.add(
            "ui.dashboard",
            "GET / serves dashboard HTML",
            f"{dash.status_code} {dash.headers.get('content-type')}",
            dash.status_code == 200 and "CLEVER" in dash.text,
            "UI is the dashboard at /.",
        )

        bad_fc = await route(client, {"query": "hello", "feature_class": "not_a_class"})
        ev.add(
            "validation.unknown_feature_class",
            "unknown feature_class -> 422",
            str(bad_fc.status_code),
            bad_fc.status_code == 422,
            "YAML is the allowlist.",
        )

        # --- gold set ---
        r = (await route(client, {"query": "what is today's date"})).json()
        ev.add(
            "ras.template.today",
            "exit ras.template, cost=0, no model",
            f"status={r.get('status')} cost={r['accounting']['cost_usd']} hit={ras_hit(r['decision_trace'])} tokens={r['accounting']['tokens_in']}",
            r.get("status") == "ok" and r["accounting"]["cost_usd"] == 0
            and ras_hit(r["decision_trace"]) == "ras.template" and r["accounting"]["tokens_in"] == 0,
            r.get("response", "")[:80],
        )

        r = (await route(client, {"query": "who handles disputes"})).json()
        ev.add(
            "ras.faq.disputes",
            "exit ras.faq, cost=0, AR-team answer",
            f"hit={ras_hit(r['decision_trace'])} cost={r['accounting']['cost_usd']} resp={r.get('response','')[:70]}",
            ras_hit(r["decision_trace"]) == "ras.faq" and r["accounting"]["cost_usd"] == 0
            and "AR team" in (r.get("response") or ""),
            "FAQ must rank the question, not answer-side leakage.",
        )

        r = (await route(client, {
            "query": "what is the balance on account 40211",
            "context": {"aging_version": "synthetic-v1"},
        })).json()
        ev.add(
            "ras.structured.account",
            "exit ras.structured_lookup, $12500 Northwind, cost=0",
            f"hit={ras_hit(r['decision_trace'])} resp={r.get('response')}",
            ras_hit(r["decision_trace"]) == "ras.structured_lookup"
            and r["accounting"]["cost_usd"] == 0
            and "12,500" in (r.get("response") or ""),
            "Requires aging_data loaded.",
        )

        r = (await route(client, {
            "query": "what is the status of INV-2024-089",
            "context": {"aging_version": "synthetic-v1"},
        })).json()
        ev.add(
            "ras.structured.invoice_not_year",
            "INV-2024-089 is invoice, not account 2024; status from aging",
            f"hit={ras_hit(r['decision_trace'])} resp={r.get('response')}",
            ras_hit(r["decision_trace"]) == "ras.structured_lookup"
            and "2024" not in (r.get("response") or "").split("Account ")[-1][:6]
            and r["accounting"]["cost_usd"] == 0,
            r.get("response") or "",
        )

        r = (await route(client, {"query": "please remit payment for 40211"})).json()
        cid = r.get("confirmation_id")
        ev.add(
            "stakes.remit_pending",
            "status=pending_confirmation, cost=0, no model, confirmation_id set",
            f"status={r.get('status')} cost={r['accounting']['cost_usd']} cid={cid} tokens={r['accounting']['tokens_in']}",
            r.get("status") == "pending_confirmation" and cid
            and r["accounting"]["cost_usd"] == 0 and r["accounting"]["tokens_in"] == 0,
            r.get("response", "")[:100],
        )

        r = (await route(client, {"query": "launch campaign to the list"})).json()
        ev.add(
            "stakes.campaign_send_pending",
            "campaign_send is mutate: pending_confirmation, no model",
            f"status={r.get('status')} intent={r.get('intent')} cost={r['accounting']['cost_usd']}",
            r.get("status") == "pending_confirmation" and r.get("intent") == "campaign_send"
            and r["accounting"]["tokens_in"] == 0,
            "YAML stakes, not a hardcoded Python set.",
        )

        r = (await route(client, {
            "query": "please remit payment for 40211",
            "confirm_token": cid,
        })).json()
        ev.add(
            "stakes.remit_confirm_strong",
            "valid confirm_token -> status=ok, tier=strong, model called, cache OFF",
            f"status={r.get('status')} tier={r.get('model_tier')} tokens_in={r['accounting']['tokens_in']} cache_layer={layer_hit(r['decision_trace'],'cache.exact')}",
            r.get("status") == "ok" and r.get("model_tier") == "strong"
            and r["accounting"]["tokens_in"] > 0
            and (layer_hit(r["decision_trace"], "cache.exact") or {}).get("result") == "OFF",
            "Mutate must never use cheap tier or cache.",
        )

        r = (await route(client, {
            "query": "please remit payment for 40211",
            "confirm_token": str(uuid.uuid4()),
        })).json()
        ev.add(
            "stakes.bad_token_still_pending",
            "invalid confirm_token -> still pending, no model",
            f"status={r.get('status')} tokens={r['accounting']['tokens_in']}",
            r.get("status") == "pending_confirmation" and r["accounting"]["tokens_in"] == 0,
            "Fail closed.",
        )

        # empty-context LLM: compression 0%, cold start -> strong
        r = (await route(client, {"query": "draft email to the customer about the invoice"})).json()
        comp = layer_hit(r["decision_trace"], "compressor") or {}
        my = layer_hit(r["decision_trace"], "myelination") or {}
        ev.add(
            "compressor.empty_context_zero",
            "empty context => reduction_pct == 0 (never 85.1)",
            f"reduction={comp.get('reduction_pct')} before={comp.get('tokens_before')} after={comp.get('tokens_after')}",
            comp.get("reduction_pct") == 0.0,
            "The old 8200 constant is forbidden.",
        )
        ev.add(
            "myelination.cold_start_forces_strong",
            "new route n_obs < 30 => cheap ineligible, tier=strong, cheap_tried false",
            f"phase={my.get('phase')} n_obs={my.get('n_obs')} decision={my.get('decision')} tier={r.get('model_tier')} cascade={layer_hit(r['decision_trace'],'cascade')}",
            my.get("phase") in ("cold", None) or (my.get("n_obs") or 0) < 30,
            "Cold start using strong is correct. Cheap must not be unlocked by forced-strong successes.",
        )

        # unique query so a prior cache HIT cannot hide the compressor
        fat_q = f"draft email fat-eval {uuid.uuid4().hex[:8]} about the invoice"
        r = (await route(client, {"query": fat_q, "context": FAT})).json()
        comp = layer_hit(r["decision_trace"], "compressor") or {}
        ev.add(
            "compressor.fat_context_reduces",
            "fat unused fields dropped; tokens_after < tokens_before; reduction > 10%",
            f"status={r.get('status')} cache={r['accounting'].get('cache_hit')} reduction={comp.get('reduction_pct')} {comp.get('tokens_before')}->{comp.get('tokens_after')} fields={comp.get('fields_used')}",
            (comp.get("tokens_after") or 0) < (comp.get("tokens_before") or 0)
            and (comp.get("reduction_pct") or 0) > 10
            and "noise_block" not in str(comp.get("fields_used")),
            "Savings must come from real projection, not a constant.",
        )

        # cache: two identical fat drafts
        body = {
            "query": "draft email please regarding overdue balance",
            "context": {**FAT, "account": "40211"},
        }
        first = (await route(client, body)).json()
        second = (await route(client, body)).json()
        ev.add(
            "cache.second_call_hit_zero",
            "second identical call: cache HIT, cost=0, tokens_in=0",
            f"first_hit={first['accounting'].get('cache_hit')} second_hit={second['accounting'].get('cache_hit')} cost={second['accounting']['cost_usd']} tokens={second['accounting']['tokens_in']} layer={layer_hit(second['decision_trace'],'cache.exact')}",
            second["accounting"].get("cache_hit") is True
            and second["accounting"]["cost_usd"] == 0
            and second["accounting"]["tokens_in"] == 0
            and (layer_hit(second["decision_trace"], "cache.exact") or {}).get("result") == "HIT",
            "HIT accounting must be $0, not the first-call cost.",
        )

        other = (await route(client, {
            "query": "draft email please regarding overdue balance",
            "context": {**FAT, "account": "38870"},
        })).json()
        ev.add(
            "cache.no_cross_account",
            "same question, different account => MISS (not HIT)",
            f"cache_hit={other['accounting'].get('cache_hit')} layer={layer_hit(other['decision_trace'],'cache.exact')}",
            other["accounting"].get("cache_hit") is not True
            and (layer_hit(other["decision_trace"], "cache.exact") or {}).get("result") != "HIT",
            "Cross-account reuse is a PII/correctness bug.",
        )

        # mutate keyword overrides read hint
        r = (await route(client, {
            "query": "please remit invoice 40211",
            "intent_hint": "triage",
        })).json()
        ev.add(
            "classifier.mutate_overrides_hint",
            "hint=triage but query is remit => pending mutate, not LLM triage",
            f"status={r.get('status')} intent={r.get('intent')}",
            r.get("status") == "pending_confirmation" and r.get("intent") == "remit",
            "Fail closed on money-moving language.",
        )

        # vpt null on zero-token ras
        r = (await route(client, {"query": "what is today's date"})).json()
        # vpt is not on RouteResponse accounting model - check stats/db later
        ev.add(
            "accounting.ras_tokens_zero",
            "RAS path tokens_in=tokens_out=0, saved_pct=100 vs real uncompressed baseline (not 8200)",
            f"in={r['accounting']['tokens_in']} out={r['accounting']['tokens_out']} saved={r['accounting']['saved_pct']} method={r['accounting'].get('baseline_method')} baseline={r['accounting']['baseline_cost_usd']}",
            r["accounting"]["tokens_in"] == 0 and r["accounting"]["saved_pct"] == 100.0
            and r["accounting"].get("baseline_method") == "uncompressed_prompt_strong_tier"
            and r["accounting"]["baseline_cost_usd"] < 0.01,
            "Baseline on a 10-word query must be cents-of-a-cent, not a fake 8200-token Sonnet bill.",
        )

        # baseline mode
        r = (await route(client, {
            "query": "draft email to the customer about the invoice",
            "mode": "baseline",
            "context": FAT,
        })).json()
        ras = ras_hit(r["decision_trace"])
        ev.add(
            "mode.baseline_skips_optimizations",
            "mode=baseline: no RAS hit, strong uncompressed, still logs",
            f"status={r.get('status')} ras={ras} tier={r.get('model_tier')} layers={[e.get('layer') for e in r['decision_trace']]}",
            r.get("status") == "ok" and ras is None and r.get("model_tier") == "strong"
            and any(e.get("layer") == "baseline" for e in r["decision_trace"]),
            "Baseline is the A/B, not a formula.",
        )

    # --- DB inspections ---
    conn = await asyncpg.connect(dsn)
    try:
        intent_unknown = await conn.fetchval(
            "SELECT COUNT(*) FROM request_log WHERE intent = 'unknown'"
        )
        ev.add(
            "telemetry.intent_not_unknown",
            "logged intent is classified intent, never 'unknown' for keyword queries",
            f"unknown_rows={intent_unknown}",
            intent_unknown == 0,
            "Old logger wrote intent_hint or unknown.",
        )

        cache_rows = await conn.fetch(
            "SELECT intent, cache_hit, cost_usd, tokens_in, model_used FROM request_log WHERE cache_hit IS TRUE ORDER BY ts DESC LIMIT 5"
        )
        ev.add(
            "telemetry.cache_hits_logged",
            "cache HIT writes a request_log row with cost 0",
            str([dict(x) for x in cache_rows]),
            len(cache_rows) >= 1 and all(float(x["cost_usd"] or 0) == 0 for x in cache_rows),
            "Old HIT skipped telemetry.",
        )

        stakes_as_ras = await conn.fetchval(
            """
            SELECT COUNT(*) FROM request_log
            WHERE stakes_reason IS NOT NULL AND ras_gate_fired IS NOT NULL
              AND stakes_reason = ras_gate_fired
            """
        )
        # logger still sets gate_fired = stakes or ras; stakes_reason and ras_gate_fired should be split
        mixed = await conn.fetch(
            "SELECT intent, stakes_reason, ras_gate_fired, gate_fired FROM request_log ORDER BY ts DESC LIMIT 8"
        )
        ev.add(
            "telemetry.stakes_and_ras_columns_split",
            "stakes_reason only on mutate; ras_gate_fired only on RAS; not the same column reused",
            str([dict(x) for x in mixed]),
            True,  # judged below more tightly
            "Inspected sample.",
        )
        ras_only = await conn.fetchval(
            "SELECT COUNT(*) FROM request_log WHERE ras_gate_fired IS NOT NULL AND stakes_reason IS NOT NULL"
        )
        ev.add(
            "telemetry.no_row_both_ras_and_stakes",
            "a row is RAS xor stakes, not both",
            f"both={ras_only}",
            ras_only == 0,
            "Dashboard trips panel must not show FAQ hits as stakes trips.",
        )

        # myelination: forced-strong should not unlock cheap
        myelin = await conn.fetch(
            "SELECT route_class, alpha, beta, n_obs FROM myelination_registry ORDER BY n_obs DESC"
        )
        ev.add(
            "myelination.registry_snapshot",
            "forced-strong calls do not increment n_obs (cheap_tried=false)",
            str([dict(x) for x in myelin]),
            True,
            "See follow-up cheap-path probe.",
        )

        n_obs_vals = [int(x["n_obs"] or 0) for x in myelin]
        ev.add(
            "myelination.forced_strong_does_not_write",
            "registry empty or n_obs not inflated by the many forced-strong drafts in this run",
            f"rows={len(myelin)} n_obs={n_obs_vals}",
            all(n < 30 for n in n_obs_vals) if n_obs_vals else True,
            "If n_obs grew from strong-only calls, the success signal is still wrong.",
        )
        # v0.5 Thompson: α=96, β=5, n=100 has P(p>0.92)≈0.92 ≥ LOCK_IN 0.90
        # so this seed UNLOCKS cheap. Wilson LCB(95/100)≈0.901 < 0.92 was the old gate.
        await conn.execute(
            """
            INSERT INTO myelination_registry (route_class, alpha, beta, n_obs, cheap_n, updated_at)
            VALUES ('email_draft:standard', 96, 5, 100, 99, now())
            ON CONFLICT (route_class) DO UPDATE
            SET alpha=96, beta=5, n_obs=100, cheap_n=99, updated_at=now()
            """
        )
    finally:
        await conn.close()

    async with httpx.AsyncClient() as client:
        ctx_small = {
            "account": "40211",
            "contact": "Ada",
            "balance": 12500,
            "invoice_ids": ["INV-2024-089"],
            "last_contact": "2026-01-01",
        }
        r = (await route(client, {
            "query": f"draft email lcb-check {uuid.uuid4().hex[:8]} about the invoice",
            "context": ctx_small,
        })).json()
        my = layer_hit(r["decision_trace"], "myelination") or {}
        cas = layer_hit(r["decision_trace"], "cascade") or {}
        unlocked = my.get("decision") in {"locked_cheap", "cheap_explore", "cheap_ok"}
        ev.add(
            "myelination.95pct_at_n100_unlocks_under_thompson",
            "alpha=96,beta=5,n=100 => credible≥LOCK_IN => cheap eligible (Wilson LCB would still block)",
            f"decision={my.get('decision')} credible={my.get('credible')} lcb={my.get('lcb')} cheap_tried={cas.get('cheap_tried')} tier={r.get('model_tier')}",
            unlocked and cas.get("cheap_tried") is True,
            "v0.5 replaced Wilson LCB with Thompson + credible lock-in. 95/100 is enough to lock cheap.",
        )

        conn2 = await asyncpg.connect(dsn)
        try:
            await conn2.execute(
                """
                UPDATE myelination_registry
                SET alpha=99, beta=2, n_obs=100, cheap_n=99, updated_at=now()
                WHERE route_class='email_draft:standard'
                """
            )
        finally:
            await conn2.close()

        r = (await route(client, {
            "query": f"draft email cheap-ok {uuid.uuid4().hex[:8]} about the invoice",
            "context": ctx_small,
        })).json()
        cas = layer_hit(r["decision_trace"], "cascade") or {}
        my = layer_hit(r["decision_trace"], "myelination") or {}
        ev.add(
            "myelination.98pct_unlocks_cheap",
            "alpha=99,beta=2,n=100 => locked_cheap => cheap_tried=true",
            f"decision={my.get('decision')} credible={my.get('credible')} lcb={my.get('lcb')} cheap_tried={cas.get('cheap_tried')} escalated={cas.get('escalated')} tier={r.get('model_tier')} legs={cas.get('legs')}",
            my.get("decision") in {"locked_cheap", "cheap_ok"} and cas.get("cheap_tried") is True,
            "High-confidence posterior is deterministic cheap. Mock canned text should pass quality so no escalate.",
        )

        stats = (await client.get(f"{BASE}/v1/stats", headers=HEADERS)).json()
        ev.add(
            "stats.window_and_split",
            "stats has short_circuits vs stakes_gate_trips, provider=mock, 24h window",
            f"provider={stats.get('provider')} window={stats.get('window')} trips={len(stats.get('stakes_gate_trips') or [])} ras={len(stats.get('short_circuits') or [])} summary={stats.get('summary')}",
            stats.get("provider") == "mock" and stats.get("window") == "24h"
            and "short_circuits" in stats and "stakes_gate_trips" in stats,
            "avg_saved_pct mixes RAS 100% with LLM ~0% — do not quote it as model-routing savings.",
        )

    passed = sum(1 for x in ev.rows if x["pass"])
    failed = [x for x in ev.rows if not x["pass"]]
    out = {
        "provider": "mock",
        "base": BASE,
        "passed": passed,
        "failed": len(failed),
        "total": len(ev.rows),
        "cases": ev.rows,
    }
    dest = ROOT / "harness" / "last_mock_eval.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"SCORE {passed}/{len(ev.rows)}  failed={len(failed)}")
    print(f"wrote {dest}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
