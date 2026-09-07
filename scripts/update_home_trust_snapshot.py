"""Write static homepage trust-strip snapshot from current corpus meta.

Run after a crawler/data refresh so the homepage stays static at runtime
while reflecting the latest known dataset state.
"""

from __future__ import annotations

import json
from pathlib import Path

from groundtruth.database.session import get_session_factory
from groundtruth.services.lookup import get_corpus_meta

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "static" / "home-trust.json"


def main() -> None:
    session = get_session_factory()()
    try:
        meta = get_corpus_meta(session)
    finally:
        session.close()

    payload = {
        "active_listings": int(meta.active_listings or 0),
        "source_count": int(meta.source_count or 0),
        "updated_at": meta.corpus_updated_at.date().isoformat() if meta.corpus_updated_at else "",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {OUT} -> {payload}")


if __name__ == "__main__":
    main()
