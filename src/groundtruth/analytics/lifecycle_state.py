"""Healthy-crawl-gated listing lifecycle transitions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.orm import Session

from groundtruth.models.lifecycle import ListingLifecycleState


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    POSSIBLY_INACTIVE = "POSSIBLY_INACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LifecyclePolicy:
    misses_before_inactive: int = 2


@dataclass(frozen=True)
class CrawlHealth:
    healthy: bool
    reason: str


@dataclass(frozen=True)
class LifecycleValue:
    status: LifecycleStatus
    first_seen_at: datetime
    last_seen_at: datetime
    last_seen_run_id: int | None
    consecutive_successful_misses: int = 0
    inactive_at: datetime | None = None
    reactivated_at: datetime | None = None


def transition_lifecycle(
    current: LifecycleValue | None,
    *,
    seen: bool,
    crawl_health: CrawlHealth,
    run_id: int,
    observed_at: datetime,
    policy: LifecyclePolicy = LifecyclePolicy(),
    identity_changed: bool = False,
) -> LifecycleValue | None:
    """Return the next state; unhealthy absence can never advance lifecycle."""
    if current is None:
        if not seen:
            return None
        return LifecycleValue(
            status=LifecycleStatus.ACTIVE,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            last_seen_run_id=run_id,
        )
    if seen:
        reactivated = (
            observed_at
            if current.status in {LifecycleStatus.INACTIVE, LifecycleStatus.POSSIBLY_INACTIVE}
            else current.reactivated_at
        )
        first_seen = observed_at if identity_changed else current.first_seen_at
        return replace(
            current,
            status=LifecycleStatus.ACTIVE,
            first_seen_at=first_seen,
            last_seen_at=observed_at,
            last_seen_run_id=run_id,
            consecutive_successful_misses=0,
            inactive_at=None,
            reactivated_at=reactivated,
        )
    if not crawl_health.healthy:
        return current
    misses = current.consecutive_successful_misses + 1
    inactive = misses >= max(1, policy.misses_before_inactive)
    return replace(
        current,
        status=LifecycleStatus.INACTIVE if inactive else LifecycleStatus.POSSIBLY_INACTIVE,
        consecutive_successful_misses=misses,
        inactive_at=observed_at if inactive else current.inactive_at,
    )


def source_crawl_health(
    *,
    completed: bool,
    listings_stored: int,
    errors_count: int,
    expected_min_listings: int = 1,
) -> CrawlHealth:
    if not completed:
        return CrawlHealth(False, "crawl_not_completed")
    if listings_stored < expected_min_listings:
        return CrawlHealth(False, "listing_count_below_healthy_minimum")
    if errors_count > 0:
        return CrawlHealth(False, "crawl_completed_with_errors")
    return CrawlHealth(True, "healthy")


def _value(row: ListingLifecycleState) -> LifecycleValue:
    return LifecycleValue(
        status=LifecycleStatus(row.status),
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        last_seen_run_id=row.last_seen_run_id,
        consecutive_successful_misses=row.consecutive_successful_misses,
        inactive_at=row.inactive_at,
        reactivated_at=row.reactivated_at,
    )


def apply_source_crawl_lifecycle(
    session: Session,
    *,
    source_website: str,
    run_id: int,
    observed_listing_ids: Iterable[str],
    crawl_health: CrawlHealth,
    observed_at: datetime | None = None,
    policy: LifecyclePolicy = LifecyclePolicy(),
    identity_changed_ids: Iterable[str] = (),
) -> dict[str, int]:
    """Persist one source run atomically; caller owns the transaction."""
    timestamp = observed_at or datetime.now(UTC)
    observed = {str(value) for value in observed_listing_ids}
    changed = {str(value) for value in identity_changed_ids}
    existing = {
        row.source_listing_id: row
        for row in session.query(ListingLifecycleState)
        .filter(ListingLifecycleState.source_website == source_website)
        .all()
    }
    counts = {"seen": 0, "possibly_inactive": 0, "inactive": 0, "unchanged_unhealthy": 0}
    for listing_id in sorted(set(existing) | observed):
        row = existing.get(listing_id)
        next_value = transition_lifecycle(
            _value(row) if row else None,
            seen=listing_id in observed,
            crawl_health=crawl_health,
            run_id=run_id,
            observed_at=timestamp,
            policy=policy,
            identity_changed=listing_id in changed,
        )
        if next_value is None:
            continue
        if row is None:
            row = ListingLifecycleState(
                source_website=source_website,
                source_listing_id=listing_id,
                first_seen_at=next_value.first_seen_at,
                last_seen_at=next_value.last_seen_at,
            )
            session.add(row)
        row.status = next_value.status.value
        row.first_seen_at = next_value.first_seen_at
        row.last_seen_at = next_value.last_seen_at
        row.last_seen_run_id = next_value.last_seen_run_id
        row.consecutive_successful_misses = next_value.consecutive_successful_misses
        row.inactive_at = next_value.inactive_at
        row.reactivated_at = next_value.reactivated_at
        if listing_id in observed:
            counts["seen"] += 1
        elif not crawl_health.healthy:
            counts["unchanged_unhealthy"] += 1
        elif next_value.status == LifecycleStatus.INACTIVE:
            counts["inactive"] += 1
        else:
            counts["possibly_inactive"] += 1
    return counts


def canonical_group_is_current(statuses: Iterable[LifecycleStatus | str]) -> bool:
    return any(LifecycleStatus(status) == LifecycleStatus.ACTIVE for status in statuses)


SOURCE_LIFECYCLE_POLICIES: dict[str, LifecyclePolicy] = {
    "gjirafa": LifecyclePolicy(misses_before_inactive=2),
    "merrjep": LifecyclePolicy(misses_before_inactive=2),
    "pro-rks": LifecyclePolicy(misses_before_inactive=3),
    "vision": LifecyclePolicy(misses_before_inactive=3),
    "topia": LifecyclePolicy(misses_before_inactive=2),
    "myrealestate": LifecyclePolicy(misses_before_inactive=2),
}


def lifecycle_policy_for_source(source_website: str) -> LifecyclePolicy:
    return SOURCE_LIFECYCLE_POLICIES.get(source_website, LifecyclePolicy())
