"""Log crawl health for one or all spiders — run manually or on an interval."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from groundtruth.config import get_settings
from groundtruth.database.session import get_session_factory

LOG_PATH = get_settings().reports_generated_dir / "crawl_monitor.log"

KNOWN_SPIDERS = (
    "gjirafa",
    "merrjep",
    "pro-rks",
    "topia",
    "vision",
    "myrealestate",
)

# CLI spider name → raw_listings.source_website (identical for current sources).
_SOURCE_WEBSITE = {name: name for name in KNOWN_SPIDERS}


def _process_running(spider: str) -> bool:
    if spider not in KNOWN_SPIDERS:
        raise ValueError(f"Unknown spider: {spider}")
    if sys.platform != "win32":
        return False
    pattern = re.escape(spider)
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
            f"Where-Object {{ $_.CommandLine -match 'crawl\\s+{pattern}' }}).Count",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return int(result.stdout.strip() or "0") > 0
    except ValueError:
        return False


def snapshot(spider: str) -> dict[str, Any]:
    source = _SOURCE_WEBSITE.get(spider, spider)
    with get_session_factory()() as session:
        raw_count, last_scraped = session.execute(
            text(
                """
                SELECT COUNT(*), MAX(scraped_at)
                FROM raw_listings
                WHERE source_website = :source
                """
            ),
            {"source": source},
        ).one()
        run = session.execute(
            text(
                """
                SELECT id, status::text, started_at, finished_at, errors_count,
                       metadata
                FROM scrape_runs
                WHERE spider_name = :spider
                ORDER BY started_at DESC
                LIMIT 1
                """
            ),
            {"spider": spider},
        ).first()
    age_s = (datetime.now(UTC) - last_scraped).total_seconds() if last_scraped else None
    error_codes = None
    if run is not None and isinstance(run[5], dict):
        stats = run[5].get("scrapy_stats") or {}
        error_codes = stats.get("error_codes") or run[5].get("error_codes")
    return {
        "spider": spider,
        "ts": datetime.now(UTC).isoformat(),
        "process_running": _process_running(spider),
        "raw_count": int(raw_count or 0),
        "last_scraped": last_scraped.isoformat() if last_scraped else None,
        "seconds_since_last_scrape": age_s,
        "scrape_run_id": run[0] if run else None,
        "scrape_run_status": run[1] if run else None,
        "scrape_run_started": run[2].isoformat() if run and run[2] else None,
        "errors_count": run[4] if run else None,
        "error_codes": error_codes,
    }


def assess(s: dict[str, Any]) -> str:
    if s["scrape_run_status"] == "RUNNING" and not s["process_running"]:
        return "STALE — DB says RUNNING but no crawl process found"
    age = s["seconds_since_last_scrape"]
    if (
        age is not None
        and age > 600
        and (s["process_running"] or s["scrape_run_status"] == "RUNNING")
    ):
        return f"STALE — no new raw listings for {int(age)}s"
    if s["process_running"]:
        return "OK"
    if s["scrape_run_status"] == "RUNNING":
        return "STALE — RUNNING without process"
    return "STOPPED"


def log_line(s: dict[str, Any]) -> str:
    codes = s.get("error_codes") or {}
    codes_part = f" | codes={codes}" if codes else ""
    return (
        f"{s['ts']} | {s['spider']} | {assess(s)} | raw={s['raw_count']} | "
        f"last_scrape_age_s={int(s['seconds_since_last_scrape'] or -1)} | "
        f"run=#{s['scrape_run_id']} {s['scrape_run_status']} | "
        f"errors={s['errors_count']} | process={s['process_running']}"
        f"{codes_part}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor crawl health for one or all spiders")
    parser.add_argument(
        "--spider",
        action="append",
        dest="spiders",
        choices=KNOWN_SPIDERS,
        help="Spider to monitor (repeatable). Default: all known spiders.",
    )
    parser.add_argument(
        "--interval-min",
        type=int,
        default=0,
        help="Repeat every N minutes (0 = once)",
    )
    args = parser.parse_args()
    spiders = tuple(args.spiders) if args.spiders else KNOWN_SPIDERS

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    while True:
        for spider in spiders:
            s = snapshot(spider)
            line = log_line(s)
            print(line)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        if args.interval_min <= 0:
            break
        time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    main()
