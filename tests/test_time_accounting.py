"""Tests for governance time accounting."""

from groundtruth.analytics.time_accounting import governance_ratio_from_rows


def test_governance_ratio() -> None:
    rows = [
        {
            "analysis_hours": "10",
            "writing_hours": "5",
            "governance_hours": "2",
            "review_hours": "3",
            "engineering_hours": "1",
        }
    ]
    ratio, totals = governance_ratio_from_rows(rows)
    assert ratio == 0.1
    assert totals["research_hours"] == 20.0
