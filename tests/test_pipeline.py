import pytest

from gateway.layers.myelination import MyelinDecision
from gateway.models import RouteRequest
from gateway.pipeline import route
from gateway.providers.mock import MockProvider
from tests.fakes import FakeRedis


async def _noop(*_a, **_k):
    return None


_GROUNDED_EMAIL = (
    "Dear Ada, our records show account 4021 invoice INV-1 totalling $12 "
    "remains outstanding as of last contact. Please arrange payment at your "
    "earliest convenience so we can close this item on the aging report."
)


class State:
    def __init__(self):
        self.provider = MockProvider()
        self.pool = None
        self.redis = FakeRedis()


@pytest.mark.asyncio
async def test_template_short_circuit_no_llm():
    st = State()
    resp = await route(RouteRequest(query="what is today's date"), st)
    assert resp.status == "ok"
    assert any(e.get("layer") == "ras.template" and e.get("result") == "HIT" for e in resp.decision_trace)
    assert st.provider.calls == []
    assert resp.accounting.cost_usd == 0.0
    assert resp.accounting.tokens_in == 0
    assert resp.intent  # classified


@pytest.mark.asyncio
async def test_remit_pending_no_llm():
    st = State()
    resp = await route(RouteRequest(query="please remit payment for 40211"), st)
    assert resp.status == "pending_confirmation"
    assert resp.confirmation_id
    assert st.provider.calls == []
    assert "confirm_token" in resp.response.lower() or "mutation" in resp.response.lower()


@pytest.mark.asyncio
async def test_remit_with_token_calls_strong():
    st = State()
    first = await route(RouteRequest(query="please remit payment for 40211"), st)
    assert first.status == "pending_confirmation"
    second = await route(
        RouteRequest(query="please remit payment for 40211", confirm_token=first.confirmation_id),
        st,
    )
    assert second.status == "ok"
    assert len(st.provider.calls) == 1
    assert st.provider.calls[0]["tier"] == "strong"


@pytest.mark.asyncio
async def test_campaign_send_pending():
    st = State()
    resp = await route(RouteRequest(query="launch campaign to the west list"), st)
    assert resp.status == "pending_confirmation"
    assert st.provider.calls == []


@pytest.mark.asyncio
async def test_empty_context_not_85_percent():
    st = State()
    resp = await route(RouteRequest(query="draft email to the customer about invoice"), st)
    comp = next(e for e in resp.decision_trace if e.get("layer") == "compressor")
    assert comp["reduction_pct"] == 0.0
    assert resp.accounting.saved_pct < 85.0 or resp.model_tier == "strong"


@pytest.mark.asyncio
async def test_cache_second_call_zero_cost(monkeypatch):
    st = State()

    async def eligible(*a, **k):
        return MyelinDecision(
            eligible=True, phase="stable", p_hat=0.96, sigma=0.02,
            n_obs=120, lcb=0.93, decision="cheap_ok",
        )

    monkeypatch.setattr("gateway.pipeline.myelination.check", eligible)
    monkeypatch.setattr("gateway.pipeline.myelination.update", _noop)
    st.provider.cheap_text = _GROUNDED_EMAIL
    st.provider.strong_text = _GROUNDED_EMAIL

    req = RouteRequest(
        query="draft email to the customer about invoice",
        context={"account": "4021", "contact": "Ada", "balance": 12, "invoice_ids": ["INV-1"], "last_contact": "2026-01-01"},
    )
    first = await route(req, st)
    assert first.status == "ok"
    assert first.accounting.cache_hit is False
    n_calls = len(st.provider.calls)
    second = await route(req, st)
    assert second.accounting.cache_hit is True
    assert second.accounting.cost_usd == 0.0
    assert len(st.provider.calls) == n_calls


@pytest.mark.asyncio
async def test_cache_does_not_cross_accounts(monkeypatch):
    st = State()

    async def eligible(*a, **k):
        return MyelinDecision(
            eligible=True, phase="stable", p_hat=0.96, sigma=0.02,
            n_obs=120, lcb=0.93, decision="cheap_ok",
        )

    monkeypatch.setattr("gateway.pipeline.myelination.check", eligible)
    monkeypatch.setattr("gateway.pipeline.myelination.update", _noop)
    st.provider.cheap_text = _GROUNDED_EMAIL
    st.provider.strong_text = _GROUNDED_EMAIL

    a = RouteRequest(query="draft email please", context={"account": "1", "contact": "A", "balance": 1, "invoice_ids": [], "last_contact": None})
    b = RouteRequest(query="draft email please", context={"account": "2", "contact": "B", "balance": 2, "invoice_ids": [], "last_contact": None})
    await route(a, st)
    second = await route(b, st)
    assert second.accounting.cache_hit is False


@pytest.mark.asyncio
async def test_escalate_bills_both_legs(monkeypatch):
    st = State()
    st.provider.cheap_text = "no"

    async def eligible(*a, **k):
        return MyelinDecision(
            eligible=True, phase="stable", p_hat=0.96, sigma=0.02,
            n_obs=120, lcb=0.93, decision="cheap_ok",
        )

    monkeypatch.setattr("gateway.pipeline.myelination.check", eligible)
    monkeypatch.setattr("gateway.pipeline.myelination.update", _noop)

    resp = await route(RouteRequest(query="draft email to the customer about invoice"), st)
    cascade = next(e for e in resp.decision_trace if e.get("layer") == "cascade")
    assert cascade["escalated"] is True
    assert len(cascade["legs"]) == 2
    assert resp.accounting.tokens_in == sum(l["tokens_in"] for l in cascade["legs"])
