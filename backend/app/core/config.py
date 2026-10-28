from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), ".env"), extra="ignore", env_file_encoding="utf-8"
    )

    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    cors_origins: Annotated[list[str], NoDecode] = Field(default=["http://localhost:5173"])
    dashboard_url: str = "http://localhost:5173"

    yahoo_enabled: bool = True
    alpha_vantage_api_key: SecretStr | None = None
    alpha_vantage_daily_limit: int = 25
    alpha_vantage_per_minute_limit: int = 5

    scheduler_enabled: bool = True
    refresh_interval_seconds: int = Field(default=300, ge=60)
    market_timezone: str = "Asia/Kolkata"
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    stale_after_minutes: int = 30
    holidays_file: Path = DATA_DIR / "market_holidays.json"
    uploads_dir: Path = DATA_DIR / "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_timeout_seconds: float = 90

    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    notification_cooldown_minutes: int = 60

    paper_starting_capital: float = 1_000_000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("alpha_vantage_api_key", "telegram_bot_token", mode="before")
    @classmethod
    def empty_to_none(cls, v: object) -> object:
        return None if v in ("", None) else v

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
