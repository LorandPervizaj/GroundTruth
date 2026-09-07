"""Report generation service. Output goes to reports/generated/, never beside source."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from groundtruth.analytics.coverage import build_neighborhood_coverage_table
from groundtruth.analytics.dataframe import normalized_listings_dataframe
from groundtruth.analytics.market_table import build_neighborhood_market_table
from groundtruth.analytics.valuation import MIN_COMPARABLES
from groundtruth.config import Settings, get_settings
from groundtruth.gazetteers.version import compute_gazetteer_version
from groundtruth.logging import get_logger
from groundtruth.services.normalization import NORMALIZATION_VERSION
from groundtruth.services.parsing import PARSER_VERSION

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

    def generate_market_report_v01(self, session: Session) -> Path:
        """Generate Market Report v0.1 markdown from all normalized listings."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        df = normalized_listings_dataframe(session)
        if df.empty:
            raise ValueError("No normalized listings available for market report")

        table = build_neighborhood_market_table(df)
        nh_names = df.drop_duplicates("neighborhood_id").set_index("neighborhood_id")[
            "neighborhood"
        ]
        if not table.empty and "neighborhood_id" in table.columns:
            table = table.copy()
            table["neighborhood"] = table["neighborhood_id"].map(nh_names).fillna("Unknown")

        sale_df = df[df["listing_type"] == "sale"]
        rent_df = df[df["listing_type"] == "rent"]
        total = len(df)
        sale_pct = round(100.0 * len(sale_df) / total, 1) if total else 0.0
        rent_pct = round(100.0 * len(rent_df) / total, 1) if total else 0.0
        median_price_per_sqm = sale_df["price_per_sqm"].median() if not sale_df.empty else 0.0
        mean_area = df["area_sqm"].dropna().mean() if not df["area_sqm"].dropna().empty else 0.0

        def _fmt(value, fmt: str = ".0f", fallback: str = "—") -> str:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return fallback
            return format(value, fmt)

        top20 = table.head(20) if not table.empty else pd.DataFrame()
        neighborhood_rows = []
        for _, row in top20.iterrows():
            name = row.get("neighborhood", row.get("neighborhood_id", "?"))
            neighborhood_rows.append(
                f"| {name} | {_fmt(row.get('median_price_per_sqm'))} | "
                f"{int(row.get('inventory', 0) or 0)} | {_fmt(row.get('median_size_sqm'))} | "
                f"{_fmt(row.get('median_rent'))} | {_fmt(row.get('gross_yield_pct'))} | "
                f"{_fmt(row.get('luxury_percentage'))} |"
            )

        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        executive_summary = (
            f"GroundTruth Market Report v0.1 covers **{total:,}** normalized listings "
            f"from Gjirafa ({sale_pct}% sale, {rent_pct}% rent). "
            f"Overall median sale price is **€{median_price_per_sqm:,.0f}/m²** "
            f"with average apartment size **{mean_area:.0f} m²**. "
            f"Parser {PARSER_VERSION}, normalizer {NORMALIZATION_VERSION}, "
            f"gazetteer {compute_gazetteer_version()}."
        )

        template_path = self._templates_dir / "neighborhood_summary.md"
        if template_path.exists():
            body = template_path.read_text(encoding="utf-8")
        else:
            body = "# Kosovo Real Estate Market Report\n\n**Generated:** {{ generated_at }}\n"

        body = (
            body.replace("{{ generated_at }}", generated_at)
            .replace("{{ data_period }}", "All available listings")
            .replace("{{ executive_summary }}", executive_summary)
            .replace(
                "{{ neighborhood_rows }}",
                "\n".join(neighborhood_rows) or "| — | — | — | — | — | — | — |",
            )
        )

        timestamp = datetime.now(UTC).strftime("%Y%m%d")
        output_path = self._output_dir / f"market_report_v0.1_{timestamp}.md"
        output_path.write_text(body, encoding="utf-8")
        table_path = self._output_dir / f"market_report_v0.1_{timestamp}_table.csv"
        if not table.empty:
            table.to_csv(table_path, index=False)

        logger.info("market_report_generated", path=str(output_path), listings=total)
        return output_path

    def generate_coverage_report(self, session: Session) -> tuple[Path, Path]:
        """Export neighborhood rent/sale comparable coverage as CSV + markdown."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        table = build_neighborhood_coverage_table(session)
        if table.empty:
            raise ValueError("No neighborhoods in gazetteer")

        timestamp = datetime.now(UTC).strftime("%Y%m%d")
        csv_path = self._output_dir / f"coverage_{timestamp}.csv"
        table.to_csv(csv_path, index=False)

        rent_ready = int(table["rent_estimate_ready"].sum())
        sale_ready = int(table["sale_estimate_ready"].sum())
        total_rent = int(table["rent_comps"].sum())
        total_sale = int(table["sale_comps"].sum())
        nh_count = len(table)

        lines = [
            "# Neighborhood data coverage",
            "",
            f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Parser:** {PARSER_VERSION} · **Estimate-ready threshold:** n≥{MIN_COMPARABLES}",
            "",
            "## Summary",
            "",
            f"- **{nh_count}** gazetteer neighborhoods",
            f"- **{total_rent:,}** rent comparables · **{rent_ready}** neighborhoods estimate-ready",
            f"- **{total_sale:,}** sale comparables · **{sale_ready}** neighborhoods estimate-ready",
            "",
            "Rent comps use valuation filters (apartments, €80–2,500/mo, 20–200 m²). "
            "Sale comps mirror sale valuation prep (apartments, €10k–500k, 20–200 m²).",
            "",
            "## By neighborhood",
            "",
            "| Neighborhood | Rent comps | Sale comps | Rent ready | Sale ready |",
            "| --- | ---: | ---: | --- | --- |",
        ]
        for _, row in table.iterrows():
            rent_flag = "Yes" if row["rent_estimate_ready"] else "No"
            sale_flag = "Yes" if row["sale_estimate_ready"] else "No"
            lines.append(
                f"| {row['neighborhood']} | {int(row['rent_comps'])} | "
                f"{int(row['sale_comps'])} | {rent_flag} | {sale_flag} |"
            )

        md_path = self._output_dir / f"coverage_{timestamp}.md"
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(
            "coverage_report_generated",
            csv=str(csv_path),
            markdown=str(md_path),
            rent_comps=total_rent,
            sale_comps=total_sale,
        )
        return csv_path, md_path

    def list_templates(self) -> list[Path]:
        """Return available report templates."""
        if not self._templates_dir.exists():
            return []
        return list(self._templates_dir.glob("*.md"))
