# Task 2 publication report: evidence registries and protected joins

Status: review-repair implementation and local verification are complete; fresh independent exact review is pending.

## Delivered scope

- `data/evidence_registry.csv`: the complete 24-source Section 16 evidence set, with 19 DOI-anchored records and 5 official URL-only records.
- `data/candidate_registry.csv`: 6 frozen primary candidates plus all 14 held prequalification candidates. It contains no winner, best-candidate, or biological-efficacy field.
- `data/reference_chemistry.csv`: all 5 source-reported rootstock-screen recipes. EC remains a reported measurement and is never used to derive ion composition.
- `src/almondlab/registries.py`: strict UTF-8/LF parsing, exact schemas and associations, canonical decimal grammar, literal whole-file audit seals, candidate cross-checks, and typed chemistry validation.
- `src/almondlab/safe_data.py`: sealed defensive `ProvenanceFrame` snapshots and fail-closed, arbitrarily chainable `safe_join` behavior.
- `tests/test_registries.py` and `tests/test_safe_data.py`: focused positive, malformed-input, mutation, and adversarial regression coverage.

## Literature and sequence-record correction

The official 2025 rice paper reports three sequence accessions: PyAPX `AY282755.1`, PyMnSOD `DQ146477.2`, and the *Kappaphycus alvarezii* Na+/H+ antiporter under the author label `KaNa+/H+` as `MT473962`. The deposited `MT473962` record resolves to accession.version `MT473962.1`.

The paper reports 250 mM NaCl applied every 3 days, 30 seeds per dish with 3 dishes, germination read on day 10, and 12, 11, and 9 homozygous T1 lines for the respective constructs. These are source-reported experimental details; they are not efficacy claims for the AlmondLab program.

The guarded small-data workflow independently fetched and validated the corresponding NCBI records:

- `AY282755.1`: 1,041 bp *Pyropia yezoensis* cytosolic APX mRNA with complete CDS; FASTA SHA-256 `1fa50794a31470077978611121ada346a9a0d5f8fe8a1bd58864617e3804113a`.
- `DQ146477.2`: 910 bp *Pyropia yezoensis* MnSOD complete CDS; FASTA SHA-256 `cd64caf3868d196b869e45415fbb09b21a97c0a7d96e555f11e449ba69da0d0d`.
- `MT473962.1`: 1,194 bp *Kappaphycus alvarezii* Na+/H+ antiporter partial CDS; FASTA SHA-256 `182bc6de02e53212b7319f7ed9f1549ad32e34f8f12654492b12cbe8fdf14733`.

The guarded receipt covers 5 GEO and 15 NCBI payloads; its SHA-256 is `6a414634e72db373b86dbd702e40e47db31a58acb2fb0a124cbe30cac5aaeb06`. All 20 payload hashes and sidecars were independently revalidated, all GEO gzip payloads were nonempty, and every FASTA header matched its requested accession.version.

These are three distinct evidence states and must not be conflated:

1. The paper reports an accession for an experimental construct.
2. The repository independently verifies the identity and deposited completeness state of the matching NCBI record.
3. Exact experimental construct mapping, event identity, targeting, and other build-readiness validation may still be unresolved.

NCBI record verification therefore does not make any candidate construct-ready.

## Candidate identity and readiness

The six primary identities cross-check the frozen `configs/candidates.yaml` contract, including sequence identity/accessions, construct and donor, evidence tier/label, primary parameter, H3 rule, gates, and principal failure mode. Prequalification sequence identity, readiness, status, and evidence tier are also fail-closed against the audited registry.

- C1 is frozen to nucleotide `AJ972674.1` and protein `CAI99405.1`.
- C2 is frozen to paper-reported and repository-verified `AY282755.1`, with status `accession_verified`. Its exact construct map, event, and targeting remain unresolved, so sequence build remains blocked.
- C3 retains `Esi0017_0062|Esi0100_0020`, but its assembly crosswalk is unproven and its status is `crosswalk_pending`, not verified.
- C4 is frozen to nucleotide `EU879059.1` and protein `ACJ63441.1`.
- PQ_PyMnSOD uses repository-verified complete-CDS record `DQ146477.2`; exact construct mapping and targeting remain unresolved.
- PQ_KaNa+/H+ uses repository-verified partial-CDS record `MT473962.1`; exact construct mapping, a complete construct sequence, and direct transport characterization remain unresolved.
- Exact construct-ready identities remain unresolved for the *Prunus* KCS1-like, generic NHX1/2, and PavNHX37 candidates.

No source label, coordinate, protein length, reference ortholog, or homolog analogy was promoted into an accession, construct map, event certificate, targeting certificate, or biological-efficacy claim.

## Semantically frozen registries

All three audited CSVs are pinned by independent literal SHA-256 constants in code. The seals are not calculated from the files at import time and cannot self-authorize a mutation. Each loader performs semantic validation before checking its expected whole-file seal, so malformed inputs retain specific diagnostics while any otherwise valid mutation still fails closed.

The freeze includes complete row meaning, not just identifiers: title, DOI, primary URL, sample context, reported effect, limitation, candidate-to-evidence links, and chemistry values are all covered. Candidate/evidence associations and DOI/URL pairings are exact. Numeric CSV text has one canonical decimal spelling, so aliases such as `3.00` and `0.900` are rejected.

The `.gitattributes` contract pins the three sealed CSV paths to `text eol=lf`; `git check-attr` confirmed the rule under the Windows checkout where `core.autocrlf=true`.

## Protected-join guarantees

Raw frames must have exact type `pandas.DataFrame`; subclasses are rejected before caller-overridable dataframe methods can run. Provenance cells require exact strings and registered `record_id` namespaces. Raw row provenance is consumed into the immutable `almondlab.provenance.v1` ancestry namespace rather than retained as mergeable or reserved user columns.

`ProvenanceFrame` snapshots deep-freeze supported nested list, tuple, dict, set, and frozenset cells. `to_pandas()` recursively detaches those cells, so caller mutation cannot change protected state in either direction. Private assignment is blocked, and a SHA-256 content seal covering the frame, ancestry, and metadata is checked on every protected use; direct private-state tampering fails closed.

Joins preserve complete row ancestry through arbitrary chains, including empty intermediate results, without reserving ordinary user column names. Collision-free suffixes are planned deterministically. Join keys require one registered exact non-boolean kind per column and the same exact kind on both sides; boolean/integer and integer/float equality cannot pass by coercion. Null and cardinality validation complete before `pandas.merge` executes.

`measured`, `empirical`, and `literature_derived` are intentionally one empirical ancestry family and may be joined when all other contracts pass. Any join that would mix synthetic and empirical ancestry raises `SYNTHETIC_CONTAMINATION`; there is no production override or caller-controlled attribute path that can launder origin.

## TDD and verification record

Review repairs were reproduced RED before implementation. Exact regressions now cover the false PyAPX absence statement, recent-rice accession/readiness boundaries, complete registry-row mutation and DOI/URL reassociation, numeric aliases, chained ancestry and former reserved-name collisions, nested-cell mutation, private-state tampering, dataframe subclasses, exact provenance strings, exact key kinds and pre-merge validation, and the intentional measured-plus-literature empirical-family rule.

Final commands and observed results:

```text
.venv\Scripts\python.exe -m pytest tests/test_registries.py tests/test_safe_data.py -q -p no:cacheprovider
111 passed in 2.49s

.venv\Scripts\python.exe -m pytest tests/test_safe_data.py tests/test_registries.py tests/test_paper1_contracts.py -q -p no:cacheprovider
163 passed in 3.93s

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
967 passed, 3 expected POSIX-only skips in 117.34s

.venv\Scripts\python.exe -m compileall -q src tests
exit 0

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\public_data\phase2\Test-Phase2PublicData.ps1
Smoke tests: 22 passed, 0 failed
```

The three skipped tests exercise POSIX descriptor-relative cleanup and are platform-skipped on Windows.

## Repair commits

- `f739404`: admit the three verified rice-comparator NCBI records to the exact Phase 2 allowlist and correct exclusion text.
- `99dbbb7`: correct frozen candidate accession.version identities and readiness states.
- `61f5c37`: correct public evidence audit, manifest, seed, README, and sanitized acquisition receipt.
- `507f89a`: seal registry semantics and redesign protected joins.

## SHA-256 manifest

```text
e118ac2d590e054b2073cfa1677dd9dd8c1848dd9000a53267e33126fdb3e02f  src/almondlab/registries.py
fdb9823dcfcaed5ef10c14d5594bf1ccabe501df2808cb876084075aed650fc1  src/almondlab/safe_data.py
3296138c408220c9b5919cc5f1126bc18e1def9c5dd72ff0188d1c5ce8159bb8  data/evidence_registry.csv
8e95c90ee9d85180a0b2dee7ef71ae8471b9784da1bafd52bf4d0d9aa044d0ae  data/candidate_registry.csv
262a3b3210181d73bac416a6c0e09151de397fc8cc3752692a88d296a75f430a  data/reference_chemistry.csv
ef6a4127335c14b408827ee412f0b54132d9333508dd6fdb7c3a8e9a4a6b28ff  tests/test_registries.py
d8ee415146585c3dfe14a394c38c1dcfe28a62e6cb9309442852369728c5b75c  tests/test_safe_data.py
```

These hashes describe commit `507f89a`. Any later change to an owned file requires a refreshed manifest and affected verification results before publication handoff.
