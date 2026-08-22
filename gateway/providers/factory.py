from gateway.config import settings
from gateway.providers.base import Provider
from gateway.providers.mock import MockProvider


def build_provider() -> Provider:
    if settings.LLM_PROVIDER == "mock":
        return MockProvider()
    if settings.LLM_PROVIDER == "openai_compat":
        from gateway.providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider()
    raise RuntimeError(f"unsupported LLM_PROVIDER={settings.LLM_PROVIDER}")
