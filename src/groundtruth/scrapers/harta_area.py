"""Labelled source area assertions, never a gross-to-interior conversion."""

from __future__ import annotations

import re
import unicodedata

_MEASUREMENT = re.compile(
    r"(?<![\d.,])(?P<value>\d+(?:[.,]\d+)*)\s*"
    r"(?:m\s*(?:²|2|\^2|/\s*2)|㎡|sqm\b|metra\s+katror[ëe]?\b)(?!\d)",
    re.I,
)
_CONCEPTS = (
    ("nonliving_component", r"\b(?:garazh\w*|garage|parking|storage|depo|toke|oborr|garden)\b"),
    ("terrace", r"\b(?:terase|terrace|ballkon|balcony)\b"),
    ("gross", r"\b(?:bruto|gross)\b"),
    ("net", r"\b(?:neto|net)\b"),
    ("interior", r"\b(?:interior|living\s+area|(?:hapesire|siperfaqe)\s+banimi)\b"),
    ("total", r"\b(?:totale?|total\s+area)\b"),
    ("reported_actual", r"\bfaktike\b"),
)


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )


def extract_area_facts(text: str) -> list[dict[str, str]]:
    """Retain numeric facts and fixed labels only, excluding free text/contacts.

    A suffix label must immediately follow the measurement. Prefixes cannot cross
    another measurement or a clause boundary. Unqualified m² stays unspecified.
    Net and interior are source claims; neither is independent measurement.
    """
    # HTML/plain descriptions sometimes join a place-name sentence to an area.
    # Split a letter-period-number boundary without rewriting decimal numbers.
    text = re.sub(r"(?<=[^\W\d_])\.(?=\d)", ". ", text)
    facts = []
    previous_end = 0
    for match in _MEASUREMENT.finditer(text):
        prefix = text[max(previous_end, match.start() - 70) : match.start()]
        prefix = re.split(r"[\n;|!?+]", prefix)[-1]
        prefix = _fold(prefix)
        suffix = _fold(text[match.end() : match.end() + 35])
        suffix = re.split(r"[\n;|!?+,]", suffix)[0]
        # Only an immediately adjacent label, optionally parenthesized, can be
        # a suffix; later mentions may describe a different part of the property.
        immediate = re.match(
            r"\s*\(?\s*(bruto|gross|neto|net\b|interior|living\s+area|"
            r"(?:hapesire|siperfaqe)\s+banimi|terase|terrace|ballkon|balcony|totale?|faktike|"
            r"garazh\w*|garage|parking|storage|depo|toke|oborr|garden)\b",
            suffix,
        )
        labels = [concept for concept, pattern in _CONCEPTS if re.search(pattern, prefix)]
        if immediate:
            labels.extend(
                concept for concept, pattern in _CONCEPTS if re.search(pattern, immediate.group(1))
            )
        unique = set(labels)
        if re.search(r"(?:\d\s*[-–—]|[-−~])\s*$", prefix):
            unique.add("uncertain_measurement")
        if re.search(r"\b(?:jo|nuk|not|rreth|approximately|about)\b", prefix):
            unique.add("uncertain_measurement")
        concept = (
            next(iter(unique)) if len(unique) == 1 else "ambiguous" if unique else "unspecified"
        )
        fact = {
            "concept": concept,
            "value_raw": match.group("value"),
            "unit": "m2",
            "origin": "description",
        }
        if fact not in facts:
            facts.append(fact)
        previous_end = match.end()
    return facts
