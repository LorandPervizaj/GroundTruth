"""Pytest fixtures."""

import pytest

from groundtruth.gazetteers.loader import GazetteerService


@pytest.fixture
def gazetteer_service() -> GazetteerService:
    """Load gazetteers from project data directory."""
    service = GazetteerService()
    service.load()
    return service
