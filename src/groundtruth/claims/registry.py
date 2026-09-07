"""Immutable claim registry — the API for truth."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from groundtruth.config import PROJECT_ROOT
from groundtruth.methodology.version import METHODOLOGY_VERSION

REGISTRY_PATH = PROJECT_ROOT / "data" / "claims" / "registry.csv"

ClaimType = Literal["fact", "interpretation", "negative", "method"]
ClaimStructure = Literal["descriptive", "structural", "method"]
ClaimStatus = Literal["draft", "reviewed", "published", "superseded", "retracted"]

MaturityLevel = Literal["M0", "M1", "M2", "M3", "M4"]
ImpactLevel = Literal["very_low", "low", "medium", "high", "very_high"]

FIELDNAMES = [
    "claim_id",
    "statement",
    "claim_type",
    "claim_structure",
    "half_life",
    "evidence_grade",
    "causal_level",
    "maturity",
    "impact",
    "retest_interval",
    "research_hours",
    "estimate",
    "lower_ci",
    "upper_ci",
    "confidence_level",
    "depends_on",
    "observation_date",
    "etl_run_id",
    "etl_date",
    "etl_version",
    "raw_crawl_hash",
    "parser_version",
    "methodology_version",
    "notebook_path",
    "notebook_hash",
    "query_path",
    "sql_hash",
    "dataset_hash",
    "n",
    "reviewer",
    "status",
    "superseded_by",
    "created_at",
    "notes",
]


EvidenceGrade = Literal["A", "B", "C", "D", "E"]
CausalLevel = Literal["C0", "C1", "C2", "C3"]

CAUSAL_LEVEL_MEANINGS: dict[str, str] = {
    "C0": "descriptive only",
    "C1": "adjusted association",
    "C2": "quasi-experimental",
    "C3": "replicated intervention evidence",
}


@dataclass
class Claim:
    claim_id: str
    statement: str
    claim_type: ClaimType = "fact"
    claim_structure: ClaimStructure = "descriptive"
    half_life: str = ""
    evidence_grade: EvidenceGrade = "C"
    causal_level: CausalLevel = "C0"
    maturity: MaturityLevel = "M0"
    impact: ImpactLevel = "medium"
    retest_interval: str = ""
    research_hours: str = ""
    estimate: str = ""
    lower_ci: str = ""
    upper_ci: str = ""
    confidence_level: str = ""
    depends_on: str = ""
    observation_date: str = ""
    etl_run_id: str = ""
    etl_date: str = ""
    etl_version: str = ""
    raw_crawl_hash: str = ""
    parser_version: str = ""
    methodology_version: str = METHODOLOGY_VERSION
    notebook_path: str = ""
    notebook_hash: str = ""
    query_path: str = ""
    sql_hash: str = ""
    dataset_hash: str = ""
    n: str = ""
    reviewer: str = ""
    status: ClaimStatus = "draft"
    superseded_by: str = ""
    created_at: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str]:
        return {k: str(getattr(self, k) or "") for k in FIELDNAMES}

    def to_api_dict(self) -> dict[str, Any]:
        """Structured claim for machine reasoning (not RAG over prose)."""
        trace = self.to_reasoning_trace()
        return {**trace, "statement": self.statement, "claim_type": self.claim_type}

    def to_reasoning_trace(self, *, policy_id: str | None = None) -> dict[str, Any]:
        """Graph-friendly trace for downstream agents — not an isolated fact string."""
        estimate = float(self.estimate) if self.estimate else None
        lower = float(self.lower_ci) if self.lower_ci else None
        upper = float(self.upper_ci) if self.upper_ci else None
        deps = [x.strip() for x in self.depends_on.split(";") if x.strip()]
        return {
            "claim": self.claim_id,
            "depends_on": deps,
            "evidence": self.evidence_grade,
            "causal": self.causal_level,
            "maturity": self.maturity,
            "structure": self.claim_structure,
            "policy": policy_id,
            "estimate": estimate,
            "uncertainty": {"lower": lower, "upper": upper}
            if lower is not None and upper is not None
            else None,
            "retest": self.retest_interval or self.half_life or None,
            "n": int(self.n) if self.n.isdigit() else self.n or None,
            "methodology_version": self.methodology_version,
            "status": self.status,
        }

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Claim:
        data = {k: row.get(k, "") or "" for k in FIELDNAMES}
        return cls(**data)  # type: ignore[arg-type]


def load_claims(path: Path | None = None) -> list[Claim]:
    path = path or REGISTRY_PATH
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [Claim.from_row(row) for row in csv.DictReader(fh)]


def _write_claims(claims: list[Claim], path: Path | None = None) -> None:
    path = path or REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for claim in claims:
            writer.writerow(claim.to_row())


def next_claim_id(claims: list[Claim] | None = None) -> str:
    claims = claims or load_claims()
    numbers = []
    for claim in claims:
        if claim.claim_id.startswith("GT-"):
            try:
                numbers.append(int(claim.claim_id.split("-", 1)[1]))
            except ValueError:
                continue
    return f"GT-{max(numbers, default=-1) + 1:03d}"


def get_claim(claim_id: str, claims: list[Claim] | None = None) -> Claim | None:
    claims = claims or load_claims()
    for claim in claims:
        if claim.claim_id == claim_id:
            return claim
    return None


def register_claim(claim: Claim, *, path: Path | None = None) -> Claim:
    """Append a new claim. Never overwrite existing claim_id."""
    claims = load_claims(path)
    if get_claim(claim.claim_id, claims):
        raise ValueError(f"Claim {claim.claim_id} already exists — use supersede_claim()")
    if not claim.created_at:
        claim.created_at = datetime.now(UTC).isoformat()
    if not claim.methodology_version:
        claim.methodology_version = METHODOLOGY_VERSION
    claims.append(claim)
    _write_claims(claims, path)
    return claim


def supersede_claim(
    old_id: str,
    new_claim: Claim,
    *,
    path: Path | None = None,
) -> Claim:
    """
    Mark old claim as superseded; register new claim with fresh ID.

    Historical claims remain immutable.
    """
    claims = load_claims(path)
    old = get_claim(old_id, claims)
    if old is None:
        raise ValueError(f"Claim {old_id} not found")
    if old.status == "superseded":
        raise ValueError(f"Claim {old_id} is already superseded by {old.superseded_by}")

    if not new_claim.claim_id or new_claim.claim_id == old_id:
        new_claim.claim_id = next_claim_id(claims)

    if not new_claim.created_at:
        new_claim.created_at = datetime.now(UTC).isoformat()
    if not new_claim.methodology_version:
        new_claim.methodology_version = METHODOLOGY_VERSION

    for i, claim in enumerate(claims):
        if claim.claim_id == old_id:
            claims[i] = Claim(
                **{
                    **claim.to_row(),
                    "status": "superseded",
                    "superseded_by": new_claim.claim_id,
                }
            )
            break

    if get_claim(new_claim.claim_id, claims):
        raise ValueError(f"Claim {new_claim.claim_id} already exists")
    claims.append(new_claim)
    _write_claims(claims, path)
    return new_claim


def active_claims(claims: list[Claim] | None = None) -> list[Claim]:
    """Claims that are not superseded or retracted."""
    claims = claims or load_claims()
    return [c for c in claims if c.status not in ("superseded", "retracted")]
