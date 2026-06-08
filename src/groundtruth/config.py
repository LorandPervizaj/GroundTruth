"""Application configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Central configuration. Loaded once and injected where needed."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://groundtruth:groundtruth_dev_password@localhost:5432/groundtruth"
    )

    # Scraping
    scrapy_download_delay: float = 2.0
    scrapy_concurrent_requests: int = 4
    scrapy_user_agent_rotation: bool = True

    # Geocoding
    geocoding_enabled: bool = False
    nominatim_user_agent: str = "groundtruth-kosovo-market-analysis/0.1.0"

    # Gazetteers
    gazetteer_dir: Path = Field(default=PROJECT_ROOT / "data" / "gazetteers")

    # Reports
    reports_templates_dir: Path = Field(default=PROJECT_ROOT / "reports" / "templates")
    reports_generated_dir: Path = Field(default=PROJECT_ROOT / "reports" / "generated")

    # Deduplication
    dedup_fuzzy_threshold: float = 85.0
    dedup_auto_merge: bool = False

    @field_validator("gazetteer_dir", "reports_templates_dir", "reports_generated_dir", mode="before")
    @classmethod
    def resolve_path(cls, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            return PROJECT_ROOT / path
        return path

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
