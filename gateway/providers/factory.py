"""Build every LLM backend that has credentials. Default follows LLM_PROVIDER."""
from __future__ import annotations

import logging

from gateway.config import settings
from gateway.providers.base import Provider
from gateway.providers.mock import MockProvider

log = logging.getLogger(__name__)


def _try_compat() -> Provider | None:
    if not settings.compat_configured():
        return None
    try:
        from gateway.providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider()
    except Exception as exc:
        log.warning("openai_compat not started: %s", exc)
        return None


def _try_bedrock() -> Provider | None:
    if not settings.bedrock_configured():
        return None
    try:
        from gateway.providers.bedrock import BedrockProvider
        return BedrockProvider()
    except Exception as exc:
        log.warning("bedrock not started: %s", exc)
        return None


def build_providers() -> tuple[Provider, dict[str, Provider]]:
    """Return (default, {name: provider}). Mock is last-resort, never silent."""
    if settings.compat_partial():
        raise RuntimeError(
            "HTTP API config is incomplete. Set LLM_API_KEY, LLM_BASE_URL, "
            "COMPAT_MODEL_CHEAP, and COMPAT_MODEL_STRONG (or MODEL_CHEAP / MODEL_STRONG). "
            "Refusing to fall back to mock while a partial key is present."
        )
    if settings.bedrock_partial():
        raise RuntimeError(
            "Bedrock config is incomplete. Set AWS keys (or AWS_PROFILE), AWS_REGION, "
            "BEDROCK_MODEL_CHEAP, and BEDROCK_MODEL_STRONG. Refusing mock fallback."
        )

    available: dict[str, Provider] = {}
    compat = _try_compat()
    if compat is not None:
        available["openai_compat"] = compat
        log.info("backend ready: openai_compat")
    bedrock = _try_bedrock()
    if bedrock is not None:
        available["bedrock"] = bedrock
        log.info("backend ready: bedrock")
    # Mock only when no live backend is configured, or LLM_PROVIDER=mock.
    if not available or (settings.LLM_PROVIDER or "").strip().lower() == "mock":
        available["mock"] = MockProvider()
        if (settings.LLM_PROVIDER or "").strip().lower() != "mock":
            log.warning("no live LLM configured; using mock. Fill .env and restart.")

    wanted = (settings.LLM_PROVIDER or "auto").strip().lower()
    if wanted == "auto":
        for name in ("bedrock", "openai_compat", "mock"):
            if name in available:
                log.info("default provider=%s (auto)", name)
                return available[name], available
    if wanted in available:
        log.info("default provider=%s", wanted)
        return available[wanted], available
    raise RuntimeError(
        f"LLM_PROVIDER={wanted} is not available. "
        f"ready={sorted(available)} "
        "Fill Bedrock AWS_* keys or openai_compat LLM_API_KEY/LLM_BASE_URL."
    )


def build_provider() -> Provider:
    default, _ = build_providers()
    return default


def pick_provider(app_state, name: str | None) -> Provider:
    wanted = (name or "auto").strip().lower()
    catalog = getattr(app_state, "providers", None) or {}
    if wanted in ("", "auto"):
        return app_state.provider
    if wanted in catalog:
        return catalog[wanted]
    if getattr(app_state.provider, "name", None) == wanted:
        return app_state.provider
    ready = sorted(catalog) or [getattr(app_state.provider, "name", "unknown")]
    raise RuntimeError(f"llm_backend '{wanted}' is not configured; ready={ready}")
