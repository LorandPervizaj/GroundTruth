from pathlib import Path

from groundtruth.analytics.dedup_benchmark import (
    evaluate_pairs,
    load_benchmark,
    threshold_sensitivity,
)

BENCHMARK = Path(__file__).parents[1] / "data" / "deduplication" / "benchmark.csv"


def test_benchmark_reports_scoring_and_blocking_errors() -> None:
    result, details = evaluate_pairs(load_benchmark(BENCHMARK), threshold=80)
    assert result.labelled_pairs == 6
    assert result.positive_pairs == 3
    assert result.blocking_recall < 1
    assert any(row["error"] == "false_negative" for row in details)


def test_threshold_sensitivity_is_deterministic() -> None:
    rows = load_benchmark(BENCHMARK)
    first = threshold_sensitivity(rows)
    assert first == threshold_sensitivity(rows)
    assert [row["threshold"] for row in first] == [70, 75, 80, 85, 90]
