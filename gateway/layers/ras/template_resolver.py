"""Deterministic templates. No eval. Date group indexes are tested."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

log = logging.getLogger(__name__)


def _today(_m, _q):
    return f"Today is {date.today().strftime('%B %d, %Y')}."


def _date_diff(m, _q):
    try:
        d1 = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        d2 = date.today()
        delta = (d2 - d1).days
        return f"{delta} days between {d1.isoformat()} and today ({d2.isoformat()})."
    except Exception:
        return None


def _invoice_format(m, _q):
    return f"Invoice reference: {m.group(1).upper()}"


def _days_from_now(m, _q):
    # groups: (far|many days) (until|to|from) (DATE)
    try:
        d1 = datetime.strptime(m.group(3), "%Y-%m-%d").date()
        d2 = date.today()
        delta = (d1 - d2).days
        if delta > 0:
            return f"{d1.isoformat()} is {delta} days from today."
        if delta == 0:
            return f"{d1.isoformat()} is today."
        return f"{d1.isoformat()} was {abs(delta)} days ago."
    except Exception:
        return None


_RESOLVERS = [
    (re.compile(r"\b(today|current date|what date is it|what is today)\b", re.I), _today),
    (re.compile(r"days between (\d{4}-\d{2}-\d{2}) and today", re.I), _date_diff),
    (re.compile(r"how (far|many days) (until|to|from) (\d{4}-\d{2}-\d{2})", re.I), _days_from_now),
    (re.compile(r"format invoice (INV-[\d-]+)", re.I), _invoice_format),
]


def attempt(query: str) -> Optional[dict]:
    for pattern, handler in _RESOLVERS:
        m = pattern.search(query)
        if m:
            result = handler(m, query)
            if result:
                log.info("ras.template HIT pattern=%r", pattern.pattern[:40])
                return {"response": result, "resolver": pattern.pattern}
    return None
