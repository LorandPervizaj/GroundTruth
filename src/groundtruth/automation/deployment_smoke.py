"""Read-only HTTP acceptance checks shared by CI, PowerShell and offline tests."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from groundtruth.automation.deployment import require

READS = [
    "/api/health",
    "/api/ready",
    "/api/meta",
    "/api/search?q=ulpiana",
    "/api/markets",
    "/api/compare?neighborhoods=ulpiana,arberia",
    "/api/lookup/neighborhood/ulpiana",
    "/api/rent-yield",
    "/api/reports/annual_data",
]
PAGES = ["/", "/statistics", "/compare", "/rent-yield", "/valuate", "/alerts", "/contact"]


def validate(path: str, status: int, body: Any, expected: dict) -> None:
    require(status == 200, f"Critical read failed: {path} HTTP {status}")
    if path in PAGES:
        require(
            isinstance(body, str) and "<html" in body.lower() and "</html>" in body.lower(),
            f"Invalid frontend: {path}",
        )
        return
    require(isinstance(body, (dict, list)), f"Malformed JSON/schema: {path}")
    if path == "/api/meta":
        require(
            isinstance(body, dict) and body.get("release_id") == expected["data_release_id"],
            "Wrong exact release_id",
        )
        require(
            type(body.get("active_listings")) is int
            and body["active_listings"] >= 0
            and bool(body.get("data_through")),
            "Invalid metadata schema",
        )
    elif path == "/api/ready":
        require(
            isinstance(body, dict) and body.get("ok") is True and not body.get("reasons"),
            "Readiness failed",
        )
    elif path == "/api/health":
        require(body == {"status": "ok"}, "Invalid health response")
    elif path == "/api/deployment":
        require(isinstance(body, dict), "Missing runtime identity")
        for key in ("revision", "serving_source_sha", "image", "data_release_id"):
            require(body.get(key) == expected[key], f"Wrong runtime identity: {key}")
        require(
            body.get("backend") == "azure_table" and body.get("ok") is True,
            "Table connectivity/backend failed",
        )
        require(
            body.get("cache_guard_verified") is True and body.get("artifacts_verified") is True,
            "Cache/artifact startup guard failed",
        )
    elif path == "/api/markets":
        require(
            isinstance(body, list)
            and bool(body)
            and all(isinstance(x, dict) and x.get("slug") and x.get("name") for x in body),
            "Invalid markets schema",
        )
    elif path.startswith("/api/compare"):
        require(
            isinstance(body, dict)
            and isinstance(body.get("neighborhoods"), list)
            and len(body["neighborhoods"]) == 2,
            "Invalid compare schema",
        )
    elif path == "/api/rent-yield":
        require(
            isinstance(body, dict) and isinstance(body.get("rows"), list) and bool(body["rows"]),
            "Invalid rent yield schema",
        )
    elif path.startswith("/api/search"):
        require(
            isinstance(body, dict) and isinstance(body.get("results"), list),
            "Invalid search schema",
        )
    elif path.startswith("/api/lookup/"):
        require(
            isinstance(body, dict)
            and body.get("slug") == "ulpiana"
            and body.get("entity_type") == "neighborhood"
            and bool(body.get("display_name")),
            "Invalid lookup schema",
        )
    elif path == "/api/reports/annual_data":
        require(
            isinstance(body, dict)
            and isinstance(body.get("kpis"), dict)
            and isinstance(body.get("volume"), dict)
            and type(body.get("total_listings")) is int,
            "Invalid annual report schema",
        )


def smoke(
    base_url: str, expected: dict, *, token: str = "", identity: bool = True, fetch=None
) -> None:
    require(base_url.startswith("https://"), "HTTPS candidate endpoint required")
    require(identity, "Exact worker identity required before telemetry-free read probes")
    require(bool(token), "Ops token required for read-only deployment probes")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # Never forward the ops credential to another origin.

    opener = urllib.request.build_opener(NoRedirect)

    def request(path):
        req = urllib.request.Request(
            base_url.rstrip("/") + path,
            headers={"X-Health-Token": token, "X-Metrik-Deployment-Probe": "1"},
        )
        with opener.open(req, timeout=30) as response:
            require(response.geturl() == req.full_url, "Unexpected HTTP redirect")
            raw = response.read().decode("utf-8")
            return response.status, raw if path in PAGES else json.loads(raw)

    get = fetch or request
    # Authenticate and bind the worker BEFORE search can log a product event.
    for path in ["/api/deployment"] + READS + PAGES:
        status, body = get(path)
        validate(path, status, body, expected)
