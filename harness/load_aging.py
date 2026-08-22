"""Load synthetic aging JSON into Postgres. Do not point this at production files."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import asyncpg

from gateway.config import settings

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "aging.json"


async def load(path: Path, dsn: str) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data["version"]
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO data_versions (version, status) VALUES ($1, 'active') ON CONFLICT (version) DO NOTHING",
            version,
        )
        await conn.execute(
            """
            INSERT INTO active_pointer (id, active_aging_version)
            VALUES (true, $1)
            ON CONFLICT (id) DO UPDATE SET active_aging_version = EXCLUDED.active_aging_version
            """,
            version,
        )
        await conn.execute("DELETE FROM aging_data WHERE aging_version = $1", version)
        n = 0
        for row in data["rows"]:
            await conn.execute(
                """
                INSERT INTO aging_data (
                    aging_version, account_id, account, balance, days_overdue,
                    status, contact, invoice_ids
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                version, row["account_id"], row["account"], row["balance"],
                row["days_overdue"], row["status"], row["contact"], row["invoice_ids"],
            )
            n += 1
        return n
    finally:
        await conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", type=Path, default=_FIXTURE)
    p.add_argument("--dsn", default=settings.POSTGRES_DSN)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    data = json.loads(args.file.read_text(encoding="utf-8"))
    print(f"version={data['version']} rows={len(data['rows'])} file={args.file}")
    if args.dry_run:
        return
    n = asyncio.run(load(args.file, args.dsn))
    print(f"loaded {n} rows")


if __name__ == "__main__":
    main()
