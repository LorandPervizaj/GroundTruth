"""HTML shell / static page routes for Metrik."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from groundtruth.api.deps import EntityType
from groundtruth.config import PROJECT_ROOT, get_settings
from groundtruth.services.web_shell import (
    inject_accessibility_shell,
    inject_canonical_url,
    inject_sanitize_script,
    inject_site_footer,
    inject_static_asset_hashes,
)

router = APIRouter(tags=["pages"])

WEB_DIR = PROJECT_ROOT / "web"
_STATIC_PAGE_PATHS = {
    "index.html": "/",
    "valuate.html": "/valuate",
    "find.html": "/find",
    "statistics.html": "/statistics",
    "compare.html": "/compare",
    "rent-yield.html": "/rent-yield",
    "contact.html": "/contact",
    "about.html": "/about",
    "alerts.html": "/alerts",
    "methodology.html": "/methodology",
    "privacy.html": "/privacy",
    "terms.html": "/terms",
}


def html_page(filename: str, *, status_code: int = 200) -> HTMLResponse:
    """Render a static HTML page with shared shell injections."""
    body = inject_site_footer((WEB_DIR / filename).read_text(encoding="utf-8"))
    body = inject_static_asset_hashes(body)
    body = inject_sanitize_script(body)
    body = inject_accessibility_shell(body)
    page_path = _STATIC_PAGE_PATHS.get(filename)
    if page_path is not None:
        base_url = get_settings().public_base_url.rstrip("/")
        body = inject_canonical_url(body, f"{base_url}{page_path}")
    return HTMLResponse(
        content=body,
        status_code=status_code,
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/")
def index() -> HTMLResponse:
    return html_page("index.html")


@router.get("/robots.txt")
def robots_txt() -> PlainTextResponse:
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nSitemap: "
        f"{get_settings().public_base_url.rstrip('/')}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
def sitemap_xml() -> Response:
    from groundtruth.services.market_seo import market_sitemap_urls

    base = get_settings().public_base_url.rstrip("/")
    paths = [
        "/",
        "/valuate",
        "/find",
        "/statistics",
        "/compare",
        "/rent-yield",
        "/alerts",
        "/about",
        "/contact",
        "/methodology",
        "/privacy",
        "/terms",
    ]
    paths.extend(market_sitemap_urls())
    urls = "\n".join(f"  <url><loc>{base}{path}</loc></url>" for path in paths)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/favicon.svg")
def favicon_svg() -> FileResponse:
    return FileResponse(WEB_DIR / "favicon.svg", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/favicon.ico")
def favicon_ico() -> FileResponse:
    return FileResponse(
        WEB_DIR / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/valuate")
def valuate_page() -> HTMLResponse:
    return html_page("valuate.html")


@router.get("/find")
def find_page() -> HTMLResponse:
    return html_page("find.html")


@router.get("/statistics")
def statistics_page() -> HTMLResponse:
    return html_page("statistics.html")


@router.get("/reports")
def reports_page() -> RedirectResponse:
    """Legacy URL — same content as /statistics."""
    return RedirectResponse("/statistics", status_code=308)


@router.get("/about")
def about_page() -> HTMLResponse:
    return html_page("about.html")


@router.get("/methodology")
def methodology_page() -> HTMLResponse:
    return html_page("methodology.html")


@router.get("/alerts")
def alerts_page() -> HTMLResponse:
    return html_page("alerts.html")


@router.get("/privacy")
def privacy_page() -> HTMLResponse:
    return html_page("privacy.html")


@router.get("/terms")
def terms_page() -> HTMLResponse:
    return html_page("terms.html")


@router.get("/annual")
def annual_page() -> RedirectResponse:
    """Legacy URL — same content as /statistics."""
    return RedirectResponse("/statistics", status_code=308)


@router.get("/compare")
def compare_page() -> HTMLResponse:
    return html_page("compare.html")


@router.get("/rent-yield")
def rent_yield_page() -> HTMLResponse:
    return html_page("rent-yield.html")


@router.get("/contact")
def contact_page() -> HTMLResponse:
    return html_page("contact.html")


@router.get("/market/{entity_type}/{slug}")
def market_page(entity_type: EntityType, slug: str) -> HTMLResponse:
    if entity_type not in ("neighborhood", "district", "street", "complex"):
        raise HTTPException(status_code=404)
    from groundtruth.services.market_seo import render_market_html

    html = render_market_html(entity_type, slug, session=None)
    html = inject_site_footer(html)
    html = inject_static_asset_hashes(html)
    html = inject_sanitize_script(html)
    html = inject_accessibility_shell(html)
    base_url = get_settings().public_base_url.rstrip("/")
    html = inject_canonical_url(html, f"{base_url}/market/{entity_type}/{slug}")
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})
