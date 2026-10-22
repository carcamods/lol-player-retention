"""Configuration: non-secret constants plus settings read from the environment.

Secrets (the Riot key, the Discord webhook) are only ever read from environment
variables or a git-ignored `.env` file. They are typed as `SecretStr`, so printing
or logging the settings object never reveals their values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_NAME = "lolret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    riot_api_key: SecretStr | None = None
    discord_webhook_url: SecretStr | None = None
    data_dir: Path = Path("data")
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
