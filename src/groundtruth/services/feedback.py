"""Persist user-reported data errors."""

from __future__ import annotations

from groundtruth.schemas.feedback import DataFeedbackRequest
from groundtruth.services.product_submissions import append_product_submission


def log_data_feedback(feedback: DataFeedbackRequest) -> None:
    append_product_submission("feedback", feedback.model_dump(exclude_none=True))
