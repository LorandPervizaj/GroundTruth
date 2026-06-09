"""CI gates: parser regression thresholds and golden dataset accuracy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from groundtruth.config import PROJECT_ROOT
from groundtruth.golden.evaluate import evaluate_golden_file, load_baseline, verified_rows, load_golden_rows
from groundtruth.services.parsing import ParsingService

GOLDEN_DIR = PROJECT_ROOT / "data" / "golden"
BASELINE_PATH = GOLDEN_DIR / "parser_baseline.json"


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
        assert result.price >= 1.0, f"Price {result.price:.1%} < 100%"
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
