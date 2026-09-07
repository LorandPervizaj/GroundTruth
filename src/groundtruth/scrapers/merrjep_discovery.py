"""MerrJep index traversal helpers — Phase 1 discovery (URLs only)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

_LISTING_HREF_RE = re.compile(r'href="(/shpallja/[^"]+/\d+)"', re.IGNORECASE)
_LISTING_ID_RE = re.compile(r"/(\d+)/?$")
_PAGE_LINK_RE = re.compile(r"[?&]Page=(\d+)", re.IGNORECASE)
_SLUG_RE = re.compile(r"/shpallja/([^/]+)/\d+", re.IGNORECASE)

_RENT_MARKERS = (
    "me-qera",
    "me-qira",
    "per-qira",
    "per-qera",
    "-qira",
    "-qera",
    "qira-ne",
    "qera-ne",
)
_SALE_MARKERS = ("ne-shitje", "per-shitje", "-shitje", "shitje-ne", "per-shitje")
_COMMERCIAL_MARKERS = ("lokal", "zyre", "dyqan", "komerc", "magazin", "garazh", "hapir")
_HOUSE_MARKERS = ("shtepi", "shtepia", "shpi", "shpia", "villa", "vila", "shtëpi", "kopesht")
_LAND_MARKERS = ("truall", "toke", "parcel", "tokë")
_APT_MARKERS = ("banes", "banese", "banesa", "apartament", "garsonier", "penthouse", "studio")

# Phase 1 success gates — calibrated from 50-page discovery (2026-06-10).
# ~50 new ids/page, ~9% href duplication from pagination overlap.
DEFAULT_INDEX_PAGES_TARGET = 50
EXPECTED_NEW_IDS_PER_PAGE = 48
DEFAULT_LISTING_URLS_TARGET = DEFAULT_INDEX_PAGES_TARGET * EXPECTED_NEW_IDS_PER_PAGE  # 2400
DEFAULT_MAX_DUPLICATE_RATE_PCT = 12.0
MIN_UNIQUE_ID_RATIO = 0.9  # pass if unique >= 90% of expected floor

# MerrJep index filters — use site-side filters to avoid mixed rent/sale crawl noise.
MERRJEP_INDEX_URLS: dict[str, str] = {
    # Patundshmëri me qera, Prishtinë (all property types, rent only).
    "rent": "https://www.merrjep.com/shpallje/patundshmeri/me-qera/prishtine",
    # Patundshmëri në shitje, Prishtinë (sale only — DM-003 target).
    "sale": "https://www.merrjep.com/shpallje/patundshmeri/ne-shitje/prishtine",
    # Banesa Prishtinë (mixed rent + sale — legacy discovery URL).
    "apartments": "https://www.merrjep.com/shpallje/patundshmeri/banesa/prishtine",
    # Banesa me qera, Prishtinë (apartments for rent only).
    "apartments_rent": "https://www.merrjep.com/shpallje/patundshmeri/banesa/me-qera/prishtine",
    # Banesa në shitje, Prishtinë (apartments for sale only).
    "apartments_sale": "https://www.merrjep.com/shpallje/patundshmeri/banesa/ne-shitje/prishtine",
    # Shtëpi me qera / në shitje, Prishtinë.
    "houses_rent": "https://www.merrjep.com/shpallje/patundshmeri/shtepi/me-qera/prishtine",
    "houses_sale": "https://www.merrjep.com/shpallje/patundshmeri/shtepi/ne-shitje/prishtine",
}

DEFAULT_INDEX_KEY = "apartments_rent"
DEFAULT_START_URLS = (MERRJEP_INDEX_URLS[DEFAULT_INDEX_KEY],)


def resolve_start_urls(index: str = DEFAULT_INDEX_KEY) -> list[str]:
    """Resolve MerrJep index filter key(s) to start URL(s).

    ``index`` may be a single key or a comma-separated list
    (e.g. ``apartments_rent,houses_rent``).
    """
    keys = [part.strip().lower() for part in index.split(",") if part.strip()]
    if not keys:
        keys = [DEFAULT_INDEX_KEY]
    urls: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in MERRJEP_INDEX_URLS:
            allowed = ", ".join(sorted(MERRJEP_INDEX_URLS))
            raise ValueError(f"Unknown MerrJep index '{key}'. Choose one of: {allowed}")
        url = MERRJEP_INDEX_URLS[key]
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


@dataclass
class DiscoveryStats:
    """Aggregated discovery crawl metrics."""

    mode: str = "discovery"
    spider: str = "merrjep"
    completed_at: str = ""
    start_urls: list[str] = field(default_factory=list)
    index_pages_crawled: int = 0
    listing_urls_seen: int = 0
    listing_ids_unique: int = 0
    duplicate_url_hits: int = 0
    duplicate_rate_pct: float = 0.0
    last_page_number: int = 0
    max_page_link_seen: int | None = None
    sample_urls: list[str] = field(default_factory=list)
    category_coverage: dict[str, int] = field(default_factory=dict)
    marginal_yield: list[dict[str, int | str]] = field(default_factory=list)
    per_page_new_ids: list[dict[str, int]] = field(default_factory=list)
    id_stability: dict[str, object] = field(default_factory=dict)
    targets: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def category_base_url(url: str) -> str:
    """Strip pagination query params, keeping the category path."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key in list(query):
        if key.lower() == "page":
            del query[key]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def build_page_url(category_url: str, page: int) -> str:
    """Build MerrJep index URL with ``Page`` query parameter."""
    base = category_base_url(category_url)
    parsed = urlparse(base)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["Page"] = [str(page)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def listing_id_from_url(url: str) -> str | None:
    """Extract numeric listing id from a MerrJep detail URL."""
    path = urlparse(url).path
    match = _LISTING_ID_RE.search(path)
    return match.group(1) if match else None


def listing_slug_from_url(url: str) -> str:
    """Extract the slug segment from a MerrJep detail URL."""
    match = _SLUG_RE.search(urlparse(url).path)
    return match.group(1).lower() if match else ""


def classify_listing_category(url: str) -> str:
    """
    Infer listing category from URL slug heuristics.

    Returns keys like ``apartment_rent``, ``apartment_sale``, ``house_rent``,
    ``commercial_sale``, ``land_sale``, ``other``.
    """
    slug = listing_slug_from_url(url)
    if not slug:
        return "other"

    is_rent = any(marker in slug for marker in _RENT_MARKERS)
    is_sale = any(marker in slug for marker in _SALE_MARKERS)
    if is_rent and not is_sale:
        tx = "rent"
    elif is_sale and not is_rent:
        tx = "sale"
    else:
        tx = "unknown"

    if any(marker in slug for marker in _LAND_MARKERS):
        prop = "land"
    elif any(marker in slug for marker in _COMMERCIAL_MARKERS):
        prop = "commercial"
    elif any(marker in slug for marker in _HOUSE_MARKERS):
        prop = "house"
    elif any(marker in slug for marker in _APT_MARKERS):
        prop = "apartment"
    else:
        prop = "other"

    if tx == "unknown":
        return f"{prop}_unknown"
    return f"{prop}_{tx}"


def extract_listing_urls(html: str, base_url: str) -> list[str]:
    """Return absolute detail URLs found on an index page."""
    paths = _LISTING_HREF_RE.findall(html)
    return [urljoin(base_url, path) for path in sorted(set(paths))]


def extract_max_page_number(html: str) -> int | None:
    """Largest ``Page=N`` link on an index page (site-reported depth hint)."""
    pages = [int(m) for m in _PAGE_LINK_RE.findall(html)]
    return max(pages) if pages else None


def register_listing_urls(
    urls: Iterable[str],
    *,
    seen_ids: set[str],
    duplicate_hits: int,
    id_to_url: dict[str, str] | None = None,
    category_counts: dict[str, int] | None = None,
) -> tuple[int, int, list[str]]:
    """
    Track listing ids across pages.

    Returns (new_ids_added, updated_duplicate_hits, new_id_list).
    """
    added = 0
    new_ids: list[str] = []
    for url in urls:
        listing_id = listing_id_from_url(url)
        if not listing_id:
            continue
        if listing_id in seen_ids:
            duplicate_hits += 1
        else:
            seen_ids.add(listing_id)
            new_ids.append(listing_id)
            if id_to_url is not None:
                id_to_url[listing_id] = url
            if category_counts is not None:
                category = classify_listing_category(url)
                category_counts[category] = category_counts.get(category, 0) + 1
            added += 1
    return added, duplicate_hits, new_ids


def marginal_yield_buckets(
    page_yields: list[tuple[int, int]],
    *,
    bucket_size: int = 10,
) -> list[dict[str, int | str]]:
    """Sum new unique ids per page-range bucket (e.g. pages 1–10, 11–20)."""
    totals: dict[str, int] = {}
    for page_num, new_count in page_yields:
        start = ((page_num - 1) // bucket_size) * bucket_size + 1
        end = start + bucket_size - 1
        label = f"{start}-{end}"
        totals[label] = totals.get(label, 0) + new_count
    return [
        {"pages": label, "new_ids": totals[label]}
        for label in sorted(totals, key=lambda s: int(s.split("-")[0]))
    ]


def analyze_id_stability(
    seen_ids: set[str],
    id_to_url: dict[str, str],
    page_yields: list[tuple[int, int]],
    *,
    page_id_samples: list[tuple[int, list[str]]] | None = None,
) -> dict[str, object]:
    """Assess whether MerrJep numeric ids are suitable as primary keys."""
    ids = sorted(seen_ids, key=lambda x: int(x) if x.isdigit() else 0)
    numeric_ids = [i for i in ids if i.isdigit()]
    int_ids = [int(i) for i in numeric_ids]

    id_in_url = all(url.rstrip("/").endswith(f"/{lid}") for lid, url in id_to_url.items())
    one_url_per_id = len(id_to_url) == len(seen_ids)

    mean_id_by_bucket: dict[str, float] = {}
    if page_id_samples:
        bucket_size = 10
        bucket_sums: dict[str, list[int]] = {}
        for page_num, page_ids in page_id_samples:
            numeric_page = [int(i) for i in page_ids if i.isdigit()]
            if not numeric_page:
                continue
            start = ((page_num - 1) // bucket_size) * bucket_size + 1
            end = start + bucket_size - 1
            label = f"{start}-{end}"
            bucket_sums.setdefault(label, []).extend(numeric_page)
        mean_id_by_bucket = {
            label: round(sum(vals) / len(vals), 1)
            for label, vals in sorted(bucket_sums.items(), key=lambda x: int(x[0].split("-")[0]))
        }

    monotonic_trend = "flat"
    if len(int_ids) >= 2:
        spread = int_ids[-1] - int_ids[0]
        if spread > 0 and mean_id_by_bucket:
            first_bucket = next(iter(mean_id_by_bucket.values()))
            last_bucket = list(mean_id_by_bucket.values())[-1]
            if last_bucket > first_bucket * 1.05:
                monotonic_trend = "increasing_by_page_bucket"
            elif last_bucket < first_bucket * 0.95:
                monotonic_trend = "decreasing_by_page_bucket"

    return {
        "all_numeric": len(numeric_ids) == len(ids),
        "id_embedded_in_url": id_in_url,
        "one_url_per_id": one_url_per_id,
        "id_count": len(ids),
        "id_min": min(int_ids) if int_ids else None,
        "id_max": max(int_ids) if int_ids else None,
        "id_digit_lengths": sorted({len(i) for i in numeric_ids}),
        "suitable_as_primary_key": bool(
            ids and len(numeric_ids) == len(ids) and id_in_url and one_url_per_id
        ),
        "monotonic_trend_by_page_bucket": monotonic_trend,
        "mean_id_by_page_bucket": mean_id_by_bucket,
        "sample_ids_oldest": numeric_ids[:5],
        "sample_ids_newest": numeric_ids[-5:],
    }


def build_discovery_stats(
    *,
    start_urls: list[str],
    index_pages_crawled: int,
    seen_ids: set[str],
    duplicate_hits: int,
    urls_seen: int,
    last_page_number: int,
    max_page_link_seen: int | None,
    index_pages_target: int = DEFAULT_INDEX_PAGES_TARGET,
    listing_urls_target: int = DEFAULT_LISTING_URLS_TARGET,
    max_duplicate_rate_pct: float = DEFAULT_MAX_DUPLICATE_RATE_PCT,
    sample_size: int = 20,
    all_urls: list[str] | None = None,
    id_to_url: dict[str, str] | None = None,
    category_counts: dict[str, int] | None = None,
    page_yields: list[tuple[int, int]] | None = None,
    page_id_samples: list[tuple[int, list[str]]] | None = None,
) -> DiscoveryStats:
    """Compute Phase 1 pass/fail against discovery gates."""
    unique = len(seen_ids)
    dup_rate = 100.0 * duplicate_hits / urls_seen if urls_seen else 0.0

    min_unique = int(listing_urls_target * MIN_UNIQUE_ID_RATIO)
    passed = (
        index_pages_crawled >= index_pages_target
        and unique >= min_unique
        and dup_rate <= max_duplicate_rate_pct
    )

    notes: list[str] = []
    if index_pages_crawled < index_pages_target:
        notes.append(f"Index pages {index_pages_crawled} < target {index_pages_target}.")
    if unique < min_unique:
        notes.append(
            f"Unique listing ids {unique} < floor {min_unique} "
            f"(90% of {listing_urls_target} expected at ~{EXPECTED_NEW_IDS_PER_PAGE}/page)."
        )
    if dup_rate > max_duplicate_rate_pct:
        notes.append(f"Duplicate rate {dup_rate:.2f}% >= max {max_duplicate_rate_pct}%.")
        if index_pages_crawled > 1:
            notes.append(
                "MerrJep index pages overlap a few listings between pages (~6–9% href "
                "duplication is normal). Dedup is by numeric listing id."
            )
    if index_pages_crawled > 0:
        avg_new_per_page = unique / index_pages_crawled
        projected = avg_new_per_page * index_pages_target
        if projected < listing_urls_target:
            notes.append(
                f"At ~{avg_new_per_page:.0f} unique ids/page, {index_pages_target} pages "
                f"≈ {projected:.0f} unique (target {listing_urls_target}). "
                "Raise max_pages or add category start URLs."
            )
    if max_page_link_seen and index_pages_crawled < max_page_link_seen:
        notes.append(
            f"Site reports up to page {max_page_link_seen}; crawled {index_pages_crawled}."
        )

    sample = sorted(all_urls or [])[:sample_size]
    yields = page_yields or []
    marginal = marginal_yield_buckets(yields)
    id_stability = analyze_id_stability(
        seen_ids,
        id_to_url or {},
        yields,
        page_id_samples=page_id_samples,
    )
    per_page = [{"page": p, "new_ids": n} for p, n in yields]

    if marginal and len(marginal) >= 2:
        last_bucket = marginal[-1]["new_ids"]
        prev_bucket = marginal[-2]["new_ids"]
        if (
            isinstance(last_bucket, int)
            and isinstance(prev_bucket, int)
            and prev_bucket > 0
            and last_bucket < prev_bucket * 0.5
        ):
            notes.append(
                f"Marginal yield dropped in {marginal[-1]['pages']}: "
                f"{last_bucket} new ids vs {prev_bucket} in prior bucket — "
                "consider early-stop pagination."
            )

    category_sorted = dict(
        sorted((category_counts or {}).items(), key=lambda kv: kv[1], reverse=True)
    )
    apt_sale = category_sorted.get("apartment_sale", 0)
    if apt_sale > 0:
        notes.append(
            f"Apartment sale slugs: {apt_sale} unique ids "
            f"({100.0 * apt_sale / unique:.1f}% of discovery sample)."
        )

    return DiscoveryStats(
        completed_at=datetime.now(UTC).isoformat(),
        start_urls=start_urls,
        index_pages_crawled=index_pages_crawled,
        listing_urls_seen=urls_seen,
        listing_ids_unique=unique,
        duplicate_url_hits=duplicate_hits,
        duplicate_rate_pct=round(dup_rate, 3),
        last_page_number=last_page_number,
        max_page_link_seen=max_page_link_seen,
        sample_urls=sample,
        category_coverage=category_sorted,
        marginal_yield=marginal,
        per_page_new_ids=per_page,
        id_stability=id_stability,
        targets={
            "index_pages": index_pages_target,
            "listing_urls_unique_floor": min_unique,
            "listing_urls_unique_expected": listing_urls_target,
            "expected_new_ids_per_page": EXPECTED_NEW_IDS_PER_PAGE,
            "max_duplicate_rate_pct": max_duplicate_rate_pct,
        },
        passed=passed,
        notes=notes,
    )


def write_discovery_report(stats: DiscoveryStats, output_dir: Path) -> Path:
    """Write JSON discovery report; return path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"merrjep_discovery_{stamp}.json"
    path.write_text(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
