# Resolver and parser changes

Actual runtime files changed in the isolated implementation checkout:

- `data/gazetteers/districts.json`
- `data/gazetteers/draft/prishtina_location_tree.yaml`
- `data/gazetteers/market_relationships.json`
- `data/gazetteers/neighborhoods.json`
- `src/groundtruth/analytics/market_hierarchy.py`
- `src/groundtruth/gazetteers/location_resolver.py`
- `src/groundtruth/gazetteers/location_tree.py`
- `src/groundtruth/gazetteers/market_graph.py`
- `src/groundtruth/gazetteers/version.py`
- `src/groundtruth/processing/confidence.py`
- `src/groundtruth/services/merrjep_parsing.py`
- `src/groundtruth/services/normalization.py`
- `src/groundtruth/services/pro_rks_parsing.py`
- `tests/fixtures/phase5/location_examples.json`
- `tests/test_location_resolver.py`
- `tests/test_normalizers.py`
- `tests/test_phase5_locations.py`

The active resolver now enforces complete tokens, preserves punctuation boundaries
and NFC-normalizes decomposed Albanian text. JSON aliases and YAML aliases agree
for the seven confirmed groups; existing inflections are retained. Broad Dardania
is not the school district. Explicit school-area variants remain supported;
nearby-school references are proximity evidence. Ahmet Krasniqi cannot be matched
through the prefix of Rr. A. Park, mall, view, developer and distance references
are guarded. A named complex is distinct from a developer or nearby landmark;
Royal City/Mall remain separate; Narteli and Beni Dona retain parent guards.

Normalization version2.1.0 carries typed entity/subarea/parent/proximity evidence
in confidence details. Pro-RKS parsed city preserves explicit source city and
distinguishes absence. The old normalized pricing city is retained only through
explicit `pricing_compatibility_city` / pending-policy metadata, preserving scope.
This is not permission to exclude Fushë Kosovë or relocate any historical listing.
New reference fingerprint `fc2fe497e0e4` includes all
five JSON inputs, active YAML and the typed relationship graph. Historical
five-JSON interpretation remains reproducible with the legacy hash helper.
