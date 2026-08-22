"""Runtime settings. Names are provider-agnostic — no vendor lock-in in fields."""
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CLEVER_ENV: str = "dev"
    LOG_LEVEL: str = "info"

    POSTGRES_DSN: str = "postgresql://clever:clever@localhost:5432/clever"
    REDIS_URL: str = "redis://:clever@localhost:6379/0"

    # mock | openai_compat
    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    MODEL_CHEAP: str = ""
    MODEL_STRONG: str = ""
    LLM_TIMEOUT_S: float = 90.0
    LLM_MAX_TOKENS: int = 1024
    # disabled | enabled — some vendors default to hidden reasoning tokens
    LLM_THINKING: str = "disabled"

    CLEVER_API_KEY: str = "dev-key-change-me"
    CLEVER_ADMIN_KEY: str = "dev-admin-change-me"
    CORS_ORIGINS: str = "http://localhost:8080,http://127.0.0.1:8080"

    CACHE_TTL_S: int = 3600
    SEMANTIC_ENABLED: bool = True
    SEMANTIC_THRESHOLD: float = 0.88
    SEMANTIC_MODEL: str = "all-MiniLM-L6-v2"
    CONFIRM_TTL_S: int = 300
    QUERY_MAX_CHARS: int = 8000
    CONTEXT_MAX_BYTES: int = 262144
    FAQ_MIN_SCORE: float = 0.5
    N_MIN: int = 30
    N_EXPLORE: int = 10  # cheap trials after cold before LCB gating
    RATE_LIMIT_PER_MIN: int = 60

    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    @field_validator("LLM_PROVIDER")
    @classmethod
    def _provider(cls, v: str) -> str:
        allowed = {"mock", "openai_compat"}
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def _prod_guards(self):
        if self.CLEVER_ENV == "prod":
            if self.CLEVER_API_KEY in ("", "dev-key-change-me"):
                raise ValueError("CLEVER_API_KEY must be set in prod")
            if self.CLEVER_ADMIN_KEY in ("", "dev-admin-change-me"):
                raise ValueError("CLEVER_ADMIN_KEY must be set in prod")
            if "clever:clever" in self.POSTGRES_DSN:
                raise ValueError("default database password is not allowed in prod")
            if ":clever@" in self.REDIS_URL:
                raise ValueError("default redis password is not allowed in prod")
            if self.LLM_PROVIDER == "openai_compat" and not self.LLM_API_KEY:
                raise ValueError("LLM_API_KEY required when LLM_PROVIDER=openai_compat")
        return self


settings = Settings()
