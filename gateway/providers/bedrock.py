"""AWS Bedrock Runtime adapter. Converse API so model IDs stay opaque env strings.

Auth is the normal boto3 chain: AWS_PROFILE (SSO), env keys, or instance role.
Does not invent token counts. Missing usage is an error.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from gateway.config import settings
from gateway.providers.base import Completion

log = logging.getLogger(__name__)


def split_messages(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """OpenAI-style messages -> Bedrock Converse system + messages."""
    system: list[dict] = []
    conv: list[dict] = []
    for m in messages or []:
        role = (m.get("role") or "user").lower()
        content = m.get("content")
        if content is None:
            text = ""
        elif isinstance(content, str):
            text = content
        else:
            text = str(content)
        if role == "system":
            if text.strip():
                system.append({"text": text})
            continue
        br = "assistant" if role == "assistant" else "user"
        conv.append({"role": br, "content": [{"text": text}]})
    return system, conv


def extract_text(resp: dict[str, Any]) -> str:
    msg = ((resp or {}).get("output") or {}).get("message") or {}
    parts: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def extract_usage(resp: dict[str, Any]) -> tuple[int, int]:
    usage = (resp or {}).get("usage") or {}
    if "inputTokens" not in usage or "outputTokens" not in usage:
        raise RuntimeError("provider response missing usage; refuse to invent tokens")
    return int(usage["inputTokens"]), int(usage["outputTokens"])


class BedrockProvider:
    name = "bedrock"

    def __init__(self, client=None) -> None:
        cheap = settings.bedrock_model("cheap")
        strong = settings.bedrock_model("strong")
        if not cheap or not strong:
            raise RuntimeError("BEDROCK_MODEL_CHEAP/STRONG or MODEL_CHEAP/STRONG must be set for bedrock")
        if not (settings.AWS_REGION or "").strip():
            raise RuntimeError("AWS_REGION must be set for bedrock")
        self._models = {"cheap": cheap, "strong": strong}
        self._region = settings.AWS_REGION.strip()
        self._profile = (settings.AWS_PROFILE or "").strip() or None
        self._uses_static_keys = settings.bedrock_has_static_keys()
        if client is not None:
            self._client = client
            return
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for LLM_PROVIDER=bedrock") from exc
        cfg = Config(
            connect_timeout=min(10.0, float(settings.LLM_TIMEOUT_S)),
            read_timeout=float(settings.LLM_TIMEOUT_S),
            retries={"max_attempts": 2, "mode": "standard"},
        )
        session_kw: dict[str, Any] = {"region_name": self._region}
        if self._uses_static_keys:
            session_kw["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID.strip()
            session_kw["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY.strip()
            token = (settings.AWS_SESSION_TOKEN or "").strip()
            if token:
                session_kw["aws_session_token"] = token
        elif self._profile:
            session_kw["profile_name"] = self._profile
        session = boto3.Session(**session_kw)
        self._client = session.client("bedrock-runtime", config=cfg)
        auth = "static_keys" if self._uses_static_keys else (
            f"profile={self._profile}" if self._profile else "default_chain"
        )
        log.info(
            "bedrock client region=%s auth=%s cheap=%s strong=%s",
            self._region,
            auth,
            self._models["cheap"],
            self._models["strong"],
        )

    def _converse_sync(self, *, model_id: str, messages: list[dict], max_tokens: int) -> dict:
        system, conv = split_messages(messages)
        if not conv:
            raise RuntimeError("bedrock converse requires at least one non-system message")
        kwargs: dict[str, Any] = {
            "modelId": model_id,
            "messages": conv,
            "inferenceConfig": {"maxTokens": int(max_tokens)},
        }
        if system:
            kwargs["system"] = system
        thinking = (settings.LLM_THINKING or "disabled").lower()
        if thinking == "enabled":
            kwargs["additionalModelRequestFields"] = {"thinking": {"type": "enabled"}}
        return self._client.converse(**kwargs)

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
        try:
            resp = await asyncio.to_thread(
                self._converse_sync,
                model_id=model_id,
                messages=messages,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            )
        except Exception as exc:
            log.exception("bedrock converse failed tier=%s model=%s", tier, model_id)
            raise RuntimeError(f"bedrock converse failed: {exc}") from exc
        if not isinstance(resp, dict):
            # boto3 returns a dict-like Response. Normalize.
            resp = dict(resp)
        text = extract_text(resp)
        tokens_in, tokens_out = extract_usage(resp)
        if not text:
            raise RuntimeError("bedrock returned empty text")
        return Completion(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_id=model_id,
            tier=tier,
            latency_ms=int((time.time() - start) * 1000),
        )
