"""Generate professional annual market PDF from cached annual report JSON."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from groundtruth.analytics.annual_conclusions import build_rankings_commentary_from_payload
from groundtruth.analytics.annual_export import load_annual_report_cache
from groundtruth.analytics.corpus_filters import source_display_name

NAVY = colors.HexColor("#1a365d")
ACCENT = colors.HexColor("#1a4d38")
MUTED = colors.HexColor("#4a5568")
LIGHT_BG = colors.HexColor("#f7faf8")
CALLOUT_BG = colors.HexColor("#fff8e6")
CALLOUT_BORDER = colors.HexColor("#d4a84b")

LABELS: dict[str, dict[str, str]] = {
    "cover_tag": {
        "sq": "RAPORT VJETOR I TREGUT TË BANIMIT, PRISHTINË",
        "en": "ANNUAL RESIDENTIAL MARKET REPORT, PRISHTINA",
    },
    "cover_title": {
        "sq": "Raporti vjetor i tregut të Prishtinës {year}",
        "en": "{year} Prishtina Market Report",
    },
    "cover_sub": {
        "sq": "Pasqyrë e listimeve aktive të banimit në kryeqytet",
        "en": "Snapshot of active residential listings in the capital",
    },
    "cover_period": {
        "sq": "Periudha e mbuluar: {start} deri më {end}",
        "en": "Period covered: {start} to {end}",
    },
    "cover_sources": {
        "sq": (
            "Bazuar në listime aktive nga portalet kryesore. "
            "Të gjitha çmimet janë çmime kërkuese, jo transaksione të mbyllura."
        ),
        "en": (
            "Based on active listings from major portals. "
            "All figures are asking prices, not closed transactions."
        ),
    },
    "toc": {"sq": "Përmbajtja", "en": "Contents"},
    "executive_summary": {"sq": "Përmbledhje ekzekutive", "en": "Executive Summary"},
    "key_takeaways": {"sq": "Pikat kryesore", "en": "Key takeaways"},
    "quick_facts": {"sq": "Fakte kryesore", "en": "Quick Facts"},
    "kpi_total": {"sq": "Listime aktive", "en": "Active listings"},
    "kpi_rent": {"sq": "Pjesa e qirasë", "en": "Rent share"},
    "kpi_psm": {"sq": "Mediana €/m² (shitje)", "en": "Median €/m² (sale)"},
    "kpi_rent_med": {"sq": "Mediana qira", "en": "Median rent"},
    "sources": {"sq": "Burimet", "en": "Sources"},
    "market_overview": {"sq": "Pasqyra e tregut", "en": "Market Overview"},
    "listing_activity": {"sq": "Aktiviteti i listimeve", "en": "Listing Activity"},
    "sale_price_trend": {"sq": "Trendi i çmimeve të shitjes", "en": "Sale Price Trend"},
    "rent_price_trend": {"sq": "Trendi i qirasë", "en": "Rent Price Trend"},
    "area_overviews": {"sq": "Pasqyrat sipas lagjeve", "en": "Area Overviews"},
    "area_intro": {
        "sq": (
            "Tabela më poshtë përmbledh inventarin aktiv dhe medianat e kërkuara për dhjetë lagjet "
            "me më shumë listime. Krahasimet brenda lagjes janë më të besueshme se mesatarja e qytetit."
        ),
        "en": (
            "The table below summarizes active inventory and asking medians for the ten "
            "neighborhoods with the most listings. Within-neighborhood comparisons are more "
            "reliable than a single citywide average."
        ),
    },
    "rankings": {"sq": "Renditja e çmimeve sipas lagjes", "en": "Price Rankings by Neighborhood"},
    "rankings_note": {
        "sq": "Vetëm lagjet me ≥{n} listime shitje; mediana e çmimeve të kërkuara €/m².",
        "en": "Neighborhoods with ≥{n} sale listings; median asking €/m².",
    },
    "expensive": {"sq": "Më të shtrenjtat", "en": "Most expensive"},
    "affordable": {"sq": "Më të lirat", "en": "Most affordable"},
    "methodology": {
        "sq": "Metodologjia dhe burimet e të dhënave",
        "en": "Methodology & Data Sources",
    },
    "limitations_title": {"sq": "Kufizimet kryesore", "en": "Key Limitations"},
    "technical": {"sq": "Detaje teknike", "en": "Technical details"},
    "header": {
        "sq": "Metrik | Raporti vjetor i tregut, Prishtinë",
        "en": "Metrik | Prishtina Market Report",
    },
    "footer": {
        "sq": "Çmime kërkuese, jo transaksione. © {year} Metrik",
        "en": "Asking prices, not transactions. © {year} Metrik",
    },
    "page": {"sq": "Faqja {n}", "en": "Page {n}"},
    "nh_col": {"sq": "Lagja", "en": "Neighborhood"},
    "listings_col": {"sq": "Listime", "en": "Listings"},
    "psm_col": {"sq": "Mediana €/m²", "en": "Median €/m²"},
    "sale_col": {"sq": "Mediana shitje", "en": "Median sale"},
    "rent_col": {"sq": "Mediana qira", "en": "Median rent"},
    "n_col": {"sq": "n", "en": "n"},
}


def _t(key: str, lang: str, **kwargs: Any) -> str:
    text = LABELS.get(key, {}).get(lang) or LABELS.get(key, {}).get("en", key)
    return text.format(**kwargs) if kwargs else text


def _pick_i18n(obj: dict[str, Any] | None, lang: str) -> Any:
    if not obj:
        return None
    return obj.get(lang) or obj.get("en")


def _fmt_num(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_euro(value: Any) -> str:
    if value is None:
        return "—"
    return f"€{_fmt_num(value)}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{int(round(float(value)))}%"


def _period_range(payload: dict[str, Any]) -> tuple[str, str]:
    methodology = payload.get("methodology") or {}
    start = str(methodology.get("cutoff_date", ""))[:7] or "—"
    labels = (payload.get("volume") or {}).get("labels") or []
    end = labels[-1] if labels else datetime.now(UTC).strftime("%Y-%m")
    return start, end


def _chart_image(
    labels: list[str],
    values: list[float] | list[list[float]],
    *,
    title: str,
    ylabel: str,
    color: str = "#1a4d38",
    chart_type: str = "line",
    height_inch: float = 2.6,
) -> Image:
    fig_h = max(2.0, height_inch * 0.42)
    fig, ax = plt.subplots(figsize=(6.5, fig_h), dpi=120)
    fig.patch.set_facecolor("white")
    if chart_type == "bar" and values and isinstance(values[0], (list, tuple)):
        rent_vals, sale_vals = values  # type: ignore[misc]
        x = range(len(labels))
        width = 0.38
        ax.bar([i - width / 2 for i in x], rent_vals, width, label="Rent", color="#8bb9a3")
        ax.bar([i + width / 2 for i in x], sale_vals, width, label="Sale", color="#1a4d38")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.legend(loc="upper right", fontsize=8)
    else:
        line_vals = [float(v) for v in values]  # type: ignore[arg-type]
        ax.plot(range(len(labels)), line_vals, color=color, linewidth=2.2, marker="o", markersize=3)
        ax.fill_between(range(len(labels)), line_vals, alpha=0.08, color=color)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.set_title(title, fontsize=10, fontweight="bold", color="#1a365d", pad=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _p: f"{int(round(x)):,}"))
    ax.grid(axis="y", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=6.5 * inch, height=height_inch * inch)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontSize=24,
            leading=28,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontSize=12,
            leading=16,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading1"],
            fontSize=15,
            leading=19,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.black,
            spaceAfter=8,
            alignment=TA_JUSTIFY,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontSize=9,
            leading=13,
            textColor=MUTED,
            spaceAfter=6,
            alignment=TA_JUSTIFY,
            fontName="Helvetica-Oblique",
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontSize=8,
            leading=11,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=5,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            parent=base["Normal"],
            fontSize=17,
            leading=21,
            textColor=NAVY,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "callout_title": ParagraphStyle(
            "callout_title",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
            textColor=NAVY,
            fontName="Helvetica-Bold",
            spaceAfter=6,
        ),
    }


def _kpi_table(kpis: dict[str, Any], styles: dict[str, ParagraphStyle], lang: str) -> Table:
    cells = [
        [
            Paragraph(_fmt_num(kpis.get("total_listings")), styles["kpi_value"]),
            Paragraph(_fmt_pct(kpis.get("rent_pct")), styles["kpi_value"]),
            Paragraph(_fmt_euro(kpis.get("median_sale_price_per_sqm")), styles["kpi_value"]),
            Paragraph(_fmt_euro(kpis.get("median_rent")), styles["kpi_value"]),
        ],
        [
            Paragraph(_t("kpi_total", lang), styles["kpi_label"]),
            Paragraph(_t("kpi_rent", lang), styles["kpi_label"]),
            Paragraph(_t("kpi_psm", lang), styles["kpi_label"]),
            Paragraph(_t("kpi_rent_med", lang), styles["kpi_label"]),
        ],
    ]
    table = Table(cells, colWidths=[1.55 * inch] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8e2dc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _data_table(headers: list[str], rows: list[list[str]]) -> Table:
    data = [headers, *rows]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _limitations_box(
    bullets: list[str],
    styles: dict[str, ParagraphStyle],
    lang: str,
) -> Table:
    rows = [[Paragraph(_t("limitations_title", lang), styles["callout_title"])]]
    for line in bullets:
        rows.append([Paragraph(f"• {line}", styles["body"])])
    table = Table(rows, colWidths=[6.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG),
                ("BOX", (0, 0), (-1, -1), 1, CALLOUT_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _chart_block(
    title: str,
    caption: str,
    chart: Image,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    return [
        KeepTogether(
            [
                Paragraph(title, styles["section"]),
                Paragraph(caption, styles["caption"]),
                chart,
                Spacer(1, 0.12 * inch),
            ]
        )
    ]


def build_annual_pdf_bytes(
    data: dict[str, Any] | None = None,
    *,
    lang: str = "en",
) -> bytes:
    """Render annual report PDF; uses cache when *data* is omitted."""
    payload = data if data is not None else load_annual_report_cache()
    if not payload:
        raise ValueError("No annual report data available")

    lang = lang if lang in ("sq", "en") else "en"
    year = datetime.now().year
    kpis = payload.get("kpis") or {}
    methodology = payload.get("methodology") or {}
    executive = _pick_i18n(payload.get("executive_summary"), lang) or ""
    insights = (
        _pick_i18n(payload.get("insights"), lang)
        or _pick_i18n(payload.get("conclusions"), lang)
        or []
    )
    narratives = _pick_i18n(payload.get("narratives_i18n"), lang) or payload.get("narratives") or {}
    rankings_commentary = _pick_i18n(payload.get("rankings_commentary"), lang) or ""
    if not rankings_commentary:
        rankings_commentary = (
            _pick_i18n(build_rankings_commentary_from_payload(payload), lang) or ""
        )
    limitations = _pick_i18n(payload.get("limitations"), lang) or []
    methodology_plain = _pick_i18n((payload.get("methodology_plain") or {}).get("plain"), lang)
    period_start, period_end = _period_range(payload)

    buf = io.BytesIO()
    page_counter = {"n": 0}

    def on_page(canvas, doc):  # noqa: ANN001
        page_counter["n"] += 1
        n = page_counter["n"]
        canvas.saveState()
        if n > 1:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(NAVY)
            canvas.drawString(0.75 * inch, letter[1] - 0.48 * inch, _t("header", lang))
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.75 * inch, 0.42 * inch, _t("footer", lang, year=year))
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.42 * inch, _t("page", lang, n=n))
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.78 * inch,
        bottomMargin=0.62 * inch,
        title=f"Metrik Prishtina Market Report {year}",
        author="Metrik",
    )
    styles = _styles()
    story: list[Any] = []

    # —— Cover ——
    story.append(Spacer(1, 0.9 * inch))
    story.append(
        Paragraph(
            _t("cover_tag", lang),
            ParagraphStyle("tag", parent=styles["cover_sub"], fontSize=10, textColor=ACCENT),
        )
    )
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph(_t("cover_title", lang, year=year), styles["cover_title"]))
    story.append(Paragraph(_t("cover_sub", lang), styles["cover_sub"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(_t("cover_period", lang, start=period_start, end=period_end), styles["cover_sub"])
    )
    story.append(Paragraph(_t("cover_sources", lang), styles["cover_sub"]))
    story.append(Spacer(1, 0.45 * inch))
    story.append(Paragraph(_t("toc", lang), styles["section"]))
    toc_keys = [
        "executive_summary",
        "quick_facts",
        "listing_activity",
        "sale_price_trend",
        "rent_price_trend",
        "area_overviews",
        "rankings",
        "methodology",
    ]
    for i, key in enumerate(toc_keys, 1):
        story.append(Paragraph(f"{i}. {_t(key, lang)}", styles["body"]))
    story.append(PageBreak())

    # —— Executive Summary ——
    story.append(Paragraph(_t("executive_summary", lang), styles["section"]))
    if executive:
        story.append(Paragraph(executive, styles["body"]))
    if insights:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(_t("key_takeaways", lang), styles["body"]))
        for line in insights[:4]:
            story.append(Paragraph(line, styles["bullet"], bulletText="•"))
    story.append(PageBreak())

    # —— Quick Facts ——
    story.append(Paragraph(_t("quick_facts", lang), styles["section"]))
    story.append(_kpi_table(kpis, styles, lang))
    story.append(Spacer(1, 0.15 * inch))
    sources = payload.get("sources") or []
    if sources:
        src_lines = [
            f"{source_display_name(str(row.get('source_website', '')))}: {_fmt_num(row.get('listings'))}"
            for row in sources
        ]
        story.append(Paragraph(f"{_t('sources', lang)}: " + " · ".join(src_lines), styles["body"]))
    story.append(PageBreak())

    # —— Charts: activity on its own page ——
    volume = payload.get("volume") or {}
    labels = volume.get("labels") or []
    if labels:
        tail = labels[-12:]
        ri = len(labels) - len(tail)
        rent = (volume.get("rent") or [])[ri:]
        sale = (volume.get("sale") or [])[ri:]
        vol_caption = narratives.get("volume_insight", "")
        vol_chart = _chart_image(
            tail,
            [rent, sale],
            title="New listings by month (rent vs sale)",
            ylabel="Listings",
            chart_type="bar",
            height_inch=2.8,
        )
        story.extend(_chart_block(_t("listing_activity", lang), vol_caption, vol_chart, styles))
        story.append(PageBreak())

    # —— Sale + rent trends on one page (fixes orphaned rent header) ——
    price_blocks: list[Any] = []
    prices = payload.get("prices") or {}
    if prices.get("labels"):
        plabels = prices["labels"][-12:]
        pi = len(prices["labels"]) - len(plabels)
        pvals = [v for v in prices["values"][pi:] if v is not None]
        plabels = [
            m
            for m, v in zip(prices["labels"][pi:], prices["values"][pi:], strict=True)
            if v is not None
        ]
        sale_chart = _chart_image(
            plabels,
            pvals,
            title="Monthly median asking €/m² (sale)",
            ylabel="€/m²",
            height_inch=2.15,
        )
        price_blocks.extend(
            _chart_block(
                _t("sale_price_trend", lang),
                narratives.get("price_insight", ""),
                sale_chart,
                styles,
            )
        )

    rent_prices = payload.get("rent_prices") or {}
    if rent_prices.get("labels"):
        tail_pairs = list(
            zip(
                rent_prices["labels"][-12:],
                rent_prices["values"][-12:],
                strict=True,
            )
        )
        rlabels = [m for m, v in tail_pairs if v is not None]
        rvals = [v for _, v in tail_pairs if v is not None]
        rent_chart = _chart_image(
            rlabels,
            rvals,
            title="Monthly median asking rent",
            ylabel="€/month",
            color="#5a7a6a",
            height_inch=2.15,
        )
        price_blocks.extend(
            _chart_block(
                _t("rent_price_trend", lang),
                narratives.get("rent_insight", ""),
                rent_chart,
                styles,
            )
        )

    if price_blocks:
        story.extend(price_blocks)
        story.append(PageBreak())

    # —— Area overviews ——
    story.append(Paragraph(_t("area_overviews", lang), styles["section"]))
    story.append(Paragraph(_t("area_intro", lang), styles["body"]))
    nh_rows = payload.get("neighborhood_table") or []
    if nh_rows:
        story.append(
            _data_table(
                [
                    _t("nh_col", lang),
                    _t("listings_col", lang),
                    _t("psm_col", lang),
                    _t("rent_col", lang),
                ],
                [
                    [
                        str(r.get("neighborhood", "")),
                        _fmt_num(r.get("inventory")),
                        _fmt_euro(r.get("median_price_per_sqm")),
                        _fmt_euro(r.get("median_rent")),
                    ]
                    for r in nh_rows
                ],
            )
        )
    story.append(PageBreak())

    # —— Rankings ——
    rankings = payload.get("neighborhood_rankings") or {}
    min_n = rankings.get("min_sale_listings", 15)
    story.append(Paragraph(_t("rankings", lang), styles["section"]))
    story.append(Paragraph(_t("rankings_note", lang, n=min_n), styles["small"]))
    if rankings_commentary:
        story.append(Paragraph(rankings_commentary, styles["body"]))
    expensive = rankings.get("expensive") or []
    affordable = rankings.get("affordable") or []
    if expensive:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(_t("expensive", lang), styles["body"]))
        story.append(
            _data_table(
                [_t("nh_col", lang), _t("psm_col", lang), _t("sale_col", lang), _t("n_col", lang)],
                [
                    [
                        str(r.get("neighborhood", "")),
                        _fmt_euro(r.get("median_price_per_sqm")),
                        _fmt_euro(r.get("median_sale_eur")),
                        _fmt_num(r.get("n")),
                    ]
                    for r in expensive
                ],
            )
        )
    if affordable:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(_t("affordable", lang), styles["body"]))
        story.append(
            _data_table(
                [_t("nh_col", lang), _t("psm_col", lang), _t("sale_col", lang), _t("n_col", lang)],
                [
                    [
                        str(r.get("neighborhood", "")),
                        _fmt_euro(r.get("median_price_per_sqm")),
                        _fmt_euro(r.get("median_sale_eur")),
                        _fmt_num(r.get("n")),
                    ]
                    for r in affordable
                ],
            )
        )
    story.append(PageBreak())

    # —— Methodology ——
    story.append(Paragraph(_t("methodology", lang), styles["section"]))
    if methodology_plain:
        story.append(Paragraph(methodology_plain, styles["body"]))
    else:
        story.append(
            Paragraph(
                f"Active listings published within {methodology.get('window_months', 12)} months "
                f"from {methodology.get('cutoff_date', '—')}. "
                f"{methodology.get('note', 'Asking prices from portal listings.')}",
                styles["body"],
            )
        )
    if limitations:
        story.append(Spacer(1, 0.12 * inch))
        story.append(_limitations_box(limitations, styles, lang))

    tech_parts: list[str] = []
    plain_tech = (payload.get("methodology_plain") or {}).get("technical") or {}
    if plain_tech.get("parsers") or methodology.get("parser_versions"):
        parsers = plain_tech.get("parsers") or ", ".join(methodology.get("parser_versions") or [])
        tech_parts.append(f"Parsers: {parsers}")
    if plain_tech.get("gazetteer") or methodology.get("gazetteer_version"):
        gaz = plain_tech.get("gazetteer") or methodology.get("gazetteer_version")
        tech_parts.append(f"Gazetteer version: {gaz}")
    generated = payload.get("generated_at", "")[:10]
    if generated:
        tech_parts.append(f"Generated: {generated}")
    if tech_parts:
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(_t("technical", lang), styles["callout_title"]))
        story.append(Paragraph(" · ".join(tech_parts), styles["small"]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
