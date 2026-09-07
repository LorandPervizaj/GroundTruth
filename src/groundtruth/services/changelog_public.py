"""Load curated public changelog from data/product/changelog.json."""

from __future__ import annotations

import json

from groundtruth.config import PROJECT_ROOT
from groundtruth.schemas.changelog import ChangelogCategory, ChangelogEntry, ChangelogResponse

CHANGELOG_PATH = PROJECT_ROOT / "data" / "product" / "changelog.json"


def load_public_changelog(
    *,
    category: ChangelogCategory | None = None,
    limit: int = 100,
) -> ChangelogResponse:
    if not CHANGELOG_PATH.exists():
        return ChangelogResponse()

    raw = json.loads(CHANGELOG_PATH.read_text(encoding="utf-8"))
    entries = [ChangelogEntry.model_validate(row) for row in raw]
    entries.sort(key=lambda e: (e.date, e.title_en), reverse=True)

    if category:
        entries = [e for e in entries if e.category == category]

    return ChangelogResponse(entries=entries[:limit])
