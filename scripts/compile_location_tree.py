"""Compile prishtina_location_tree.yaml into districts.json and sync complexes."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GAZ = ROOT / "data" / "gazetteers"
YAML_PATH = GAZ / "draft" / "prishtina_location_tree.yaml"


def _district_entry(
    did: int,
    item: dict,
    neighborhood_slug: str,
) -> dict:
    aliases = list(item.get("aliases") or [])
    name = item["name"]
    return {
        "id": did,
        "name": name,
        "slug": item["slug"],
        "city": "Prishtina",
        "neighborhood_slug": neighborhood_slug,
        "aliases": aliases,
        "district_type": item.get("type", "district"),
    }


def _complex_entry(
    cid: int,
    item: dict,
    neighborhood_slug: str,
    district_slug: str | None = None,
) -> dict:
    return {
        "id": cid,
        "name": item["name"],
        "slug": item["slug"],
        "neighborhood_slug": neighborhood_slug,
        "district_slug": district_slug,
        "aliases": list(item.get("aliases") or []),
    }


def compile_tree() -> None:
    tree = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    districts: list[dict] = []
    complexes: list[dict] = []
    did = 1
    cid = 100

    for nh in tree["city"]["neighborhoods"]:
        nh_slug = nh["slug"]
        for item in nh.get("districts") or []:
            districts.append(_district_entry(did, item, nh_slug))
            did += 1
            for cx in item.get("complexes") or []:
                complexes.append(_complex_entry(cid, cx, nh_slug, item["slug"]))
                cid += 1
        for cx in nh.get("complexes_direct") or []:
            complexes.append(_complex_entry(cid, cx, nh_slug, None))
            cid += 1

    (GAZ / "districts.json").write_text(
        json.dumps(districts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    existing_path = GAZ / "complexes.json"
    existing = (
        json.loads(existing_path.read_text(encoding="utf-8")) if existing_path.exists() else []
    )
    by_slug = {row["slug"]: row for row in existing}
    for row in complexes:
        prev = by_slug.get(row["slug"], {})
        by_slug[row["slug"]] = {
            **prev,
            **row,
            "aliases": sorted(set([*(prev.get("aliases") or []), *row.get("aliases", [])])),
        }

    # Reparent key complexes per tree
    overrides = {
        "royal-mall": {"neighborhood_slug": "matiqan", "district_slug": "rruga-b"},
        "royal-city": {"neighborhood_slug": "spitali", "district_slug": None},
        "mati-2": {"neighborhood_slug": "matiqan", "district_slug": None},
    }
    for slug, patch in overrides.items():
        if slug in by_slug:
            by_slug[slug].update(patch)

    merged = sorted(by_slug.values(), key=lambda r: r.get("id", 9999))
    existing_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    nh_path = GAZ / "neighborhoods.json"
    neighborhoods = json.loads(nh_path.read_text(encoding="utf-8"))
    by_nh = {n["slug"]: n for n in neighborhoods}

    def ensure_nh(
        slug: str, name: str, *, lat: float, lng: float, aliases: list[str] | None = None
    ) -> None:
        if slug in by_nh:
            row = by_nh[slug]
            row["name"] = name
            row["city"] = "Prishtina"
            if aliases:
                row["aliases"] = sorted(set([*(row.get("aliases") or []), *aliases]))
            return
        new_id = max(n.get("id", 0) for n in neighborhoods) + 1
        row = {
            "id": new_id,
            "name": name,
            "slug": slug,
            "city": "Prishtina",
            "centroid_lat": lat,
            "centroid_lng": lng,
            "aliases": aliases or [],
        }
        neighborhoods.append(row)
        by_nh[slug] = row

    ensure_nh(
        "matiqan",
        "Matiqan",
        lat=42.6710,
        lng=21.1780,
        aliases=["Mati", "Matiçan", "Matican", "Matiqan"],
    )
    ensure_nh(
        "pejton-lakrishte",
        "Pejton / Lakrishte",
        lat=42.6670,
        lng=21.1700,
        aliases=["Pejton", "Lakrishte"],
    )
    ensure_nh("marigona-residence", "Marigona Residence", lat=42.6280, lng=21.1200)
    ensure_nh("marigona-hill", "Marigona Hill", lat=42.6260, lng=21.1180)
    ensure_nh("kolovice", "Kolovice", lat=42.6540, lng=21.1780, aliases=["Kolovica"])
    ensure_nh(
        "aktash-muhaxhere",
        "Aktash / Muhaxherë",
        lat=42.6720,
        lng=21.1680,
        aliases=["Muhaxherë", "Lagjja e Muhaxherve"],
    )
    ensure_nh(
        "llullat-dodona",
        "4 Lullat / Dodona",
        lat=42.6530,
        lng=21.1620,
        aliases=["Llullat", "4 Lullat"],
    )
    ensure_nh(
        "vranjevc-kodra-trimave",
        "Vranjevc / Kodra e Trimave",
        lat=42.6560,
        lng=21.1820,
        aliases=["Vranjevc"],
    )

    canonicals = {
        "mati": "matiqan",
        "mati-2": "matiqan",
        "mati-3": "matiqan",
        "matican": "matiqan",
        "pejton": "pejton-lakrishte",
        "lakrishte": "pejton-lakrishte",
        "aktash": "aktash-muhaxhere",
        "muhaxhere": "aktash-muhaxhere",
        "llullat": "llullat-dodona",
        "dodona": "llullat-dodona",
        "kodra-e-trimave": "vranjevc-kodra-trimave",
    }
    for slug, canonical in canonicals.items():
        if slug in by_nh:
            by_nh[slug]["canonical_slug"] = canonical

    if "hajvali" in by_nh:
        by_nh["hajvali"]["city"] = "Prishtina"

    nh_path.write_text(
        json.dumps(neighborhoods, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(districts)} districts, {len(merged)} complexes, {len(neighborhoods)} neighborhoods"
    )


if __name__ == "__main__":
    compile_tree()
