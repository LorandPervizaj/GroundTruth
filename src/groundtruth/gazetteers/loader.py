"""Load and query gazetteer JSON files. Deterministic lookup before fuzzy matching."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from groundtruth.config import get_settings
from groundtruth.logging import get_logger

logger = get_logger(__name__)

_FUZZY_THRESHOLD = 85

_CITY_ALIASES: dict[str, str] = {
    "prishtine": "prishtina",
    "pristina": "prishtina",
    "prizreni": "prizren",
    "peje": "peja",
    "gjakova": "gjakove",
    "fushe kosove": "fushe kosove",
    "fushë kosovë": "fushe kosove",
    "fushë kosova": "fushe kosove",
}


@dataclass(frozen=True)
class GazetteerMatch:
    """Result of a gazetteer lookup."""

    id: int | None
    name: str
    slug: str
    match_type: str  # exact | alias | fuzzy
    score: float = 100.0


class GazetteerService:
    """Load lookup tables from JSON and resolve names to canonical entries."""

    def __init__(self, gazetteer_dir: Path | None = None) -> None:
        settings = get_settings()
        self._dir = gazetteer_dir or settings.gazetteer_dir
        self._data: dict[str, list[dict[str, Any]]] = {}

    def load(self) -> None:
        """Load all gazetteer files from disk."""
        files = {
            "neighborhoods": "neighborhoods.json",
            "streets": "streets.json",
            "complexes": "complexes.json",
            "buildings": "building_aliases.json",
        }
        for key, filename in files.items():
            path = self._dir / filename
            if path.exists():
                self._data[key] = json.loads(path.read_text(encoding="utf-8"))
                logger.info("gazetteer_loaded", name=key, entries=len(self._data[key]))
            else:
                self._data[key] = []
                logger.warning("gazetteer_missing", path=str(path))

    def _ensure_loaded(self) -> None:
        if not self._data:
            self.load()

    def match_neighborhood(self, name: str, city: str | None = None) -> GazetteerMatch | None:
        """Match a neighborhood name. Deterministic first, then fuzzy."""
        self._ensure_loaded()
        return self._match_entry(
            self._data["neighborhoods"],
            name,
            filter_key="city",
            filter_value=city,
        )

    def match_street(
        self,
        name: str,
        neighborhood_slug: str | None = None,
    ) -> GazetteerMatch | None:
        """Match a street name within an optional neighborhood."""
        self._ensure_loaded()
        return self._match_entry(
            self._data["streets"],
            name,
            filter_key="neighborhood_slug",
            filter_value=neighborhood_slug,
        )

    def match_complex(
        self,
        name: str,
        neighborhood_slug: str | None = None,
    ) -> GazetteerMatch | None:
        """Match a residential complex name."""
        self._ensure_loaded()
        return self._match_entry(
            self._data["complexes"],
            name,
            filter_key="neighborhood_slug",
            filter_value=neighborhood_slug,
        )

    def match_building(
        self,
        name: str,
        complex_slug: str | None = None,
    ) -> GazetteerMatch | None:
        """Match a building name or alias."""
        self._ensure_loaded()
        return self._match_entry(
            self._data["buildings"],
            name,
            filter_key="complex_slug",
            filter_value=complex_slug,
        )

    def get_neighborhood_centroid(self, slug: str) -> tuple[float, float] | None:
        """Return lat/lng centroid for a neighborhood slug."""
        self._ensure_loaded()
        for entry in self._data["neighborhoods"]:
            if entry.get("slug") == slug:
                lat, lng = entry.get("centroid_lat"), entry.get("centroid_lng")
                if lat is not None and lng is not None:
                    return (lat, lng)
        return None

    def _match_entry(
        self,
        entries: list[dict[str, Any]],
        name: str,
        filter_key: str | None = None,
        filter_value: str | None = None,
    ) -> GazetteerMatch | None:
        normalized_input = self._normalize(name)
        candidates = entries

        if filter_value and filter_key:
            normalized_filter = (
                self._canonical_city(filter_value)
                if filter_key == "city"
                else self._normalize(filter_value)
            )
            filtered: list[dict[str, Any]] = []
            for entry in entries:
                entry_value = entry.get(filter_key, "")
                if filter_key == "city":
                    matches = self._canonical_city(str(entry_value)) == normalized_filter
                else:
                    matches = self._normalize(str(entry_value)) == normalized_filter
                if matches:
                    filtered.append(entry)
            if filtered:
                candidates = filtered

        for entry in candidates:
            if self._normalize(entry["name"]) == normalized_input:
                return GazetteerMatch(
                    id=entry.get("id"),
                    name=entry["name"],
                    slug=entry["slug"],
                    match_type="exact",
                )
            for alias in entry.get("aliases", []):
                if self._normalize(alias) == normalized_input:
                    return GazetteerMatch(
                        id=entry.get("id"),
                        name=entry["name"],
                        slug=entry["slug"],
                        match_type="alias",
                    )

        choices = {self._normalize(e["name"]): e for e in candidates}
        for entry in candidates:
            for alias in entry.get("aliases", []):
                choices[self._normalize(alias)] = entry

        if not choices:
            return None

        result = process.extractOne(
            normalized_input,
            choices.keys(),
            scorer=fuzz.token_sort_ratio,
        )
        if result and result[1] >= _FUZZY_THRESHOLD:
            entry = choices[result[0]]
            return GazetteerMatch(
                id=entry.get("id"),
                name=entry["name"],
                slug=entry["slug"],
                match_type="fuzzy",
                score=result[1],
            )
        return None

    @classmethod
    def _canonical_city(cls, city: str) -> str:
        normalized = cls._normalize(city)
        return _CITY_ALIASES.get(normalized, normalized)

    @staticmethod
    @lru_cache(maxsize=4096)
    def _normalize(text: str) -> str:
        """Normalize text for comparison: lowercase, strip accents, collapse whitespace."""
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s]", "", text)
        return re.sub(r"\s+", " ", text)
