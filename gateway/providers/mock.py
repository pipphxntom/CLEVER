"""Deterministic test/dev provider. Token counts are tokenizer-measured, never random."""
from __future__ import annotations

import time

from gateway.providers.base import Completion
from gateway.tokens import count_tokens

_CANNED = {
    "triage": (
        "Top overdue accounts: Account 4021 ($12,500, 45 days overdue), "
        "Account 3887 ($8,200, 32 days overdue), Account 5541 ($3,100, 28 days overdue)."
    ),
    "email_draft": (
        "Dear Valued Customer, our records show invoice INV-2024-089 "
        "totalling $12,500 remains outstanding. Please arrange payment at your "
        "earliest convenience or contact us to discuss options."
    ),
    "inbox_check": (
        "3 new replies. Account 4021 disputed invoice INV-2024-089 — "
        "sentiment: frustrated. Requires human review."
    ),
    "default": (
        "Here is a concise collections response based on the supplied context. "
        "Outstanding balance is as listed. Recommend a standard dunning follow-up."
    ),
}


class MockProvider:
    name = "mock"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.cheap_text: str | None = None
        self.strong_text: str | None = None

    def reset(self) -> None:
        self.calls.clear()
        self.cheap_text = None
        self.strong_text = None

    async def complete(
        self,
        *,
        tier: str,
        messages: list[dict],
        max_tokens: int | None = None,
    ) -> Completion:
        start = time.time()
        prompt = ""
        if messages:
            prompt = str(messages[-1].get("content") or "")
        blob = prompt.lower()
        key = "default"
        for k in ("triage", "email_draft", "inbox_check"):
            if k in blob:
                key = k
                break
        text = _CANNED[key]
        if tier == "cheap" and self.cheap_text is not None:
            text = self.cheap_text
        if tier == "strong" and self.strong_text is not None:
            text = self.strong_text
        tokens_in = count_tokens(prompt)
        tokens_out = count_tokens(text)
        rec = {
            "tier": tier,
            "prompt": prompt,
            "text": text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        self.calls.append(rec)
        return Completion(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_id=f"mock-{tier}",
            tier=tier,
            latency_ms=int((time.time() - start) * 1000),
        )
