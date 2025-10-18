# src/settings.py
from typing import Optional
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Reads EMBEDDING_MODEL from env/.env
    embedding_model: str = Field(default="BAAI/bge-small-en", env="EMBEDDING_MODEL")

    # Reads VECTOR_COLLECTION
    collection: str = Field(default="agentic_copilot", env="VECTOR_COLLECTION")

    # Reads QDRANT_URL
    qdrant_url: str = Field(default="http://qdrant:6333", env="QDRANT_URL")

    # Reads OPENAI_API_KEY
    openai_api_key: Optional[SecretStr] = Field(default=None, env="OPENAI_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # convenience accessor (keeps logs/tests from printing secrets)
    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.get_secret_value())

SETTINGS = Settings()
