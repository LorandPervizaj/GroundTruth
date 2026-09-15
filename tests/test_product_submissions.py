"""Product submission durability, duplicates, and failure honesty."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import app
from groundtruth.services.product_submissions import (
    DuplicateSubmission,
    append_product_submission,
    clear_submission_dedupe_cache,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dedupe():
    clear_submission_dedupe_cache()
    yield
    clear_submission_dedupe_cache()


def test_jsonl_persistence_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "jsonl")
    from groundtruth.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "product_log_dir", tmp_path)
    monkeypatch.setattr(settings, "product_write_backend", "jsonl")

    append_product_submission("contact", {"email": "a@example.com", "message": "hello"})
    path = tmp_path / "contact.jsonl"
    assert path.is_file()
    assert "a@example.com" in path.read_text(encoding="utf-8")
    get_settings.cache_clear()


def test_duplicate_submission_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "jsonl")
    from groundtruth.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "product_log_dir", tmp_path)
    monkeypatch.setattr(settings, "product_write_backend", "jsonl")
    monkeypatch.setattr(settings, "product_submission_dedupe_seconds", 300)

    payload = {"email": "dup@example.com", "message": "same"}
    append_product_submission("contact", payload)
    with pytest.raises(DuplicateSubmission):
        append_product_submission("contact", payload)
    get_settings.cache_clear()


def test_contact_reports_duplicate_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "jsonl")
    from groundtruth.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "product_log_dir", tmp_path)
    monkeypatch.setattr(settings, "product_write_backend", "jsonl")

    body = {
        "name": "Ada",
        "email": "ada@example.com",
        "topic": "general",
        "message": "Hello Metrik",
    }
    first = client.post("/api/contact", json=body)
    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    second = client.post("/api/contact", json=body)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    get_settings.cache_clear()


def test_contact_db_failure_is_not_false_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(kind: str, payload: dict) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "groundtruth.api.routes_product_writes.append_product_submission",
        _boom,
    )
    res = client.post(
        "/api/contact",
        json={
            "name": "Ada",
            "email": "ada@example.com",
            "topic": "general",
            "message": "Hello Metrik, this is a durable failure test.",
        },
    )
    assert res.status_code == 503
    body = res.json()
    assert body.get("status") != "ok"
    assert "detail" in body


def test_database_backend_rolls_back_on_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_WRITE_BACKEND", "database")
    from groundtruth.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "product_write_backend", "database")
    monkeypatch.setattr(settings, "product_submission_dedupe_seconds", 0)

    session = MagicMock()
    session.commit.side_effect = RuntimeError("disk full")
    factory = MagicMock(return_value=session)
    with (
        patch(
            "groundtruth.services.product_submissions.get_session_factory",
            return_value=factory,
        ),
        pytest.raises(RuntimeError, match="disk full"),
    ):
        append_product_submission("feedback", {"issue": "wrong_price"})
    session.rollback.assert_called_once()
    get_settings.cache_clear()
