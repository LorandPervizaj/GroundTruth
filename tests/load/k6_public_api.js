import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const profile = (__ENV.K6_PROFILE || "smoke").toLowerCase();

const scenarios = {
  smoke: {
    executor: "constant-vus",
    vus: 3,
    duration: "15s",
  },
  baseline: {
    executor: "ramping-vus",
    startVUs: 0,
    stages: [
      { duration: "15s", target: 10 },
      { duration: "30s", target: 25 },
      { duration: "15s", target: 0 },
    ],
    gracefulRampDown: "5s",
  },
};

if (!scenarios[profile]) {
  throw new Error(`Unknown K6_PROFILE "${profile}". Use "smoke" or "baseline".`);
}

export const options = {
  scenarios: {
    public_reads: scenarios[profile],
  },
  thresholds: {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<750", "p(99)<1500"],
    "http_req_duration{endpoint:lookup}": ["p(95)<1000"],
    "http_req_duration{endpoint:markets}": ["p(95)<900"],
  },
};

function parseJson(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

export default function () {
  const responses = http.batch([
    [
      "GET",
      `${baseUrl}/api/health`,
      null,
      { tags: { endpoint: "health" }, headers: { Accept: "application/json" } },
    ],
    [
      "GET",
      `${baseUrl}/api/meta`,
      null,
      { tags: { endpoint: "meta" }, headers: { Accept: "application/json" } },
    ],
    [
      "GET",
      `${baseUrl}/api/markets`,
      null,
      { tags: { endpoint: "markets" }, headers: { Accept: "application/json" } },
    ],
    [
      "GET",
      `${baseUrl}/api/lookup/neighborhood/ulpiana`,
      null,
      { tags: { endpoint: "lookup" }, headers: { Accept: "application/json" } },
    ],
    [
      "GET",
      `${baseUrl}/`,
      null,
      { tags: { endpoint: "home" }, headers: { Accept: "text/html" } },
    ],
  ]);

  const [health, meta, markets, lookup, home] = responses;
  const healthJson = parseJson(health);
  const metaJson = parseJson(meta);
  const marketsJson = parseJson(markets);
  const lookupJson = parseJson(lookup);

  check(health, {
    "health returns 200": (r) => r.status === 200,
    "health payload is ok": () => healthJson?.status === "ok",
  });

  check(meta, {
    "meta returns 200": (r) => r.status === 200,
    "meta exposes a dataset version": () =>
      typeof metaJson?.dataset_version === "string" && metaJson.dataset_version.length > 0,
  });

  check(markets, {
    "markets returns 200": (r) => r.status === 200,
    "markets returns rows": () => Array.isArray(marketsJson) && marketsJson.length > 0,
  });

  check(lookup, {
    "lookup returns 200": (r) => r.status === 200,
    "lookup resolves Ulpiana": () => lookupJson?.slug === "ulpiana",
    "lookup exposes pulse data": () => lookupJson?.pulse && typeof lookupJson.pulse === "object",
  });

  check(home, {
    "home returns 200": (r) => r.status === 200,
    "home is html": (r) => (r.headers["Content-Type"] || "").includes("text/html"),
    "home renders Metrik": (r) => r.body.includes("Metrik"),
  });

  sleep(profile === "baseline" ? 0.2 : 0.5);
}
