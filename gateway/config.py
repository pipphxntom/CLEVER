"""Runtime settings. Names are provider-agnostic — no vendor lock-in in fields."""
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CLEVER_ENV: str = "dev"
    LOG_LEVEL: str = "info"

    POSTGRES_DSN: str = "postgresql://clever:clever@localhost:5432/clever"
    REDIS_URL: str = "redis://:clever@localhost:6379/0"

    # mock | openai_compat | bedrock | auto
    # auto = start every backend whose credentials are present; default
    # preference is bedrock, then openai_compat, then mock.
    LLM_PROVIDER: str = "auto"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    MODEL_CHEAP: str = ""
    MODEL_STRONG: str = ""
    # Per-backend model ids. If empty, MODEL_CHEAP / MODEL_STRONG are used.
    COMPAT_MODEL_CHEAP: str = ""
    COMPAT_MODEL_STRONG: str = ""
    BEDROCK_MODEL_CHEAP: str = ""
    BEDROCK_MODEL_STRONG: str = ""
    LLM_TIMEOUT_S: float = 90.0
    LLM_MAX_TOKENS: int = 1024
    # disabled | enabled — some vendors default to hidden reasoning tokens
    LLM_THINKING: str = "disabled"
    # Bedrock. Static keys (no SSO) take precedence over AWS_PROFILE.
    AWS_PROFILE: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_SESSION_TOKEN: str = ""

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
    # Cold-start: strong-only until this many observations. Production 30.
    # Eval .env may set N_MIN=6. COLD_MIN aliases N_MIN when unset.
    N_MIN: int = 30
    COLD_MIN: Optional[int] = None
    # Kept so existing .env N_EXPLORE=3 is not a surprise. Not an explore budget.
    N_EXPLORE: int = 10
    LOCK_IN: float = 0.90
    LOCK_OUT: float = 0.01
    LOCK_OUT_MIN_CHEAP: int = 10  # do not lock out on a 1-fail posterior
    SLEEP_ENABLED: bool = True
    SLEEP_INTERVAL_S: int = 604800  # 7 days
    SLEEP_DECAY_FACTOR: float = 0.80
    SLEEP_DECAY_MIN_OBS: int = 10
    SLEEP_PATTERN_THRESHOLD: int = 5
    SLEEP_PATTERN_QUALITY_FLOOR: float = 0.95
    SLEEP_COLD_CACHE_AGE_S: int = 604800  # 7 days; was hardcoded in sleep
    SLEEP_HOT_EXTEND_TTL_S: int = 7200
    RATE_LIMIT_PER_MIN: int = 60

    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    @field_validator("LLM_PROVIDER")
    @classmethod
    def _provider(cls, v: str) -> str:
        allowed = {"mock", "openai_compat", "bedrock", "auto"}
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def _prod_guards(self):
        if self.COLD_MIN is None:
            object.__setattr__(self, "COLD_MIN", self.N_MIN)
        if self.CLEVER_ENV == "prod":
            if self.CLEVER_API_KEY in ("", "dev-key-change-me"):
                raise ValueError("CLEVER_API_KEY must be set in prod")
            if self.CLEVER_ADMIN_KEY in ("", "dev-admin-change-me"):
                raise ValueError("CLEVER_ADMIN_KEY must be set in prod")
            if "clever:clever" in self.POSTGRES_DSN:
                raise ValueError("default database password is not allowed in prod")
            if ":clever@" in self.REDIS_URL:
                raise ValueError("default redis password is not allowed in prod")
            if self.LLM_PROVIDER == "openai_compat" and not self.compat_configured():
                raise ValueError("openai_compat requires LLM_API_KEY, LLM_BASE_URL, and cheap/strong model ids")
            if self.LLM_PROVIDER == "bedrock" and not self.bedrock_configured():
                raise ValueError("bedrock requires AWS keys (or profile), AWS_REGION, and cheap/strong model ids")
        return self

    def compat_model(self, tier: str) -> str:
        if tier == "cheap":
            return (self.COMPAT_MODEL_CHEAP or self.MODEL_CHEAP or "").strip()
        return (self.COMPAT_MODEL_STRONG or self.MODEL_STRONG or "").strip()

    def bedrock_model(self, tier: str) -> str:
        if tier == "cheap":
            return (self.BEDROCK_MODEL_CHEAP or self.MODEL_CHEAP or "").strip()
        return (self.BEDROCK_MODEL_STRONG or self.MODEL_STRONG or "").strip()

    def compat_configured(self) -> bool:
        return bool(
            (self.LLM_API_KEY or "").strip()
            and (self.LLM_BASE_URL or "").strip()
            and self.compat_model("cheap")
            and self.compat_model("strong")
        )

    def bedrock_has_static_keys(self) -> bool:
        return bool((self.AWS_ACCESS_KEY_ID or "").strip() and (self.AWS_SECRET_ACCESS_KEY or "").strip())

    def bedrock_configured(self) -> bool:
        auth = self.bedrock_has_static_keys() or bool((self.AWS_PROFILE or "").strip())
        return bool(
            auth
            and (self.AWS_REGION or "").strip()
            and self.bedrock_model("cheap")
            and self.bedrock_model("strong")
        )


settings = Settings()
