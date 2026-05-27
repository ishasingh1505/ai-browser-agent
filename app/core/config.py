from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Browser
    browser_headless: bool = True
    browser_timeout_ms: int = 30_000

    # Vector DB
    chroma_persist_dir: str = "./chroma_db"


settings = Settings()


@lru_cache(maxsize=1)
def get_llm():
    """
    Return a LangChain-compatible Groq chat model.
    Cached so only one instance is created per process.
    Used in Phase 3 (extraction) and Phase 4 (planner/reasoner).
    """
    from langchain_groq import ChatGroq  # lazy import

    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.2,
    )
