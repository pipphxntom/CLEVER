"""Run the lookup against aging_data. Parameterized SQL only."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


async def resolve(hint: dict, pool) -> Optional[str]:
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM aging_data")
            if not count:
                log.info("ras.structured_resolver: aging_data empty — miss")
                return None

            if hint["entity_type"] == "invoice":
                row = await conn.fetchrow(
                    """
                    SELECT account, account_id, balance, days_overdue, status, contact, invoice_ids
                    FROM aging_data
                    WHERE $1 = ANY(invoice_ids)
                      AND aging_version = (
                          SELECT active_aging_version FROM active_pointer LIMIT 1
                      )
                    LIMIT 1
                    """,
                    hint["entity_value"],
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT account, account_id, balance, days_overdue, status, contact, invoice_ids
                    FROM aging_data
                    WHERE account_id = $1
                      AND aging_version = (
                          SELECT active_aging_version FROM active_pointer LIMIT 1
                      )
                    LIMIT 1
                    """,
                    hint["entity_value"],
                )

            if not row:
                log.info("ras.structured_resolver: %s %s not found",
                         hint["entity_type"], hint["entity_value"])
                return None
            return _format(row, hint["field_ask"])
    except Exception as exc:
        log.warning("ras.structured_resolver error: %s", exc)
        return None


def _format(row, field: str) -> str:
    name = row["account"] or row["account_id"]
    if field == "balance":
        return f"Account {name}: balance ${float(row['balance']):,.2f}"
    if field == "days_overdue":
        return f"Account {name}: {row['days_overdue']} days overdue"
    if field == "status":
        return f"Account {name}: status = {row['status']}"
    if field == "contact":
        return f"Account {name}: contact = {row['contact']}"
    return (
        f"Account {name} — "
        f"Balance: ${float(row['balance']):,.2f} | "
        f"Days overdue: {row['days_overdue']} | "
        f"Status: {row['status']}"
    )
