"""Tests for valuation evaluation harness."""

import json

import pandas as pd

from groundtruth.analytics.valuation import MIN_COMPARABLES
from groundtruth.evaluation.valuate import (
    assess_release_readiness,
    compare_eval_reports,
    evaluate_holdout_rows,
    write_eval_report,
)


def _synthetic_comparables(
    n: int = 50,
    *,
    neighborhood_id: int = 5,
    neighborhood_name: str = "Ulpiana",
    base_area: float = 78.0,
    base_rpsm: float = 4.5,
    website: str = "gjirafa",
) -> pd.DataFrame:
    rows = []
    for i in range(n):
        area = base_area + (i % 7 - 3) * 2
        rent = base_rpsm * area
        rows.append(
            {
                "source_website": website,
                "source_listing_id": f"L{i}",
                "rent_price": rent,
                "area_sqm": area,
                "bedrooms": 2,
                "neighborhood_id": neighborhood_id,
                "neighborhood_name": neighborhood_name,
                "property_type": "APARTMENT",
                "is_commercial": False,
                "rent_per_sqm": base_rpsm,
            }
        )
    return pd.DataFrame(rows)


class TestValuationEvaluation:
    def test_evaluate_holdout_with_synthetic_corpus(self, session) -> None:
        rent_df = _synthetic_comparables(55, base_rpsm=5.0)
        holdout = [
            {
                "holdout_id": "t-001",
                "source_website": "gjirafa",
                "source_listing_id": "L0",
                "valuation_type": "rent",
                "municipality": "Prishtina",
                "neighborhood": "Ulpiana",
                "area_sqm": "78",
                "bedrooms": "2",
                "actual_price_eur": "390",
            }
        ]
        report = evaluate_holdout_rows(session, holdout, rent_df=rent_df, sale_df=pd.DataFrame())
        assert report.evaluated_rows == 1
        assert report.mae is not None
        assert report.mape_pct is not None
        assert report.by_confidence_tier

    def test_leave_one_out_excludes_holdout_listing(self, session) -> None:
        rent_df = _synthetic_comparables(55, base_rpsm=5.0)
        rent_df.loc[0, "rent_per_sqm"] = 10.0
        rent_df.loc[0, "rent_price"] = 10.0 * rent_df.loc[0, "area_sqm"]
        holdout = [
            {
                "holdout_id": "t-loo",
                "source_website": "gjirafa",
                "source_listing_id": "L0",
                "valuation_type": "rent",
                "municipality": "Prishtina",
                "neighborhood": "Ulpiana",
                "area_sqm": str(int(rent_df.loc[0, "area_sqm"])),
                "actual_price_eur": str(int(rent_df.loc[0, "rent_price"])),
            }
        ]
        report = evaluate_holdout_rows(session, holdout, rent_df=rent_df, sale_df=pd.DataFrame())
        assert report.evaluated_rows == 1
        row = report.row_results[0]
        assert row["skipped"] is False
        assert row["abs_pct_error"] is not None
        assert row["abs_pct_error"] > 1.0

    def test_compare_passes_on_improvement(self) -> None:
        baseline = {"mape_pct": 12.0, "mae": 50.0, "rmse": 60.0, "median_ae": 40.0}
        candidate = {"mape_pct": 10.5, "mae": 50.0, "rmse": 60.0, "median_ae": 40.0}
        verdict = compare_eval_reports(baseline, candidate)
        assert verdict.passed is True

    def test_compare_fails_on_regression(self) -> None:
        baseline = {"mape_pct": 10.0, "mae": 50.0, "rmse": 60.0, "median_ae": 40.0}
        candidate = {"mape_pct": 12.0, "mae": 50.0, "rmse": 60.0, "median_ae": 40.0}
        verdict = compare_eval_reports(baseline, candidate)
        assert verdict.passed is False

    def test_write_eval_report(self, tmp_path, session) -> None:
        rent_df = _synthetic_comparables(MIN_COMPARABLES + 5)
        holdout = [
            {
                "holdout_id": "t-002",
                "valuation_type": "rent",
                "municipality": "Prishtina",
                "neighborhood": "Ulpiana",
                "area_sqm": "78",
                "actual_price_eur": "350",
            }
        ]
        report = evaluate_holdout_rows(session, holdout, rent_df=rent_df, sale_df=pd.DataFrame())
        json_path = tmp_path / "out.json"
        md_path = tmp_path / "out.md"
        write_eval_report(report, json_path=json_path, markdown_path=md_path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["evaluated_rows"] == 1
        assert "MAPE" in md_path.read_text(encoding="utf-8")

    def test_invalid_holdout_price_is_excluded(self, session) -> None:
        rent_df = _synthetic_comparables(55)
        holdout = [
            {
                "holdout_id": "bad-rent",
                "valuation_type": "rent",
                "municipality": "Prishtina",
                "neighborhood": "Ulpiana",
                "area_sqm": "78",
                "actual_price_eur": "1",
            }
        ]
        report = evaluate_holdout_rows(
            session,
            holdout,
            rent_df=rent_df,
            sale_df=pd.DataFrame(),
        )
        assert report.invalid_rows == 1
        assert report.evaluated_rows == 0
        assert report.row_results[0]["skip_reason"].startswith("invalid_holdout:")

    def test_absolute_release_gate_fails_closed(self) -> None:
        verdict = assess_release_readiness(
            {
                "evaluated_rows": 20,
                "evaluation_coverage_pct": 47.0,
                "invalid_rows": 0,
                "confidence_monotonic": None,
                "by_valuation_type": {
                    "rent": {"n": 10, "mdape_pct": 21.0},
                    "sale": {"n": 10, "mdape_pct": 40.0},
                },
            }
        )
        assert verdict.passed is False
        assert "MdAPE" in verdict.message

    def test_absolute_release_gate_passes_qualified_model(self) -> None:
        verdict = assess_release_readiness(
            {
                "evaluated_rows": 50,
                "evaluation_coverage_pct": 95.0,
                "invalid_rows": 0,
                "confidence_monotonic": None,
                "by_valuation_type": {
                    "rent": {"n": 25, "mdape_pct": 12.0},
                    "sale": {"n": 25, "mdape_pct": 28.0},
                },
            }
        )
        assert verdict.passed is True

    def test_confidence_monotonic_optional_until_calibrated(self) -> None:
        verdict = assess_release_readiness(
            {
                "evaluated_rows": 50,
                "evaluation_coverage_pct": 95.0,
                "invalid_rows": 0,
                "confidence_monotonic": None,
                "by_valuation_type": {
                    "rent": {"n": 25, "mdape_pct": 12.0},
                    "sale": {"n": 25, "mdape_pct": 28.0},
                },
            },
            require_confidence_monotonic=True,
        )
        assert verdict.passed is False
        assert "monotonic" in verdict.message
