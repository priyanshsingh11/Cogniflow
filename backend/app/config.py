from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    mongo_url: str
    mongo_db: str
    redis_url: str
    cors_origins: list[str] = ["http://localhost:3000"]

    # HS256 requires a >= 32-byte key per RFC 7518 §3.2; generate a real one
    # for production (e.g. `openssl rand -hex 32`).
    jwt_secret: str = "dev-only-secret-change-me-32bytes-min!!"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # LLM providers (free tiers). A provider without a key is simply skipped
    # by the gateway.
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    groq_rpm: int = 25  # requests/minute the gateway allows itself per provider
    openrouter_rpm: int = 15
    llm_timeout_seconds: float = 60.0
    llm_max_attempts: int = 8


settings = Settings()
