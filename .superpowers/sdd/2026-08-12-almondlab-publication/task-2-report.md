# Task 2 publication report: evidence registries and protected joins

Status: implementation and local verification complete; independent code review pending an available review slot.

## Delivered scope

- `data/evidence_registry.csv`: the complete 24-source Section 16 evidence set, with 19 DOI-anchored records and 5 official URL-only records.
- `data/candidate_registry.csv`: 6 frozen primary candidates plus all 14 held prequalification candidates. It contains no winner, best-candidate, or biological-efficacy field.
- `data/reference_chemistry.csv`: all 5 source-reported rootstock-screen recipes. EC is stored as a reported measurement and is never used to derive ion composition.
- `src/almondlab/registries.py`: strict UTF-8/LF CSV parsing, exact schemas and source identities, stable-ID validation, duplicate DOI/URL/row/header rejection, canonical evidence-list parsing, defensive dataframes, frozen candidate cross-checks, and typed chemistry validation.
- `src/almondlab/safe_data.py`: defensive `ProvenanceFrame` snapshots and fail-closed `safe_join` enforcement before `pandas.merge`.
- `tests/test_registries.py` and `tests/test_safe_data.py`: focused positive, malformed-input, and adversarial coverage.

## Registry reconciliation

Evidence records carry title, DOI and/or primary URL, organism/donor, life stage, chemistry/concentration/EC context, exposure duration, experimental unit, sample size, endpoint, reported effect and units/context, limitation, evidence tier, retrieval date, source reference identity, source-hash status, metadata basis, and explicit program assumptions. Values unavailable from the audited source are represented as `not_reported`, `unresolved`, `not_applicable`, or `not_evaluable`; no missing values were inferred.

The source PDFs/pages themselves are not vendored as immutable payloads. Consequently, every current evidence row truthfully records `source_sha256=not_available` and `source_sha256_status=primary_source_not_archived`, while `source_reference_identity` provides its stable DOI or official URL anchor. A manifest or HTML index hash was not mislabeled as a primary-source payload hash.

The source set is fail-closed in code: removing, adding, reordering, or reassigning a stable evidence ID to another DOI/URL is rejected as `EVIDENCE_REGISTRY_INCOMPLETE`.

Primary-source reconciliation retained important study-specific details and contradictions rather than smoothing them over, including:

- Ectocarpus mannitol: three independent fifth-generation Arabidopsis lines, 100 mM NaCl, 10-day soil exposure, and figure-level `n=30` context.
- Esi0017_0056: two 35S plus three RD29A fifth-generation lines, plate `n=90`, peat `n=15`, and assay-specific durations.
- PpHKT1: two named stable lines, treatment-specific 80/90/120/150 mM contexts, 12 soil plants per line, and the retained methods-versus-figure seedling-count discrepancy.
- Intensia: the reported seven-year primary trial, a later 2010 trial, 6-12 trees per replicate, and its Texas-by-Earlygold parentage.
- PavNHX37: source-reported assay conditions are retained, but no public sequence accession is invented.

## Candidate identity and unresolved fields

The six primary identities cross-check the frozen `configs/candidates.yaml` contract, including sequence identity/accessions, construct and donor, evidence tier/label, primary parameter, H3 rule, gates, and principal failure mode. Prequalification sequence identity, readiness, status, and evidence tier are also fail-closed against the audited registry.

Six records currently have unresolved exact sequence identity: C2 PyAPX, PQ_PyMnSOD, PQ_KaNa+/H+, PQ_KCS1-like, PQ_NHX1/2, and PQ_PavNHX37. In particular, the publication-required gaps remain explicit:

- PyAPX nucleotide accession: unresolved.
- KaNa+/H+ deposited sequence/accession: unresolved.
- exact construct-ready Prunus KCS1-like locus: unresolved.
- PavNHX37 public sequence accession/frozen donor sequence: unresolved.

No source label, chromosome coordinate, protein length, reference ortholog, or homolog analogy was promoted into an accession or experimental-clone certificate.

## Protected-join guarantees

`safe_join` validates both complete input snapshots and all private ancestry before merge. It requires exact row-level `record_id` and `source_type` fields, validates every record namespace (`SYN_`, `OBS_`, `EMP_`, or `LIT_`), rejects unknown or mixed source types, checks null and duplicate join keys against declared cardinality, forbids many-to-many joins, and rejects protected suffix/internal-column collisions. A synthetic/empirical collision always raises `SYNTHETIC_CONTAMINATION`; there is no production override and caller-controlled dataframe attributes cannot launder origin.

Output row order is deterministic, both immediate source records remain visible with protected suffixes, and immutable row-aligned ancestry is retained in the returned `ProvenanceFrame`. Materialization returns a defensive copy.

## TDD and verification record

The initial focused tests failed on missing modules/files. Later hardening cases were also observed RED before implementation: 8 failures for incomplete/drifted source identities, prequalification identity drift, compact ISO dates, and noncanonical decimal text.

Final commands and results (Windows virtual environment used because `uv` is unavailable on PATH):

```text
.venv\Scripts\python.exe -m pytest tests/test_registries.py tests/test_safe_data.py -q -p no:cacheprovider
83 passed in 2.32s

.venv\Scripts\python.exe -m pytest tests/test_paper1_contracts.py tests/test_chemistry.py tests/test_contracts.py tests/test_schemas.py tests/test_provenance.py tests/test_verification_manifest.py tests/test_verification_resources.py -q -p no:cacheprovider
381 passed in 12.12s

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
887 passed in 116.80s

.venv\Scripts\python.exe -m compileall -q src
exit 0
```

The focused suite includes a mixed-origin collision, prefix spoofing, a synthetic row hidden at position 10,001, untrusted attributes, renamed provenance columns, null keys, duplicate and many-to-many keys, suffix collisions, malformed CSV, missing sources/links/limitations, invented unresolved identities, and defensive-caller-mutation cases.

## SHA-256 manifest

```text
d0f6a120361076d98d82f93f17e5c7503fbd841551a527e206304ce550a0dcb1  src/almondlab/registries.py
a878e90260361afcd6027ce449a5c0f85a8590309ac4cc1519094dcfacf2b299  src/almondlab/safe_data.py
0e1bfbd32c10d22546b33f2b4b193fca109d7e03f89167dbbe633250a90986c3  data/evidence_registry.csv
8c9182e1cc3e2cd951d8e99002a2de7af40591b8835bf53ecd4d90b9d7166146  data/candidate_registry.csv
7a68b21873a3fabc2dd6467fb0ec7bba2760378f31d3f9b63c9a7803f05e4f5a  data/reference_chemistry.csv
9473aac347deed9a131383d905e29ccc470ddc1c163dcb9d5f96efd1faed3ad5  tests/test_registries.py
a7240bc5fda0fcf1e4e02d8b7e065b2c78e523bb791e5d8753d24ca045f07c3c  tests/test_safe_data.py
```

These hashes describe the pre-review implementation. If review changes any owned file, the manifest and affected verification results must be refreshed before publication handoff.
