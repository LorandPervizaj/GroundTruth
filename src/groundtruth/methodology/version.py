"""Semantic versioning for statistical methodology — independent from parser version."""

METHODOLOGY_VERSION = "1.0.0"

METHODOLOGY_CHANGELOG: dict[str, str] = {
    "1.0.0": (
        "Bootstrap median CI (5000 resamples). Median + IQR + MAD. "
        "Dataset confidence v1 with smooth sample_reliability. Stability score v1."
    ),
}
