"""Rule-based bilingual copy for the public statistics dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import pandas as pd

from groundtruth.analytics.corpus_filters import active_sources_phrase

Trend = Literal["up", "down", "stable"]

MIN_NEIGHBORHOOD_LISTINGS = 15
MIN_SALE_LISTINGS_PER_NH = 15
ACTIVITY_CHANGE_THRESHOLD_PCT = 10.0
PRICE_CHANGE_THRESHOLD_PCT = 5.0
NH_CONCENTRATION_THRESHOLD_PCT = 15.0
VOLUME_SPIKE_RATIO = 2.0


@dataclass(frozen=True)
class AnnualConclusionContext:
    total: int
    rent_count: int
    sale_count: int
    rent_pct: float
    median_sale_psm: float | None
    median_rent: float | None
    cutoff_date: date
    coverage: dict[str, float]
    sources: list[dict[str, Any]]
    top_neighborhood: str | None
    top_neighborhood_count: int
    volume_by_month: dict[str, dict[str, int]]  # month -> {rent, sale}
    sale_psm_by_month: dict[str, float]
    work: pd.DataFrame


def _three_month_activity_trend(volume_by_month: dict[str, dict[str, int]]) -> Trend | None:
    months = sorted(volume_by_month)
    if len(months) < 6:
        return None
    recent = sum(volume_by_month[m]["rent"] + volume_by_month[m]["sale"] for m in months[-3:])
    prior = sum(volume_by_month[m]["rent"] + volume_by_month[m]["sale"] for m in months[-6:-3])
    if prior <= 0:
        return None
    change_pct = 100.0 * (recent - prior) / prior
    if change_pct >= ACTIVITY_CHANGE_THRESHOLD_PCT:
        return "up"
    if change_pct <= -ACTIVITY_CHANGE_THRESHOLD_PCT:
        return "down"
    return "stable"


def _three_month_sale_price_trend(sale_psm_by_month: dict[str, float]) -> Trend | None:
    months = sorted(sale_psm_by_month)
    if len(months) < 6:
        return None
    recent_vals = [sale_psm_by_month[m] for m in months[-3:] if m in sale_psm_by_month]
    prior_vals = [sale_psm_by_month[m] for m in months[-6:-3] if m in sale_psm_by_month]
    if len(recent_vals) < 2 or len(prior_vals) < 2:
        return None
    recent_med = float(pd.Series(recent_vals).median())
    prior_med = float(pd.Series(prior_vals).median())
    if prior_med <= 0:
        return None
    change_pct = 100.0 * (recent_med - prior_med) / prior_med
    if change_pct >= PRICE_CHANGE_THRESHOLD_PCT:
        return "up"
    if change_pct <= -PRICE_CHANGE_THRESHOLD_PCT:
        return "down"
    return "stable"


def _nh_sale_medians(work: pd.DataFrame) -> pd.DataFrame:
    sale = work[work["listing_type"] == "sale"].dropna(subset=["neighborhood", "price_per_sqm"])
    if sale.empty:
        return pd.DataFrame(columns=["neighborhood", "n", "median_psm"])
    grouped = (
        sale.groupby("neighborhood")["price_per_sqm"]
        .agg(n="count", median_psm="median")
        .reset_index()
    )
    return grouped[grouped["n"] >= MIN_SALE_LISTINGS_PER_NH]


def _volume_spike_month(volume_by_month: dict[str, dict[str, int]]) -> str | None:
    if not volume_by_month:
        return None
    totals = {m: v["rent"] + v["sale"] for m, v in volume_by_month.items()}
    if len(totals) < 4:
        return None
    median_vol = float(pd.Series(list(totals.values())).median())
    if median_vol <= 0:
        return None
    month, peak = max(totals.items(), key=lambda x: x[1])
    if peak >= median_vol * VOLUME_SPIKE_RATIO:
        return month
    return None


def _price_spike_month(sale_psm_by_month: dict[str, float]) -> tuple[str | None, bool]:
    if len(sale_psm_by_month) < 4:
        return None, False
    series = pd.Series(sale_psm_by_month)
    peak_month = str(series.idxmax())
    peak_val = float(series.max())
    others = series.drop(peak_month)
    median_val = float(others.median())
    is_outlier = peak_val >= median_val * 1.15
    return peak_month, is_outlier


def _price_trough_month(
    sale_psm_by_month: dict[str, float],
) -> tuple[str | None, bool, float | None]:
    if len(sale_psm_by_month) < 4:
        return None, False, None
    series = pd.Series(sale_psm_by_month)
    trough_month = str(series.idxmin())
    trough_val = float(series.min())
    others = series.drop(trough_month)
    median_val = float(others.median())
    is_outlier = trough_val <= median_val * 0.75
    return trough_month, is_outlier, trough_val


def _top_neighborhood_share(ctx: AnnualConclusionContext) -> float:
    if ctx.total <= 0 or not ctx.top_neighborhood_count:
        return 0.0
    return 100.0 * ctx.top_neighborhood_count / ctx.total


def build_executive_summary(ctx: AnnualConclusionContext) -> dict[str, str]:
    """Two to three sentences for the headline panel."""
    if ctx.total == 0:
        return {
            "sq": "Nuk kemi të dhëna të mjaftueshme për të përshkruar tregun në këtë periudhë.",
            "en": "We do not have enough data to describe the market for this period.",
        }

    sources = active_sources_phrase(ctx.sources)
    rent_led = ctx.rent_pct >= 55

    if rent_led:
        sq_lead = (
            "Tregu i banimit në Prishtinë gjatë vitit të fundit është kryesisht i orientuar nga qiratë: "
            "shumica e ofertës aktive vjen nga listime qiraje, jo shitje."
        )
        en_lead = (
            "Prishtina's housing market over the past year is primarily rent-led: "
            "most active supply on major portals is rental, not for-sale stock."
        )
    else:
        sq_lead = (
            "Oferta aktive e banimit në Prishtinë është më e balancuar midis qirasë dhe shitjes "
            "krahasuar me një treg të orientuar vetëm nga qiratë."
        )
        en_lead = (
            "Active housing supply in Prishtina is more balanced between rent and sale "
            "than in a rent-only market."
        )

    sq_mid = (
        f"Monitorojmë listime nga {sources}; çmimet më poshtë janë çmime kërkuese nga portalet, "
        "jo çmime të konfirmuara transaksionesh."
    )
    en_mid = (
        f"We track listings from {sources}; figures below are asking prices from portals, "
        "not confirmed transaction prices."
    )

    if ctx.median_sale_psm is not None and ctx.median_rent is not None:
        sq_tail = (
            "Në nivel qyteti, medianat e fundit sugjerojnë presion të moderuar në qira, "
            "ndërsa çmimet e kërkuara të shitjes ndryshojnë më shumë sipas lagjes."
        )
        en_tail = (
            "Citywide, recent medians suggest moderate rent levels, "
            "while asking sale prices vary more by neighborhood."
        )
    else:
        sq_tail = "Krahasimet midis lagjeve janë më të besueshme se vlerësimi i një 'çmimi të vetëm qyteti'."
        en_tail = "Neighborhood comparisons are more reliable than a single citywide price tag."

    return {
        "sq": " ".join([sq_lead, sq_mid, sq_tail]),
        "en": " ".join([en_lead, en_mid, en_tail]),
    }


def build_insights(ctx: AnnualConclusionContext) -> dict[str, list[str]]:
    """Three to four analyst-style insights — not KPI restatements."""
    sq: list[str] = []
    en: list[str] = []

    if ctx.total == 0:
        return {
            "sq": ["Nuk ka të dhëna të mjaftueshme për përfundime në këtë periudhë."],
            "en": ["Not enough data for market insights in this period."],
        }

    rent_led = ctx.rent_pct >= 55
    if rent_led:
        sq.append(
            "Dominimi i qirasë do të thotë që qiramarrësit kanë më shumë zgjedhje dhe mundësi negociimi, "
            "ndërsa blerësit duhet të filtrojnë me kujdes listimet e shitjes që mbeten më të pakta. "
            "Kjo nuk tregon automatikisht një treg të ftohtë të shitjes; shpesh pasqyron se portalet "
            "përdoren më shumë për qira."
        )
        en.append(
            "Rent dominance means tenants have more choice and room to negotiate, "
            "while buyers should filter carefully through a thinner for-sale pool. "
            "This does not automatically signal a cold sale market; portals are often used more for rentals."
        )
    else:
        sq.append(
            "Shpërndarja më e balancuar midis qirasë dhe shitjes i jep blerësve dhe qiramarrësve "
            "bazë më të mirë krahasimi brenda të njëjtave lagje."
        )
        en.append(
            "A more balanced rent/sale mix gives both buyers and renters a stronger "
            "comparison base within the same neighborhoods."
        )

    nh_share = _top_neighborhood_share(ctx)
    if ctx.top_neighborhood and nh_share >= NH_CONCENTRATION_THRESHOLD_PCT:
        sq.append(
            f"Inventari është i përqendruar te '{ctx.top_neighborhood}', rreth {nh_share:.0f}% e "
            "listimeve të raportuara. Kjo mund të pasqyrojë si aktivitetin real të tregut, "
            "ashtu edhe mënyrën se si agjencitë dhe portalet etiketojnë lagjet periferike ose "
            "zonat e paqarta gjeografikisht. Për blerës dhe qiramarrës, krahasimet brenda lagjes "
            "janë më të vlefshme se mesatarja e qytetit."
        )
        en.append(
            f"Inventory is concentrated in '{ctx.top_neighborhood}', about {nh_share:.0f}% of "
            "reported listings. That may reflect real market activity, but also how agencies and "
            "portals label peripheral or loosely geocoded areas. "
            "Neighborhood-level comparisons matter more than a citywide average."
        )

    spike_month = _volume_spike_month(ctx.volume_by_month)
    activity_trend = _three_month_activity_trend(ctx.volume_by_month)
    if spike_month or activity_trend == "up":
        sq.append(
            "Rritja e aktivitetit në muajt e fundit mund të pasqyrojë hyrje të reja të të dhënave "
            "(p.sh. arkiva të portalit), jo domosdoshmërisht një rritje sezonale. "
            + (
                f"Muaji {spike_month} duket veçanërisht i lartë krahasuar me mesataren; "
                "trajtoje si sinjal, jo si fakt ekonomik."
                if spike_month
                else "Krahaso trendin afatmesëm, jo një muaj të vetëm."
            )
        )
        en.append(
            "Higher activity in recent months may reflect new data ingestion "
            "(e.g. portal archives), not necessarily a seasonal boom. "
            + (
                f"Month {spike_month} looks unusually high versus the median; "
                "treat it as a signal, not an economic fact."
                if spike_month
                else "Focus on the medium-term trend, not a single month."
            )
        )
    elif activity_trend == "down":
        sq.append(
            "Aktiviteti i listimeve ka rënë pak në tremujorin e fundit. "
            "Kjo mund të tregojë pakësim oferte ose thjesht më pak publikime të reja në portale."
        )
        en.append(
            "Listing activity has eased slightly in the latest quarter. "
            "That may mean less supply, or simply fewer new portal postings."
        )

    peak_month, price_outlier = _price_spike_month(ctx.sale_psm_by_month)
    price_trend = _three_month_sale_price_trend(ctx.sale_psm_by_month)
    if peak_month and price_outlier:
        sq.append(
            f"Kulmi i medianës së shitjes në {peak_month} ka të ngjarë të jetë artefakt i mostrës "
            "(pak listime ose segment i pazakontë), jo një rritje reale e tregut. "
            "Për vendime, përdor medianën e lagjes dhe listimet e ngjashme, jo një pikë mujore."
        )
        en.append(
            f"The sale median peak in {peak_month} is likely a sample artifact "
            "(thin listings or an odd segment), not a true market step-change. "
            "For decisions, use neighborhood medians and comparables, not one monthly point."
        )
    elif price_trend == "up":
        sq.append(
            "Mediana e çmimeve të kërkuara të shitjes po ngrihet pak në tremujorin e fundit. "
            "Meqenëse nuk kemi transaksione, mbaje si sinjal të ofertës, jo si konfirmim vlere."
        )
        en.append(
            "Median asking sale prices have edged up in the latest quarter. "
            "Without closed sales, treat this as an asking-price signal, not a value confirmation."
        )
    elif price_trend == "down":
        sq.append(
            "Mediana e çmimeve të kërkuara të shitjes po zbehet pak në tremujorin e fundit. "
            "Shitësit mund të jenë më të gatshëm të negociojnë, por mostra ndryshon sipas lagjes."
        )
        en.append(
            "Median asking sale prices have softened slightly in the latest quarter. "
            "Sellers may be more negotiable, but samples differ widely by neighborhood."
        )

    nh_sale = _nh_sale_medians(ctx.work)
    if not nh_sale.empty and len(sq) < 4:
        priciest = nh_sale.loc[nh_sale["median_psm"].idxmax()]
        cheapest = nh_sale.loc[nh_sale["median_psm"].idxmin()]
        if priciest["neighborhood"] != cheapest["neighborhood"]:
            sq.append(
                f"Hendeku i çmimeve midis lagjeve me mjaftueshëm të dhëna mbetet i madh: "
                f"{priciest['neighborhood']} kërkon nivel premium ndaj {cheapest['neighborhood']}. "
                "Blerësit që kërkojnë vlerë duhet të shohin periferinë; ata që kërkojnë likuiditet "
                "duhet të pranojnë premium në lagjet e dokumentuara mirë."
            )
            en.append(
                f"The price gap across well-covered neighborhoods remains wide: "
                f"{priciest['neighborhood']} asks at a premium versus {cheapest['neighborhood']}. "
                "Value seekers should look outward; liquidity seekers should expect a premium in well-documented areas."
            )

    if ctx.coverage.get("neighborhood_pct", 100) < 80 and len(sq) < 4:
        sq.append(
            "Jo çdo listim ka lagje të verifikuar; krahasimet midis zonave me pak të dhëna "
            "janë më të dobëta. Prefero profilet e lagjeve me inventar të dendur."
        )
        en.append(
            "Not every listing has a verified neighborhood; cross-area comparisons are weaker "
            "where data is thin. Prefer neighborhood profiles with dense inventory."
        )

    return {"sq": sq[:4], "en": en[:4]}


def build_coverage_narrative(ctx: AnnualConclusionContext) -> dict[str, Any]:
    """Plain-language data quality copy for the dashboard."""
    cov = ctx.coverage
    score = cov.get("neighborhood_pct", 0)
    if score >= 90:
        label_sq, label_en = "E lartë", "High"
    elif score >= 75:
        label_sq, label_en = "E mirë", "Good"
    else:
        label_sq, label_en = "E moderuar", "Moderate"

    return {
        "label": {"sq": label_sq, "en": label_en},
        "summary": {
            "sq": (
                "Vlerësimi i besueshmërisë bazohet në sa shpesh kemi çmim, sipërfaqe, lagje dhe "
                "dhoma të plotësuara në listimet aktive."
            ),
            "en": (
                "Reliability reflects how often active listings include price, area, neighborhood, "
                "and bedroom information."
            ),
        },
        "items": {
            "sq": [
                f"Çmimi raportohet në {cov.get('price_pct', 0):.0f}% të listimeve.",
                f"Sipërfaqja në {cov.get('area_pct', 0):.0f}% të listimeve.",
                f"Lagja e identifikuar në {cov.get('neighborhood_pct', 0):.0f}% të listimeve.",
                f"Numri i dhomave në {cov.get('bedrooms_pct', 0):.0f}% të listimeve.",
            ],
            "en": [
                f"Price is reported on {cov.get('price_pct', 0):.0f}% of listings.",
                f"Floor area on {cov.get('area_pct', 0):.0f}% of listings.",
                f"Neighborhood identified on {cov.get('neighborhood_pct', 0):.0f}% of listings.",
                f"Bedroom count on {cov.get('bedrooms_pct', 0):.0f}% of listings.",
            ],
        },
    }


def build_methodology_plain(
    *,
    window_months: int,
    cutoff_date: str,
    sources: list[dict[str, Any]],
    parser_versions: list[str] | None = None,
    gazetteer_version: str | None = None,
    generated_date: str | None = None,
) -> dict[str, Any]:
    """User-facing methodology — technical ids in a separate block."""
    total_listings = sum(int(row.get("listings", 0) or 0) for row in sources)
    n_sources = len(
        {
            str(row.get("source_website", "")).strip()
            for row in sources
            if str(row.get("source_website", "")).strip()
        }
    )
    if n_sources <= 0:
        sources_line_sq = "portale publike të listimeve"
        sources_line_en = "public listing portals"
    elif n_sources == 1:
        sources_line_sq = f"1 portal publik listimesh ({total_listings:,} listime)"
        sources_line_en = f"1 public listing portal ({total_listings:,} listings)"
    else:
        sources_line_sq = f"{n_sources} portale publike listimesh ({total_listings:,} listime)"
        sources_line_en = f"{n_sources} public listing portals ({total_listings:,} listings)"

    plain_sq = (
        f"Ky raport përmbledh listime aktive të banimit në Prishtinë nga {sources_line_sq}, "
        f"publikuar brenda {window_months} muajve të fundit (nga {cutoff_date}). "
        "Çdo listim numërohet një herë; çmimet janë medianë të çmimeve të kërkuara, jo transaksione. "
        "Përditësohet pas çdo cikli të përpunimit të të dhënave."
    )
    plain_en = (
        f"This report summarizes active residential listings in Prishtina from {sources_line_en}, "
        f"published within the last {window_months} months (from {cutoff_date}). "
        "Each listing is counted once; prices are medians of asking prices, not transactions. "
        "Updated after each data processing cycle."
    )

    technical: dict[str, str] = {}
    # Do not expose parser version strings that embed portal brand tokens.
    if parser_versions:
        technical["parsers"] = f"{len(parser_versions)} active parser version(s)"
    if gazetteer_version:
        technical["gazetteer"] = gazetteer_version
    if generated_date:
        technical["generated"] = generated_date

    return {
        "plain": {"sq": plain_sq, "en": plain_en},
        "technical": technical,
    }


def build_chart_narratives(
    ctx: AnnualConclusionContext,
    *,
    peak_price_month: str | None,
) -> dict[str, dict[str, str]]:
    """One-sentence takeaway under each chart."""
    spike_month = _volume_spike_month(ctx.volume_by_month)
    _, price_outlier = _price_spike_month(ctx.sale_psm_by_month)
    trough_month, trough_outlier, trough_val = _price_trough_month(ctx.sale_psm_by_month)

    sq_volume = (
        "Qiratë dominojnë volumin e listimeve; rritjet e mëdha mujore shpesh pasqyrojnë hyrje të dhënash, jo sezonalitet."
        if spike_month
        else "Qiratë përbëjnë pjesën më të madhe të ofertës së re çdo muaj: treg i orientuar nga qiramarrësit."
    )
    en_volume = (
        "Rent dominates listing volume; large monthly jumps often reflect data ingestion, not seasonality."
        if spike_month
        else "Rent makes up most new supply each month: a tenant-oriented market."
    )

    sq_price_parts: list[str] = []
    en_price_parts: list[str] = []
    peak_ref = peak_price_month if peak_price_month and price_outlier else None
    if peak_ref:
        sq_price_parts.append(
            f"Kulmi në {peak_ref} duket i tepruar nga mostra e hollë; "
            "shiko trendin afatmesëm, jo një muaj të vetëm."
        )
        en_price_parts.append(
            f"The peak in {peak_ref} looks exaggerated by a thin sample; "
            "watch the medium-term trend, not one month alone."
        )
    if trough_month and trough_outlier and trough_val is not None:
        sq_price_parts.append(
            f"Rënia në {trough_month} (rreth €{int(round(trough_val))}/m²) është shumë e mundshme "
            "artefakt i cilësisë së të dhënave nga mostra e vogël mujore, jo një rrëzim real i tregut."
        )
        en_price_parts.append(
            f"The dip in {trough_month} (around €{int(round(trough_val))}/m²) is very likely a "
            "thin-sample data-quality artifact, not a real market crash."
        )
    if not sq_price_parts:
        sq_price_parts.append(
            "Mediana mujore e €/m² tregon drejtimin e ofertës së shitjes, me luhatje normale muaj pas muaji."
        )
        en_price_parts.append(
            "The monthly €/m² median shows the direction of asking sale prices, "
            "with normal month-to-month noise."
        )
    sq_price = " ".join(sq_price_parts)
    en_price = " ".join(en_price_parts)

    sq_rent = (
        "Qiratë e kërkuara kanë qenë relativisht të qëndrueshme në nivel qyteti; "
        "ndryshimet reale ndodhin më shumë sipas lagjes dhe madhësisë."
        if ctx.median_rent
        else "Qiratë ndryshojnë më shumë sipas lagjes sesa në nivel qyteti."
    )
    en_rent = (
        "Asking rents have been relatively stable citywide; "
        "real differences show up more by neighborhood and size."
        if ctx.median_rent
        else "Rents vary more by neighborhood than at city level."
    )

    nh_share = _top_neighborhood_share(ctx)
    sq_nh = (
        f"Inventari grumbullohet te disa lagje (veçanërisht {ctx.top_neighborhood}); "
        "kjo pasqyron si tregun, ashtu edhe mënyrën e etiketimit të vendndodhjes."
        if ctx.top_neighborhood and nh_share >= NH_CONCENTRATION_THRESHOLD_PCT
        else "Lagjet me më shumë listime ofrojnë krahasime më të besueshme për çmime dhe segmente."
    )
    en_nh = (
        f"Inventory clusters in a few areas (especially {ctx.top_neighborhood}), "
        "reflecting both the market and how locations are labeled."
        if ctx.top_neighborhood and nh_share >= NH_CONCENTRATION_THRESHOLD_PCT
        else "Neighborhoods with more listings offer more reliable price comparisons."
    )

    return {
        "sq": {
            "volume_insight": sq_volume,
            "price_insight": sq_price,
            "rent_insight": sq_rent,
            "nh_insight": sq_nh,
        },
        "en": {
            "volume_insight": en_volume,
            "price_insight": en_price,
            "rent_insight": en_rent,
            "nh_insight": en_nh,
        },
    }


def build_rankings_commentary(rankings: dict[str, Any]) -> dict[str, str]:
    """Context for the sale price spread across neighborhoods."""
    expensive = rankings.get("expensive") or []
    affordable = rankings.get("affordable") or []
    if not expensive or not affordable:
        return {"sq": "", "en": ""}

    priciest = expensive[0]
    cheapest = affordable[0]
    top_name = str(priciest.get("neighborhood", ""))
    bottom_name = str(cheapest.get("neighborhood", ""))
    top_psm = float(priciest.get("median_price_per_sqm") or 0)
    bottom_psm = float(cheapest.get("median_price_per_sqm") or 0)
    if top_psm <= 0 or bottom_psm <= 0:
        return {"sq": "", "en": ""}

    ratio = top_psm / bottom_psm
    top_e = int(round(top_psm))
    bottom_e = int(round(bottom_psm))

    return {
        "sq": (
            f"Hendeku midis {top_name} (€{top_e}/m²) dhe {bottom_name} (€{bottom_e}/m²), "
            f"rreth {ratio:.1f}×, pasqyron ndarjen klasike të qytetit: zona qendrore dhe "
            "të dokumentuara mirë kërkojnë premium, ndërsa periferitë ofrojnë çmime më të ulëta "
            "të kërkuara. Blerësit që kërkojnë vlerë duhet të krahasojnë lagjet periferike; "
            "ata që kërkojnë likuiditet dhe afërsi me qendrën duhet të presin premium."
        ),
        "en": (
            f"The gap between {top_name} (€{top_e}/m²) and {bottom_name} (€{bottom_e}/m²), "
            f"about {ratio:.1f}×, reflects a classic city split: central, well-documented areas "
            "command a premium, while outer neighborhoods show lower asking prices. "
            "Value seekers should compare peripheral areas; buyers prioritizing centrality "
            "and liquidity should expect to pay more."
        ),
    }


def build_limitations_callout(coverage: dict[str, float]) -> dict[str, list[str]]:
    """Transparency bullets for methodology / PDF callout box."""
    price_pct = int(round(coverage.get("price_pct", 0)))
    nh_pct = int(round(coverage.get("neighborhood_pct", 0)))
    return {
        "sq": [
            "Çmimet janë çmime kërkuese nga listime aktive në portale, jo çmime transaksionesh të mbyllura.",
            "Çdo listim numërohet një herë pas deduplikimit; oferta aktive nuk pasqyron volumin e shitjeve të realizuara.",
            f"Fushat kryesore nuk janë 100% të plota: çmimi në {price_pct}% të listimeve, lagja në {nh_pct}%.",
            "Medianat mujore mund të luhaten kur mostra mujore është e vogël; shiko trendin afatmesëm dhe profilin e lagjes.",
        ],
        "en": [
            "All prices are asking prices from active portal listings, not closed transaction prices.",
            "Each listing is counted once after deduplication; active supply does not equal completed sales volume.",
            f"Key fields are not 100% complete: price on {price_pct}% of listings, neighborhood on {nh_pct}%.",
            "Monthly medians can swing when the monthly sample is thin; rely on medium-term trends and neighborhood profiles.",
        ],
    }


def build_conclusions(ctx: AnnualConclusionContext) -> dict[str, list[str]]:
    """Backward-compatible alias — insights only (no corpus-debug bullets)."""
    return build_insights(ctx)


def build_dashboard_copy(
    ctx: AnnualConclusionContext,
    *,
    peak_price_month: str | None,
    methodology_meta: dict[str, Any],
) -> dict[str, Any]:
    """Full narrative payload for the statistics page."""
    chart = build_chart_narratives(ctx, peak_price_month=peak_price_month)
    generated = methodology_meta.get("generated_at", "")[:10] or None
    methodology = build_methodology_plain(
        window_months=int(methodology_meta.get("window_months", 12)),
        cutoff_date=str(methodology_meta.get("cutoff_date", "")),
        sources=ctx.sources,
        parser_versions=methodology_meta.get("parser_versions"),
        gazetteer_version=methodology_meta.get("gazetteer_version"),
        generated_date=generated,
    )
    return {
        "executive_summary": build_executive_summary(ctx),
        "insights": build_insights(ctx),
        "coverage_narrative": build_coverage_narrative(ctx),
        "chart_takeaways": chart,
        "methodology_plain": methodology,
        "limitations": build_limitations_callout(ctx.coverage),
        "conclusions": build_insights(ctx),
        "narratives": chart["sq"],
        "narratives_i18n": chart,
    }


def build_rankings_commentary_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    return build_rankings_commentary(payload.get("neighborhood_rankings") or {})
