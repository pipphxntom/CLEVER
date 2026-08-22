"""A/B: same queries in clever vs baseline. Live API. No secrets in output."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

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


CASES = [
    {"id": "date", "body": {"query": "what is today's date"}},
    {"id": "faq", "body": {"query": "who handles disputes"}},
    {"id": "balance", "body": {"query": "what is the balance on account 40211", "context": {"aging_version": "synthetic-v1"}}},
    {"id": "dunning", "body": {"query": None, "context": CTX}},  # filled unique
]


async def once(client, body, mode):
    payload = {**body, "mode": mode}
    r = await client.post(f"{BASE}/v1/route", headers=HEADERS, json=payload, timeout=180)
    data = r.json()
    acc = data.get("accounting") or {}
    return {
        "http": r.status_code,
        "status": data.get("status"),
        "intent": data.get("intent"),
        "tier": data.get("model_tier"),
        "tokens_in": acc.get("tokens_in"),
        "tokens_out": acc.get("tokens_out"),
        "cost_usd": acc.get("cost_usd"),
        "cache_hit": acc.get("cache_hit"),
        "layers": [e.get("layer") for e in data.get("decision_trace") or []],
        "preview": (data.get("response") or "")[:120],
    }


async def main():
    tag = uuid.uuid4().hex[:6]
    CASES[3]["body"]["query"] = f"Write a short collections dunning email. AB {tag}."
    rows = []
    async with httpx.AsyncClient() as client:
        h = (await client.get(f"{BASE}/health")).json()
        if h.get("provider") != "openai_compat":
            print("STOP provider", h.get("provider"))
            return 2
        for case in CASES:
            clever = await once(client, case["body"], "clever")
            baseline = await once(client, case["body"], "baseline")
            rows.append({"id": case["id"], "clever": clever, "baseline": baseline})
            print(f"{case['id']:10} clever $={clever['cost_usd']} in={clever['tokens_in']} "
                  f"base $={baseline['cost_usd']} in={baseline['tokens_in']} "
                  f"tier={clever['tier']}/{baseline['tier']}")
    dest = ROOT / "harness" / "last_ab.json"
    dest.write_text(json.dumps({"provider": "openai_compat", "rows": rows}, indent=2), encoding="utf-8")
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
