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


settings = Settings()
