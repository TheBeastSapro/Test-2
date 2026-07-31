from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, read from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_prefix="FORGECAST_", env_file=".env", extra="ignore"
    )

    secret_key: str = "dev-insecure-secret-change-me"
    encryption_key: str = ""
    database_url: str = "sqlite:///./forgecast.db"
    storage_dir: Path = Path("./storage")
    base_url: str = "http://localhost:8000"

    access_token_ttl_minutes: int = 60 * 24 * 7

    # Registration is closed by default. This is the one setting whose default has to
    # be the *restrictive* one: a private instance that becomes reachable — a tunnel, a
    # VPS, a forwarded port — must not accept strangers because nobody remembered to
    # turn signup off. Open it deliberately when you want other people on it, and
    # create your own account with `forgecast bootstrap`.
    allow_signup: bool = False

    # How long a signed media URL stays valid. Long enough to watch a render without
    # the link expiring mid-playback, short enough that a copied URL is not a
    # permanent key to the file.
    media_url_ttl_seconds: int = 60 * 60 * 6

    # "mock" never touches the network and never spends money.
    provider_mode: Literal["mock", "live"] = "mock"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    fal_key: str = ""
    runway_api_key: str = ""
    heygen_api_key: str = ""

    youtube_client_id: str = ""
    youtube_client_secret: str = ""

    # Research search providers. Tavily is preferred when both are present because it
    # returns extracted page content, saving a fetch per result.
    tavily_api_key: str = ""
    brave_api_key: str = ""

    worker_concurrency: int = 2
    worker_poll_seconds: float = 2.0

    # Signup grant. Must cover at least one complete short run or the free tier is a
    # dead end — a 60s long-form run reserves ~260 credits, a Short ~150.
    signup_credit_grant: int = 400

    @property
    def is_mock(self) -> bool:
        return self.provider_mode == "mock"

    def platform_key(self, provider: str) -> str:
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "elevenlabs": self.elevenlabs_api_key,
            "fal": self.fal_key,
            "runway": self.runway_api_key,
            "heygen": self.heygen_api_key,
            "tavily": self.tavily_api_key,
            "brave": self.brave_api_key,
        }.get(provider, "")

    def run_dir(self, run_id: int) -> Path:
        path = self.storage_dir / "runs" / str(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
