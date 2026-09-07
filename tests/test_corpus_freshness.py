"""Tests for corpus freshness metadata."""

from groundtruth.analytics.annual_export import corpus_last_updated


def test_corpus_last_updated_returns_datetime_or_none(require_postgres) -> None:
    from groundtruth.database.session import get_session_factory

    session = get_session_factory()()
    try:
        updated = corpus_last_updated(session)
    finally:
        session.close()
    assert updated is None or hasattr(updated, "isoformat")
