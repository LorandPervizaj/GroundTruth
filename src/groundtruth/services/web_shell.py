"""Shared HTML chrome injection for static pages."""

from __future__ import annotations

import hashlib
import html as html_module
import re
from functools import lru_cache

from groundtruth.config import PROJECT_ROOT

WEB_DIR = PROJECT_ROOT / "web"
FOOTER_PLACEHOLDER = '<div id="site-footer"></div>'
_STATIC_ASSET_RE = re.compile(r'(?P<prefix>["\'])/static/(?P<path>[^?"\']+)(?:\?v=[^"\']*)?')


@lru_cache(maxsize=1)
def load_site_footer() -> str:
    path = WEB_DIR / "partials" / "site-footer.html"
    return path.read_text(encoding="utf-8").strip()


def inject_site_footer(html: str) -> str:
    """Replace the footer placeholder with the universal hardcoded footer."""
    if FOOTER_PLACEHOLDER not in html:
        return html
    return html.replace(FOOTER_PLACEHOLDER, load_site_footer(), 1)


@lru_cache(maxsize=128)
def _static_asset_version(relative_path: str) -> str:
    content = (WEB_DIR / "static" / relative_path).read_bytes()
    return hashlib.sha256(content).hexdigest()[:12]


def inject_static_asset_hashes(html: str) -> str:
    """Replace manual cache-bust values with content-derived versions."""

    def replace(match: re.Match[str]) -> str:
        relative_path = match.group("path")
        path = WEB_DIR / "static" / relative_path
        if not path.is_file():
            return match.group(0)
        version = _static_asset_version(relative_path)
        return f"{match.group('prefix')}/static/{relative_path}?v={version}"

    return _STATIC_ASSET_RE.sub(replace, html)


def inject_accessibility_shell(html: str) -> str:
    """Add a keyboard skip link and ensure main#main-content exists."""
    if 'id="main-content"' not in html:
        replacements = (
            ("<main>", '<main id="main-content">'),
            ('<main class="market-main">', '<main id="main-content" class="market-main">'),
            ("<main ", '<main id="main-content" '),
            (
                '<div class="valuate-workspace">',
                '<main id="main-content" class="valuate-workspace">',
            ),
            (
                '<div class="compare-workspace">',
                '<main id="main-content" class="compare-workspace">',
            ),
        )
        for needle, replacement in replacements:
            if needle in html:
                html = html.replace(needle, replacement, 1)
                break
        # If we promoted a workspace <div> to <main>, close before the footer.
        footer = '<div id="site-footer"></div>'
        for cls in ("valuate-workspace", "compare-workspace"):
            marker = f'<main id="main-content" class="{cls}">'
            if marker in html and footer in html:
                prefix, sep, suffix = html.partition(footer)
                if sep and prefix.rfind(marker) > prefix.rfind("</main>"):
                    # Close the last </div> in prefix as </main>
                    idx = prefix.rfind("</div>")
                    if idx != -1:
                        prefix = prefix[:idx] + "</main>" + prefix[idx + len("</div>") :]
                        html = prefix + sep + suffix

    if 'class="skip-link"' not in html:
        body_match = re.search(r"<body[^>]*>", html)
        if body_match:
            skip_link = '<a class="skip-link" href="#main-content" data-i18n="skip_to_content"></a>'
            html = html[: body_match.end()] + skip_link + html[body_match.end() :]
    return html


def inject_sanitize_script(html: str) -> str:
    """Load sanitize.js before other app scripts (XSS hardening for API-rendered HTML)."""
    if "sanitize.js" in html:
        return html
    tag = '<script src="/static/sanitize.js"></script>'
    marker = '<script src="/static/i18n.js'
    if marker in html:
        return html.replace(marker, f"{tag}\n  {marker}", 1)
    return html.replace("</head>", f"  {tag}\n</head>", 1)


def inject_canonical_url(html: str, canonical_url: str) -> str:
    """Add canonical and Open Graph URL metadata to static pages."""
    escaped = html_module.escape(canonical_url, quote=True)
    if 'rel="canonical"' not in html:
        html = html.replace(
            "</head>",
            f'  <link rel="canonical" href="{escaped}" />\n</head>',
            1,
        )
    if 'property="og:url"' not in html:
        html = html.replace(
            "</head>",
            f'  <meta property="og:url" content="{escaped}" />\n</head>',
            1,
        )
    return html
