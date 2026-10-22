# GroundTruth — independent evidence verification

2026-10-22 · **EVIDENCE-LIMITED** · policy **1.1.0** unchanged.

This is the durable reference for this chat's execution request. It extends,
without rewriting, the [matching pilot](HARTA_CROSS_SOURCE_MATCHING_PILOT.md)
and [source-quality assessment](SOURCE_QUALITY_GATE_2.md).

## Matching result and evidence boundary

Twenty candidates from the frozen forty were selected by descending score,
subject to at least two per established portal. Allocation: Gjirafa 3, Merrjep 2,
Pro-rks 8, Topia 3, Vision 2, MyRealEstate 2. This is a deliberate review sample,
not a probability sample of duplicate properties. All twenty Harta pages returned
HTTP 200. Existing archived reference descriptions, identifiers, field values,
dates and stored price versions were inspected first. One hundred published media
responses were inspected: initial views for all cases and eight images per side
for HCM-007 and HCM-002. A reference logo was correctly excluded as identity proof.
No access blocks or challenge bypasses were needed; no new listing cohort was collected.

**1 verified true, 2 verified false, 17 unresolved.**

HCM-007 establishes the same advertised Harta/Pro-rks apartment through matching
kitchen cabinetry and geometry, living-room windows and fittings, bedroom/wardrobe
details, and the laundry bathroom. Development, sixth floor, 86.30 m², two bedrooms
and EUR470 rent corroborate the visual link. This is advertised-property identity,
not a cadastral, ownership, physical-location or interior-area certification.

HCM-010 and HCM-021 show distinct exterior building geometry, corroborated by
different named developments. They are verified different advertised properties.
Other field, furniture and address conflicts remain unresolved because source
mistakes, changed interiors and nonsimultaneous advertisements remain possible.
HCM-022 also exposes commercial-space contamination in an apartment-scoped pool.

Resolved-only agreement is 1/3, with 2/3 false proposals; the precision's 95% Wilson
reference interval is 6.15–79.23%. Selective resolution makes those figures
unsuitable as population precision or false-match rates. No independently
confirmed held-out controls exist. No operating threshold has been validated.

Location adds ranking points in 14/20 cases, including the true case. This does
not establish incremental matching accuracy or a causal location benefit. No
ranker, threshold, deduplication, field-transfer or automatic merging changes were made.

## Source reliability

All 180 source snapshots and 1,080 original field checks were revisited. Explicit
bedroom claims in archived narratives supplement previously unknown source fields.
Publisher real-world truth remains unknown for every snapshot; there are no
independently established publisher-error rates or location-accuracy rates.

| Portal | Independent publisher truth | Source issues | Confirmed representation-error cases/30 | Unknown/noncomparable fields | Previous = replay quality | Weight |
|---|---:|---|---|---:|---:|---:|
| gjirafa | 0/30 | 5 conflicts | 4 parser, 0 normalization | 6.1% | 75.517867 | 1.00 inactive |
| merrjep | 0/30 | 0 conflicts | 5 parser, 0 normalization | 29.4% | 68.392480 | 1.00 inactive |
| myrealestate | 0/30 | 0 conflicts | 2 parser, 0 normalization | 10.6% | 70.323090 | 1.00 inactive |
| pro-rks | 0/30 | 0 conflicts | 1 parser, 1 normalization | 6.7% | 69.275033 | 1.00 inactive |
| topia | 0/30 | 0 conflicts | 0 parser, 0 normalization | 16.7% | 75.622093 | 1.00 inactive |
| vision | 0/30 | 0 conflicts | 1 parser, 0 normalization | 21.7% | 68.927974 | 1.00 inactive |

Error-case columns can overlap and are diagnostic counts, not population rates.
Pro-rks additionally retains inactive zero prices in 10/30 snapshots; these are
pipeline representation issues, separate from the active-price comparison above.
Placeholders and conflicts are not established real-world publisher errors.

Four Gjirafa unit-price descriptions establish arithmetic totals of EUR104,000,
51,000, 94,300 and 189,000; stored parser totals were EUR130,000, 85,000, 115,000
and 140,000. Five sale-label/rent-narrative conflicts support the parser's rent
choice and should not be mislabeled parser classification errors. Merrjep includes
automotive and land offers represented as apartments, missing explicit transaction
classifications and an unassigned displayed price. MyRealEstate has a house parsed
as apartment and an omitted bedroom count. Vision has an omitted bedroom count.
Pro-rks has a per-m² price retained as total and a home category changed by
normalization; its multiunit narrative does not independently prove physical type.

Topia's 30 apparent area agreements concern **gross_area**, not independently
validated interior area. Three snapshots also supply different positive interior
values (gross/interior: 110/61, 140/79 and 105/94 m²). Keep this semantic risk
separate from literal extraction accuracy and from claims that a publisher is false.
It warrants a separate bounded area-basis remediation; this task changes no
existing valuation or validation behavior.

Publication comparison: 141 source-date agreements, 30 Pro-rks media-date proxies,
9 unknown source dates, no comparable date disagreement. Source agreement does
not prove original publication or active status. Street/neighborhood assertions
remain physically unverified. Explicit null/zero API slots are recorded separately;
unsupported extraction paths do not prove information was absent from the original.

Every portal has 15 random-segment audit cases. Failure-enriched cases stay separate:
15 each, except Topia's 5 plus 10 random top-ups. Field-specific rates, denominators,
sale/rent/unknown segments and Wilson reference intervals are in the private
assessment. Intervals concern comparable source representation in the random
stratum, not source-wide error margins. Fields are correlated and are never pooled
into a binomial trial count. Missing/ambiguous facts remain outside comparable
denominators. No publisher interval is calculated from zero independent trials.

The exact frozen historical processed population was rescored using the existing
calculator, unchanged policy 1.1.0 and unchanged evidence inputs. All six provisional
quality scores reproduce exactly. New parser evidence does not become independent
source-location or publisher-history evidence. Observed criterion coverage remains
below 90%, independent location verification below 80%; every proposed weight stays
**1.00 inactive**. Harta remains provisional **48.815**, weight **1.00 inactive**.
Usability, completeness, coverage and extraction diagnostics are not reputation rankings.

## Reviewed case index

Detailed local reports contain original source URLs/IDs, raw record IDs, observed
timestamps, numeric claims, typed areas, price versions, visual findings and media
checksums. Those identifying source references and images remain outside Git.

| Case | Reference | Rank points | Verdict | Case evidence |
|---|---|---:|---|---|
| HCM-007 | pro-rks | 53.158 | VERIFIED_TRUE | Eight images per side inspected. Kitchen has the same wood-grain upper cabinets, dark lower units, white splashback and sink/window relationship; living room has the same sofa arrangement, floating TV shelf and balcony/window geometry; bedroom headboard and wardrobe align; laundry bathroom has matching dark tile, washer, toilet and shower. Both name Park Residence, 86.30 m², floor 6, two bedrooms and EUR470 rent. Establishes the same advertised apartment, not independently surveyed area or physical ownership. |
| HCM-008 | pro-rks | 52.745 | UNRESOLVED | Harta describes furnished 98 m² opposite SPAR on Rruga C; reference describes 94.5 m² at VG Construction (normalized area 96). Floors and bedrooms agree. Images show different kitchen finishes, ceiling design and living-room decor. Renovation, stale photos or another unit remain possible; no apartment key or same-room correspondence. |
| HCM-001 | gjirafa | 52.439 | UNRESOLVED | Harta names Rezidenca e Mbretëreshës/R&Rukolli and 62.8 m² with ad code 2653; Gjirafa describes Rruga B behind Maxi24, 65 m² and code2770. Harta exterior and living room do not provide a shared reference exterior; floor6 agrees. Harta structured bedrooms0 contradicts its one-bedroom description, so the room disagreement is not reliable negative identity evidence. |
| HCM-009 | pro-rks | 52.400 | UNRESOLVED | Harta: 60 m² above Sarajeva Steak House/Rruga B, Termokos, garage, ad A1077. Reference: explicit48 m² net at Banesat e Tregtisë/Rruga C, heat pump. Floor5, one bedroom and EUR400 agree. Living-room and kitchen images show different fittings but no independently linked unit. |
| HCM-013 | topia | 50.000 | UNRESOLVED | Harta:115 m² near US Embassy, underfloor heating, storage by kitchen, three bedrooms/floor4. Topia T5321:120 m² at Tregtia near Avicena, Termokos and garage included. Images show different room/ceiling arrangements; generic sofas do not link units. |
| HCM-002 | gjirafa | 48.353 | UNRESOLVED | Eight images per side inspected. Both advertise88 m², EUR500, floor4, two bedrooms near Minimax in Dragodan. Harta code2145 describes one balcony, WC and storage; reference code6098 describes two terraces. Kitchens, wall finishes and wardrobes differ. No matching multiroom arrangement was established. |
| HCM-019 | pro-rks | 48.182 | UNRESOLVED | Both60 m², floor2, one bedroom and EUR500. Harta names Asi Universal/Muhaxherët near Dubrovniku; reference names Santea/Dardani near Albi Market. Images have distinct kitchens and room fittings. Shared size/price cannot overrule unresolved building evidence. |
| HCM-020 | pro-rks | 47.923 | UNRESOLVED | Harta text:82 m² at Park Residence/Berisha Group, new unfurnished, floor1; structured surface85. Reference:70 m² at ACG/Elbasani, furnished, electric underfloor heating. EUR330, two bedrooms/floor1 agree; Harta balcony/exterior and reference furnished interior do not link the unit. |
| HCM-003 | gjirafa | 47.765 | UNRESOLVED | Harta has only one architectural render/plan and minimal text (one neighbor per floor), surface120. Gjirafa code92100 describes92 m² near Comandante Marcos, two bedrooms in text despite normalized3. No linked building exterior or unit identifier. |
| HCM-004 | merrjep | 47.159 | UNRESOLVED | Harta penthouse:125 m² living plus94 m² terrace, Partner&Dervisholli, EUR360000, structured surface171 unspecified. Merrjep code30031:120 m² gross/106 m² net, first residential floor,20 m² balconies, two garages/two cellars, negotiable price in text versus normalized450000. Available Harta views and reference interior do not establish shared structure. |
| HCM-021 | pro-rks | 47.034 | VERIFIED_FALSE | Harta exterior shows the completed Tregtia complex of repeated towers with dark/red roofline elements and a furnished apartment; text names Tregtia/Rruga C,121 m². Pro-rks exterior/render shows a different stepped building massing and facade; text names Grand Tower/Gashi Invest/Holger Petersen and explicitly offers multiple135 m² units across floors. Different named developments are corroborated by incompatible advertised building geometry. |
| HCM-014 | topia | 46.000 | UNRESOLVED | Harta80 m² near new municipality, Termokos, two balconies; Topia98 m² total near Ministry of Health/Bajram Curri, electric boiler. Floor3, two bedrooms and EUR450 agree. Living-room colors, cabinets and ceiling differ; no unit link. |
| HCM-015 | topia | 45.000 | UNRESOLVED | Harta110.60 m² on Shkupi/Veternik with direct Pika property68 link; Topia advertises134 m² (gross taxonomy). Exterior/view photographs lack an identified common facade or unit. The Pika link is a distinct third-source ad reference, not a cross-reference to the selected Topia listing. |
| HCM-022 | pro-rks | 42.545 | UNRESOLVED | Both descriptions advertise commercial spaces although normalized candidates were apartment/studio scoped. Harta120 m² plus50 m² terrace near Ministry of Education/Aktash; reference330 m² near HotelGloria/CityPark. Photographs show unfinished business interiors with differing openings/columns; no shared unit key. |
| HCM-010 | vision | 41.765 | VERIFIED_FALSE | Harta exterior shows tall white/black towers with continuous vertical dark balcony bands; description names Kulla Zotnisë,86 m². Vision exterior shows a shorter building with an orange/red facade and different balcony/window massing; description identifies Trio Construction,97 m². Distinct complete exterior structures corroborate different named developments. |
| HCM-023 | pro-rks | 41.455 | UNRESOLVED | Harta has no description; images include a modern white building with stacked angular balconies and a gray-sofa interior. Pro-rks photos show a terrace/night view and corridor. Structured57 versus63 m² and shared floor/rent-type details cannot establish identity. |
| HCM-011 | vision | 41.346 | UNRESOLVED | Harta95 m² in a newly completed building, floor5, two lifts, bedrooms furnished on request. Vision115 m² plus30 m² terraces near Swiss Embassy, older2024 publication. EUR700 and two bedrooms agree. Kitchen/ceiling/window arrangements differ; nonsimultaneous ads leave renovation ambiguity. |
| HCM-005 | merrjep | 41.176 | UNRESOLVED | Harta96 m² net/130 factual on Xheladin Rekaliu near Gizzi, three bedrooms/two balconies. Merrjep95 m² on Hyzri Talla, first floor and basement with windows. Harta exterior and reference plan do not connect the same apartment. |
| HCM-016 | myrealestate | 37.389 | UNRESOLVED | Harta87.5 m² in description (structured87), Muhaxherët near Swiss Embassy/CityPark, garage included, floor4. MyRealEstate72 m² at Aktash, communal bills included, southeast orientation. BothEUR500/two bedrooms. Images show different living-room openings and finishes. |
| HCM-017 | myrealestate | 32.892 | UNRESOLVED | Harta86 m² at Emshir/Kalabri/Ali Vitia, furnished with two garages, EUR153000. MyRealEstate92 m² at CONIN/Mati1, Termokos and terrace, EUR155000. One reference media item is a logo and supplies no visual property evidence; remaining room images have no established correspondence. |

## Deliverables and reproduction

Private deliverables under `reports/generated/independent_evidence_v1/reviewed/`:

- `matching_verification.md`: all 20 cases, references and evidence.
- `source_reliability.md`, `field_reviews.json`, `snapshot_reviews.json`:
  180 case adjudications and 1,080 field checks with separate error origins.
- `source_weights_proposed_v1.json`: versioned proposal, confidence, coverage and
  eligibility explanations; every weight inactive.
- `manual_review_queue.md`: only the 17 unresolved cases, with exact evidence requests.
- `assessment.json`, `policy_replay.json`, `input_receipt.json`: calculations and hashes.

Frozen reviewed input: `reports/generated/independent_evidence_v1/frozen_evidence_private.json`.
Bounded collection/inspection helpers and image sheets: `.tmp/independent-evidence/`.
Full descriptions, contacts, source UUIDs and image files stay outside Git.
An executed [companion notebook](../reports/research/independent_evidence_verification.ipynb)
provides inspectable aggregate calculations.

Reproduce without network, credentials or database writes; choose a new output folder:

```powershell
.venv/Scripts/python.exe scripts/research/verify_independent_evidence.py --evidence reports/generated/independent_evidence_v1/frozen_evidence_private.json --calibration reports/generated/source_quality/six_portal_calibration_095214 --output reports/generated/independent_evidence_v1/replay
```

Frozen input digests are checked before scoring. Historical artifacts are not rewritten.
See [completion and QA](INDEPENDENT_EVIDENCE_COMPLETION.md) for actual gate results.

## Smallest useful next action

Use the manual queue only for apartment-specific evidence that automation could
not establish. Prioritize HCM-002 (dated renovation/unit linkage) and HCM-008
(building and floor-plan linkage). Do not request contacts or ownership documents.
Separately, repair and verify the four explicit unit-price calculations in a
bounded parser task, then evaluate Topia gross/interior semantics. More Harta
collection and non-neutral weighting are not supported by this evidence.
