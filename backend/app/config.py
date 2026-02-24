from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

# .env lives at the project root (two levels above this file: app/config.py → backend/ → root/)
_ENV_FILE = str(Path(__file__).parent.parent.parent / ".env")


class Settings(BaseSettings):
    # Database
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

    # Data paths
    raw_data_path: str = "./data/raw"
    processed_data_path: str = "./data/processed"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = _ENV_FILE
        case_sensitive = False
        extra = "ignore"  # silently ignore any extra env vars not defined as fields


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
