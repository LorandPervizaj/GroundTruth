# k6 reference baseline

A local regression reference, not a production benchmark. Production runs on
Azure Container Apps with different CPU, network, and TLS; these numbers only
make later runs on similar hardware comparable.

## Context

| Item | Value |
| --- | --- |
| Date | 2026-10-06 |
| Machine | Windows 11 laptop, Intel Core Ultra 5 125U (14 logical CPUs), 31 GB RAM |
| k6 | v2.2.0 (winget `GrafanaLabs.k6`) |
| Application code | `master` at `d486add` (load script from `8d550bf`) |
| Release artifacts | Local `lookup_cache` from the 2026-10-05 research run, 210 entries, dataset v2.0 |
| Target | `groundtruth serve --no-reload`, one worker, `APP_ENV=development`, rate limits off |
| Database | Disposable `groundtruth_perf` (tmpfs, port 15434), migrated, empty |
| Command | `.\scripts\performance\k6.ps1 baseline`, four runs |

## Baseline profile (25 VUs peak, 60 s)

| Run | p50 | p90 | p95 | p99 | max | Failed | Checks | req/s | iterations/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 127.4 ms | 255.1 ms | 331.1 ms | 571.7 ms | 725.9 ms | 0.00% | 100% | 176.3 | 35.27 |
| 2 | 103.7 ms | 294.4 ms | 369.6 ms | 543.3 ms | 728.0 ms | 0.00% | 100% | 181.9 | 36.37 |
| 3 | 92.5 ms | 251.8 ms | 373.9 ms | 575.9 ms | 769.8 ms | 0.00% | 100% | 188.1 | 37.62 |
| 4 | 109.5 ms | 291.5 ms | 391.5 ms | 730.4 ms | 887.7 ms | 0.00% | 100% | 177.6 | 35.52 |

Runs 1–3 were consecutive on one server process; run 4 used a freshly restarted
target. Per-endpoint p95 in runs 1–3: `lookup` 360–404 ms, `markets` 367–405 ms.

## Smoke profile (3 VUs, 15 s)

p50 42.2 ms, p95 86.6 ms, p99 127.9 ms, 0.00% failed, 100% checks,
26.4 req/s, 5.29 iterations/s. Later runs measured p95 142.4 ms and 84.9 ms:
expect this much variance on a laptop.

## Cold start

Lookup and comparables caches load before `/api/health` returns 200. Right
after startup, the first request per endpoint took 10–15 ms and later ones
7–10 ms, so the profiles have no separate warm-up stage.
