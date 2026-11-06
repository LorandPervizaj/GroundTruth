import pandas as pd
import pytest

from groundtruth.analytics.unit_price_impact import latest_active, project_prices


def rows():
    return pd.DataFrame(
        [
            {
                "normalized_id": 1,
                "source_website": "gjirafa",
                "source_listing_id": "a",
                "sale_price": 90000.0,
                "price_per_sqm": 900.0,
                "currently_valid": True,
                "currently_active": True,
            },
            {
                "normalized_id": 2,
                "source_website": "gjirafa",
                "source_listing_id": "a",
                "sale_price": 130000.0,
                "price_per_sqm": 1300.0,
                "currently_valid": True,
                "currently_active": True,
            },
            {
                "normalized_id": 3,
                "source_website": "harta",
                "source_listing_id": "b",
                "sale_price": 70000.0,
                "price_per_sqm": 1000.0,
                "currently_valid": False,
                "currently_active": False,
            },
        ]
    )


def decision(identifier=2, codes=None, projectable=True):
    return {
        "normalized_id": identifier,
        "projectable": projectable,
        "new_sale_price": None,
        "new_price_per_sqm": None,
        "introduced_validation_codes": codes or [],
    }


def test_quarantine_exposes_older_eligible_row_without_changing_the_input():
    original = rows()
    projected = project_prices(original, [decision(codes=["missing_price"])])
    assert latest_active(projected)["normalized_id"].tolist() == [1]
    assert latest_active(original)["normalized_id"].tolist() == [2]


def test_existing_exclusions_are_never_promoted_and_manual_cases_do_not_change():
    original = rows()
    projected = project_prices(original, [decision(3), decision(projectable=False)])
    assert not projected.loc[2, "currently_active"]
    pd.testing.assert_series_equal(projected.loc[1], original.loc[1])


def test_repeated_or_unknown_targets_fail():
    with pytest.raises(ValueError, match="Duplicate"):
        project_prices(rows(), [decision(), decision()])
    with pytest.raises(ValueError, match="Missing"):
        project_prices(rows(), [decision(99)])
