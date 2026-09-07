"""Claim dependency graph — identify downstream impact of data or methodology changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from groundtruth.claims.registry import Claim, load_claims

ChangeKind = Literal["methodology", "parser", "dataset", "claim"]


@dataclass
class ImpactReport:
    """Claims that may need reevaluation after a change."""

    trigger: str
    kind: ChangeKind
    direct: list[Claim]
    transitive: list[Claim]

    @property
    def all_affected(self) -> list[Claim]:
        seen: set[str] = set()
        ordered: list[Claim] = []
        for claim in self.direct + self.transitive:
            if claim.claim_id not in seen:
                seen.add(claim.claim_id)
                ordered.append(claim)
        return ordered


def parse_depends_on(claim: Claim) -> list[str]:
    """Semicolon-separated parent claim IDs."""
    return [part.strip() for part in claim.depends_on.split(";") if part.strip()]


def dependency_ancestors(claim_id: str, claims: list[Claim] | None = None) -> list[Claim]:
    """Walk depends_on upward — GT-005 → GT-002 → …"""
    claims = claims or load_claims()
    by_id = {c.claim_id: c for c in claims}
    visited: set[str] = set()
    chain: list[Claim] = []

    def walk(cid: str) -> None:
        if cid in visited:
            return
        visited.add(cid)
        claim = by_id.get(cid)
        if claim is None:
            return
        chain.append(claim)
        for parent in parse_depends_on(claim):
            walk(parent)

    walk(claim_id)
    return chain


def dependency_descendants(claim_id: str, claims: list[Claim] | None = None) -> list[Claim]:
    """Claims that transitively depend on claim_id."""
    claims = claims or load_claims()
    children: dict[str, list[str]] = {}
    for claim in claims:
        for parent in parse_depends_on(claim):
            children.setdefault(parent, []).append(claim.claim_id)

    visited: set[str] = set()
    result: list[Claim] = []
    by_id = {c.claim_id: c for c in claims}

    def walk(cid: str) -> None:
        for child_id in children.get(cid, []):
            if child_id in visited:
                continue
            visited.add(child_id)
            child = by_id.get(child_id)
            if child:
                result.append(child)
                walk(child_id)

    walk(claim_id)
    return result


def impacted_claims(
    *,
    methodology_version: str | None = None,
    parser_version: str | None = None,
    dataset_hash: str | None = None,
    parent_claim_id: str | None = None,
    claims: list[Claim] | None = None,
) -> ImpactReport:
    """
    Find claims requiring reevaluation when an upstream artifact changes.

    Matches claims that pin the given version/hash, plus all transitive dependents.
    """
    claims = claims or load_claims()
    active = [c for c in claims if c.status not in ("superseded", "retracted")]

    if parent_claim_id:
        trigger = f"claim:{parent_claim_id}"
        kind: ChangeKind = "claim"
        direct = dependency_descendants(parent_claim_id, claims)
    elif methodology_version:
        trigger = f"methodology:{methodology_version}"
        kind = "methodology"
        direct = [c for c in active if c.methodology_version == methodology_version]
    elif parser_version:
        trigger = f"parser:{parser_version}"
        kind = "parser"
        direct = [c for c in active if c.parser_version == parser_version]
    elif dataset_hash:
        trigger = f"dataset:{dataset_hash[:12]}…"
        kind = "dataset"
        direct = [c for c in active if c.dataset_hash == dataset_hash]
    else:
        raise ValueError(
            "Specify methodology_version, parser_version, dataset_hash, or parent_claim_id"
        )

    transitive_ids: set[str] = {c.claim_id for c in direct}
    transitive: list[Claim] = []
    for claim in direct:
        for desc in dependency_descendants(claim.claim_id, claims):
            if desc.claim_id not in transitive_ids:
                transitive_ids.add(desc.claim_id)
                transitive.append(desc)

    return ImpactReport(trigger=trigger, kind=kind, direct=direct, transitive=transitive)


def validate_dependencies(claims: list[Claim] | None = None) -> list[str]:
    """Return human-readable errors for broken depends_on references."""
    claims = claims or load_claims()
    ids = {c.claim_id for c in claims}
    errors: list[str] = []
    for claim in claims:
        for parent in parse_depends_on(claim):
            if parent not in ids:
                errors.append(f"{claim.claim_id} depends on missing {parent}")
    return errors
