from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from groundtruth.automation.data_quality import DataQualityResult, classify_data_quality
from groundtruth.automation.source_health import SourceHealth, classify_source_health
from groundtruth.automation.state import PipelineLock, calculate_lookback_days
from groundtruth.automation.statistical_sanity import (
    StatisticalSanityResult,
    evaluate_statistical_sanity,
)
from groundtruth.automation.weekly_release import make_release_id, run_weekly_release


def test_release_id_uses_iso_week() -> None:
    assert make_release_id(datetime(2026, 9, 23, tzinfo=UTC), git_sha="abc123") == "2026-W39-abc123"


def test_lookback_uses_verified_watermark_and_recovers_missed_week() -> None:
    assert calculate_lookback_days(date(2026, 9, 14), today=date(2026, 9, 28)) == 15
    assert calculate_lookback_days(date(2026, 9, 27), today=date(2026, 9, 28)) == 7
    assert calculate_lookback_days(None, today=date(2026, 9, 28)) == 7


def test_pipeline_lock_prevents_overlap(tmp_path: Path) -> None:
    lock_path = tmp_path / "weekly-release.lock"
    with (
        PipelineLock(lock_path, "first"),
        pytest.raises(RuntimeError, match="another weekly release"),
        PipelineLock(lock_path, "second"),
    ):
        pass
    assert not lock_path.exists()


def test_source_health_uses_historical_source_baseline() -> None:
    result = classify_source_health(
        source="topia",
        scrape_run_id=9,
        completed=True,
        listings_found=2,
        listings_stored=2,
        errors_count=0,
        historical_counts=[100, 110, 90],
    )
    assert result.level == "RED"
    assert result.historical_median == 100


def healthy_sources(_: object) -> list[SourceHealth]:
    return [SourceHealth(source="topia", level="GREEN", scrape_run_id=1)]


def healthy_data(_: object) -> list[DataQualityResult]:
    return [
        DataQualityResult(
            source="topia",
            level="GREEN",
            scrape_run_id=1,
            raw=12,
            parsed=12,
            normalized=12,
            valid=12,
        )
    ]


def healthy_statistics(_: object) -> StatisticalSanityResult:
    return StatisticalSanityResult(level="GREEN", shadow_mode=True, snapshot={"total_listings": 10})


def test_statistical_sanity_is_sample_aware_and_shadowed() -> None:
    result = evaluate_statistical_sanity(
        {
            "total_listings": 1000,
            "median_rent": 900,
            "median_rent_sample_n": 500,
            "coverage": {"price_pct": 90},
        },
        {
            "total_listings": 1000,
            "median_rent": 450,
            "median_rent_sample_n": 500,
            "coverage": {"price_pct": 99},
        },
        shadow_mode=True,
    )
    assert result.level == "RED"
    assert result.shadow_mode is True
    assert any(issue.metric == "median_rent" for issue in result.issues)


def test_data_quality_blocks_parser_collapse() -> None:
    result = classify_data_quality(
        source="topia",
        scrape_run_id=1,
        raw=100,
        parsed=10,
        parse_failures=90,
        normalized=10,
        normalization_failures=0,
        validation_failures=0,
    )
    assert result.level == "RED"
    assert result.valid == 10


def test_weekly_release_records_verified_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDTRUTH_PIPELINE_STATE_DIR", str(tmp_path / "state"))
    report = SimpleNamespace(
        sources=[SimpleNamespace(error=None, etl_normalized=12)],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )
    output = tmp_path / "run.json"
    result = run_weekly_release(
        days=8,
        output_path=output,
        weekly_runner=lambda **_: report,
        verifier=lambda: ["ok"],
        source_health_runner=healthy_sources,
        data_quality_runner=healthy_data,
        statistical_runner=healthy_statistics,
    )
    assert result.outcome == "verified"
    assert [stage.status for stage in result.stages] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
    ]
    assert output.is_file()


def test_weekly_release_records_verification_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDTRUTH_PIPELINE_STATE_DIR", str(tmp_path / "state"))
    report = SimpleNamespace(
        sources=[],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )

    def fail() -> list[str]:
        raise ValueError("hash mismatch")

    with pytest.raises(ValueError, match="hash mismatch"):
        run_weekly_release(
            output_path=tmp_path / "failed.json",
            weekly_runner=lambda **_: report,
            verifier=fail,
            source_health_runner=healthy_sources,
            data_quality_runner=healthy_data,
            statistical_runner=healthy_statistics,
        )


def test_red_source_blocks_release_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDTRUTH_PIPELINE_STATE_DIR", str(tmp_path / "state"))
    report = SimpleNamespace(
        sources=[],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )
    verifier_called = False

    def verify() -> list[str]:
        nonlocal verifier_called
        verifier_called = True
        return ["ok"]

    with pytest.raises(RuntimeError, match="sources are RED"):
        run_weekly_release(
            output_path=tmp_path / "red.json",
            weekly_runner=lambda **_: report,
            verifier=verify,
            source_health_runner=lambda _: [
                SourceHealth(source="topia", level="RED", scrape_run_id=1)
            ],
            data_quality_runner=healthy_data,
            statistical_runner=healthy_statistics,
        )
    assert verifier_called is False


def test_red_data_quality_blocks_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDTRUTH_PIPELINE_STATE_DIR", str(tmp_path / "state"))
    report = SimpleNamespace(
        sources=[],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )
    with pytest.raises(RuntimeError, match="data-integrity gate is RED"):
        run_weekly_release(
            output_path=tmp_path / "red-data.json",
            weekly_runner=lambda **_: report,
            verifier=lambda: ["should not run"],
            source_health_runner=healthy_sources,
            data_quality_runner=lambda _: [
                DataQualityResult(source="topia", level="RED", scrape_run_id=1)
            ],
            statistical_runner=healthy_statistics,
        )


def test_non_shadow_red_statistics_blocks_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROUNDTRUTH_PIPELINE_STATE_DIR", str(tmp_path / "state"))
    report = SimpleNamespace(
        sources=[],
        window=SimpleNamespace(window_start=date(2026, 9, 15), window_end=date(2026, 9, 22)),
    )
    with pytest.raises(RuntimeError, match="statistical sanity gate is RED"):
        run_weekly_release(
            output_path=tmp_path / "red-statistics.json",
            weekly_runner=lambda **_: report,
            verifier=lambda: ["should not run"],
            source_health_runner=healthy_sources,
            data_quality_runner=healthy_data,
            statistical_runner=lambda _: StatisticalSanityResult(
                level="RED", shadow_mode=False, snapshot={}, baseline_available=True
            ),
        )
