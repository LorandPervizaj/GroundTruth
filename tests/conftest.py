"""Pytest fixtures."""

import pytest

from groundtruth.gazetteers.loader import GazetteerService


def _postgres_available() -> bool:
    import socket
    from urllib.parse import urlparse

    from groundtruth.config import get_settings

    parsed = urlparse(str(get_settings().database_url))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


@pytest.fixture(scope="session")
def require_postgres() -> None:
    """Skip DB-backed tests when Postgres is not reachable."""
    if not _postgres_available():
        pytest.skip("Postgres not available (start with: docker compose up -d postgres)")


@pytest.fixture(autouse=True)
def _test_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from a developer's production .env."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("API_REQUIRE_LOOKUP_CACHE", "false")
    from groundtruth.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def disable_api_rate_limits(request: pytest.FixtureRequest):
    """Disable per-IP rate limits unless a test is marked @pytest.mark.rate_limit."""
    from groundtruth.api.security import limiter

    if request.node.get_closest_marker("rate_limit"):
        limiter.enabled = True
        yield
        return
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


@pytest.fixture
def session():
    """Lightweight DB session for tests that inject their own comparables frames."""
    from unittest.mock import MagicMock

    return MagicMock()


@pytest.fixture
def gazetteer_service() -> GazetteerService:
    """Load gazetteers from project data directory."""
    service = GazetteerService()
    service.load()
    return service
