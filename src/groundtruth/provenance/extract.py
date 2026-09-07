"""Regex extraction helpers that return rule-level provenance metadata."""

from __future__ import annotations

import re
from collections.abc import Callable


def extract_by_rules(
    text: str | None,
    rules: list[tuple[str, str]],
    *,
    postprocess: Callable[[str, re.Match[str]], str | None] | None = None,
) -> tuple[str | None, re.Match[str] | None, str | None]:
    """
    Apply ordered regex rules; return (value, match, rule_id).

    First matching rule wins.
    """
    if not text:
        return None, None, None
    for rule_id, pattern in rules:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).strip()
        value = postprocess(raw, match) if postprocess else raw
        if value:
            return value, match, rule_id
    return None, None, None


def neighborhood_postprocess(raw: str, _match: re.Match[str]) -> str | None:
    """Strip nested lagjen prefix from neighborhood capture groups."""
    value = raw.strip()
    if "lagjen" in value.lower():
        sub = re.search(r"lagjen\s+(.+)", value, re.IGNORECASE)
        if sub:
            value = sub.group(1).strip()
    return value if len(value) > 2 else None
