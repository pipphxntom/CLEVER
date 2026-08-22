"""Optional future adapter. Not registered. Study path is mock | openai_compat."""
from gateway.providers.base import Completion


class NotEnabled:
    name = "not_enabled"

    async def complete(self, *, tier: str, messages: list[dict], max_tokens: int | None = None) -> Completion:
        raise RuntimeError("this adapter is not enabled; use LLM_PROVIDER=mock or openai_compat")
