from __future__ import annotations

from datetime import UTC, datetime, timedelta

from groundtruth.analytics.lifecycle_state import (
    CrawlHealth,
    LifecyclePolicy,
    LifecycleStatus,
    LifecycleValue,
    canonical_group_is_current,
    source_crawl_health,
    transition_lifecycle,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)
HEALTHY = CrawlHealth(True, "healthy")
FAILED = CrawlHealth(False, "failed")


def _active() -> LifecycleValue:
    return LifecycleValue(LifecycleStatus.ACTIVE, NOW, NOW, 1)


def test_seen_missing_reappearing_transition() -> None:
    possible = transition_lifecycle(
        _active(), seen=False, crawl_health=HEALTHY, run_id=2, observed_at=NOW + timedelta(days=7)
    )
    assert possible and possible.status == LifecycleStatus.POSSIBLY_INACTIVE
    inactive = transition_lifecycle(
        possible, seen=False, crawl_health=HEALTHY, run_id=3, observed_at=NOW + timedelta(days=14)
    )
    assert inactive and inactive.status == LifecycleStatus.INACTIVE
    active = transition_lifecycle(
        inactive, seen=True, crawl_health=HEALTHY, run_id=4, observed_at=NOW + timedelta(days=21)
    )
    assert active and active.status == LifecycleStatus.ACTIVE
    assert active.reactivated_at == NOW + timedelta(days=21)


def test_failed_partial_or_zero_crawl_never_advances_absence() -> None:
    current = _active()
    for health in (
        FAILED,
        source_crawl_health(completed=False, listings_stored=100, errors_count=0),
        source_crawl_health(completed=True, listings_stored=0, errors_count=0),
        source_crawl_health(completed=True, listings_stored=100, errors_count=1),
    ):
        assert (
            transition_lifecycle(
                current, seen=False, crawl_health=health, run_id=2, observed_at=NOW
            )
            == current
        )


def test_source_specific_miss_policy() -> None:
    current = _active()
    policy = LifecyclePolicy(misses_before_inactive=3)
    first = transition_lifecycle(
        current, seen=False, crawl_health=HEALTHY, run_id=2, observed_at=NOW, policy=policy
    )
    second = transition_lifecycle(
        first, seen=False, crawl_health=HEALTHY, run_id=3, observed_at=NOW, policy=policy
    )  # type: ignore[arg-type]
    assert second and second.status == LifecycleStatus.POSSIBLY_INACTIVE
    third = transition_lifecycle(
        second, seen=False, crawl_health=HEALTHY, run_id=4, observed_at=NOW, policy=policy
    )
    assert third and third.status == LifecycleStatus.INACTIVE


def test_group_current_while_any_source_member_active() -> None:
    assert canonical_group_is_current([LifecycleStatus.INACTIVE, LifecycleStatus.ACTIVE])
    assert not canonical_group_is_current([LifecycleStatus.INACTIVE, LifecycleStatus.UNKNOWN])


def test_recycled_portal_id_restarts_first_seen() -> None:
    changed = transition_lifecycle(
        _active(),
        seen=True,
        crawl_health=HEALTHY,
        run_id=2,
        observed_at=NOW + timedelta(days=7),
        identity_changed=True,
    )
    assert changed and changed.first_seen_at == NOW + timedelta(days=7)
