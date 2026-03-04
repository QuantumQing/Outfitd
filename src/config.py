"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings sourced from .env file."""

    # API Keys
    perplexity_api_key: str = Field(default="", description="Perplexity Sonar API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    serper_api_key: str = Field(default="", description="Serper.dev API key for Google Shopping")
    firecrawl_api_key: str = Field(default="", description="Firecrawl API key for deeper product parsing")

    # LLM Config
    openrouter_model: str = Field(
        default="deepseek/deepseek-chat-v3-0324",
        description="OpenRouter model to use for curation",
    )
    openrouter_fast_model: str = Field(
        default="anthropic/claude-haiku-4.5",
        description="Faster/cheaper OpenRouter model for lightweight LLM tasks",
    )

    # Database
    database_url: str = Field(
        default="sqlite:///./data/trunk.db",
        description="SQLite database path",
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def db_path(self) -> str:
        """Extract the file path from the SQLite URL."""
        return self.database_url.replace("sqlite:///", "")


settings = Settings()
