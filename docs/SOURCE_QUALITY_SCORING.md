# Source quality calculator — policy 1.1.0

Part 1 of [the integration plan](GROUNDTRUTH_SOURCE_QUALITY_HARTA_PLAN.md).
This private diagnostic produces recommendations. It does not feed corpus selection,
deduplication winners, market statistics, valuations, Metrik, or deployment.

## Implementation map

| Existing component | Integration decision |
| --- | --- |
| `processing/validation.py`, `services/etl.py` | Reuse `ListingValidator` without changing its bounds; retain persisted rejection codes, including ETL location exclusions. |
| `processing/confidence.py` | Keep listing extraction confidence separate; never treat its gazetteer/geocode score as verified location accuracy. |
| `processing/parser_kpis.py` | Keep extraction coverage and golden-parser accuracy separate. Parser accuracy does not establish publisher reliability. |
| `processing/invalid_classification.py` | Its attribution rules are heuristics, so do not import them as confirmed source-error evidence. |
| `analytics/source_skew.py`, `corpus.py`, `corpus_filters.py` | These describe a filtered population. Do not use that population for source quality. |
| `analytics/cross_dedup.py`, `listing_fingerprint.py`, `processing/deduplicator/scoring.py` | Reuse blocking and `DuplicateScorer` for probable-duplicate diagnostics only; never call priority-based winner selection. |
| `models/pipeline.py`, `models/etl.py`, `models/scrape_run.py` | Raw-rooted read-only population, latest parsed attempt per raw version, optional normalized data, all linked quarantine outcomes. |
| `services/normalization.py`, `gazetteers/location_resolver.py` | Consume existing resolved IDs and rejection evidence; no new resolver or geocoding requests. |
| `models/listing_observation.py`, `models/lifecycle.py` | Their observations/current mutable lifecycle state do not prove publication or independently verified active status. Do not substitute them for source dates. |
| `portals/registry.py`, `cli.py` | Discover registered sources dynamically; register a private diagnostic command under `analytics`. |

New modules: `analytics/source_quality_models.py` defines Pydantic contracts;
`source_quality.py` provides scoring/reporting; `source_quality_population.py` reads
pipeline data; `commands/source_quality_commands.py` handles operator inputs.

## Population and time

Use the inclusive **raw-ingestion** interval `[as_of - days, as_of]`, not a
publication-date filter. Stale/missing publication dates therefore remain visible.
`records_examined` counts raw versions in that interval. The scoring grain is the
latest `(source_website, source_listing_id)` by raw `scraped_at`, then raw ID.
Old versions contribute to the repeat counter, not to source-score averages.
For each version select the latest parsed row by `parsed_at`, then ID, with
processing/quarantine timestamps bounded by `as_of`. A successful reparse supersedes
older raw-only failures. Validation records linked only through the selected parsed
ID remain visible, matching existing ETL behavior.

Accepted/rejected counts describe persisted pipeline outcomes; pending means no
completed normalized result or recorded rejection. Revalidation diagnostics may
identify additional invalid fields in a historically accepted record without
changing its stored outcome. Parse/normalization failures get validity zero and
unknown field-dependent criteria when no structured extraction exists. Pending
validity remains unknown. Completeness of an unavailable extraction is unknown,
not an assertion that the source omitted all fields.

Sale/rent/unknown segments use the latest version's classification. Repeat counts
in a segment include earlier versions of those final identities. `all` is the full
denominator; segments partition it and must not be added to `all`.

Unchanged recrawls often do not create a new raw row because raw content hashes are
unique. The repeat counter measures stored versions, not HTTP requests. This is
an ingestion-snapshot evaluation, not a census of every property seen during the
window. Deleted historical processing rows and unseen crawl failures cannot be
reconstructed: keep a database/fixture snapshot to reproduce a historical run.

## Six dimensions

| Criterion | Weight | Listing measurement |
| --- | ---: | --- |
| Validity | 25% | 100 if completed, no recorded rejection, and existing validation passes; 0 for rejection or validation issues. Missing transaction/property classifications are explicitly invalid. |
| Completeness | 20% | Weighted presence: price/area 3 each; transaction/property/municipality 2 each; neighborhood/street/publication 1 each. Bedrooms add 1 for apartments, houses, villas; not for land, studios, rooms, garages, commercial, or other. |
| Location accuracy | 25% | Mean of explicit independently checked source-location evidence. Unknown without it. Precision is separately reported: municipality presence 20, resolved neighborhood 30, street 30, building 20. Coordinates/centroids do not imply accuracy. |
| Internal consistency | 15% | Mean of applicable checks: price exclusivity, total/area versus stored €/m² using existing validator tolerance, floor versus total floors, flagged transaction/location contradictions, explicit consistency reviews. Missing comparisons are unknown. Each physical check counts once. |
| Freshness | 10% | `100 * max(0, 1 - age_days / 180)` from a source-declared publication date; source-update timestamp is an explicitly labelled fallback. Proxy/unknown-origin dates remain unknown. Future supported dates score 0 with a future-date marker. |
| Historical reliability | 5% | Mean correctness of independently reviewed historical evidence explicitly attributed to the source; parser-origin reviews do not enter this criterion. Unknown without evidence. |

Validity and completeness deliberately overlap for missing mandatory price or type:
one records unusability, the other information availability. Presence of an invalid
number still counts as present; validity owns correctness. Consistency overlaps
validity only for explicit cross-field contradictions, not generic range failures.
Parser failures lower pipeline usability; they are never automatically described
as publisher errors. Attribution remains `unattributed` or
`pipeline_failure_unattributed` unless independent evidence identifies its origin.

Inputs can distinguish publication, source update, first seen, last seen, crawl,
and verified-active timestamps. The DB adapter supplies the raw crawl timestamp
and existing listing date with explicit origin; it does not manufacture other date semantics from
arbitrary payload keys. First/last-seen/crawl timestamps never replace publication
or update evidence in freshness scoring. Independent evidence has an ID, check
timestamp, kind, origin, and correctness; future reviews are ignored and duplicate
review IDs per kind/record are rejected. No human evidence is required to run.

Policy 1.1.0 corrects a real-data provenance defect discovered in Part 2. Pro-RKS's
parser derives `listing_date` from image media dates and can fall back to scrape
time. Those values are not publication evidence. The reader now marks these dates
`proxy`; they contribute neither publication completeness nor publication freshness.
The other five inspected adapters map source-declared date fields; new/undocumented
adapters default to `unknown`. The scoring engine reads the generic
`publication_date_basis` contract and contains no portal reputation rule. Offline
inputs must explicitly state `source_declared` when that assertion is supported.
All six contribution weights, imputation 50, and source-weight eligibility rules
are unchanged. Original policy 1.0.0 example/results remain available for comparison.

## Composite, uncertainty, and recommended weight

Each listing receives `sum(policy_weight * criterion_score)`. Unknown scores stay
JSON `null`; for this **provisional composite only**, substitute neutral 50.
Observed coverage is the sum of measured criterion weights. Source quality is
the mean of individual composites, including failed and pending records. This
avoids hiding low-coverage listings behind averages over only successful rows.
Empty sources have null scores, `no_data`, and weight 1.00.

Source criterion scores average only measured values and report their exact
`criterion_sample_counts`; their denominator is that count, not all listings.
`unknown_criteria` also includes partially unknown criteria. Coverage averages
over all unique source listings. `score_status` is `provisional` whenever any
weighted criterion remains unknown; `measured` is not a claim of calibrated accuracy.

Default weight eligibility requires at least 30 unique listings, 90% observed
weighted coverage, 80% independently location-checked listings, and 95% processed
listings. Otherwise the weight remains 1.00 with every failed condition listed.
Eligible recommendations use `clamp(1 + (quality - 70) / 100, .75, 1.25)`.
Historical reviews are not mandatory when other evidence reaches those thresholds.
These initial settings require real-data calibration in Part 2. A policy JSON can
override settings; change its version when changing assumptions. The entire policy
is embedded in reports. No confidence interval or statistically calibrated error
rate is claimed; sample counts, coverage, and explicit eligibility state provide
the uncertainty indicators in this version.

Duplication never changes quality or source weights. Within-source exact-content
duplicates count excess distinct IDs sharing a nonempty raw hash. Cross-portal
diagnostics use existing structured blocking (transaction, neighborhood, area,
bedrooms, price) and duplicate scoring at threshold 85. Descriptions are excluded.
`cross_portal_comparable_count` is the denominator of matchable structured listings;
`cross_portal_duplicate_listing_count` counts listings in probable cross-source
matches. These are candidate matches, not confirmed duplicate properties; matching
is restricted to sources selected for the report. No source-priority ranking is used.

## Operator examples

From the repository root, run the checked-in **synthetic** fixture:

```powershell
.venv/Scripts/groundtruth.exe analytics source-quality report --as-of 2026-10-21T00:00:00Z --days 30 --segment --fixture tests/fixtures/source_quality/synthetic.json --output reports/generated/source_quality/example
```

Read the configured database without writing it:

```powershell
.venv/Scripts/groundtruth.exe analytics source-quality report --as-of 2026-10-21T00:00:00Z --days 30 --source gjirafa --output reports/generated/source_quality/research
```

The DB command uses a repeatable-read, read-only PostgreSQL transaction. Unit and
integration tests use isolated synthetic inputs/SQLite, never the private DB.
`--policy-file` accepts the policy contract. `--fixture` accepts a JSON list of
`QualityRecord` contracts and can include version-bound independent verification
evidence for later reviewed evaluations. Programmatic consumers can attach such
evidence to the records returned by `pipeline_records` before `build_report`.
Dates without offsets mean UTC. Empty requested populations and unavailable DBs
return nonzero with a sanitized error; empty sources in a populated report remain
explicitly unrated. Future portal registration requires no scoring-engine changes.

## Artifacts and reproducibility

Outputs: `source_quality_report.json`, `source_quality_summary.csv`, and the emitted
`source_quality_report.schema.json` (Pydantic JSON Schema). JSON contains version,
embedded policy, input fingerprint, window, source summaries, and per-listing
assessments. CSV contains the same source-summary fields; dict/list cells use JSON,
and unknown scalar values are empty cells. Counts and sample counts provide explicit
denominators for rates. Subtract pending from unique count for processed coverage.

Ordering is stable; scores/coverage round to six decimals, weights to four, using
Python rounding. `generated_at` deliberately equals the supplied `as_of`, so identical
snapshot, policy, sources, segmentation, and evaluation time produce byte-identical
artifacts. SHA-256 identifies canonical ordered scoring inputs; no raw payloads,
descriptions, images, contact details, original URLs, or credentials are exported.
Non-finite input numerics are rejected and JSON serialization forbids NaN/Infinity.

[Example report](examples/source_quality/source_quality_report.json) and
[CSV](examples/source_quality/source_quality_summary.csv) contain synthetic values
only and preserve policy 1.0.0's original outputs. Current runs emit policy/report
1.1.0, including date-origin evidence; they are not byte-for-byte reproductions of
those archived examples. They are demonstrations, not measured portal rankings.

## Part 2 execution

```powershell
.venv/Scripts/python.exe scripts/research/evaluate_source_quality.py --as-of 2026-10-21T00:00:00Z --days 30 --history-days 140 --output reports/generated/source_quality/part2/final
```

The runner verifies the documented local research target before connecting and
requires an empty output directory. It reads one repeatable-read, read-only
PostgreSQL snapshot, inventories tables and high-water marks, saves a private
redacted scoring-input snapshot, evaluates recent/historical/processed cohorts,
creates separate random and failure-enriched samples, performs conservative stored
field comparisons, varies policy assumptions, and simulates representatives on a
fixed eligible apartment/studio cohort. It issues no page requests or DB writes.
Descriptions/contact fields are never exported; the private input snapshot and
per-listing reports remain ignored generated artifacts. Only aggregated evidence
and the explicitly inactive proposed weight configuration belong in Git.

Audits are automated explicit-field comparisons with agent review of rules and
disagreements. They are not independent human labels or proof of actual physical
location. Stored HTML/source assertions establish extraction agreement, not verified
publisher correctness. Checks have raw-record IDs and safe evidence paths locally;
failure-enriched samples cannot estimate source-wide error rates. See
[Gate 2 evidence](SOURCE_QUALITY_GATE_2.md) for actual results and remaining gaps.
