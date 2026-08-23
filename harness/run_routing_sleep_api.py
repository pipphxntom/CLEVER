"""Live HTTP tests for Thompson routing + sleep consolidation.

Hits a running gateway. Does not pretend mock numbers are production.
N_MIN is whatever the process loaded from .env (this repo often has 6).
Cheap quality may fail on a live model — routing PASS is cheap_tried / not,
not 'flash produced a final answer'.

Writes harness/last_routing_sleep_api.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
import redis.asyncio as aioredis

from gateway.sleep.consolidation import decay_alpha_beta as decay_ab

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"
KEY = "dev-key-change-me"
ADMIN = "dev-admin-change-me"
HEADERS = {"X-API-Key": KEY, "Content-Type": "application/json"}
ADMIN_H = {"X-API-Key": ADMIN, "Content-Type": "application/json"}
DSN = "postgresql://clever:clever@localhost:5432/clever"
REDIS_URL = "redis://:clever@localhost:6379/0"
OUT = ROOT / "harness" / "last_routing_sleep_api.json"

CTX = {
    "account": "40211",
    "contact": "Ada",
    "balance": 12500,
    "invoice_ids": ["INV-2024-089"],
    "last_contact": "2026-01-01",
    "aging_version": "synthetic-v1",
}


def layer(trace, name):
    for e in trace or []:
        if e.get("layer") == name:
            return e
    return {}


def ras_hit(trace):
    for e in trace or []:
        if str(e.get("layer", "")).startswith("ras.") and e.get("result") == "HIT":
            return e["layer"]
    return None


def num(acc, key, default=0):
    """0.0 is a real zero. Do not use `or default` — that turns 0 into default."""
    if acc is None:
        return default
    v = acc.get(key)
    return default if v is None else v


class Report:
    def __init__(self):
        self.rows = []
        self.spend = 0.0

    def add(self, case_id, intended, actual, ok, detail=""):
        self.rows.append({
            "id": case_id,
            "intended": intended,
            "actual": actual,
            "pass": bool(ok),
            "detail": detail,
        })
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {case_id}")
        print(f"  intended: {intended}")
        print(f"  actual:   {actual}")
        if detail:
            print(f"  {detail}")
        print()

    def note_cost(self, body):
        try:
            self.spend += float((body.get("accounting") or {}).get("cost_usd") or 0)
        except Exception:
            pass


async def route(client, body, timeout=180):
    return await client.post(f"{BASE}/v1/route", headers=HEADERS, json=body, timeout=timeout)


async def seed_route(conn, route_class, alpha, beta, n_obs, cheap_n):
    await conn.execute(
        """
        INSERT INTO myelination_registry (route_class, alpha, beta, n_obs, cheap_n, updated_at)
        VALUES ($1,$2,$3,$4,$5, now())
        ON CONFLICT (route_class) DO UPDATE
        SET alpha=$2, beta=$3, n_obs=$4, cheap_n=$5, updated_at=now()
        """,
        route_class, alpha, beta, n_obs, cheap_n,
    )


async def main() -> int:
    ev = Report()
    started = datetime.now(timezone.utc).isoformat()

    conn = await asyncpg.connect(DSN)
    rds = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await rds.delete("sleep_lock")
        await rds.flushdb()
    except Exception as exc:
        print(f"redis flush warning: {exc}")

    async with httpx.AsyncClient() as client:
        try:
            h = await client.get(f"{BASE}/health", timeout=5)
            health = h.json()
        except Exception as exc:
            print(f"GATEWAY DOWN: {exc}")
            ev.add("health", "gateway /health ok", str(exc), False)
            OUT.write_text(json.dumps({"ok": False, "rows": ev.rows}, indent=2), encoding="utf-8")
            await conn.close()
            await rds.aclose()
            return 2

        ev.add(
            "health",
            "status=ok, db=ok, redis=ok (provider is whatever .env loaded)",
            json.dumps(health),
            health.get("status") == "ok" and health.get("db") == "ok" and health.get("redis") == "ok",
            f"provider={health.get('provider')} version={health.get('version')}",
        )
        live = health.get("provider") == "openai_compat"
        mock = health.get("provider") == "mock"

        noauth = await client.post(f"{BASE}/v1/route", json={"query": "hello"}, timeout=10)
        ev.add("auth.route_401", "401 without key", str(noauth.status_code), noauth.status_code == 401)

        noadmin = await client.post(f"{BASE}/v1/admin/consolidate", timeout=10)
        ev.add(
            "auth.consolidate_401",
            "401 without admin key",
            str(noadmin.status_code),
            noadmin.status_code == 401,
        )

        # ---- existing pipeline: must not regress ----
        r = (await route(client, {"query": "what is today's date"})).json()
        ev.note_cost(r)
        acc = r.get("accounting") or {}
        ev.add(
            "pipeline.ras_date",
            "ras.template HIT, cost=0, tokens_in=0",
            f"hit={ras_hit(r.get('decision_trace'))} cost={acc.get('cost_usd')} tokens={acc.get('tokens_in')}",
            ras_hit(r.get("decision_trace")) == "ras.template"
            and float(num(acc, "cost_usd")) == 0.0
            and int(num(acc, "tokens_in")) == 0,
        )

        r = (await route(client, {"query": "please remit payment for 40211"})).json()
        ev.note_cost(r)
        acc = r.get("accounting") or {}
        ev.add(
            "pipeline.stakes_remit",
            "pending_confirmation, no LLM tokens",
            f"status={r.get('status')} tokens={acc.get('tokens_in')} cost={acc.get('cost_usd')}",
            r.get("status") == "pending_confirmation"
            and int(num(acc, "tokens_in")) == 0,
        )

        # ---- routing: Thompson ----
        # Semantic cache sits BEFORE myelination. A near-duplicate draft email
        # will HIT postgres semantic_cache and never reach Thompson. Flush it.
        await conn.execute("DELETE FROM semantic_cache")
        await conn.execute("DELETE FROM myelination_registry WHERE route_class LIKE 'dispute%'")
        uid = uuid.uuid4().hex[:8]
        r = (await route(client, {
            "query": f"analyze dispute pattern {uid} for account 40211",
            "intent_hint": "dispute",
            "context": CTX,
        })).json()
        ev.note_cost(r)
        my = layer(r.get("decision_trace"), "myelination")
        cas = layer(r.get("decision_trace"), "cascade")
        ev.add(
            "routing.cold_start",
            "n_obs=0 → decision=cold_start, cheap_tried=false, strong",
            f"decision={my.get('decision')} phase={my.get('phase')} n={my.get('n_obs')} "
            f"cheap_tried={cas.get('cheap_tried')} tier={r.get('model_tier')} cost={r.get('accounting',{}).get('cost_usd')}",
            my.get("decision") == "cold_start"
            and cas.get("cheap_tried") is False
            and r.get("model_tier") == "strong",
            "Cold start is independent of N_MIN as long as n_obs=0.",
        )

        # n_obs just below process N_MIN (6 in this .env) must stay cold
        await seed_route(conn, "email_draft:standard", 1, 1, 5, 0)
        uid = uuid.uuid4().hex[:8]
        r = (await route(client, {
            "query": f"draft email {uid} to Ada about invoice INV-2024-089",
            "intent_hint": "email_draft",
            "context": CTX,
        })).json()
        ev.note_cost(r)
        my = layer(r.get("decision_trace"), "myelination")
        cas = layer(r.get("decision_trace"), "cascade")
        still_cold = my.get("decision") == "cold_start" and cas.get("cheap_tried") is False
        ev.add(
            "routing.below_n_min_still_cold",
            "n_obs=5, cheap_n=0 → still cold if process N_MIN>5 (this .env is 6)",
            f"decision={my.get('decision')} n={my.get('n_obs')} cheap_tried={cas.get('cheap_tried')} "
            f"tier={r.get('model_tier')} credible={my.get('credible')}",
            still_cold,
            "If this FAIL, the process N_MIN is ≤5 or seeding did not stick.",
        )

        await conn.execute("DELETE FROM semantic_cache")
        await seed_route(conn, "email_draft:standard", 1, 1, 6, 0)
        uid = uuid.uuid4().hex[:8]
        r = (await route(client, {
            "query": f"draft email {uid} to Ada about the outstanding invoice",
            "intent_hint": "email_draft",
            "context": {**CTX, "invoice_ids": [f"INV-EXPLORE-{uid}"]},
        })).json()
        ev.note_cost(r)
        my = layer(r.get("decision_trace"), "myelination")
        cas = layer(r.get("decision_trace"), "cascade")
        ev.add(
            "routing.first_explore_after_cold",
            "n_obs>=N_MIN and cheap_n=0 → decision=explore, cheap_tried=true",
            f"decision={my.get('decision')} phase={my.get('phase')} n={my.get('n_obs')} "
            f"cheap_tried={cas.get('cheap_tried')} escalated={cas.get('escalated')} "
            f"tier={r.get('model_tier')} score={r.get('quality',{}).get('score')}",
            my.get("decision") == "explore" and cas.get("cheap_tried") is True,
            "Escalation after cheap is a quality result, not a routing fail.",
        )

        await seed_route(conn, "email_draft:standard", 99, 2, 100, 99)
        uid = uuid.uuid4().hex[:8]
        r = (await route(client, {
            "query": f"draft email {uid} lock-in probe about invoice INV-2024-089",
            "intent_hint": "email_draft",
            "context": CTX,
        })).json()
        ev.note_cost(r)
        my = layer(r.get("decision_trace"), "myelination")
        cas = layer(r.get("decision_trace"), "cascade")
        ev.add(
            "routing.lock_in_cheap",
            "α=99,β=2,n=100 → locked_cheap, cheap_tried=true",
            f"decision={my.get('decision')} credible={my.get('credible')} lcb={my.get('lcb')} "
            f"cheap_tried={cas.get('cheap_tried')} escalated={cas.get('escalated')} "
            f"tier={r.get('model_tier')} thompson_sample={my.get('thompson_sample')}",
            my.get("decision") == "locked_cheap" and cas.get("cheap_tried") is True,
            "Wilson LCB on this seed is ~0.96 diagnostic only; gate is credible.",
        )

        await seed_route(conn, "triage:standard", 2, 20, 25, 21)
        uid = uuid.uuid4().hex[:8]
        r = (await route(client, {
            "query": f"summarize outstanding risk {uid} for account 40211",
            "intent_hint": "triage",
            "context": CTX,
        })).json()
        ev.note_cost(r)
        my = layer(r.get("decision_trace"), "myelination")
        cas = layer(r.get("decision_trace"), "cascade")
        ev.add(
            "routing.lock_out_strong",
            "α=2,β=20,cheap_n=21 → locked_strong, cheap_tried=false",
            f"decision={my.get('decision')} phase={my.get('phase')} credible={my.get('credible')} "
            f"cheap_tried={cas.get('cheap_tried')} tier={r.get('model_tier')}",
            my.get("decision") == "locked_strong"
            and cas.get("cheap_tried") is False
            and r.get("model_tier") == "strong",
        )

        # ---- sleep ----
        await seed_route(conn, "sleep_probe:standard", 51, 3, 55, 52)
        expected_a, expected_b = decay_ab(51, 3, 0.80)

        good_hash = f"sleepgood{uuid.uuid4().hex[:10]}"
        bad_hash = f"sleepbad{uuid.uuid4().hex[:10]}"
        await conn.execute("DELETE FROM faq_candidates WHERE query_hash LIKE 'sleep%'")
        for i in range(5):
            await conn.execute(
                """
                INSERT INTO request_log (
                    request_id, mode, feature_class, intent, query_hash,
                    quality_score, query_text_redacted, ras_gate_fired, stakes_reason, ts
                ) VALUES (
                    $1, 'clever', 'collections_outreach', 'email_draft', $2,
                    0.970, $3, NULL, NULL, now()
                )
                """,
                uuid.uuid4(),
                good_hash,
                "draft email to Ada about invoice INV-2024-089",
            )
        for i in range(5):
            await conn.execute(
                """
                INSERT INTO request_log (
                    request_id, mode, feature_class, intent, query_hash,
                    quality_score, query_text_redacted, ras_gate_fired, stakes_reason, ts
                ) VALUES (
                    $1, 'clever', 'collections_outreach', 'email_draft', $2,
                    0.700, $3, NULL, NULL, now()
                )
                """,
                uuid.uuid4(),
                bad_hash,
                "low quality repeat",
            )

        log_before = await conn.fetchval("SELECT COUNT(*) FROM consolidation_log")
        faq_before = await conn.fetchval("SELECT COUNT(*) FROM faq_entries")

        s1 = await client.post(f"{BASE}/v1/admin/consolidate", headers=ADMIN_H, timeout=30)
        body = s1.json() if s1.status_code == 200 else {"http": s1.status_code, "text": s1.text[:300]}
        ev.add(
            "sleep.manual_consolidate",
            "POST /v1/admin/consolidate → 200 status=ok",
            json.dumps(body, default=str)[:800],
            s1.status_code == 200 and body.get("status") == "ok",
        )

        row = await conn.fetchrow(
            "SELECT alpha, beta, n_obs, cheap_n FROM myelination_registry WHERE route_class='sleep_probe:standard'"
        )
        ev.add(
            "sleep.decay_applied",
            f"α,β decay 51,3 → {expected_a},{expected_b}; n_obs stays 55",
            f"row={dict(row) if row else None} expected_ab=({expected_a},{expected_b})",
            row is not None
            and int(row["alpha"]) == expected_a
            and int(row["beta"]) == expected_b
            and int(row["n_obs"]) == 55,
        )

        good_c = await conn.fetchrow(
            "SELECT frequency, status, avg_quality FROM faq_candidates WHERE query_hash=$1",
            good_hash,
        )
        bad_c = await conn.fetchrow(
            "SELECT frequency, status FROM faq_candidates WHERE query_hash=$1",
            bad_hash,
        )
        ev.add(
            "sleep.pattern_quality_gate",
            "high-quality repeats → pending candidate; quality 0.70 → no row",
            f"good={dict(good_c) if good_c else None} bad={dict(bad_c) if bad_c else None}",
            good_c is not None
            and int(good_c["frequency"]) >= 5
            and good_c["status"] in ("pending", "candidate")
            and bad_c is None,
        )

        faq_after = await conn.fetchval("SELECT COUNT(*) FROM faq_entries")
        sleep_faq = await conn.fetchval(
            "SELECT COUNT(*) FROM faq_entries WHERE source = 'sleep'"
        )
        ev.add(
            "sleep.no_auto_publish",
            "faq_entries count unchanged; source=sleep is 0",
            f"before={faq_before} after={faq_after} sleep_source={sleep_faq}",
            faq_after == faq_before and int(sleep_faq or 0) == 0,
        )

        log_after = await conn.fetchval("SELECT COUNT(*) FROM consolidation_log")
        last_log = await conn.fetchrow(
            "SELECT trigger, routes_decayed, candidates_created, duration_ms FROM consolidation_log ORDER BY id DESC LIMIT 1"
        )
        ev.add(
            "sleep.consolidation_log",
            "consolidation_log grew by 1, trigger=manual",
            f"before={log_before} after={log_after} last={dict(last_log) if last_log else None}",
            (log_after or 0) >= (log_before or 0) + 1
            and last_log is not None
            and last_log["trigger"] == "manual",
        )

        s2 = await client.post(f"{BASE}/v1/admin/sleep", headers=ADMIN_H, timeout=30)
        b2 = s2.json() if s2.status_code == 200 else {"http": s2.status_code}
        ev.add(
            "sleep.legacy_endpoint_and_lock_release",
            "POST /v1/admin/sleep works (lock was released after first job)",
            json.dumps(b2, default=str)[:500],
            s2.status_code == 200 and b2.get("status") == "ok",
        )

        # decay twice: 51,3 → e1 → e2
        e2a, e2b = decay_ab(expected_a, expected_b, 0.80)
        row2 = await conn.fetchrow(
            "SELECT alpha, beta, n_obs FROM myelination_registry WHERE route_class='sleep_probe:standard'"
        )
        ev.add(
            "sleep.second_cycle_decays_again",
            f"second sleep → α,β {e2a},{e2b}, n_obs still 55",
            f"row={dict(row2) if row2 else None}",
            row2 is not None
            and int(row2["alpha"]) == e2a
            and int(row2["beta"]) == e2b
            and int(row2["n_obs"]) == 55,
        )

        # cache still works after sleep
        uid = uuid.uuid4().hex[:8]
        q = f"draft email {uid} cache-isolation probe about invoice INV-2024-089"
        first = (await route(client, {"query": q, "intent_hint": "email_draft", "context": CTX})).json()
        ev.note_cost(first)
        second = (await route(client, {"query": q, "intent_hint": "email_draft", "context": CTX})).json()
        ev.note_cost(second)
        # quality-fail on first means no cache write — that is existing behavior, not a sleep bug
        cached = bool((second.get("accounting") or {}).get("cache_hit"))
        qpass = bool((first.get("quality") or {}).get("passed"))
        second_cost = float(num(second.get("accounting") or {}, "cost_usd"))
        ev.add(
            "pipeline.cache_after_sleep",
            "repeat query HITs exact cache IF first quality passed; else miss is honest",
            f"first_passed={qpass} first_cost={first.get('accounting',{}).get('cost_usd')} "
            f"second_hit={cached} second_cost={second_cost} "
            f"tier1={first.get('model_tier')}",
            (qpass and cached and second_cost == 0.0) or (not qpass and not cached),
            "Do not count a quality-fail miss as a cache regression.",
        )

    await conn.close()
    await rds.aclose()

    passed = sum(1 for x in ev.rows if x["pass"])
    failed = [x["id"] for x in ev.rows if not x["pass"]]
    out = {
        "started": started,
        "ended": datetime.now(timezone.utc).isoformat(),
        "provider_live": live,
        "provider_mock": mock,
        "health": health,
        "spend_usd": round(ev.spend, 6),
        "passed": passed,
        "failed": failed,
        "n": len(ev.rows),
        "ok": len(failed) == 0,
        "rows": ev.rows,
        "honesty": {
            "n_min_note": "Process N_MIN comes from .env (often 6). Production default is 30.",
            "cheap_final_note": "Routing pass ≠ cheap produced the final answer. Escalation is quality.",
            "sleep_note": "This proves the manual job, decay, candidate gate, and log. Not a week of prod traffic.",
        },
    }
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("=" * 60)
    print(f"passed={passed}/{len(ev.rows)} spend_usd={out['spend_usd']} failed={failed}")
    print(f"wrote {OUT}")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
