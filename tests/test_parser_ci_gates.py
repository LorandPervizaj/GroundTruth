"""CI gates: parser regression thresholds and golden dataset accuracy."""

from __future__ import annotations

import json

import pytest

from groundtruth.config import PROJECT_ROOT
from groundtruth.golden.evaluate import (
    evaluate_golden_file,
    load_baseline,
    load_golden_rows,
    verified_rows,
)
from groundtruth.services.parse_health import ParseHealthAlert
from groundtruth.services.parsing import ParsingService

GOLDEN_DIR = PROJECT_ROOT / "data" / "golden"
BASELINE_PATH = GOLDEN_DIR / "parser_baseline.json"
PARSE_FAILURE_SPIKE_THRESHOLD = 0.10


class TestParserRegressionGates:
    """Hard gates on regression test fixtures — must pass on every commit."""

    def setup_method(self) -> None:
        self.parser = ParsingService()

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Banese me qira ne Emshir", "Emshir"),
            ("Banese ne lagjen e Spitalit", "Spitalit"),
            ("Mati 1, rruga B", "Mati 1"),
            ("Banese me qira ne Dardania", "Dardania"),
        ],
    )
    def test_neighborhood_regression_gate(self, title: str, expected: str) -> None:
        result = self.parser.extract_neighborhood(title)
        assert result == expected, f"Neighborhood gate failed: {title!r} -> {result!r}"


class TestGoldenDatasetGates:
    """Golden dataset gates — only enforced when verified labels exist."""

    def test_golden_thresholds_if_labeled(self) -> None:
        baseline = load_baseline()
        golden_file = baseline.get("golden_dataset", {}).get("file", "golden_v1.csv")
        path = GOLDEN_DIR / golden_file
        if not path.exists():
            pytest.skip("No golden dataset file")

        rows = load_golden_rows(path)
        if not verified_rows(rows):
            pytest.skip("Golden dataset has no verified labels yet")

        result = evaluate_golden_file(path)
        assert result is not None

        assert result.neighborhood >= 0.95, f"Neighborhood {result.neighborhood:.1%} < 95%"
        assert result.price >= 0.99, f"Price {result.price:.1%} < 99%"
        assert result.area >= 0.95, f"Area {result.area:.1%} < 95%"

        min_overall = baseline.get("golden_dataset", {}).get("min_overall_accuracy", 0.97)
        assert result.overall >= min_overall, f"Overall {result.overall:.1%} < {min_overall:.1%}"

    def test_golden_accuracy_not_below_baseline(self) -> None:
        """Fail if golden accuracy regresses below the stored baseline score."""
        if not BASELINE_PATH.exists():
            pytest.skip("No parser baseline")

        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        golden_file = baseline.get("golden_dataset", {}).get("file", "golden_v1.csv")
        path = GOLDEN_DIR / golden_file
        if not path.exists() or not verified_rows(load_golden_rows(path)):
            pytest.skip("Golden dataset not labeled")

        result = evaluate_golden_file(path)
        assert result is not None
        stored = baseline.get("golden_scores", {}).get("overall")
        if stored is None:
            pytest.skip("No stored golden baseline score")
        assert result.overall >= stored, (
            f"Golden accuracy regressed: {result.overall:.1%} < baseline {stored:.1%}"
        )


class TestParseFailureAlerting:
    """Mid-week parse-failure spike detection (threshold from remediation brief)."""

    def test_parse_alert_message_format(self) -> None:
        alert = ParseHealthAlert(
            source="merrjep",
            scrape_run_id=42,
            parse_failure_rate=0.12,
            parsed_failed=12,
            total_scraped=100,
            threshold=PARSE_FAILURE_SPIKE_THRESHOLD,
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
        assert alert.parse_failure_rate > PARSE_FAILURE_SPIKE_THRESHOLD
        assert "merrjep" in alert.message

    def test_recent_etl_parse_rates_within_threshold(self) -> None:
        """Fail loudly when any source's latest ETL run exceeds parse-failure threshold."""
        import socket

        sock = socket.socket()
        sock.settimeout(1)
        try:
            sock.connect(("127.0.0.1", 5432))
        except OSError:
            pytest.skip("Database unavailable")
        finally:
            sock.close()

        from groundtruth.database.session import get_session_factory
        from groundtruth.services.parse_health import check_parse_health

        session = get_session_factory()()
        try:
            alerts = check_parse_health(
                session, threshold=PARSE_FAILURE_SPIKE_THRESHOLD, min_sample=20
            )
        finally:
            session.close()

        if not alerts:
            return
        lines = "; ".join(a.message for a in alerts)
        pytest.fail(f"Parse-failure spike detected: {lines}")
