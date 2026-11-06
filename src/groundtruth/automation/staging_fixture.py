"""Deterministic synthetic release and allowlisted Docker context; no corpus reads."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from groundtruth.automation.deployment import SHA, require
from groundtruth.schemas.lookup import MarketLookup, MarketPulse

STAMP = "2026-01-01T00:00:00+00:00"
PROHIBITED = (
    "stmetrikbetalgy2mu",
    "ca-metrik-api",
    "acrmetrikbetalgy2mu",
    "2026-W43-saved-oct18",
    "rg-metrik-beta-eus2",
    "7702035686450352163",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def no_production(value) -> None:
    text = json.dumps(value).lower()
    require(
        not any(marker.lower() in text for marker in PROHIBITED),
        "Production reference in staging input",
    )


def generate(root: Path, source_sha: str) -> dict:
    require(bool(SHA.fullmatch(source_sha)), "Full synthetic source SHA required")
    require(not root.exists() or not any(root.iterdir()), "Synthetic destination must be empty")
    root.mkdir(parents=True, exist_ok=True)
    base = root / "reports/generated/lookup_cache"
    release = "synthetic-stage-" + source_sha[:12]
    entries, markets, listings, yields = [], [], [], []
    for index, slug in enumerate(("ulpiana", "arberia"), 1):
        # Slugs exercise existing read contracts; every listing/address is invented.
        name = f"Synthetic {slug.title()}"
        recent = []
        for kind, price in (("sale", 100000 + index * 10000), ("rent", 500 + index * 50)):
            for sample in range(6):
                listing = {
                    "source": "synthetic",
                    "source_listing_id": f"synthetic-{index}-{kind}-{sample}",
                    "url": f"https://synthetic.invalid/{index}/{kind}/{sample}",
                    "listing_type": kind,
                    "property_type": "apartment",
                    "price_eur": price,
                    "price_per_sqm_eur": price / 100,
                    "area_sqm": 100,
                    "bedrooms": 2,
                }
                recent.append(listing)
                listings.append(
                    {
                        **listing,
                        "neighborhood_id": index,
                        "neighborhood_name": name,
                        "address": f"Imaginary Street {index}, Test City",
                        "contact": f"fixture-{index}@example.invalid",
                    }
                )
        payload = MarketLookup(
            entity_type="neighborhood",
            slug=slug,
            display_name=name,
            city="Synthetic Test City",
            total_listings=12,
            corpus_updated_at=STAMP,
            pulse=MarketPulse(
                active_listings=12,
                observations=12,
                median_sale_eur=recent[0]["price_eur"],
                median_rent_eur=recent[6]["price_eur"],
            ),
            recent_listings=recent,
        ).model_dump(mode="json")
        path = base / f"neighborhood/{slug}.json"
        write_json(path, payload)
        entries.append(
            {
                "entity_type": "neighborhood",
                "slug": slug,
                "path": f"neighborhood/{slug}.json",
                "sha256": digest(path),
            }
        )
        markets.append(
            {
                "slug": slug,
                "name": name,
                "sale_listings": 6,
                "rent_listings": 6,
                "listings": 12,
                "estimate_ready": False,
            }
        )
        yields.append(
            {
                "slug": slug,
                "neighborhood_name": name,
                "neighborhood_id": index,
                "median_sale_eur": recent[0]["price_eur"],
                "median_rent_eur": recent[6]["price_eur"],
                "gross_yield_pct": 6.0,
                "rent_listings": 6,
                "sale_listings": 6,
                "estimate_ready": False,
            }
        )
    write_json(root / "synthetic/listings.json", listings)
    write_json(root / "synthetic/product_submissions.json", [])
    write_json(
        root / "synthetic/expected.json",
        {
            "release_id": release,
            "active_listings": 24,
            "search_slugs": [m["slug"] for m in markets],
            "gross_yield_pct": 6.0,
            "sale_total": 1380000,
            "rent_total_monthly": 6900,
            "submissions": 0,
        },
    )
    hashes = {}
    for kind in ("rent", "sale"):
        frame = pd.DataFrame(
            [
                {
                    **x,
                    "rent_price": x["price_eur"],
                    "sale_price": x["price_eur"],
                    "is_commercial": False,
                    "source_website": "synthetic",
                }
                for x in listings
                if x["listing_type"] == kind
            ]
        )
        target = base / f"{kind}_comparables.json.gz"
        target.write_bytes(
            gzip.compress(frame.to_json(orient="table", date_format="iso").encode(), mtime=0)
        )
        hashes[target.name] = digest(target)
    write_json(
        base / "comparables_meta.json", {"corpus_revision": STAMP, "rent_rows": 12, "sale_rows": 12}
    )
    hashes["comparables_meta.json"] = digest(base / "comparables_meta.json")
    write_json(
        base / "_qa/details.json",
        {"synthetic": True, "listing_count": 24, "price_checks_passed": True},
    )
    annual = root / "data/api/annual_report.json"
    write_json(
        annual,
        {
            "generated_at": STAMP,
            "total_listings": 24,
            "kpis": {"active_listings": 24},
            "volume": {"labels": ["2026-01"], "sale": [12], "rent": [12]},
            "synthetic": True,
        },
    )
    rent = root / "data/api/rent_yield.json"
    write_json(rent, {"rows": yields})
    manifest = {
        "synthetic": True,
        "built_at": STAMP,
        "corpus_revision": STAMP,
        "dataset_version": "synthetic-v1",
        "entry_count": 2,
        "entries": entries,
        "markets": markets,
        "corpus_meta": {
            "active_listings": 24,
            "raw_listings": 24,
            "corpus_updated_at": STAMP,
            "data_sources": ["synthetic"],
            "source_count": 1,
        },
        "artifact_hashes": hashes,
        "related_artifacts": {
            "annual_report": {"sha256": digest(annual)},
            "rent_yield": {"sha256": digest(rent)},
        },
        "statistical_qa": {
            "status": "PASS",
            "details": "_qa/details.json",
            "details_sha256": digest(base / "_qa/details.json"),
        },
        "release": {
            "release_id": release,
            "generated_at": STAMP,
            "data_through": "2026-01-01",
            "source_git_sha": source_sha,
            "qa_decision": "SYNTHETIC_PASS",
        },
    }
    write_json(base / "manifest.json", manifest)
    for folder in (
        "data/claims",
        "data/datasets",
        "data/product",
        "data/gazetteers",
        "reports/templates",
    ):
        write_json(root / folder / "synthetic.json", {"synthetic": True})
    write_json(
        root / "data/gazetteers/neighborhoods.json",
        [
            {"id": i, "name": m["name"], "slug": m["slug"], "city": "Synthetic Test City"}
            for i, m in enumerate(markets, 1)
        ],
    )
    write_json(root / "data/gazetteers/streets.json", [])
    inventory = {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}
    write_json(root / "synthetic-inventory.json", inventory)
    verify(root)
    return manifest


def verify(root: Path) -> dict:
    inventory = json.loads((root / "synthetic-inventory.json").read_text())
    require(isinstance(inventory, dict) and bool(inventory), "Missing synthetic inventory")
    for name, expected in inventory.items():
        path = root / name
        require(
            path.resolve().is_relative_to(root.resolve())
            and path.is_file()
            and not path.is_symlink(),
            "Unsafe synthetic path",
        )
        require(digest(path) == expected, "Synthetic checksum differs")
        if path.suffix == ".json":
            no_production(json.loads(path.read_text()))
        elif path.name.endswith(".json.gz"):
            no_production(json.loads(gzip.decompress(path.read_bytes())))
    require(
        set(inventory)
        == {
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).as_posix() != "synthetic-inventory.json"
        },
        "Unexpected synthetic file",
    )
    require(
        json.loads((root / "synthetic/product_submissions.json").read_text()) == [],
        "Synthetic submissions must be empty",
    )
    manifest = json.loads((root / "reports/generated/lookup_cache/manifest.json").read_text())
    require(
        manifest.get("synthetic") is True
        and manifest["release"]["release_id"].startswith("synthetic-stage-"),
        "Synthetic release required",
    )
    return manifest


def build_context(source: Path, fixture: Path, destination: Path) -> dict:
    """Copy only source-controlled runtime code; never copy source data/reports."""
    verify(fixture)
    require(not destination.exists(), "Build context already exists")
    shutil.copytree(fixture, destination)
    sha = verify(fixture)["release"]["source_git_sha"]
    allowed = (
        "src",
        "web",
        "alembic",
        "Dockerfile",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "alembic.ini",
        "scripts/docker-entrypoint.sh",
    )
    # Read immutable Git blobs, never dirty/untracked working files or symlink targets.
    listing = subprocess.check_output(
        ["git", "-C", str(source), "ls-tree", "-rz", sha, "--", *allowed]
    )
    for record in listing.split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        require(metadata.startswith(b"100"), "Only regular source blobs permitted")
        name = raw_name.decode()
        require(
            ".env" not in Path(name).name and ".." not in Path(name).parts, "Unsafe context path"
        )
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            subprocess.check_output(["git", "-C", str(source), "show", f"{sha}:{name}"])
        )
    write_json(destination / "web/static/home-trust.json", {"synthetic": True, "listings": 24})
    inventory = {
        p.relative_to(destination).as_posix(): digest(p)
        for p in destination.rglob("*")
        if p.is_file()
    }
    write_json(destination / "context-inventory.json", inventory)
    return inventory
