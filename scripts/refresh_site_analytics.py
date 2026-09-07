"""Refresh corpus, lookup cache, annual report, and homepage trust snapshot.

Run after weekly ETL so public stats/pages show current dates and numbers.
"""

from __future__ import annotations

import runpy
from pathlib import Path

from sqlalchemy import text

from groundtruth.crawl.checkpoints import load_checkpoint, save_checkpoint
from groundtruth.crawl.weekly import checkpoint_path, refresh_analytics
from groundtruth.crawl.window import CrawlWindow
from groundtruth.database.session import get_session_factory


def main() -> None:
    session = get_session_factory()()
    try:
        session.execute(text("SET statement_timeout = '0'"))
        session.execute(text("SET lock_timeout = '0'"))
        window = CrawlWindow.last_n_days(7)
        print(f"Refreshing analytics for {window.crawl_week}...")
        refresh_analytics(session, window=window)
        cp = load_checkpoint(window.crawl_week)
        if cp is not None:
            cp.analytics = "done"
            save_checkpoint(cp)
            print(f"Checkpoint analytics=done ({checkpoint_path(window.crawl_week)})")
    finally:
        session.close()

    print("Updating home-trust snapshot...")
    trust_script = Path(__file__).resolve().with_name("update_home_trust_snapshot.py")
    runpy.run_path(str(trust_script), run_name="__main__")
    print("DONE")


if __name__ == "__main__":
    main()
