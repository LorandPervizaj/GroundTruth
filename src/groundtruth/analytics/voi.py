"""Value of Information — prioritize research by decision impact per hour."""

from __future__ import annotations

IMPACT_SCORES: dict[str, float] = {
    "very_low": 1.0,
    "low": 2.0,
    "medium": 3.0,
    "high": 4.0,
    "very_high": 5.0,
}

UNCERTAINTY_SCORES: dict[str, float] = {
    "unknown": 1.0,
    "under_investigation": 0.7,
    "partially_known": 0.5,
    "solved": 0.0,
    "active": 0.8,
}


def value_of_information(
    *,
    decision_impact: str,
    uncertainty: str,
    cost_hours: float,
    min_hours: float = 0.5,
) -> float:
    """
    VoI priority = decision_impact × uncertainty ÷ research_cost.

    Higher = better return on the next research hour.
    """
    impact = IMPACT_SCORES.get(decision_impact, 3.0)
    unc = UNCERTAINTY_SCORES.get(uncertainty, 1.0)
    hours = max(cost_hours, min_hours)
    return round(impact * unc / hours, 4)
