from pydantic import BaseSettings

class Settings(BaseSettings):
    qdrant_url: str = "http://localhost:6333"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    collection: str = "ue_codebase"

SETTINGS = Settings()
