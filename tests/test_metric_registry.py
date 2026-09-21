from __future__ import annotations

import pytest

from groundtruth.analytics.metric_registry import (
    METRICS,
    POPULATIONS,
    metric_definition,
    population_definition,
    validate_registry,
)


def test_registry_is_internally_valid() -> None:
    validate_registry()
    assert len(METRICS) == len(set(METRICS))
    assert len(POPULATIONS) == len(set(POPULATIONS))


def test_every_metric_declares_a_known_population() -> None:
    for metric in METRICS.values():
        assert population_definition(metric.population_id)
        assert metric.required_fields is not None
        assert metric.rounding_rule


def test_median_compatibility_aliases_do_not_change_statistic() -> None:
    sale = metric_definition("median_sale_psm")
    rent = metric_definition("median_rent_psm")
    assert sale.statistic == rent.statistic == "median"
    assert "average_sale_psm_eur" in sale.deprecated_api_aliases
    assert "average_rent_psm_eur" in rent.deprecated_api_aliases


def test_unknown_metric_and_population_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown public metric"):
        metric_definition("UNKNOWN")
    with pytest.raises(ValueError, match="unknown metric population"):
        population_definition("UNKNOWN")
