"""Assemble public methodology metadata for /api/methodology and the methodology page."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from groundtruth.analytics.corpus_filters import ACTIVE_PARSER_VERSIONS
from groundtruth.methodology.version import METHODOLOGY_CHANGELOG, METHODOLOGY_VERSION
from groundtruth.schemas.methodology import MethodologyPublic
from groundtruth.services.lookup import get_corpus_meta

METHODOLOGY_RELEASED = date(2026, 6, 9)


def get_public_methodology(session: Session) -> MethodologyPublic:
    meta = get_corpus_meta(session)
    return MethodologyPublic(
        version=METHODOLOGY_VERSION,
        released=METHODOLOGY_RELEASED,
        summary=METHODOLOGY_CHANGELOG.get(METHODOLOGY_VERSION, ""),
        corpus_updated_at=meta.corpus_updated_at,
        active_listings=meta.active_listings,
        raw_listings=meta.raw_listings,
        data_sources=[],
        parser_versions=list(ACTIVE_PARSER_VERSIONS),
        dataset_version=meta.dataset_version,
        dataset_frozen_at=meta.dataset_frozen_at,
        dataset_fingerprint=meta.dataset_fingerprint,
        invalid_pct=meta.invalid_pct,
        golden_accuracy_pct=meta.golden_accuracy_pct,
        public_product_scope=meta.public_product_scope,
    )
