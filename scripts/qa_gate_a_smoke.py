"""Gate A live smoke against production-shaped stack."""

from __future__ import annotations

import subprocess

import httpx

c = httpx.Client(verify=False, timeout=30, follow_redirects=True)


def hit(method: str, path: str, **kw) -> httpx.Response:
    r = c.request(method, "https://localhost" + path, **kw)
    body = r.text[:180].replace("\n", " ")
    print(f"{method} {path} -> {r.status_code} {body}")
    return r


print("=== GATE A LIVE SMOKE ===")
assert hit("GET", "/api/ready").status_code == 200
assert hit("GET", "/").status_code == 200
assert hit("GET", "/api/meta").status_code == 200
assert hit("GET", "/api/search", params={"q": "ulpiana"}).status_code == 200
assert hit("GET", "/api/markets").status_code == 200
assert hit("GET", "/api/compare", params={"neighborhoods": "ulpiana,arberia"}).status_code == 200
assert hit("GET", "/api/lookup/neighborhood/ulpiana").status_code == 200
ry = hit("GET", "/api/rent-yield")
assert ry.status_code == 200 and len(ry.json().get("rows") or []) > 0
assert hit("GET", "/api/reports/annual_data").status_code == 200
for page in (
    "/statistics",
    "/compare",
    "/rent-yield",
    "/valuate",
    "/alerts",
    "/contact",
    "/market/neighborhood/ulpiana",
):
    assert hit("GET", page).status_code == 200

alerts = hit(
    "POST",
    "/api/alerts",
    json={"email": "beta@example.com", "neighborhood_slug": "ulpiana"},
)
# 503 = feature unavailable; 429 = rate limit still protecting the edge after prior QA bursts.
assert alerts.status_code in (503, 429), alerts.text
if alerts.status_code == 503:
    assert alerts.json().get("status") == "unavailable"

valuate = hit(
    "POST",
    "/api/valuate",
    json={"neighborhood": "Ulpiana", "area_sqm": 70, "valuation_type": "rent"},
)
print("valuate_status", valuate.status_code, valuate.text[:240])
assert valuate.status_code == 503
assert "unavailable" in valuate.text.lower()

alerts_html = hit("GET", "/alerts").text
assert "alert-unavailable" in alerts_html

r = c.get("https://localhost/")
for h in (
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "content-security-policy",
    "referrer-policy",
):
    print("hdr", h, r.headers.get(h))

redir = c.get("http://localhost/api/ready", follow_redirects=False)
print("http_redirect", redir.status_code, redir.headers.get("location"))
assert redir.status_code == 301

print(
    "postgres_ports",
    subprocess.check_output(["docker", "port", "metrikqa-postgres-1"], text=True).strip() or "NONE",
)
print(
    "app_ports",
    subprocess.check_output(["docker", "port", "metrikqa-app-1"], text=True).strip() or "NONE",
)
print("GATE_A_SMOKE_OK")
