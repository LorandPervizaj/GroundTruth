"""Browser smoke tests for the public Metrik journeys."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator

import pytest
from playwright.sync_api import Browser, Page, Route, expect, sync_playwright

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="set RUN_E2E=1"),
]

BASE_URL = "http://127.0.0.1:8765"


def _wait_for_server(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", 8765)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError("Metrik test server did not start")


@pytest.fixture(scope="module")
def browser() -> Generator[Browser, None, None]:
    env = {
        **os.environ,
        "APP_ENV": "development",
        "API_REQUIRE_LOOKUP_CACHE": "false",
    }
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "groundtruth.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        env=env,
    )
    try:
        _wait_for_server()
        with sync_playwright() as playwright:
            instance = playwright.chromium.launch()
            yield instance
            instance.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


@pytest.fixture
def page(browser: Browser) -> Generator[Page, None, None]:
    context = browser.new_context(viewport={"width": 375, "height": 812})
    page = context.new_page()
    yield page
    context.close()


def test_home_and_language_switch(page: Page) -> None:
    page.goto(BASE_URL)
    page.locator('[data-lang="en"]').click()
    assert page.locator(".footer-lead").inner_text().startswith("Metrik analyzes")
    assert page.locator(".skip-link").count() == 1
    assert page.locator("main#main-content").count() == 1


META_LISTINGS = 12345
SNAPSHOT_LISTINGS = 999


def _route_home_trust(page: Page, *, meta_ok: bool) -> None:
    def meta(route: Route) -> None:
        if not meta_ok:
            route.fulfill(status=503, json={"detail": "unavailable"})
            return
        route.fulfill(
            json={
                "release_id": "2026-W40-test",
                "data_through": "2026-10-04",
                "corpus_updated_at": "2026-10-04T23:33:32Z",
                "active_listings": META_LISTINGS,
                "raw_listings": 16000,
                "cross_portal_duplicates_removed": 3655,
            }
        )

    def snapshot(route: Route) -> None:
        route.fulfill(json={"active_listings": SNAPSHOT_LISTINGS, "updated_at": "2026-09-21"})

    page.route("**/api/meta", meta)
    page.route("**/static/home-trust.json*", snapshot)


def _formatted(page: Page, value: int) -> str:
    return page.evaluate("(n) => window.MetrikFormat.int(n)", value)


def test_home_trust_counter_uses_api_meta_over_static_snapshot(page: Page) -> None:
    _route_home_trust(page, meta_ok=True)
    page.goto(BASE_URL)
    listings = page.locator("#trust-listings")
    expect(listings).to_have_text(_formatted(page, META_LISTINGS))
    expect(page.locator("#trust-updated")).to_have_text(
        page.evaluate("window.MetrikFormat.dateShort('2026-10-04T23:33:32Z')")
    )
    expect(page.locator("#home-trust-strip")).to_have_attribute("data-source", "meta")

    page.locator('[data-lang="en"]').first.click()
    expect(listings).to_have_text("12,345")
    expect(page.locator("#trust-updated")).to_have_text(
        page.evaluate("window.MetrikFormat.dateShort('2026-10-04T23:33:32Z')")
    )


def test_home_trust_counter_falls_back_to_snapshot_when_meta_fails(page: Page) -> None:
    _route_home_trust(page, meta_ok=False)
    page.goto(BASE_URL)
    expect(page.locator("#trust-listings")).to_have_text(_formatted(page, SNAPSHOT_LISTINGS))
    expect(page.locator("#home-trust-strip")).to_have_attribute("data-source", "snapshot")


def test_statistics_loads_self_hosted_chart_library(page: Page) -> None:
    page.goto(f"{BASE_URL}/statistics")
    assert page.evaluate("typeof window.Chart") == "function"
    assert "cdn.jsdelivr.net" not in page.content()


def test_alerts_page_is_real(page: Page) -> None:
    alerts = page.goto(f"{BASE_URL}/alerts")
    assert alerts is not None and alerts.status == 200
    assert page.locator("#alert-form").count() == 1


def test_about_page_is_real(page: Page) -> None:
    about = page.goto(f"{BASE_URL}/about")
    assert about is not None and about.status == 200
    page.wait_for_selector('[data-i18n="about_hero"]')
    assert page.locator('a.nav-link[href="/about"]').count() >= 1


def test_core_static_routes_have_canonical_metadata(page: Page) -> None:
    for path in ("/valuate", "/find", "/compare", "/methodology", "/about"):
        page.goto(f"{BASE_URL}{path}")
        assert page.locator('link[rel="canonical"]').get_attribute("href").endswith(path)


def test_no_horizontal_page_overflow_at_mobile_width(page: Page) -> None:
    page.goto(BASE_URL)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert overflow is False
