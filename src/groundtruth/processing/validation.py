"""Validation rules for normalized listings — flag impossible data, never delete."""

from decimal import Decimal

from groundtruth.models.enums import ListingType
from groundtruth.schemas.etl import ValidationIssue, ValidationResult
from groundtruth.schemas.pipeline import NormalizedListingSchema

MIN_AREA_SQM = 15.0
MAX_AREA_SQM = 1000.0
MIN_SALE_PRICE = Decimal("1000")
MAX_SALE_PRICE = Decimal("10000000")
MIN_RENT_PRICE = Decimal("50")
MAX_RENT_PRICE = Decimal("50000")
MIN_PRICE_PER_SQM = Decimal("100")
MAX_PRICE_PER_SQM = Decimal("20000")


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

        if listing.listing_type == ListingType.SALE and listing.price_per_sqm is not None:
            if listing.price_per_sqm < MIN_PRICE_PER_SQM:
                issues.append(
                    ValidationIssue(
                        code="price_per_sqm_too_low",
                        field="price_per_sqm",
                        message=f"€/m² {listing.price_per_sqm} below minimum €{MIN_PRICE_PER_SQM}",
                        value=str(listing.price_per_sqm),
                    )
                )
            elif listing.price_per_sqm > MAX_PRICE_PER_SQM:
                issues.append(
                    ValidationIssue(
                        code="price_per_sqm_too_high",
                        field="price_per_sqm",
                        message=f"€/m² {listing.price_per_sqm} above maximum €{MAX_PRICE_PER_SQM}",
                        value=str(listing.price_per_sqm),
                    )
                )

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

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

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
