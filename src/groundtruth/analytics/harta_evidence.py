"""Purpose-specific Harta evidence without promoting quarantine into valuations."""

from decimal import Decimal

from groundtruth.schemas.pipeline import ParsedListingSchema


def classify_harta_evidence(
    parsed: ParsedListingSchema, *, validation_error_codes: list[str] | None = None
) -> dict:
    """Caller supplies the complete pipeline outcome; None means not validated.

    This projection does not update corpus membership, dedup priority or weights.
    A source address/pin is matching evidence, never independent verification.
    """
    if parsed.source_website != "harta":
        raise ValueError("Harta evidence requires a Harta parsed record")
    extra = parsed.extra_fields
    errors = sorted(
        set(validation_error_codes or []) | set(extra.get("source_validation_issues", []))
    )
    validated = validation_error_codes is not None
    valuation = validated and not errors and parsed.area_sqm is not None
    street = parsed.street_raw
    address = extra.get("address_raw")
    location = bool(street or address)
    price = parsed.rent_price if parsed.listing_type == "rent" else parsed.sale_price
    gross = extra.get("gross_area_raw")
    gross = Decimal(gross) if gross else None
    gross_candidate = bool(
        validated
        and not (set(errors) - {"harta_missing_interior_area"})
        and gross
        and 15 <= gross <= 1000
        and price
        and price > 0
    )
    return {
        "source": "harta",
        "source_listing_id": parsed.source_listing_id,
        "source_url": parsed.original_url,
        "raw_listing_id": parsed.raw_listing_id,
        "scrape_run_id": parsed.scrape_run_id,
        "parser_version": parsed.parser_version,
        "pipeline_validation_observed": validated,
        "validation_errors": errors,
        "valuation_eligible": bool(valuation),
        "use_class": "valuation_candidate"
        if valuation
        else "location_evidence_only"
        if location
        else "identity_evidence_only",
        "identity_matching_candidate": True,
        "location_matching_candidate": location,
        "location_verification_status": "unverified_source_assertion",
        "municipality": parsed.city,
        "address_raw": address,
        "street_raw": street,
        "neighborhood_raw": parsed.neighborhood_raw,
        "location_provenance": extra.get("location_evidence"),
        "coordinates": [extra.get("latitude"), extra.get("longitude")],
        "coordinate_provenance": extra.get("coordinate_provenance"),
        "interior_area_sqm": parsed.area_sqm,
        "interior_area_basis": extra.get("area_basis"),
        "surface_area_raw": extra.get("surface_area_raw"),
        "surface_area_basis": extra.get("surface_area_basis", "unspecified"),
        "gross_area_research": {
            "candidate": gross_candidate,
            "area_sqm": str(gross) if gross else None,
            "asking_price_per_gross_sqm": str((price / gross).quantize(Decimal("0.01")))
            if gross_candidate
            else None,
            "basis": "source_description_explicit_gross" if gross else None,
            "validated_for_pooled_statistics": False,
        },
    }
