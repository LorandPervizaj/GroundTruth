# Methodology (Draft)

## Data Collection

Listings are collected from publicly accessible web sources using automated scrapers. Each listing is stored in its original form before any transformation.

## Normalization

Field values are standardized using rule-based normalizers:

- Prices converted to EUR decimals
- Areas converted to m² floats
- Geographic names matched against curated gazetteers
- Descriptions cleaned for encoding and whitespace

## Deduplication

Duplicate detection uses weighted similarity scoring across price, area, location, and description. Listings above the confidence threshold are flagged as likely duplicates but not automatically merged.

## Geographic Enrichment

Coordinates are assigned using neighborhood centroids when exact addresses are unavailable. Address-level geocoding is optional and disabled by default.

## Limitations

- Scraped data may contain errors from original listings
- Duplicate detection is probabilistic
- Market statistics reflect asking prices, not transaction prices
- Coverage depends on which sources are actively scraped
