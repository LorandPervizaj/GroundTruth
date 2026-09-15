"""Production startup validation — fail fast on unsafe configuration."""

from __future__ import annotations

import logging

from groundtruth.config import Settings

logger = logging.getLogger(__name__)

_DEV_PASSWORD_MARKERS = (
    "groundtruth_dev_password",
    "replace-me",
    "changeme",
)


def validate_production_settings(settings: Settings) -> None:
    """Reject known-unsafe production configuration before serving traffic."""
    if settings.app_env != "production":
        return

    errors: list[str] = []
    db_url = str(settings.database_url).lower()

    for marker in _DEV_PASSWORD_MARKERS:
        if marker in db_url:
            errors.append(f"DATABASE_URL contains unsafe placeholder '{marker}' in production")
            break

    if settings.product_write_backend == "jsonl":
        errors.append(
            "PRODUCT_WRITE_BACKEND=jsonl is not allowed in production "
            "(submissions would be lost on container restart)"
        )

    ops_token = (settings.health_check_token or "").strip()
    if len(ops_token) < 24 or any(marker in ops_token.lower() for marker in _DEV_PASSWORD_MARKERS):
        errors.append(
            "HEALTH_CHECK_TOKEN must be a non-placeholder secret of at least "
            "24 characters in production"
        )

    if settings.forwarded_allow_ips.strip() == "*":
        errors.append("FORWARDED_ALLOW_IPS='*' is not allowed in production")

    if settings.api_docs_enabled:
        errors.append("API_DOCS_ENABLED must be false in production")

    if not settings.api_require_lookup_cache:
        errors.append(
            "API_REQUIRE_LOOKUP_CACHE must be true in production "
            "(public Metrik must boot from verified release artifacts)"
        )

    if not settings.api_rate_limit_enabled:
        errors.append(
            "API_RATE_LIMIT_ENABLED must be true in production "
            "(disabling rate limits exposes public write endpoints to abuse)"
        )

    if settings.require_sentry_dsn and not (settings.sentry_dsn or "").strip():
        errors.append(
            "SENTRY_DSN is required when REQUIRE_SENTRY_DSN=true "
            "(set REQUIRE_SENTRY_DSN=false only for break-glass internal deploys)"
        )

    if errors:
        for msg in errors:
            logger.critical("production_config_error: %s", msg)
        raise SystemExit(
            "Refusing to start in production with unsafe configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
