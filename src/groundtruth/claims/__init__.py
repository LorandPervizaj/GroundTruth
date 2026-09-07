"""Claim registry — immutable research artifacts."""

from groundtruth.claims.graph import (
    dependency_ancestors,
    dependency_descendants,
    impacted_claims,
    parse_depends_on,
    validate_dependencies,
)
from groundtruth.claims.hashes import (
    dataset_fingerprint,
    raw_crawl_fingerprint,
    reproducibility_tuple,
    sha256_file,
    sha256_sql,
)
from groundtruth.claims.registry import (
    Claim,
    active_claims,
    get_claim,
    load_claims,
    next_claim_id,
    register_claim,
    supersede_claim,
)

__all__ = [
    "Claim",
    "active_claims",
    "dataset_fingerprint",
    "dependency_ancestors",
    "dependency_descendants",
    "get_claim",
    "impacted_claims",
    "load_claims",
    "next_claim_id",
    "parse_depends_on",
    "raw_crawl_fingerprint",
    "register_claim",
    "reproducibility_tuple",
    "sha256_file",
    "sha256_sql",
    "supersede_claim",
    "validate_dependencies",
]
