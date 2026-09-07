"""Research time accounting — governance ratio and Goodhart-safe splits."""

from __future__ import annotations


def governance_ratio_from_rows(rows: list[dict[str, str]]) -> tuple[float | None, dict[str, float]]:
    """
    governance / (analysis + writing + governance + review).

    Target < 15%. Above 20% suggests self-referential overhead.
    """
    analysis = sum(float(r.get("analysis_hours") or 0) for r in rows)
    writing = sum(float(r.get("writing_hours") or 0) for r in rows)
    gov = sum(float(r.get("governance_hours") or 0) for r in rows)
    review = sum(float(r.get("review_hours") or 0) for r in rows)
    engineering = sum(float(r.get("engineering_hours") or 0) for r in rows)
    research = analysis + writing + gov + review
    research + engineering
    ratio = gov / research if research > 0 else None
    return ratio, {
        "analysis_hours": analysis,
        "writing_hours": writing,
        "governance_hours": gov,
        "review_hours": review,
        "engineering_hours": engineering,
        "research_hours": research,
    }
