from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings

# .env lives at the project root (two levels above this file: app/config.py → backend/ → root/)
_ENV_FILE = str(Path(__file__).parent.parent.parent / ".env")


class Settings(BaseSettings):
    # Database — prefer DATABASE_URL if set; otherwise build from POSTGRES_* vars
    database_url: str = Field(default="", alias="DATABASE_URL")
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "solara_dashboard"
    postgres_user: str = "solara_user"
    postgres_password: str = ""

    # Slack
    slack_webhook_url: str = ""
    slack_bot_token: str = ""
    slack_channel_id: str = ""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change-me-in-production"

    # External API access — comma-separated API keys that grant programmatic
    # (server-to-server) access to /api, e.g. the autonomous runner.
    # EMPTY = auth disabled (open), so local/dev keeps working unchanged.
    dashboard_api_keys: str = Field(default="", alias="DASHBOARD_API_KEYS")

    # Browser origins allowed to call /api without a key (the dashboard UI) and
    # used for CORS. Comma-separated.
    allowed_origins: str = Field(
        default=(
            "http://localhost:3000,"
            "http://localhost:3131,"
            "https://solara-frontend-891651347357.asia-south1.run.app"
        ),
        alias="ALLOWED_ORIGINS",
    )

    # Data paths
    raw_data_path: str = "./data/raw"
    processed_data_path: str = "./data/processed"
    source_data_path: str = "./data/source"

    # Database SSL — set DB_SSL=true for Supabase/cloud Postgres; false for local Docker
    db_ssl: bool = False

    # AI / LLM (Ask Me Anything feature)
    llm_api_key: str = ""

    def get_db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def api_key_map(self) -> dict[str, str]:
        """External API keys mapped to an owner label.

        Each comma-separated entry is either ``label:key`` (per-person, so a key
        is attributable and individually revocable) or a bare ``key`` (labelled
        "unnamed"). Keys are colon-free (url-safe tokens), so splitting on the
        first ``:`` is unambiguous. Empty = auth disabled.
        """
        out: dict[str, str] = {}
        for raw in self.dashboard_api_keys.split(","):
            entry = raw.strip()
            if not entry:
                continue
            if ":" in entry:
                label, key = entry.split(":", 1)
                label, key = label.strip() or "unnamed", key.strip()
            else:
                label, key = "unnamed", entry
            if key:
                out[key] = label
        return out

    def api_key_set(self) -> set[str]:
        """Configured external API keys (empty set = auth disabled)."""
        return set(self.api_key_map())

    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    model_config = {
        "env_file": _ENV_FILE,
        "case_sensitive": False,
        "extra": "ignore",
        "populate_by_name": True,
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
