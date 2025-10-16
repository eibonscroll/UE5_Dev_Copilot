from typing import Optional
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # maps EMBEDDING_MODEL -> embedding_model
    embedding_model: str = Field(default="BAAI/bge-small-en", validation_alias="EMBEDDING_MODEL")

    # 👇 add this: maps VECTOR_COLLECTION -> collection (what your code uses)
    collection: str = Field(default="agentic_copilot", validation_alias="VECTOR_COLLECTION")

    # maps QDRANT_URL -> qdrant_url (works whether code uses upper or lower)
    qdrant_url: str = Field(default="http://qdrant:6333", validation_alias="QDRANT_URL")

    OPENAI_API_KEY: Optional[SecretStr] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

SETTINGS = Settings()