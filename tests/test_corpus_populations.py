from __future__ import annotations

import pandas as pd
import pytest

from groundtruth.analytics import corpus_populations as populations


def test_named_population_functions_are_distinct() -> None:
    assert populations.current_inventory_dataframe is not populations.recent_pricing_dataframe
    assert populations.recent_pricing_dataframe is not populations.valuation_comparables_dataframe
    assert (
        populations.valuation_comparables_dataframe
        is not populations.historical_observations_dataframe
    )


def test_recent_pricing_requires_explicit_positive_window() -> None:
    with pytest.raises(ValueError, match="positive"):
        populations.recent_pricing_dataframe(None, window_days=0)  # type: ignore[arg-type]


def test_canonical_population_selects_only_primaries(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame({"normalized_id": [1, 2]})
    monkeypatch.setattr(
        populations,
        "apply_cross_dedupe",
        lambda value: value.assign(is_canonical_primary=[True, False]),
    )
    assert populations._canonical(frame)["normalized_id"].tolist() == [1]
