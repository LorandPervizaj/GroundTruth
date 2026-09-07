"""Load on-disk spider contract fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).resolve().parent


def fixture_text(*parts: str) -> str:
    path = FIXTURES_ROOT.joinpath(*parts)
    return path.read_text(encoding="utf-8")


def fixture_json(*parts: str) -> Any:
    return json.loads(fixture_text(*parts))
