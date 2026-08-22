"""real_test-2: mixed authentic + repeat queries. Honest layer log. No secret printing."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

import asyncpg
import httpx
import redis.asyncio as aioredis

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"
HEADERS = {"X-API-Key": "dev-key-change-me", "Content-Type": "application/json"}
CTX = {
    "account": "40211",
    "contact": "Ada Cole",
    "balance": 12500,
    "invoice_ids": ["INV-2024-089"],
    "last_contact": "2026-01-01",
    "days_overdue": 45,
    "status": "open",
}


def exit_of(r: dict) -> str:
    if r.get("status") == "pending_confirmation":
        return "stakes_pending"
    if r.get("accounting", {}).get("cache_hit"):
        return "cache"
    for e in r.get("decision_trace") or []:
        if e.get("layer", "").startswith("ras.") and e.get("result") == "HIT":
            return e["layer"]
    if (r.get("accounting") or {}).get("tokens_in", 0) > 0:
        return f"llm:{r.get('model_tier')}"
    return "other"


def myelin(r):
    for e in r.get("decision_trace") or []:
        if e.get("layer") == "myelination":
            return e
    return {}


async def post(client, body):
    res = await client.post(f"{BASE}/v1/route", headers=HEADERS, json=body, timeout=120)
    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {"error": res.text[:300]}
    return res.status_code, data


async def main():
    rds = aioredis.from_url("redis://:clever@localhost:6379/0", decode_responses=True)
    await rds.flushdb()
    await rds.aclose()
    conn = await asyncpg.connect("postgresql://clever:clever@localhost:5432/clever")
    try:
        await conn.execute("DELETE FROM myelination_registry")
    finally:
        await conn.close()

    rows = []
    spend = 0.0
    h = {}
    async with httpx.AsyncClient() as client:
        h = (await client.get(f"{BASE}/health")).json()
        if h.get("provider") != "openai_compat":
            print("STOP: provider is", h.get("provider"))
            return 2

        script = [
            ("lookup", {"query": "what is the balance on account 40211", "context": {"aging_version": "synthetic-v1"}}),
            ("lookup_repeat", {"query": "what is the balance on account 40211", "context": {"aging_version": "synthetic-v1"}}),
            ("faq", {"query": "who handles disputes"}),
            ("date", {"query": "what is today's date"}),
            ("remit", {"query": "please remit payment for 40211"}),
            ("campaign", {"query": "launch campaign to the west list"}),
            *[(f"draft_{i}", {"query": f"Write a short collections dunning email. Ref {uuid.uuid4().hex[:6]}.", "context": CTX}) for i in range(8)],
            ("draft_same_a", {"query": "Write a short collections dunning email. Ref SAMEONE.", "context": CTX}),
            ("draft_same_b", {"query": "Write a short collections dunning email. Ref SAMEONE.", "context": CTX}),
            ("other_account", {"query": "Write a short collections dunning email. Ref SAMEONE.", "context": {**CTX, "account": "38870", "contact": "Lee Park", "balance": 8200, "invoice_ids": ["INV-2024-101"]}}),
            ("invoice", {"query": "what is the status of INV-2024-089", "context": {"aging_version": "synthetic-v1"}}),
            ("triage", {"query": "who owes us money on the aging report", "context": CTX}),
        ]

        for name, body in script:
            code, r = await post(client, body)
            acc = r.get("accounting") or {}
            spend += float(acc.get("cost_usd") or 0)
            rec = {
                "name": name,
                "http": code,
                "status": r.get("status"),
                "intent": r.get("intent"),
                "exit": exit_of(r) if code == 200 else f"http_{code}",
                "tier": r.get("model_tier"),
                "tokens_in": acc.get("tokens_in"),
                "tokens_out": acc.get("tokens_out"),
                "cost_usd": acc.get("cost_usd"),
                "saved_pct": acc.get("saved_pct"),
                "cache_hit": acc.get("cache_hit"),
                "quality": r.get("quality"),
                "myelination": myelin(r),
                "preview": (r.get("response") or "")[:160],
            }
            rows.append(rec)
            print(
                f"{name:16} exit={rec['exit']:22} intent={rec['intent']} tier={rec['tier']} "
                f"$={rec['cost_usd']} in={rec['tokens_in']} "
                f"q={(rec['quality'] or {}).get('method')} my={(rec['myelination'] or {}).get('decision')}"
            )

        stats = (await client.get(f"{BASE}/v1/stats", headers=HEADERS)).json()

    exits = Counter(r["exit"] for r in rows)
    tiers = Counter(r["tier"] for r in rows if r["tier"])
    out = {
        "test_id": "real_test-2",
        "provider": h.get("provider"),
        "n_min_note": "Uses process N_MIN/N_EXPLORE from .env (eval: 6/3). Production defaults 30/10.",
        "accounted_usd": round(spend, 6),
        "exit_counts": dict(exits),
        "tier_counts": dict(tiers),
        "stats_summary": stats.get("summary"),
        "stats_by_exit": stats.get("by_exit"),
        "rows": rows,
    }
    dest = ROOT / "harness" / "last_real_test2.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("exits", dict(exits))
    print("tiers", dict(tiers))
    print("accounted_usd", spend)
    print("wrote", dest)
    _plots(out)
    return 0


def _plots(out: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print("plots skipped:", exc)
        return
    plot_dir = ROOT / "harness" / "plots"
    plot_dir.mkdir(exist_ok=True)
    exits = out["exit_counts"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(list(exits.keys()), list(exits.values()), color="#6a92ff")
    ax.set_title("real_test-2 exit layers (honest counts)")
    ax.set_ylabel("requests")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(plot_dir / "test2_exits.png", dpi=120)
    plt.close()
    paid = [r for r in out["rows"] if (r.get("cost_usd") or 0) > 0]
    if paid:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.barh([r["name"] for r in paid], [r["cost_usd"] for r in paid], color="#f5a623")
        ax.set_title("real_test-2 paid calls (CLEVER table $)")
        ax.set_xlabel("USD")
        fig.tight_layout()
        fig.savefig(plot_dir / "test2_paid.png", dpi=120)
        plt.close()
    print("plots", plot_dir)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
