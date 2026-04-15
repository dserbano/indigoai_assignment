import logging
import os
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def build_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    return logging.getLogger("document-intelligence")


logger = build_logger()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg2://indigoai:indigoai@postgres:5432/indigoai"
    upload_dir: str = "data/uploads"
    backend_cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173"
    )

    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str | None = None

    default_top_k: int = 5
    max_top_k: int = 20

    mcp_bearer_token: str = "change-me"
    mcp_url: str = "http://localhost:8000/mcp"

    @property
    def backend_cors_origins(self) -> List[str]:
        return [x.strip() for x in self.backend_cors_origins_raw.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    return settings