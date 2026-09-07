"""Source volume skew analysis for confidence scoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.corpus import active_corpus_dataframe


@dataclass(frozen=True)
class SourceSkewReport:
    lookback_days: int
    total_listings: int
    by_source: dict[str, int]
    shares: dict[str, float]
    dominant_source: str | None
    dominant_share: float
    is_structural_skew: bool
    notes: list[str]

    def as_dict(self) -> dict:
        return {
            "lookback_days": self.lookback_days,
            "total_listings": self.total_listings,
            "by_source": self.by_source,
            "shares": {k: round(v, 4) for k, v in self.shares.items()},
            "dominant_source": self.dominant_source,
            "dominant_share": round(self.dominant_share, 4),
            "is_structural_skew": self.is_structural_skew,
            "notes": self.notes,
        }


def source_skew_report(session: Session, *, lookback_days: int = 30) -> SourceSkewReport:
    """Measure listing-volume ratio per source over the active corpus."""
    df = active_corpus_dataframe(session)
    notes: list[str] = []
    if df.empty:
        return SourceSkewReport(
            lookback_days=lookback_days,
            total_listings=0,
            by_source={},
            shares={},
            dominant_source=None,
            dominant_share=0.0,
            is_structural_skew=False,
            notes=["Empty active corpus"],
        )

    if "listing_date" in df.columns:
        cutoff = date.today() - timedelta(days=lookback_days)
        dated = pd.to_datetime(df["listing_date"], errors="coerce")
        recent = df[dated.dt.date >= cutoff] if dated.notna().any() else df
    else:
        recent = df

    counts = recent["source_website"].value_counts().to_dict()
    counts = {str(k): int(v) for k, v in counts.items()}
    total = sum(counts.values())
    shares = {k: v / total for k, v in counts.items()} if total else {}
    dominant = max(shares, key=shares.get) if shares else None
    dominant_share = shares.get(dominant, 0.0) if dominant else 0.0

    if dominant_share >= 0.50:
        notes.append(
            f"{dominant} contributes {dominant_share:.0%} of listings — "
            "likely structural (portal size), not a pipeline bug. "
            "Document in confidence scoring; do not force-balance."
        )
        structural = True
    else:
        notes.append("No single source exceeds 50% — skew is moderate.")
        structural = False

    return SourceSkewReport(
        lookback_days=lookback_days,
        total_listings=total,
        by_source=counts,
        shares=shares,
        dominant_source=dominant,
        dominant_share=dominant_share,
        is_structural_skew=structural,
        notes=notes,
    )


def source_diversity_penalty(shares: dict[str, float]) -> float:
    """
    Return multiplier in (0, 1] penalizing confidence when one source dominates.
    1.0 = balanced; lower when dominant_share is high.
    """
    if not shares:
        return 1.0
    dominant = max(shares.values())
    if dominant <= 0.50:
        return 1.0
    # Linear ramp: 50% -> 1.0, 100% -> 0.85
    return max(0.85, 1.0 - (dominant - 0.50) * 0.30)
