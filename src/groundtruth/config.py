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
    public_base_url: str = "http://127.0.0.1:8000"
    # Comma-separated extra Host values for TrustedHostMiddleware (e.g. Azure FQDNs).
    trusted_hosts: str = ""
    api_docs_enabled: bool = False

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://groundtruth:groundtruth_dev_password@localhost:5432/groundtruth"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Scraping
    scrapy_download_delay: float = 2.0
    scrapy_concurrent_requests: int = 4
    scrapy_user_agent_rotation: bool = True
    scrapy_fast_mode: bool = False
    scrapy_html_concurrent_requests: int = 16
    scrapy_html_download_delay: float = 0.25
    scrapy_api_concurrent_requests: int = 32

    # Geocoding
    geocoding_enabled: bool = False
    nominatim_user_agent: str = "groundtruth-kosovo-market-analysis/0.1.0"

    # Gazetteers
    gazetteer_dir: Path = Field(default=PROJECT_ROOT / "data" / "gazetteers")

    # Reports
    reports_templates_dir: Path = Field(default=PROJECT_ROOT / "reports" / "templates")
    reports_generated_dir: Path = Field(default=PROJECT_ROOT / "reports" / "generated")
    product_log_dir: Path = Field(default=PROJECT_ROOT / "data" / "product")
    product_write_backend: Literal["jsonl", "database"] = "jsonl"

    # Deduplication
    dedup_fuzzy_threshold: float = 85.0
    dedup_auto_merge: bool = False

    # Observability
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1
    require_sentry_dsn: bool = False
    health_check_token: str | None = None
    forwarded_allow_ips: str = "127.0.0.1"

    # API security (internet-facing deploy)
    api_rate_limit_enabled: bool = True
    api_rate_limit_feedback: str = "5/hour"
    api_rate_limit_alerts: str = "3/hour"
    api_rate_limit_events: str = "60/hour"
    api_rate_limit_valuate: str = "30/hour"
    api_rate_limit_lang: str = "30/hour"
    api_rate_limit_contact: str = "5/hour"
    api_rate_limit_report_refresh: str = "2/hour"
    api_max_body_bytes: int = 16_384
    api_search_max_length: int = 80
    api_search_timeout_sec: float = 5.0
    api_valuate_timeout_sec: float = 15.0
    valuation_public_enabled: bool = False
    api_compare_max_neighborhoods: int = 3
    api_require_lookup_cache: bool = True
    # Email alert delivery is not implemented — keep signup closed until it is.
    alerts_signup_enabled: bool = False
    product_submission_dedupe_seconds: int = 300
    run_migrations_on_start: bool = True

    # Parse health alerting (mid-week portal breakage)
    parse_failure_alert_threshold: float = 0.10

    # Weekly crawl parallelism (across sources only — single machine)
    weekly_crawl_parallel_workers: int = 4
    weekly_crawl_trailing_etl: bool = True

    # Data retention (research database — local only)
    raw_html_retention_days: int = 730
    raw_payload_retention_days: int = 730
    parsed_description_retention_days: int = 730

    @field_validator(
        "gazetteer_dir",
        "reports_templates_dir",
        "reports_generated_dir",
        "product_log_dir",
        mode="before",
    )
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
