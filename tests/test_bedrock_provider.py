"""Bedrock adapter unit tests. No AWS calls."""
from __future__ import annotations

import pytest

from gateway.providers.bedrock import (
    BedrockProvider,
    extract_text,
    extract_usage,
    split_messages,
)


def test_split_system_and_turns():
    system, conv = split_messages(
        [
            {"role": "system", "content": "You are CLEVER."},
            {"role": "user", "content": "balance?"},
            {"role": "assistant", "content": "12500"},
            {"role": "user", "content": "again"},
        ]
    )
    assert system == [{"text": "You are CLEVER."}]
    assert conv[0]["role"] == "user"
    assert conv[0]["content"] == [{"text": "balance?"}]
    assert conv[1]["role"] == "assistant"
    assert conv[2]["role"] == "user"


def test_split_user_only():
    system, conv = split_messages([{"role": "user", "content": "hello"}])
    assert system == []
    assert len(conv) == 1


def test_extract_text_and_usage():
    resp = {
        "output": {"message": {"content": [{"text": "ok"}]}},
        "usage": {"inputTokens": 11, "outputTokens": 4},
    }
    assert extract_text(resp) == "ok"
    assert extract_usage(resp) == (11, 4)


def test_extract_usage_refuses_to_invent():
    with pytest.raises(RuntimeError, match="missing usage"):
        extract_usage({"output": {"message": {"content": [{"text": "x"}]}}})


class _FakeClient:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.resp


@pytest.mark.asyncio
async def test_complete_uses_converse_and_real_usage(monkeypatch):
    monkeypatch.setattr("gateway.config.settings.MODEL_CHEAP", "cheap-id")
    monkeypatch.setattr("gateway.config.settings.MODEL_STRONG", "strong-id")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_CHEAP", "")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_STRONG", "")
    monkeypatch.setattr("gateway.config.settings.AWS_REGION", "us-east-1")
    monkeypatch.setattr("gateway.config.settings.LLM_MAX_TOKENS", 64)
    monkeypatch.setattr("gateway.config.settings.LLM_THINKING", "disabled")
    client = _FakeClient(
        {
            "output": {"message": {"content": [{"text": "Northwind 12500"}]}},
            "usage": {"inputTokens": 9, "outputTokens": 6},
        }
    )
    p = BedrockProvider(client=client)
    out = await p.complete(tier="cheap", messages=[{"role": "user", "content": "hi"}])
    assert out.text == "Northwind 12500"
    assert out.tokens_in == 9
    assert out.tokens_out == 6
    assert out.model_id == "cheap-id"
    assert out.tier == "cheap"
    assert client.calls[0]["modelId"] == "cheap-id"
    assert client.calls[0]["inferenceConfig"]["maxTokens"] == 64
    assert "additionalModelRequestFields" not in client.calls[0]


@pytest.mark.asyncio
async def test_complete_rejects_empty_text(monkeypatch):
    monkeypatch.setattr("gateway.config.settings.MODEL_CHEAP", "cheap-id")
    monkeypatch.setattr("gateway.config.settings.MODEL_STRONG", "strong-id")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_CHEAP", "")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_STRONG", "")
    monkeypatch.setattr("gateway.config.settings.AWS_REGION", "us-east-1")
    p = BedrockProvider(
        client=_FakeClient(
            {
                "output": {"message": {"content": []}},
                "usage": {"inputTokens": 1, "outputTokens": 0},
            }
        )
    )
    with pytest.raises(RuntimeError, match="empty text"):
        await p.complete(tier="strong", messages=[{"role": "user", "content": "x"}])


def test_factory_bedrock(monkeypatch):
    monkeypatch.setattr("gateway.config.settings.LLM_PROVIDER", "bedrock")
    monkeypatch.setattr("gateway.config.settings.MODEL_CHEAP", "c")
    monkeypatch.setattr("gateway.config.settings.MODEL_STRONG", "s")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_CHEAP", "c")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_STRONG", "s")
    monkeypatch.setattr("gateway.config.settings.AWS_REGION", "us-east-1")
    monkeypatch.setattr("gateway.config.settings.AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setattr("gateway.config.settings.AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr("gateway.config.settings.AWS_SESSION_TOKEN", "tok")
    from gateway.providers.bedrock import BedrockProvider
    from gateway.providers.factory import build_provider

    monkeypatch.setattr(BedrockProvider, "__init__", lambda self, client=None: None)
    p = build_provider()
    assert isinstance(p, BedrockProvider)


def test_auto_falls_to_mock_without_creds(monkeypatch):
    monkeypatch.setattr("gateway.config.settings.LLM_PROVIDER", "auto")
    monkeypatch.setattr("gateway.config.settings.LLM_API_KEY", "")
    monkeypatch.setattr("gateway.config.settings.LLM_BASE_URL", "")
    monkeypatch.setattr("gateway.config.settings.AWS_ACCESS_KEY_ID", "")
    monkeypatch.setattr("gateway.config.settings.AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setattr("gateway.config.settings.AWS_PROFILE", "")
    from gateway.providers.factory import build_providers
    from gateway.providers.mock import MockProvider

    default, available = build_providers()
    assert isinstance(default, MockProvider)
    assert "mock" in available
    assert "bedrock" not in available
    assert "openai_compat" not in available


def test_bedrock_static_keys_skip_profile(monkeypatch):
    import sys
    import types

    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_CHEAP", "cheap-id")
    monkeypatch.setattr("gateway.config.settings.BEDROCK_MODEL_STRONG", "strong-id")
    monkeypatch.setattr("gateway.config.settings.AWS_REGION", "us-west-2")
    monkeypatch.setattr("gateway.config.settings.AWS_ACCESS_KEY_ID", "ASIAABC")
    monkeypatch.setattr("gateway.config.settings.AWS_SECRET_ACCESS_KEY", "sec")
    monkeypatch.setattr("gateway.config.settings.AWS_SESSION_TOKEN", "tok")
    monkeypatch.setattr("gateway.config.settings.AWS_PROFILE", "cvt-aws-developer-sandbox")

    captured = {}

    class FakeSession:
        def __init__(self, **kw):
            captured.update(kw)

        def client(self, *args, **kwargs):
            return object()

    class FakeConfig:
        def __init__(self, **kw):
            pass

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.Session = FakeSession
    cfg_mod = types.ModuleType("botocore.config")
    cfg_mod.Config = FakeConfig
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "botocore.config", cfg_mod)

    p = BedrockProvider()
    assert captured["aws_access_key_id"] == "ASIAABC"
    assert captured["aws_secret_access_key"] == "sec"
    assert captured["aws_session_token"] == "tok"
    assert captured["region_name"] == "us-west-2"
    assert "profile_name" not in captured
    assert p._uses_static_keys is True


def test_pick_provider_explicit(monkeypatch):
    from types import SimpleNamespace
    from gateway.providers.factory import pick_provider
    from gateway.providers.mock import MockProvider

    mock = MockProvider()
    st = SimpleNamespace(provider=mock, providers={"mock": mock})
    assert pick_provider(st, "auto") is mock
    assert pick_provider(st, "mock") is mock
    try:
        pick_provider(st, "bedrock")
        assert False, "expected error"
    except RuntimeError as exc:
        assert "bedrock" in str(exc)
