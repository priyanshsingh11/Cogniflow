import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/test")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
