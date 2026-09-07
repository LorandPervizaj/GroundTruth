"""Browser-like request fingerprints for resilient HTML/API crawling."""

from __future__ import annotations

import random
from typing import Literal

AcceptKind = Literal["html", "json"]

# Desktop Chrome / Firefox — keep majors current; refresh when soft-blocks rise.
_CHROME_PROFILES: tuple[dict[str, str], ...] = (
    {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec_ch_ua_platform": '"Windows"',
    },
    {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec_ch_ua_platform": '"macOS"',
    },
    {
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec_ch_ua_platform": '"Linux"',
    },
)

_FIREFOX_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0",
)

_ACCEPT_LANGUAGES: tuple[str, ...] = (
    "sq,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,sq;q=0.8",
    "sq-AL,sq;q=0.9,en;q=0.8",
)

_HTTP11_HANDLER = {
    "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
    "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
}


def http11_handlers() -> dict[str, str]:
    """Fast HTTP/1.1 download handler — avoids Playwright overhead."""
    return dict(_HTTP11_HANDLER)


def pick_user_agent() -> str:
    """Return a realistic desktop browser user agent."""
    if random.random() < 0.85:
        return random.choice(_CHROME_PROFILES)["user_agent"]
    return random.choice(_FIREFOX_USER_AGENTS)


def build_browser_headers(
    *,
    referer: str | None = None,
    accept: AcceptKind = "html",
) -> dict[str, bytes | str]:
    """Build a Chrome-like header set that passes common bot heuristics."""
    if accept == "json":
        accept_value = "application/json, text/plain, */*"
        sec_fetch_dest = "empty"
        sec_fetch_mode = "cors"
    else:
        accept_value = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        )
        sec_fetch_dest = "document"
        sec_fetch_mode = "navigate"

    profile = random.choice(_CHROME_PROFILES)
    user_agent = profile["user_agent"]

    headers: dict[str, bytes | str] = {
        "User-Agent": user_agent,
        "Accept": accept_value,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": sec_fetch_dest,
        "Sec-Fetch-Mode": sec_fetch_mode,
        "Sec-Fetch-Site": "same-origin" if referer else "none",
        "Sec-Fetch-User": "?1" if accept == "html" else None,
    }

    if user_agent.startswith("Mozilla/5.0") and "Chrome/" in user_agent:
        headers["Sec-CH-UA"] = profile["sec_ch_ua"]
        headers["Sec-CH-UA-Mobile"] = "?0"
        headers["Sec-CH-UA-Platform"] = profile["sec_ch_ua_platform"]

    if referer:
        headers["Referer"] = referer

    return {k: v for k, v in headers.items() if v is not None}


def build_api_headers(*, referer: str | None = None) -> dict[str, bytes | str]:
    """JSON API requests with browser-like fingerprint."""
    return build_browser_headers(referer=referer, accept="json")
