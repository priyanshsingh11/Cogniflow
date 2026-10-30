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

    # Knowledge / RAG (phase 3). Files go to a local folder behind a
    # StorageBackend interface; Cloudflare R2 swaps in at deploy time (phase 11)
    # without touching callers.
    storage_dir: str = "storage"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_cache_dir: str = ".embedding_cache"
    max_upload_mb: int = 5
    chunk_size: int = 1000  # characters per chunk
    chunk_overlap: int = 200  # characters of overlap between neighbours
    rag_top_k: int = 6  # passages retrieved by default
    rag_max_chunks_per_doc: int = 5_000  # safety cap against pathological files

    # MCP (phase 4): connect-per-request (no session pool until arq/phase 5).
    mcp_timeout_seconds: int = 30  # connect + discover/invoke budget
    mcp_max_result_bytes: int = 262_144  # stored/returned tool output cap (256 KB)

    # Chat message sync (phase 3b): pending Postgres row -> Mongo -> flipped.
    # A reaper retries rows stuck in `pending` (crash between the two writes).
    chat_reaper_enabled: bool = True
    chat_reaper_interval_seconds: int = 60
    chat_reaper_stuck_seconds: int = 60
    chat_reaper_max_attempts: int = 3  # then the row is marked failed


settings = Settings()
