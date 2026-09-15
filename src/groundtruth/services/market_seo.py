"""Server-side SEO metadata for market profile pages."""

from __future__ import annotations

import html
import json
import re

from sqlalchemy.orm import Session

from groundtruth.config import PROJECT_ROOT, get_settings
from groundtruth.services.lookup_cache import (
    cache_is_loaded,
    get_cached_lookup,
    resolve_market_lookup,
)

WEB_DIR = PROJECT_ROOT / "web"
_MARKET_HTML = WEB_DIR / "market.html"


def _entity_label(entity_type: str) -> str:
    return {
        "neighborhood": "neighborhood",
        "district": "district",
        "street": "street",
        "complex": "complex",
    }.get(entity_type, "market")


def _build_meta(
    entity_type: str,
    slug: str,
    session: Session | None,
) -> dict[str, str]:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    canonical = f"{base}/market/{entity_type}/{slug}"

    lookup = get_cached_lookup(entity_type, slug) if cache_is_loaded() else None
    if lookup is None and session is not None:
        resolved = resolve_market_lookup(session, entity_type, slug)
        lookup = resolved

    if lookup is None:
        display = slug.replace("-", " ").title()
        title = f"{display} — Metrik"
        description = (
            f"Market profile for {display} in Prishtina: rent, sale, inventory, "
            "and evidence-backed statistics."
        )
        return {
            "title": title,
            "description": description,
            "og_title": title,
            "og_description": description,
            "canonical": canonical,
            "json_ld": "",
        }

    display = lookup.display_name
    pulse = lookup.pulse
    label = _entity_label(entity_type)
    rent_psm = pulse.average_rent_psm_eur
    sale_psm = pulse.average_sale_psm_eur
    inventory = pulse.active_listings

    stats_parts: list[str] = []
    if rent_psm is not None:
        stats_parts.append(f"median rent €{rent_psm:.0f}/m²")
    if sale_psm is not None:
        stats_parts.append(f"median sale €{sale_psm:.0f}/m²")
    if inventory:
        stats_parts.append(f"{inventory} active listings")

    stats_text = ", ".join(stats_parts) if stats_parts else "rent and sale market data"
    title = f"{display}, Prishtina — Metrik"
    description = (
        f"{display} {label} market profile: {stats_text}. "
        "Evidence-backed inventory, confidence, and recent listings."
    )

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": display,
        "description": description,
        "url": canonical,
        "address": {
            "@type": "PostalAddress",
            "addressLocality": lookup.city or "Prishtina",
            "addressCountry": "XK",
        },
    }

    return {
        "title": title,
        "description": description,
        "og_title": title,
        "og_description": description,
        "canonical": canonical,
        "json_ld": json.dumps(json_ld, ensure_ascii=False),
    }


def render_market_html(entity_type: str, slug: str, session: Session | None) -> str:
    """Inject per-entity meta tags into the market page shell."""
    meta = _build_meta(entity_type, slug, session)
    template = _MARKET_HTML.read_text(encoding="utf-8")
    base = get_settings().public_base_url.rstrip("/")

    esc = html.escape
    replacements = {
        r"<title>[^<]*</title>": f"<title>{esc(meta['title'])}</title>",
        r'<meta name="description" content="[^"]*" />': (
            f'<meta name="description" content="{esc(meta["description"])}" />'
        ),
        r'<meta property="og:title" content="[^"]*" />': (
            f'<meta property="og:title" content="{esc(meta["og_title"])}" />'
        ),
        r'<meta property="og:description" content="[^"]*" />': (
            f'<meta property="og:description" content="{esc(meta["og_description"])}" />'
        ),
        r'<meta property="og:image" content="[^"]*" />': (
            f'<meta property="og:image" content="{esc(base)}/favicon.svg" />'
        ),
    }
    html_out = template
    for pattern, replacement in replacements.items():
        html_out = re.sub(pattern, replacement, html_out, count=1)

    if 'rel="canonical"' not in html_out:
        html_out = html_out.replace(
            '<meta property="og:type"',
            f'<link rel="canonical" href="{esc(meta["canonical"])}" />\n'
            f'  <meta name="twitter:card" content="summary" />\n'
            f'  <meta name="twitter:title" content="{esc(meta["og_title"])}" />\n'
            f'  <meta name="twitter:description" content="{esc(meta["og_description"])}" />\n'
            '  <meta property="og:type"',
        )

    if meta["json_ld"] and 'id="market-jsonld"' not in html_out:
        script = (
            f'  <script type="application/ld+json" id="market-jsonld">{meta["json_ld"]}</script>\n'
        )
        html_out = html_out.replace("</head>", f"{script}</head>")

    from groundtruth.services.web_shell import (
        inject_sanitize_script,
        inject_site_footer,
        inject_static_asset_hashes,
    )

    html_out = inject_static_asset_hashes(html_out)
    html_out = inject_sanitize_script(html_out)
    return inject_site_footer(html_out)


def market_sitemap_urls() -> list[str]:
    """Return /market/{type}/{slug} paths for sitemap generation."""
    from groundtruth.config import get_settings

    gaz_dir = get_settings().gazetteer_dir
    paths: list[str] = []
    for entity_type, filename in (
        ("neighborhood", "neighborhoods.json"),
        ("district", "districts.json"),
        ("street", "streets.json"),
        ("complex", "complexes.json"),
    ):
        data_path = gaz_dir / filename
        if not data_path.is_file():
            continue
        entries = json.loads(data_path.read_text(encoding="utf-8"))
        for entry in entries:
            slug = entry.get("slug") or entry.get("name", "").lower().replace(" ", "-")
            if slug:
                paths.append(f"/market/{entity_type}/{slug}")
    return sorted(paths)
