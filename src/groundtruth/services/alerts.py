"""Persist price alert signups (notifications not yet automated)."""

from __future__ import annotations

from groundtruth.schemas.alerts import SavedAlertRequest
from groundtruth.services.product_submissions import append_product_submission


def log_price_alert(alert: SavedAlertRequest) -> None:
    append_product_submission("alerts", alert.model_dump(exclude_none=True))
