"""Detect whether a query is a direct entity lookup. Invoice ids win over year-like digits."""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

_INVOICE_RE = re.compile(r"\b(INV-[\d-]+)\b", re.IGNORECASE)
# 5–8 digits, not part of an INV- token, not a 4-digit year
_ACCOUNT_RE = re.compile(r"(?<!INV-)(?<![A-Za-z-])\b(\d{5,8})\b")

_LOOKUP_VERBS = [
    "what is", "what's", "show me", "get", "fetch",
    "how many", "balance on", "status of", "days overdue",
    "tell me about", "look up", "lookup",
]


def attempt(query: str, pool=None) -> Optional[dict]:
    q = query.lower()
    if not any(v in q for v in _LOOKUP_VERBS):
        return None

    invoice_match = _INVOICE_RE.search(query)
    if invoice_match:
        hint = {
            "entity_type": "invoice",
            "entity_value": invoice_match.group(1).upper(),
            "field_ask": _infer_field(q),
        }
        log.info("ras.structured_lookup candidate entity=%s field=%s",
                 hint["entity_value"], hint["field_ask"])
        return hint

    account_match = _ACCOUNT_RE.search(query)
    if not account_match:
        return None

    hint = {
        "entity_type": "account",
        "entity_value": account_match.group(1),
        "field_ask": _infer_field(q),
    }
    log.info("ras.structured_lookup candidate entity=%s field=%s",
             hint["entity_value"], hint["field_ask"])
    return hint


def _infer_field(q: str) -> str:
    if "balance" in q:
        return "balance"
    if "overdue" in q or "days" in q:
        return "days_overdue"
    if "status" in q:
        return "status"
    if "contact" in q:
        return "contact"
    return "summary"
