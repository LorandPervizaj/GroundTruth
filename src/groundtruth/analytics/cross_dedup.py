"""Cross-portal duplicate grouping for the active corpus."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from groundtruth.analytics.listing_fingerprint import coarse_block_key
from groundtruth.config import get_settings
from groundtruth.models.enums import Currency, ListingType, PropertyType
from groundtruth.portals.registry import source_priority_order
from groundtruth.processing.deduplicator.scoring import DuplicateScorer
from groundtruth.schemas.pipeline import NormalizedListingSchema

# Compatibility re-export — authoritative order is portals.registry.
SOURCE_PRIORITY = source_priority_order()


@dataclass
class CrossDedupStats:
    raw_listings: int
    canonical_listings: int
    cross_portal_groups: int
    listings_in_duplicate_groups: int
    duplicates_removed: int

    def as_dict(self) -> dict[str, int]:
        return {
            "raw_listings": self.raw_listings,
            "canonical_listings": self.canonical_listings,
            "cross_portal_groups": self.cross_portal_groups,
            "listings_in_duplicate_groups": self.listings_in_duplicate_groups,
            "duplicates_removed": self.duplicates_removed,
        }


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _row_to_schema(row: pd.Series) -> NormalizedListingSchema:
    listing_type = None
    if row.get("listing_type"):
        listing_type = ListingType(str(row["listing_type"]).lower())
    property_type = None
    if row.get("property_type"):
        try:
            property_type = PropertyType(str(row["property_type"]).upper())
        except ValueError:
            property_type = None
    return NormalizedListingSchema(
        source_website=str(row["source_website"]),
        source_listing_id=str(row["source_listing_id"]),
        original_url=str(row.get("original_url") or ""),
        listing_type=listing_type,
        property_type=property_type,
        sale_price=Decimal(str(row["sale_price"])) if pd.notna(row.get("sale_price")) else None,
        rent_price=Decimal(str(row["rent_price"])) if pd.notna(row.get("rent_price")) else None,
        currency=Currency.EUR,
        neighborhood_id=int(row["neighborhood_id"])
        if pd.notna(row.get("neighborhood_id"))
        else None,
        street_id=int(row["street_id"]) if pd.notna(row.get("street_id")) else None,
        building_id=int(row["building_id"]) if pd.notna(row.get("building_id")) else None,
        area_sqm=float(row["area_sqm"]) if pd.notna(row.get("area_sqm")) else None,
        bedrooms=int(row["bedrooms"]) if pd.notna(row.get("bedrooms")) else None,
        bathrooms=int(row["bathrooms"]) if pd.notna(row.get("bathrooms")) else None,
        confidence_score=float(row["confidence_score"])
        if pd.notna(row.get("confidence_score"))
        else None,
    )


def _source_rank(source: str) -> int:
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY)


def find_cross_portal_pairs(
    df: pd.DataFrame,
    *,
    threshold: float | None = None,
) -> list[tuple[int, int, float]]:
    """Return index pairs (i, j, confidence) for likely cross-portal duplicates."""
    if df.empty:
        return []
    scorer = DuplicateScorer(threshold=threshold or get_settings().dedup_fuzzy_threshold)
    blocks: dict[tuple[Any, ...], list[int]] = {}
    for idx, row in df.iterrows():
        key = coarse_block_key(row)
        if key is None:
            continue
        blocks.setdefault(key, []).append(int(idx))

    pairs: list[tuple[int, int, float]] = []
    for indices in blocks.values():
        if len(indices) < 2:
            continue
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                ia, ib = indices[i], indices[j]
                row_a = df.loc[ia]
                row_b = df.loc[ib]
                if row_a["source_website"] == row_b["source_website"]:
                    continue
                match = scorer.score(
                    _row_to_schema(row_a),
                    _row_to_schema(row_b),
                    candidate_id=ia,
                    reference_id=ib,
                )
                if match.is_likely_duplicate:
                    pairs.append((ia, ib, match.confidence))
    return pairs


def apply_cross_dedupe(
    df: pd.DataFrame,
    *,
    threshold: float | None = None,
) -> pd.DataFrame:
    """Tag rows with canonical groups and mark one primary listing per group."""
    if df.empty:
        return df.copy()

    work = df.reset_index(drop=True).copy()
    n = len(work)
    uf = _UnionFind(n)
    for ia, ib, _ in find_cross_portal_pairs(work, threshold=threshold):
        uf.union(ia, ib)

    roots = [uf.find(i) for i in range(n)]
    root_to_uuid: dict[int, str] = {}
    for root in set(roots):
        root_to_uuid[root] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"canonical:{root}"))

    work["canonical_group_id"] = [root_to_uuid[roots[i]] for i in range(n)]
    work["group_size"] = work.groupby("canonical_group_id")["canonical_group_id"].transform("count")

    primary_flags: list[bool] = [False] * n
    for _, group in work.groupby("canonical_group_id", sort=False):
        idxs = list(group.index)
        if len(idxs) == 1:
            primary_flags[idxs[0]] = True
            continue
        best = max(
            idxs,
            key=lambda i: (
                -_source_rank(str(work.at[i, "source_website"])),
                float(work.at[i, "confidence_score"] or 0),
                int(work.at[i, "normalized_id"]) if pd.notna(work.at[i, "normalized_id"]) else 0,
            ),
        )
        primary_flags[best] = True
    work["is_canonical_primary"] = primary_flags
    work["duplicate_sources"] = work.apply(
        lambda r: ", ".join(
            sorted(
                work.loc[work["canonical_group_id"] == r["canonical_group_id"], "source_website"]
                .astype(str)
                .unique()
            )
        ),
        axis=1,
    )
    return work


def canonical_corpus_dataframe(df: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
    """One row per cross-portal canonical unit (primary listings only)."""
    tagged = apply_cross_dedupe(df, **kwargs)
    return tagged[tagged["is_canonical_primary"]].copy()


def cross_dedup_stats(df: pd.DataFrame, *, threshold: float | None = None) -> CrossDedupStats:
    tagged = apply_cross_dedupe(df, threshold=threshold)
    raw = len(tagged)
    canonical = int(tagged["is_canonical_primary"].sum())
    dup_groups = int((tagged["group_size"] > 1).sum())
    groups_with_dupes = tagged[tagged["group_size"] > 1]["canonical_group_id"].nunique()
    return CrossDedupStats(
        raw_listings=raw,
        canonical_listings=canonical,
        cross_portal_groups=groups_with_dupes,
        listings_in_duplicate_groups=dup_groups,
        duplicates_removed=raw - canonical,
    )


def duplicate_groups_table(df: pd.DataFrame, *, threshold: float | None = None) -> pd.DataFrame:
    """Exportable register of cross-portal duplicate groups."""
    tagged = apply_cross_dedupe(df, threshold=threshold)
    multi = tagged[tagged["group_size"] > 1].copy()
    if multi.empty:
        return pd.DataFrame(
            columns=[
                "canonical_group_id",
                "group_size",
                "sources",
                "neighborhood",
                "listing_type",
                "area_sqm",
                "bedrooms",
                "listing_price",
                "source_website",
                "source_listing_id",
                "is_canonical_primary",
            ]
        )
    rows: list[dict[str, Any]] = []
    for group_id, group in multi.groupby("canonical_group_id", sort=False):
        sources = sorted(group["source_website"].astype(str).unique().tolist())
        for _, row in group.iterrows():
            rows.append(
                {
                    "canonical_group_id": group_id,
                    "group_size": int(row["group_size"]),
                    "sources": ", ".join(sources),
                    "neighborhood": row.get("neighborhood"),
                    "listing_type": row.get("listing_type"),
                    "area_sqm": row.get("area_sqm"),
                    "bedrooms": row.get("bedrooms"),
                    "listing_price": row.get("listing_price"),
                    "source_website": row.get("source_website"),
                    "source_listing_id": row.get("source_listing_id"),
                    "is_canonical_primary": bool(row.get("is_canonical_primary")),
                }
            )
    return pd.DataFrame(rows).sort_values(["group_size", "neighborhood"], ascending=[False, True])
