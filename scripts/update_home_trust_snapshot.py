"""Write the homepage trust-strip fallback snapshot from current corpus meta.

The homepage reads its listing count and freshness date from ``/api/meta``.
``web/static/home-trust.json`` is only shown when that request fails, and it can
never replace values that ``/api/meta`` has already rendered. Regenerating it
does not make it authoritative.

The snapshot is not part of the release bundle: production serves the copy
committed to the repository, so it lags the live release by design. Refresh it
after a local data refresh only when you intend to commit a newer fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from groundtruth.database.session import get_session_factory
from groundtruth.services.lookup import get_corpus_meta

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "static" / "home-trust.json"


def build_payload(meta: Any) -> dict[str, Any] | None:
    """Return the snapshot payload, or None when meta cannot produce a usable fallback."""
    active_listings = int(meta.active_listings or 0)
    if active_listings <= 0 or meta.corpus_updated_at is None:
        return None
    return {
        "active_listings": active_listings,
        "source_count": int(meta.source_count or 0),
        "updated_at": meta.corpus_updated_at.date().isoformat(),
    }


def main() -> None:
    session = get_session_factory()()
    try:
        meta = get_corpus_meta(session)
    finally:
        session.close()

    payload = build_payload(meta)
    if payload is None:
        print(f"Skipped {OUT}: corpus meta has no active listings or update time")
        return
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated homepage fallback snapshot {OUT} -> {payload}")


if __name__ == "__main__":
    main()
