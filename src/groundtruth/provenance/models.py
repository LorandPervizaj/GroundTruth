"""Field-level provenance — trace every value to source evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceGrade = Literal["A", "B", "C", "D", "E"]

EVIDENCE_GRADE_MEANINGS: dict[str, str] = {
    "A": "manually verified",
    "B": "validated against benchmark",
    "C": "parser-derived with provenance",
    "D": "exploratory / insufficient n",
    "E": "hypothesis / interpretation",
}


@dataclass
class FieldProvenance:
    """Provenance for a single extracted field."""

    field: str
    value: Any
    parser_version: str
    rule_id: str
    source: str  # price_raw | title | description | listing_type_raw | ...
    source_snippet: str = ""
    source_offset: tuple[int, int] | None = None
    normalized_value: Any = None
    confidence_contribution: float = 0.0
    evidence_grade: EvidenceGrade = "C"

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": str(self.value) if self.value is not None else None,
            "parser_version": self.parser_version,
            "rule_id": self.rule_id,
            "source": self.source,
            "source_snippet": self.source_snippet,
            "source_offset": list(self.source_offset) if self.source_offset else None,
            "normalized_value": (
                str(self.normalized_value) if self.normalized_value is not None else None
            ),
            "confidence_contribution": round(self.confidence_contribution, 4),
            "evidence_grade": self.evidence_grade,
        }


@dataclass
class ProvenanceCollector:
    """Accumulates field provenance during parse/normalize."""

    parser_version: str
    fields: dict[str, FieldProvenance] = field(default_factory=dict)

    def record(
        self,
        field: str,
        value: Any,
        *,
        rule_id: str,
        source: str,
        source_text: str | None = None,
        match: re.Match[str] | None = None,
        normalized_value: Any = None,
        confidence_contribution: float = 0.0,
        evidence_grade: EvidenceGrade = "C",
    ) -> None:
        snippet = ""
        offset: tuple[int, int] | None = None
        if match and source_text:
            start, end = match.span()
            pad = 40
            snippet = source_text[max(0, start - pad) : min(len(source_text), end + pad)]
            offset = (start, end)
        elif source_text and value is not None:
            snippet = str(source_text)[:120]

        self.fields[field] = FieldProvenance(
            field=field,
            value=value,
            parser_version=self.parser_version,
            rule_id=rule_id,
            source=source,
            source_snippet=snippet.strip(),
            source_offset=offset,
            normalized_value=normalized_value if normalized_value is not None else value,
            confidence_contribution=confidence_contribution,
            evidence_grade=evidence_grade,
        )

    def to_dict(self) -> dict[str, Any]:
        return {name: prov.to_dict() for name, prov in self.fields.items()}
