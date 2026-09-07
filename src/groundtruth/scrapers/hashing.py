"""Stable content hashing for raw listing payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_payload_text(payload: dict[str, Any] | None) -> str:
    """Serialize a payload with sorted keys for stable hashing."""
    if not payload:
        return ""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(*, raw_payload: dict[str, Any] | None = None, raw_html: str | None = None) -> str:
    """SHA-256 over canonical JSON payload plus raw HTML."""
    content = canonical_payload_text(raw_payload) + (raw_html or "")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
