"""OpenAI-compatible chat completions client. Vendor is configured via env, not code."""
from __future__ import annotations

import time

from openai import AsyncOpenAI

from gateway.config import settings
from gateway.providers.base import Completion


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self) -> None:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY is required for openai_compat")
        if not settings.LLM_BASE_URL:
            raise RuntimeError("LLM_BASE_URL is required for openai_compat")
        cheap = settings.compat_model("cheap")
        strong = settings.compat_model("strong")
        if not cheap or not strong:
            raise RuntimeError("COMPAT_MODEL_* or MODEL_CHEAP/STRONG must be set")
        self._client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT_S,
            max_retries=2,
        )
        self._models = {"cheap": cheap, "strong": strong}

    async def complete(
        self,
        *,
        tier: str,
        messages: list[dict],
        max_tokens: int | None = None,
    ) -> Completion:
        if tier not in self._models:
            raise ValueError(f"unknown tier {tier}")
        model_id = self._models[tier]
        start = time.time()
        kwargs: dict = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        }
        thinking = (settings.LLM_THINKING or "disabled").lower()
        if thinking in ("disabled", "enabled"):
            kwargs["extra_body"] = {"thinking": {"type": thinking}}
        resp = await self._client.chat.completions.create(**kwargs)
        if not resp.usage:
            raise RuntimeError("provider response missing usage; refuse to invent tokens")
        msg = resp.choices[0].message
        text = (msg.content or "").strip()
        if not text:
            reasoning = getattr(msg, "reasoning_content", None) or ""
            text = str(reasoning).strip()
        return Completion(
            text=text,
            tokens_in=int(resp.usage.prompt_tokens),
            tokens_out=int(resp.usage.completion_tokens),
            model_id=model_id,
            tier=tier,
            latency_ms=int((time.time() - start) * 1000),
        )
