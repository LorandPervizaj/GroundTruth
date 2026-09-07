"""Validation rules for normalized listings — quarantine garbage at ingest, never delete."""

from decimal import Decimal

from groundtruth.models.enums import ListingType, PropertyType
from groundtruth.processing.extractors.property_type import HOUSE_MIN_AREA_SQM
from groundtruth.schemas.etl import ValidationIssue, ValidationResult
from groundtruth.schemas.pipeline import NormalizedListingSchema

# Area
MIN_AREA_SQM = 15.0
MAX_AREA_SQM = 1000.0

# Total price (EUR)
MIN_SALE_PRICE = Decimal("3000")
MAX_SALE_PRICE = Decimal("10000000")
MIN_RENT_PRICE = Decimal("50")
MAX_RENT_PRICE = Decimal("8000")

# €/m² — Prishtina residential sanity band (asking prices)
MIN_RENT_PRICE_PER_SQM = Decimal("3")
MAX_RENT_PRICE_PER_SQM = Decimal("15")
MIN_SALE_PRICE_PER_SQM = Decimal("500")
MAX_SALE_PRICE_PER_SQM = Decimal("15000")

# Cross-field consistency
MAX_PRICE_PER_SQM_REL_ERROR = Decimal("0.20")

# Mislabeled listing type (total price looks like the wrong market)
LIKELY_RENT_AS_SALE_MAX_TOTAL = Decimal("20000")
LIKELY_RENT_AS_SALE_MAX_IMPLIED_PSM = Decimal("400")

# Backward-compatible alias
MIN_PRICE_PER_SQM = MIN_SALE_PRICE_PER_SQM
MAX_PRICE_PER_SQM = MAX_SALE_PRICE_PER_SQM


class ListingValidator:
    """Apply business rules to normalized listings."""

    def validate(self, listing: NormalizedListingSchema) -> ValidationResult:
        issues: list[ValidationIssue] = []

        if listing.listing_type == ListingType.SALE and listing.sale_price is not None:
            self._check_price_range(
                issues,
                listing.sale_price,
                MIN_SALE_PRICE,
                MAX_SALE_PRICE,
            )
        elif listing.listing_type == ListingType.RENT and listing.rent_price is not None:
            self._check_price_range(
                issues,
                listing.rent_price,
                MIN_RENT_PRICE,
                MAX_RENT_PRICE,
                rent=True,
            )

        if listing.area_sqm is not None:
            if listing.area_sqm < MIN_AREA_SQM:
                issues.append(
                    ValidationIssue(
                        code="area_too_small",
                        field="area_sqm",
                        message=f"Area {listing.area_sqm} m² below minimum {MIN_AREA_SQM} m²",
                        value=listing.area_sqm,
                    )
                )
            elif listing.area_sqm > MAX_AREA_SQM:
                issues.append(
                    ValidationIssue(
                        code="area_too_large",
                        field="area_sqm",
                        message=f"Area {listing.area_sqm} m² above maximum {MAX_AREA_SQM} m²",
                        value=listing.area_sqm,
                    )
                )

        if listing.sale_price is not None and listing.rent_price is not None:
            issues.append(
                ValidationIssue(
                    code="conflicting_prices",
                    field="sale_price",
                    message="Both sale_price and rent_price are set",
                )
            )

        self._check_price_per_sqm_band(listing, issues)
        self._check_price_per_sqm_consistency(listing, issues)
        self._check_likely_mislabeled_type(listing, issues)

        if listing.listing_type == ListingType.SALE and listing.sale_price is None:
            issues.append(
                ValidationIssue(
                    code="missing_price",
                    field="sale_price",
                    message="Sale listing has no price extracted",
                )
            )
        elif listing.listing_type == ListingType.RENT and listing.rent_price is None:
            issues.append(
                ValidationIssue(
                    code="missing_price",
                    field="rent_price",
                    message="Rent listing has no price extracted",
                )
            )

        if listing.property_type == PropertyType.HOUSE:
            if listing.area_sqm is None:
                issues.append(
                    ValidationIssue(
                        code="house_area_missing",
                        field="area_sqm",
                        message=f"House requires area at least {HOUSE_MIN_AREA_SQM:.0f} m²",
                    )
                )
            elif listing.area_sqm < HOUSE_MIN_AREA_SQM:
                issues.append(
                    ValidationIssue(
                        code="house_area_too_small",
                        field="area_sqm",
                        message=(
                            f"House area {listing.area_sqm} m² below minimum "
                            f"{HOUSE_MIN_AREA_SQM:.0f} m²"
                        ),
                        value=listing.area_sqm,
                    )
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def _check_price_per_sqm_band(
        self,
        listing: NormalizedListingSchema,
        issues: list[ValidationIssue],
    ) -> None:
        if listing.price_per_sqm is None:
            return
        if listing.listing_type == ListingType.SALE:
            min_psm, max_psm = MIN_SALE_PRICE_PER_SQM, MAX_SALE_PRICE_PER_SQM
        elif listing.listing_type == ListingType.RENT:
            min_psm, max_psm = MIN_RENT_PRICE_PER_SQM, MAX_RENT_PRICE_PER_SQM
        else:
            return
        if listing.price_per_sqm < min_psm:
            issues.append(
                ValidationIssue(
                    code="price_per_sqm_too_low",
                    field="price_per_sqm",
                    message=f"€/m² {listing.price_per_sqm} below minimum €{min_psm}",
                    value=str(listing.price_per_sqm),
                )
            )
        elif listing.price_per_sqm > max_psm:
            issues.append(
                ValidationIssue(
                    code="price_per_sqm_too_high",
                    field="price_per_sqm",
                    message=f"€/m² {listing.price_per_sqm} above maximum €{max_psm}",
                    value=str(listing.price_per_sqm),
                )
            )

    def _check_price_per_sqm_consistency(
        self,
        listing: NormalizedListingSchema,
        issues: list[ValidationIssue],
    ) -> None:
        if listing.area_sqm is None or listing.area_sqm <= 0 or listing.price_per_sqm is None:
            return
        area = Decimal(str(listing.area_sqm))
        if listing.listing_type == ListingType.SALE and listing.sale_price is not None:
            computed = listing.sale_price / area
        elif listing.listing_type == ListingType.RENT and listing.rent_price is not None:
            computed = listing.rent_price / area
        else:
            return
        stored = listing.price_per_sqm
        if stored <= 0:
            return
        rel_err = abs(computed - stored) / stored
        if rel_err > MAX_PRICE_PER_SQM_REL_ERROR:
            issues.append(
                ValidationIssue(
                    code="price_per_sqm_inconsistent",
                    field="price_per_sqm",
                    message=(
                        f"€/m² {stored} inconsistent with total/area (computed €{computed:.2f}/m²)"
                    ),
                    value=str(stored),
                )
            )

    def _check_likely_mislabeled_type(
        self,
        listing: NormalizedListingSchema,
        issues: list[ValidationIssue],
    ) -> None:
        if listing.area_sqm is None or listing.area_sqm <= 0:
            return
        area = Decimal(str(listing.area_sqm))
        if (
            listing.listing_type == ListingType.SALE
            and listing.sale_price is not None
            and listing.sale_price < LIKELY_RENT_AS_SALE_MAX_TOTAL
        ):
            implied = listing.sale_price / area
            if implied < LIKELY_RENT_AS_SALE_MAX_IMPLIED_PSM:
                issues.append(
                    ValidationIssue(
                        code="likely_rent_as_sale",
                        field="listing_type",
                        message=(
                            f"Sale listing €{listing.sale_price} for {listing.area_sqm} m² "
                            f"(€{implied:.0f}/m²) looks like a rent mislabeled as sale"
                        ),
                        value=str(implied),
                    )
                )

    def _check_price_range(
        self,
        issues: list[ValidationIssue],
        price: Decimal,
        minimum: Decimal,
        maximum: Decimal,
        *,
        rent: bool = False,
    ) -> None:
        label = "Rent" if rent else "Sale"
        if price < minimum:
            issues.append(
                ValidationIssue(
                    code="price_too_low",
                    field="rent_price" if rent else "sale_price",
                    message=f"{label} price {price} below minimum €{minimum}",
                    value=str(price),
                )
            )
        elif price > maximum:
            issues.append(
                ValidationIssue(
                    code="price_too_high",
                    field="rent_price" if rent else "sale_price",
                    message=f"{label} price {price} above maximum €{maximum}",
                    value=str(price),
                )
            )
