"""Tests for business coverage KPI aggregation."""

import pandas as pd

from groundtruth.schemas.coverage_analytics import MunicipalityCoverageRow
from groundtruth.services.coverage_metrics import (
    _coverage_opportunity_backlog,
    _municipality_coverage,
    _projected_confidence_coverage,
    load_urban_demand_weights,
)


def test_load_urban_demand_weights_normalized() -> None:
    weights = load_urban_demand_weights()
    assert abs(sum(weights.values()) - 1.0) < 0.01
    assert weights["Prishtina"] > 0.3


def test_municipality_coverage_weighted() -> None:
    nh_table = pd.DataFrame(
        [
            {
                "neighborhood_id": 1,
                "neighborhood": "Ulpiana",
                "rent_comps": 40,
                "sale_comps": 10,
                "rent_estimate_ready": True,
                "sale_estimate_ready": False,
            },
            {
                "neighborhood_id": 2,
                "neighborhood": "Dardania",
                "rent_comps": 5,
                "sale_comps": 5,
                "rent_estimate_ready": False,
                "sale_estimate_ready": False,
            },
        ]
    )
    city_by_nh = {1: "Prishtina", 2: "Prishtina"}
    weights = {"Prishtina": 0.5, "Prizren": 0.5}
    pct, rows = _municipality_coverage(nh_table, city_by_nh, weights)
    assert pct == 50.0
    assert rows[0].covered is True
    assert rows[1].covered is False


def test_municipality_coverage_prishtina_only_in_gazetteer() -> None:
    nh_table = pd.DataFrame(
        [
            {
                "neighborhood_id": 10,
                "neighborhood": "Center",
                "rent_comps": 35,
                "sale_comps": 0,
                "rent_estimate_ready": True,
                "sale_estimate_ready": False,
            }
        ]
    )
    city_by_nh = {10: "Prizren"}
    weights = {"Prishtina": 0.6, "Prizren": 0.4}
    pct, rows = _municipality_coverage(nh_table, city_by_nh, weights)
    assert pct == 40.0
    prizren = next(r for r in rows if r.municipality == "Prizren")
    assert prizren.covered is True


def test_projected_confidence_coverage() -> None:
    nh_table = pd.DataFrame(
        [
            {"rent_comps": 90, "sale_comps": 0},
            {"rent_comps": 45, "sale_comps": 0},
            {"rent_comps": 10, "sale_comps": 0},
        ]
    )
    cc = _projected_confidence_coverage(nh_table)
    assert cc.high_count == 0
    assert cc.medium_count == 2
    assert cc.insufficient_count == 1
    assert cc.high_pct == 0.0
    assert cc.medium_pct == 66.7


def test_opportunity_backlog_ranks_by_demand_gap_population() -> None:
    rows = [
        MunicipalityCoverageRow(
            municipality="Peja",
            demand_weight_pct=8.0,
            covered=False,
            neighborhoods_total=1,
            neighborhoods_estimate_ready=0,
        ),
        MunicipalityCoverageRow(
            municipality="Rahovec",
            demand_weight_pct=2.0,
            covered=False,
            neighborhoods_total=0,
            neighborhoods_estimate_ready=0,
        ),
    ]
    population = {"Peja": 49000, "Rahovec": 56000}
    backlog = _coverage_opportunity_backlog(rows, population)
    assert backlog[0].municipality == "Peja"
    assert backlog[0].opportunity_score > backlog[1].opportunity_score
