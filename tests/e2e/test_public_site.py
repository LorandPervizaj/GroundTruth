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


META_UPDATED = "2026-10-04T23:33:32Z"
META_BODY = {
    "release_id": "2026-W40-test",
    "data_through": "2026-10-04",
    "corpus_updated_at": META_UPDATED,
    "active_listings": META_LISTINGS,
    "raw_listings": 16000,
    "cross_portal_duplicates_removed": 3655,
}


def _route_home_trust(
    page: Page,
    *,
    meta_ok: bool = True,
    snapshot_ok: bool = True,
    held_snapshots: list[Route] | None = None,
) -> dict[str, int | bool]:
    """Stub /api/meta and the snapshot; returns live state.

    Setting ``state["meta_ok"]`` changes how later meta requests answer.
    ``held_snapshots`` collects snapshot requests so the test decides when they answer.
    """
    state: dict[str, int | bool] = {"meta": 0, "snapshot": 0, "meta_ok": meta_ok}

    def meta(route: Route) -> None:
        state["meta"] += 1
        if not state["meta_ok"]:
            route.fulfill(status=503, json={"detail": "unavailable"})
            return
        route.fulfill(json=META_BODY)

    def snapshot(route: Route) -> None:
        state["snapshot"] += 1
        if held_snapshots is not None:
            held_snapshots.append(route)
        elif snapshot_ok:
            route.fulfill(json={"active_listings": SNAPSHOT_LISTINGS, "updated_at": "2026-09-21"})
        else:
            route.fulfill(status=404, body="")

    page.route("**/api/meta", meta)
    page.route("**/static/home-trust.json*", snapshot)
    return state


def _formatted(page: Page, value: int) -> str:
    return page.evaluate("(n) => window.MetrikFormat.int(n)", value)


def _expect_meta_values(page: Page) -> None:
    expect(page.locator("#trust-listings")).to_have_text(_formatted(page, META_LISTINGS))
    expect(page.locator("#trust-updated")).to_have_text(
        page.evaluate("(iso) => window.MetrikFormat.dateShort(iso)", META_UPDATED)
    )
    expect(page.locator("#home-trust-strip")).to_have_attribute("data-source", "meta")


def test_home_trust_counter_uses_api_meta_over_static_snapshot(page: Page) -> None:
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    calls = _route_home_trust(page)
    page.goto(BASE_URL)
    _expect_meta_values(page)
    assert calls["snapshot"] == 0, "the fallback must not be requested when meta succeeds"

    page.locator('[data-lang="en"]').first.click()
    expect(page.locator("#trust-listings")).to_have_text("12,345")
    _expect_meta_values(page)

    page.locator('[data-lang="sq"]').first.click()
    expect(page.locator("html")).to_have_attribute("lang", "sq")
    _expect_meta_values(page)
    assert calls["snapshot"] == 0
    assert errors == []


def test_home_trust_counter_falls_back_to_snapshot_when_meta_fails(page: Page) -> None:
    _route_home_trust(page, meta_ok=False)
    page.goto(BASE_URL)
    expect(page.locator("#trust-listings")).to_have_text(_formatted(page, SNAPSHOT_LISTINGS))
    expect(page.locator("#home-trust-strip")).to_have_attribute("data-source", "snapshot")


def test_home_trust_strip_hides_when_meta_and_snapshot_fail(page: Page) -> None:
    calls = _route_home_trust(page, meta_ok=False, snapshot_ok=False)
    page.goto(BASE_URL)
    expect(page.locator("#home-trust-strip")).to_be_hidden()
    assert calls["meta"] >= 1 and calls["snapshot"] == 1
    assert page.locator("#trust-listings").inner_text().strip() == ""


def test_late_snapshot_cannot_overwrite_rendered_meta(page: Page) -> None:
    held: list[Route] = []
    state = _route_home_trust(page, meta_ok=False, held_snapshots=held)
    page.goto(BASE_URL)
    deadline = time.monotonic() + 5
    while not held and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert len(held) == 1, "meta failure should request the fallback snapshot"

    state["meta_ok"] = True
    page.locator('[data-lang="en"]').first.click()
    _expect_meta_values(page)

    held[0].fulfill(json={"active_listings": SNAPSHOT_LISTINGS, "updated_at": "2026-09-21"})
    page.wait_for_timeout(1500)
    _expect_meta_values(page)


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
