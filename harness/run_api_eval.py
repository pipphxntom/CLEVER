"""Live API eval. Unique queries. Does not print secrets. Honest pass/fail."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import asyncpg
import httpx
import redis.asyncio as aioredis

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"
KEY = "dev-key-change-me"
HEADERS = {"X-API-Key": KEY, "Content-Type": "application/json"}
DSN = "postgresql://clever:clever@localhost:5432/clever"

FAT = {
    "account": "40211",
    "contact": "Ada Cole",
    "balance": 12500.0,
    "invoice_ids": ["INV-2024-089"],
    "last_contact": "2026-01-01",
    "noise_block": "AGING " + ("row-padding " * 400),
}


def ras_hit(trace):
    for e in trace or []:
        if str(e.get("layer", "")).startswith("ras.") and e.get("result") == "HIT":
            return e["layer"]
    return None


def layer(trace, name):
    for e in trace or []:
        if e.get("layer") == name:
            return e
    return {}


class Eval:
    def __init__(self):
        self.rows = []

    def add(self, cid, intended, actual, ok, detail=""):
        self.rows.append({
            "id": cid, "intended": intended, "actual": actual,
            "pass": bool(ok), "detail": detail,
        })
        print(f"[{'PASS' if ok else 'FAIL'}] {cid}")
        print(f"  intended: {intended}")
        print(f"  actual:   {actual}")
        if detail:
            print(f"  {detail}")
        print()


async def route(client, body):
    r = await client.post(f"{BASE}/v1/route", headers=HEADERS, json=body, timeout=120)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]})


async def main():
    ev = Eval()
    spend_usd = 0.0

    rds = aioredis.from_url("redis://:clever@localhost:6379/0", decode_responses=True)
    await rds.flushdb()
    await rds.aclose()
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("DELETE FROM myelination_registry")
    finally:
        await conn.close()

    async with httpx.AsyncClient() as client:
        h = (await client.get(f"{BASE}/health")).json()
        ev.add(
            "health.not_mock",
            "provider=openai_compat, db=ok, redis=ok",
            json.dumps(h),
            h.get("provider") == "openai_compat" and h.get("db") == "ok" and h.get("status") == "ok",
            "If this is still mock, stop. Do not interpret canned text as API.",
        )
        if h.get("provider") != "openai_compat":
            _write(ev, spend_usd)
            return 2

        # RAS must still be $0 and must NOT hit the vendor
        for cid, q, expect in [
            ("ras.date", "what is today's date", "ras.template"),
            ("ras.faq", "who handles disputes", "ras.faq"),
        ]:
            code, r = await route(client, {"query": q})
            hit = ras_hit(r.get("decision_trace"))
            ev.add(
                cid,
                f"HIT {expect}, cost=0, tokens_in=0",
                f"http={code} hit={hit} cost={r.get('accounting',{}).get('cost_usd')} tok={r.get('accounting',{}).get('tokens_in')} resp={(r.get('response') or '')[:80]}",
                code == 200 and hit == expect and r["accounting"]["cost_usd"] == 0 and r["accounting"]["tokens_in"] == 0,
            )

        code, r = await route(client, {
            "query": "what is the balance on account 40211",
            "context": {"aging_version": "synthetic-v1"},
        })
        ev.add(
            "ras.structured",
            "SQL HIT $12500, no vendor call",
            f"hit={ras_hit(r.get('decision_trace'))} resp={r.get('response')} cost={r.get('accounting',{}).get('cost_usd')}",
            ras_hit(r.get("decision_trace")) == "ras.structured_lookup"
            and "12,500" in (r.get("response") or "")
            and r["accounting"]["tokens_in"] == 0,
        )

        code, r = await route(client, {"query": "please remit payment for 40211"})
        ev.add(
            "stakes.pending_no_vendor",
            "pending_confirmation, tokens_in=0 (no paid call)",
            f"status={r.get('status')} tok={r.get('accounting',{}).get('tokens_in')}",
            r.get("status") == "pending_confirmation" and r["accounting"]["tokens_in"] == 0,
        )

        tag = uuid.uuid4().hex[:8]
        draft_q = f"Write a short collections dunning email for this account. Tag {tag}."
        ctx = {
            "account": "40211",
            "contact": "Ada Cole",
            "balance": 12500,
            "invoice_ids": ["INV-2024-089"],
            "last_contact": "2026-01-01",
        }

        code, clever = await route(client, {"query": draft_q, "context": ctx})
        if code != 200:
            ev.add("llm.clever_draft", "200 + real model text", f"http={code} body={clever}", False)
            _write(ev, spend_usd)
            return 1
        spend_usd += float(clever["accounting"]["cost_usd"])
        cas = layer(clever["decision_trace"], "cascade")
        comp = layer(clever["decision_trace"], "compressor")
        my = layer(clever["decision_trace"], "myelination")
        text = clever.get("response") or ""
        mentions = sum(1 for s in ("40211", "12,500", "12500", "INV-2024-089", "Ada") if s in text)
        ev.add(
            "llm.clever_draft",
            "real vendor call; usage tokens > 0; not a mock canned paragraph",
            f"http={code} tier={clever.get('model_tier')} model_id={cas.get('legs')} cost={clever['accounting']['cost_usd']} "
            f"in={clever['accounting']['tokens_in']} out={clever['accounting']['tokens_out']} "
            f"forced={cas.get('forced')} cheap_tried={cas.get('cheap_tried')} esc={cas.get('escalated')} "
            f"quality={clever.get('quality')} compress={comp.get('reduction_pct')} myelin={my.get('decision')} "
            f"mentions={mentions} preview={text[:180]!r}",
            code == 200 and clever["accounting"]["tokens_in"] > 0
            and "concise collections response based on the supplied context" not in text.lower()
            and len(text) > 40,
            "Cold start should force strong. Mentions of 40211/12500/Ada are a grounding check, not a pass gate.",
        )
        ev.add(
            "llm.clever_draft.grounding",
            "email should use account 40211 or $12500 or Ada or INV-2024-089 (at least 1)",
            f"mentions={mentions} text={text[:300]!r}",
            mentions >= 1,
            "If 0, the model ignored context. FLAG even if HTTP 200.",
        )

        code, base = await route(client, {"query": draft_q, "context": ctx, "mode": "baseline"})
        spend_usd += float(base.get("accounting", {}).get("cost_usd") or 0)
        ev.add(
            "llm.baseline_draft",
            "mode=baseline: strong, no RAS, real tokens, typically >= clever tokens_in",
            f"http={code} tier={base.get('model_tier')} cost={base.get('accounting',{}).get('cost_usd')} "
            f"in={base.get('accounting',{}).get('tokens_in')} out={base.get('accounting',{}).get('tokens_out')} "
            f"layers={[e.get('layer') for e in base.get('decision_trace') or []]}",
            code == 200 and base.get("model_tier") == "strong" and (base.get("accounting") or {}).get("tokens_in", 0) > 0,
        )
        if code == 200:
            clever_in = clever["accounting"]["tokens_in"]
            base_in = base["accounting"]["tokens_in"]
            clever_was_ras = ras_hit(clever.get("decision_trace")) is not None
            ev.add(
                "llm.clever_vs_baseline_input_tokens",
                "clever LLM path tokens_in <= baseline; clever must actually have called a model (not RAS)",
                f"clever_ras={clever_was_ras} clever_in={clever_in} baseline_in={base_in} clever_cost={clever['accounting']['cost_usd']} baseline_cost={base['accounting']['cost_usd']}",
                (not clever_was_ras) and clever_in > 0 and clever_in <= base_in,
            )

        fat_q = f"Summarize this account for a collector. Tag {uuid.uuid4().hex[:8]}."
        code, fat_c = await route(client, {"query": fat_q, "context": FAT})
        spend_usd += float((fat_c.get("accounting") or {}).get("cost_usd") or 0)
        comp = layer(fat_c.get("decision_trace"), "compressor")
        ev.add(
            "llm.fat_context_compresses",
            "noise_block dropped; tokens_after < tokens_before by >10%",
            f"http={code} red={comp.get('reduction_pct')} {comp.get('tokens_before')}->{comp.get('tokens_after')} "
            f"fields={comp.get('fields_used')} cost={fat_c.get('accounting',{}).get('cost_usd')} "
            f"in={fat_c.get('accounting',{}).get('tokens_in')}",
            code == 200 and (comp.get("reduction_pct") or 0) > 10
            and "noise_block" not in str(comp.get("fields_used")),
        )

        code, fat_b = await route(client, {"query": fat_q, "context": FAT, "mode": "baseline"})
        spend_usd += float((fat_b.get("accounting") or {}).get("cost_usd") or 0)
        if code == 200 and fat_c.get("accounting"):
            ev.add(
                "llm.fat_clever_cheaper_or_equal",
                "clever actual cost_usd <= baseline cost_usd on the same fat prompt",
                f"clever={fat_c['accounting']['cost_usd']} baseline={fat_b['accounting']['cost_usd']} "
                f"clever_in={fat_c['accounting']['tokens_in']} base_in={fat_b['accounting']['tokens_in']}",
                fat_c["accounting"]["cost_usd"] <= fat_b["accounting"]["cost_usd"] + 1e-9,
                "If clever is MORE expensive, cascade (cheap fail + strong) billed two legs. That is a real finding, not a rounding error.",
            )

        # cache: second identical clever fat call should be $0 vendor
        code2, hit = await route(client, {"query": fat_q, "context": FAT})
        ev.add(
            "cache.api_second_call_zero",
            "repeat => cache HIT, cost 0, no extra vendor tokens",
            f"http={code2} cache={hit.get('accounting',{}).get('cache_hit')} cost={hit.get('accounting',{}).get('cost_usd')} tok={hit.get('accounting',{}).get('tokens_in')}",
            hit.get("accounting", {}).get("cache_hit") is True and hit["accounting"]["cost_usd"] == 0,
        )

        stats = (await client.get(f"{BASE}/v1/stats", headers=HEADERS)).json()
        ev.add(
            "stats.provider_live",
            "stats.provider is openai_compat, not mock",
            f"provider={stats.get('provider')} summary={stats.get('summary')}",
            stats.get("provider") == "openai_compat",
        )

    _write(ev, spend_usd)
    failed = sum(1 for x in ev.rows if not x["pass"])
    return 0 if failed == 0 else 1


def _write(ev: Eval, spend_usd: float):
    passed = sum(1 for x in ev.rows if x["pass"])
    out = {
        "provider_expected": "openai_compat",
        "passed": passed,
        "failed": len(ev.rows) - passed,
        "total": len(ev.rows),
        "approx_accounted_usd": round(spend_usd, 6),
        "pricing_note": "accounted USD uses config/pricing.yaml cache-miss off-peak, not the vendor invoice",
        "cases": ev.rows,
    }
    dest = ROOT / "harness" / "last_api_eval.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"SCORE {passed}/{len(ev.rows)}  failed={len(ev.rows)-passed}  accounted_usd~{spend_usd:.6f}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
