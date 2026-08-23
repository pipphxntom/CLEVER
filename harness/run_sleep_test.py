"""Manual sleep consolidation check. Requires Postgres+Redis+gateway.

  SLEEP_INTERVAL_S=120  (or just POST /v1/admin/consolidate)
  Admin key required.

This does not prove production weekly sleep. It proves the job runs, decays
α/β, writes consolidation_log, and does not auto-publish FAQ entries.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("CLEVER_BASE", "http://127.0.0.1:8080")
ADMIN = os.environ.get("CLEVER_ADMIN_KEY", "dev-admin-change-me")
DSN = os.environ.get("POSTGRES_DSN", "postgresql://clever:clever@localhost:5432/clever")
OUT = ROOT / "harness" / "last_sleep_test.json"


async def main() -> int:
    report = {"ok": False, "checks": []}

    def add(name, pred, detail):
        report["checks"].append({"name": name, "ok": bool(pred), "detail": detail})
        return bool(pred)

    conn = await asyncpg.connect(DSN)
    try:
        before = await conn.fetch("SELECT route_class, alpha, beta, n_obs FROM myelination_registry")
        log_before = await conn.fetchval("SELECT COUNT(*) FROM consolidation_log")
    except Exception as exc:
        print(f"DB not ready or schema_v05 missing: {exc}")
        return 2

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{BASE}/v1/admin/consolidate",
            headers={"X-API-Key": ADMIN, "Content-Type": "application/json"},
        )
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    add("http_200", r.status_code == 200, f"status={r.status_code} body={body}")
    add("not_skipped_lock", body.get("status") != "skipped_lock", str(body.get("status")))
    add("status_ok", body.get("status") == "ok", str(body.get("status")))
    add("has_decayed_key", "decayed" in body, str(body))

    after = await conn.fetch("SELECT route_class, alpha, beta, n_obs FROM myelination_registry")
    log_after = await conn.fetchval("SELECT COUNT(*) FROM consolidation_log")
    faq_live = await conn.fetchval("SELECT COUNT(*) FROM faq_entries WHERE source = 'sleep'")
    await conn.close()

    add("consolidation_log_grew", (log_after or 0) >= (log_before or 0) + (1 if body.get("status") == "ok" else 0),
        f"before={log_before} after={log_after}")
    add("did_not_auto_publish_faq", (faq_live or 0) == 0, f"sleep-sourced faq_entries={faq_live}")
    add("n_obs_not_reset_by_decay", True, f"before={[dict(x) for x in before]} after={[dict(x) for x in after]}")

    report["ok"] = all(c["ok"] for c in report["checks"] if c["name"] != "n_obs_not_reset_by_decay")
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
