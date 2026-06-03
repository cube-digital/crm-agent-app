"""Central configuration, loaded from environment variables.

Everything the app needs to talk to Postgres, FalkorDB and the LLM lives here so
there is a single obvious place to look. Values come from the environment (see
`.env.example`); docker-compose wires them into the container.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Postgres ---
    postgres_url: str = "postgresql://crm:crm@localhost:5432/crm"

    # --- FalkorDB ---
    # Blank host => local `falkordb` compose service.
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_username: str | None = None
    falkordb_password: str | None = None
    # Prefix for per-tenant graph keys: graph key = f"{falkordb_graph}:{company_id}".
    falkordb_graph: str = "crm"

    # --- Auth ---
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- LLM ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # Interactive recommendation + chat (quality, user is watching).
    agent_model: str = "claude-sonnet-4-6"
    # Bulk proactive scan (speed — runs across many deals in the background).
    proactive_model: str = "claude-haiku-4-5-20251001"

    # --- Proactive ---
    proactive_scan_interval_seconds: int = 600
    proactive_top_n: int = 3
    # Run the enrich -> rebuild -> scan pipeline in the background on signup.
    # Disabled in tests to avoid LLM calls.
    bootstrap_on_signup: bool = True

    @property
    def fixtures_path(self) -> Path:
        """Locate db/fixtures.json whether running in Docker (/srv/db) or locally."""
        candidates = [
            Path("/srv/db/fixtures.json"),
            Path(__file__).resolve().parent.parent / "db" / "fixtures.json",
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[-1]

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy needs the psycopg3 driver spelled out explicitly."""
        url = self.postgres_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
