"""Provider protocol. Tiers are cheap | strong. Model ids are opaque strings from env."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model_id: str
    tier: str
    latency_ms: int


class Provider(Protocol):
    name: str

    async def complete(
        self,
        *,
        tier: str,
        messages: list[dict],
        max_tokens: int | None = None,
    ) -> Completion:
        ...
