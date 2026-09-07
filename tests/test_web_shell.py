"""Tests for universal HTML shell injection."""

from groundtruth.services.web_shell import (
    FOOTER_PLACEHOLDER,
    inject_accessibility_shell,
    inject_canonical_url,
    inject_site_footer,
    inject_static_asset_hashes,
    load_site_footer,
)


def test_load_site_footer_has_links() -> None:
    html = load_site_footer()
    assert 'data-i18n="footer_lead"' in html
    assert 'data-i18n="insights_subnav_compare"' in html
    assert 'href="/contact"' in html
    assert 'id="footer-freshness"' in html


def test_inject_site_footer_replaces_placeholder() -> None:
    page = f"<body>{FOOTER_PLACEHOLDER}</body>"
    out = inject_site_footer(page)
    assert FOOTER_PLACEHOLDER not in out
    assert "site-footer" in out


def test_inject_static_asset_hashes_replaces_manual_versions() -> None:
    page = '<link href="/static/style.css?v=1"><script src="/static/site.js?v=2"></script>'
    out = inject_static_asset_hashes(page)
    assert '"/static/style.css?v=1"' not in out
    assert '"/static/site.js?v=2"' not in out
    assert out.count("?v=") == 2


def test_inject_accessibility_shell_adds_skip_target() -> None:
    out = inject_accessibility_shell("<body><main>Content</main></body>")
    assert 'class="skip-link"' in out
    assert '<main id="main-content">' in out


def test_inject_canonical_url_adds_metadata() -> None:
    out = inject_canonical_url("<head></head>", "https://metrik.example/valuate")
    assert 'rel="canonical"' in out
    assert 'property="og:url"' in out
