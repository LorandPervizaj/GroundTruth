"""Report generation service. Output goes to reports/generated/, never beside source."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from groundtruth.analytics.market_table import build_neighborhood_market_table
from groundtruth.config import Settings, get_settings
from groundtruth.logging import get_logger

logger = get_logger(__name__)


class ReportService:
    """Generate research reports from analytics output into reports/generated/."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._templates_dir = self._settings.reports_templates_dir
        self._output_dir = self._settings.reports_generated_dir

    def generate_neighborhood_summary(self, df: pd.DataFrame) -> Path:
        """Export neighborhood market table as CSV to reports/generated/."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        table = build_neighborhood_market_table(df)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_path = self._output_dir / f"neighborhood_summary_{timestamp}.csv"
        table.to_csv(output_path, index=False)
        logger.info("report_generated", path=str(output_path), rows=len(table))
        return output_path

    def list_templates(self) -> list[Path]:
        """Return available report templates."""
        if not self._templates_dir.exists():
            return []
        return list(self._templates_dir.glob("*.md"))
