"""Persist price alert signups (notifications not yet automated)."""

from groundtruth.schemas.alerts import SavedAlertRequest
from groundtruth.services.product_submissions import append_product_submission


def log_price_alert(alert: SavedAlertRequest) -> None:
    """Persist an alert signup. Callers must check alerts_signup_enabled first."""
    append_product_submission("alerts", alert.model_dump(exclude_none=True))
