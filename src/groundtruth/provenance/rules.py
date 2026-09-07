"""Stable rule identifiers for field-level provenance — ontology separate from code paths."""

# Neighborhood title patterns (NH-Txx)
NH_TITLE_RULES: list[tuple[str, str]] = [
    ("NH-T01", r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9\s]+),\s*rrug"),
    ("NH-T02", r"(?:ne|në)\s+lagjen\s+e\s+(.+)"),
    ("NH-T03", r"(?:ne|në)\s+lagjen\s+(.+)"),
    ("NH-T04", r"(?:ne|në)\s+[Ll]agje\s+te\s+(.+)"),
    ("NH-T05", r"me\s+qira\s+(?:ne|në)\s+(.+)"),
    ("NH-T06", r"me\s+qira\s+te\s+(.+)"),
    ("NH-T07", r"me\s+qera\s+(.+?)(?:\s*$|_)"),
    ("NH-T08", r"leshohet\s+me\s+qira\s+(?:banesa\s+)?(?:ne|në|te)\s+(.+)"),
    ("NH-T09", r"leshohet\s+me\s+qira\s+banesa\s+te\s+(.+)"),
    ("NH-T10", r"(?:ne|në)\s+[Ss]hitje\s+(?:ne|në\s+)?(.+)"),
    ("NH-T11", r"ne\s+shitje\s+te\s+(.+)"),
    ("NH-T12", r"shitet\s+banese\s+te\s+(.+)"),
    ("NH-T13", r"shitet\s+banesa\s+te\s+(.+)"),
    ("NH-T14", r"shitet\s+banesa\s+ne\s+(?:lagjen\s+)?(.+)"),
    ("NH-T15", r"(?i)shitet.*?ne\s+(.+)"),
    ("NH-T16", r"(?:me\s+qira|shitje)\s+te\s+(.+)"),
    ("NH-T17", r"ne\s+shitje\s+ne\s+(.+)"),
    ("NH-T18", r"te\s+(Prishtina e Re|Prishtine e Re|Prishtina e re)"),
    ("NH-T19", r"(?:me\s+qira|shpallje)\s+(?:ne|në)\s+(.+)"),
    ("NH-T20", r"me\s+qira\s+(.+?)(?:\s*$|_)"),
    ("NH-T21", r"(?:ne|në)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]+?)(?:\s*/|\s*$)"),
]

NH_DESCRIPTION_RULES: list[tuple[str, str]] = [
    ("NH-D01", r"leshohet\s+me\s+qira\s+banesa\s+(?:ne|në|te)\s+([A-Za-zÀ-ÿ0-9\s]+)"),
    ("NH-D02", r"me\s+qira\s+(?:banesa\s+)?(?:ne|në|te)\s+([A-Za-zÀ-ÿ0-9\s]+)"),
    ("NH-D03", r"(?:ne|në)\s+lagjen\s+e\s+([A-Za-zÀ-ÿ0-9\s]+)"),
    ("NH-D04", r"(?:ne|në)\s+lagjen\s+([A-Za-zÀ-ÿ0-9\s]+)"),
    ("NH-D05", r"(?:ne|në)\s+lagje\s+te\s+([A-Za-zÀ-ÿ0-9\s]+)"),
]

# Price rules
PRICE_STRUCTURED = "PRICE-001"
PRICE_DESC_FALLBACK = "PRICE-002"
PRICE_PLACEHOLDER_OVERRIDE = "PRICE-003"
PRICE_SALE_SHORTHAND = "PRICE-004"
PRICE_SALE_DESC_FALLBACK = "PRICE-005"

# Area rules
AREA_STRUCTURED = "AREA-001"
AREA_DESC_FALLBACK = "AREA-002"
AREA_REJECT_PLACEHOLDER = "AREA-003"

# Listing type
TYPE_RAW_FIELD = "TYPE-001"
TYPE_TITLE_INFER = "TYPE-002"

# Normalization (applied in NormalizationService)
NORM_NH_EXACT = "NORM-NH-001"
NORM_NH_ALIAS = "NORM-NH-002"
NORM_NH_FUZZY = "NORM-NH-003"
NORM_STREET_FALLBACK = "NORM-NH-004"
NORM_COMPLEX_FALLBACK = "NORM-NH-005"

# Text extractor fallback
NH_TEXT_EXTRACT = "NH-E01"

# MerrJep — price / area / type (MJ-*)
MJ_PRICE_LDJSON = "MJ-PRICE-001"
MJ_PRICE_DESC = "MJ-PRICE-002"
MJ_PRICE_TITLE = "MJ-PRICE-003"
MJ_PRICE_ZERO_OVERRIDE = "MJ-PRICE-004"
MJ_PRICE_PER_SQM = "MJ-PRICE-005"
MJ_PRICE_HTML = "MJ-PRICE-006"

MJ_AREA_DESC = "MJ-AREA-001"
MJ_AREA_TITLE = "MJ-AREA-002"

MJ_TYPE_NAME = "MJ-TYPE-001"
MJ_TYPE_DESC = "MJ-TYPE-002"

MJ_NH_GAZETTEER = "MJ-NH-001"
MJ_NH_COMPLEX = "MJ-NH-002"
MJ_NH_STREET = "MJ-NH-003"
MJ_NH_REGEX = "MJ-NH-004"

MJ_BED_TEXT = "MJ-BED-001"
MJ_BED_RAW = "MJ-BED-002"
