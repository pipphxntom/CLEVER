"""API key auth. Route key vs admin key. Constant-time compare."""
from __future__ import annotations

import hmac
from collections import defaultdict
from time import time

from fastapi import Header, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

GATEWAY_KEY = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    scheme_name="GatewayKey",
    description="Gateway key (local default: dev-key-change-me). Not the LLM vendor key.",
)

from gateway.config import settings

_WINDOW = 60.0
_hits: dict[str, list[float]] = defaultdict(list)


def _extract(x_api_key: str | None, authorization: str | None) -> str:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _check(offered: str, expected: str) -> bool:
    if not offered or not expected:
        return False
    return hmac.compare_digest(offered, expected)


def _rate_limit(key: str) -> None:
    now = time()
    bucket = _hits[key]
    _hits[key] = [t for t in bucket if now - t < _WINDOW]
    if len(_hits[key]) >= settings.RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate_limited")
    _hits[key].append(now)


async def require_api_key(
    request: Request,
    x_api_key: str | None = Security(GATEWAY_KEY),
    authorization: str | None = Header(default=None),
) -> str:
    offered = _extract(x_api_key, authorization)
    if not _check(offered, settings.CLEVER_API_KEY) and not _check(
        offered, settings.CLEVER_ADMIN_KEY
    ):
        raise HTTPException(status_code=401, detail="unauthorized")
    # Dashboard/chat poll GET /v1/stats every 2s. Rate-limiting those
    # (same key as POST /v1/route) made the UI look "dead" at 60/min.
    if request.method != "GET":
        _rate_limit(offered)
    request.state.api_key = offered
    return offered


async def require_admin_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> str:
    offered = _extract(x_api_key, authorization)
    if not _check(offered, settings.CLEVER_ADMIN_KEY):
        raise HTTPException(status_code=401, detail="unauthorized")
    _rate_limit(offered)
    return offered
