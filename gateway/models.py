"""API contract. Field names are provider-agnostic."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from gateway.config import settings


class RouteRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    context: dict[str, Any] = Field(default_factory=dict)
    feature_class: str = "collections_outreach"
    intent_hint: Optional[str] = None
    stakes: Literal["auto", "read", "mutate"] = "auto"
    mode: Literal["clever", "baseline"] = "clever"
    llm_backend: Literal["auto", "bedrock", "openai_compat", "mock"] = "auto"
    confirm_token: Optional[str] = None
    outcome_count: int = Field(default=1, ge=1, le=10_000)

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        q = v.strip()
        if not q:
            raise ValueError("query must not be empty")
        return q

    @model_validator(mode="after")
    def _context_size(self):
        import json
        raw = json.dumps(self.context, default=str)
        if len(raw.encode("utf-8")) > settings.CONTEXT_MAX_BYTES:
            raise ValueError("context exceeds size limit")
        return self


class AccountingResult(BaseModel):
    tokens_in: int
    tokens_out: int
    cost_usd: float
    baseline_cost_usd: float
    saved_usd: float
    saved_pct: float
    cache_hit: bool = False
    baseline_method: str = "uncompressed_prompt_strong_tier"


class QualityResult(BaseModel):
    checked: bool
    method: str
    score: Optional[float] = None
    passed: Optional[bool] = None
    reason: Optional[str] = None


class RouteResponse(BaseModel):
    request_id: str
    status: Literal["ok", "pending_confirmation", "blocked", "error"] = "ok"
    confirmation_id: Optional[str] = None
    response: str
    decision_trace: list[dict[str, Any]]
    accounting: AccountingResult
    quality: QualityResult
    latency_ms: int
    intent: Optional[str] = None
    model_tier: Optional[str] = None
