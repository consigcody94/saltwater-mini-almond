# Task 2 publication report: evidence registries and protected joins

Status: Round 3/5 snapshot-provenance correction is implemented and proportionally verified; fresh independent exact review is required.

## Delivered scope

- `data/evidence_registry.csv`: the complete 24-source Section 16 evidence set, with 19 DOI-anchored records and 5 official URL-only records.
- `data/candidate_registry.csv`: 6 frozen primary candidates plus all 14 held prequalification candidates. It contains no winner, best-candidate, or biological-efficacy field.
- `data/reference_chemistry.csv`: all 5 source-reported rootstock-screen recipes. EC remains a reported measurement and is never used to derive ion composition.
- `src/almondlab/registries.py`: strict UTF-8/LF parsing, exact schemas and associations, canonical decimal grammar, literal whole-file audit seals, candidate cross-checks, and typed chemistry validation.
- `src/almondlab/safe_data.py`: sealed defensive `ProvenanceFrame` snapshots and fail-closed, arbitrarily chainable `safe_join` behavior.
- `tests/test_registries.py` and `tests/test_safe_data.py`: focused positive, malformed-input, mutation, and adversarial regression coverage.

## Literature and sequence-record correction

The official 2025 rice paper reports three sequence accessions: PyAPX `AY282755.1`, PyMnSOD `DQ146477.2`, and the *Kappaphycus alvarezii* Na+/H+ antiporter under the author label `KaNa+/H+` as `MT473962`. The deposited `MT473962` record resolves to accession.version `MT473962.1`.

The paper reports 250 mM NaCl applied every 3 days, 30 seeds per dish with 3 dishes, and germination read on day 10. It also reports a recovered homozygous T1 inventory of 12 PyAPX, 11 PyMnSOD, and 9 KaNa+/H+ lines. Those inventory totals are not endpoint experimental sample sizes; endpoint-specific independent-line n beyond the germination dish design remains unresolved in this extraction. These are source-reported details, not efficacy claims for the AlmondLab program.

The guarded small-data workflow independently fetched and validated the corresponding NCBI records:

- `AY282755.1`: 1,041 bp *Pyropia yezoensis* cytosolic APX mRNA with complete CDS; FASTA SHA-256 `1fa50794a31470077978611121ada346a9a0d5f8fe8a1bd58864617e3804113a`.
- `DQ146477.2`: 910 bp *Pyropia yezoensis* MnSOD complete CDS; FASTA SHA-256 `cd64caf3868d196b869e45415fbb09b21a97c0a7d96e555f11e449ba69da0d0d`.
- `MT473962.1`: 1,194 bp *Kappaphycus alvarezii* Na+/H+ antiporter partial CDS; FASTA SHA-256 `182bc6de02e53212b7319f7ed9f1549ad32e34f8f12654492b12cbe8fdf14733`. This conflicts with the paper's description of unversioned `MT473962` cloned material as a full-length coding sequence; exact construct identity and completeness therefore remain unresolved.

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
- PQ_KaNa+/H+ records the paper's unversioned `MT473962`/full-length coding-sequence claim separately from repository-resolved partial-CDS `MT473962.1`; that identity/completeness conflict, exact construct mapping, a complete construct sequence, and direct transport characterization remain unresolved.
- Exact construct-ready identities remain unresolved for the *Prunus* KCS1-like, generic NHX1/2, and PavNHX37 candidates.

No source label, coordinate, protein length, reference ortholog, or homolog analogy was promoted into an accession, construct map, event certificate, targeting certificate, or biological-efficacy claim.

The separately delivered user-facing program design was synchronized to the same C2 and KaNa boundaries. Its Round 2/5 SHA-256 is `53ab0c973a05a36014555fd855b8201adb4fe9bab1b4641837524adf1c9f0c79`; it is outside this standalone repository and is not staged here.

## Semantically frozen registries

All three audited CSVs are pinned by independent literal SHA-256 constants in code. The seals are not calculated from the files at import time and cannot self-authorize a mutation. Each loader performs semantic validation before checking its expected whole-file seal, so malformed inputs retain specific diagnostics while any otherwise valid mutation still fails closed.

The freeze includes complete row meaning, not just identifiers: title, DOI, primary URL, sample context, reported effect, limitation, candidate-to-evidence links, and chemistry values are all covered. Candidate/evidence associations and DOI/URL pairings are exact. Numeric CSV text has one canonical decimal spelling, so aliases such as `3.00` and `0.900` are rejected.

The `.gitattributes` contract pins the three sealed CSV paths to `text eol=lf`; `git check-attr` confirmed the rule under the Windows checkout where `core.autocrlf=true`.

## Protected-join guarantees

Raw frames must have exact type `pandas.DataFrame`; subclasses are rejected before caller-overridable dataframe methods can run. Provenance cells require exact strings and registered `record_id` namespaces. Raw row provenance is consumed into the immutable `almondlab.provenance.v1` ancestry namespace rather than retained as mergeable or reserved user columns.

`ProvenanceFrame` snapshots deep-freeze supported nested list, tuple, dict, set, and frozenset cells. `to_pandas()` recursively detaches those cells, so caller mutation cannot change protected state in either direction. Private assignment is blocked, and a SHA-256 content seal covering the frame, ancestry, and metadata is checked on every protected use; direct private-state tampering fails closed.

Joins preserve complete row ancestry through arbitrary chains, including empty intermediate results, without reserving ordinary user column names. Collision-free suffixes are planned deterministically. Join keys require one registered exact non-boolean kind per column and the same exact kind on both sides; boolean/integer and integer/float equality cannot pass by coercion. Null and cardinality validation complete before `pandas.merge` executes.

Every protected join has an inclusive 10,000-row ceiling for each input and for the result. Oversized inputs and an exactly predicted oversized output fail before `pandas.merge`; the materialized result is always checked again. Violations raise stable `JOIN_ROW_LIMIT_EXCEEDED` details containing `maximum_rows`, `observed_rows`, and the validation stage.

`measured`, `empirical`, and `literature_derived` are intentionally one empirical ancestry family and may be joined when all other contracts pass. Any join that would mix synthetic and empirical ancestry raises `SYNTHETIC_CONTAMINATION`; there is no production override or caller-controlled attribute path that can launder origin.

## TDD and verification record

The second exact rereview produced four Important findings. New tests were run against the unfixed code first: the selected 11-case command produced 10 expected failures and 1 passing inclusive-10,000 control. The failures covered left and right inputs of 10,001 rows, predicted 10,002-row outer results under all three permitted cardinalities, a defensive post-merge result check, C2 unsafe targeting language, rice line-inventory/sample-size conflation, KaNa identity/completeness conflict, and structured public-manifest separation. The final one-to-many and many-to-one regressions were then strengthened to use their permitted duplicate shapes, each producing an exactly predicted 10,001-row outer result.

Exact regressions now also cover the false PyAPX absence statement, recent-rice accession/readiness boundaries, complete registry-row mutation and DOI/URL reassociation, numeric aliases, chained ancestry and former reserved-name collisions, nested-cell mutation, private-state tampering, dataframe subclasses, exact provenance strings, exact key kinds and pre-merge validation, and the intentional measured-plus-literature empirical-family rule.

Final commands and observed results:

```text
.venv\Scripts\python.exe -m pytest tests/test_safe_data.py tests/test_registries.py -q -p no:cacheprovider
120 passed in 7.53s

.venv\Scripts\python.exe -m pytest tests/test_safe_data.py tests/test_registries.py tests/test_paper1_contracts.py -q -p no:cacheprovider
181 passed in 8.79s

.venv\Scripts\python.exe -m pytest tests/test_safe_data.py tests/test_registries.py tests/test_contracts.py tests/test_schemas.py tests/test_verification_manifest.py tests/test_verification_resources.py -q -p no:cacheprovider
272 passed in 8.11s

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
1057 passed, 3 skipped in 127.78s

.venv\Scripts\python.exe -m compileall -q src tests
exit 0

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\public_data\phase2\Test-Phase2PublicData.ps1
Smoke tests: 22 passed, 0 failed
```

The three full-suite skips are the documented POSIX descriptor-relative cleanup cases on Windows (`tests/test_provenance.py` lines 3647, 3692, and 3738). Public verification additionally passed all 13 local snapshot hashes, parsed 23 manifest datasets with 23 unique IDs, confirmed LF plus terminal newline and `text eol=lf` for all three canonical CSVs, and found none of seven forbidden stale-claim patterns across the nine implicated registry/public/program-design surfaces.

For TDD provenance, an earlier interim integration run reached 176 passes and 5 failures, all five in concurrent intentionally RED Paper 1 YAML hardening tests owned by the biology task; no registry or safe-data test failed. That interim result was superseded after biology commit `38da80d` by the 181-test integration and 1,057-test full-suite passes above.

### Round 3/5 snapshot-provenance correction

Fresh exact review found that `data/public/README.md` incorrectly described each local hash sidecar as wholly frozen at one historical commit even though reviewed documentation/data entries had since been refreshed. A new deterministic regression failed first on the missing mixed-snapshot disclosure. Independent `git diff --quiet` checks then established the narrower history that the prose may claim: all five unchanged top-level acquisition entries remain byte-identical to `0c61054`, and the three unchanged Phase 2 module/entry-point/offline-test entries remain byte-identical to `f739404`; the reviewed README entries are newer.

The corrected README now describes both sidecars as mixed repository snapshots. It states that each line encodes only the current bytes of its named file, not a whole-tree or single-commit identity, and distinguishes the current reviewed documentation/data surfaces from unchanged acquisition implementation entries with independently verified earlier history. Both sidecar comments make the same per-file boundary explicit, and the refreshed top-level README entry is exact.

Round 3 verification observed:

```text
.venv\Scripts\python.exe -m pytest tests/test_registries.py::test_public_snapshot_sidecars_hash_current_files_and_describe_mixed_history -q -p no:cacheprovider
1 passed in 0.89s

.venv\Scripts\python.exe -m pytest tests/test_registries.py -q -p no:cacheprovider
71 passed in 2.24s

.venv\Scripts\python.exe -m pytest tests/test_safe_data.py tests/test_registries.py tests/test_contracts.py tests/test_schemas.py tests/test_verification_manifest.py tests/test_verification_resources.py -q -p no:cacheprovider
273 passed in 8.14s

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\public_data\phase2\Test-Phase2PublicData.ps1
Smoke tests: 22 passed, 0 failed

deterministic SHA-256 sidecar verification
13/13 entries exact
```

Round 3 core commit: `2e3a82a` (`docs: correct mixed snapshot provenance`). Its owned-file SHA-256 values are:

```text
8ff4165665dff1cb39818ca4e40ac7b4b41651779ef74016e065080d150a0543  data/public/README.md
e0310cb704fbdac90389d130dcc2e85f50ac750df2cb833de31c219d150cf4fd  data/public/local_snapshot.sha256
1c8b1feb679f0634f1e6ea90ec8abf6d38169aca626597031457c7e856068592  scripts/public_data/phase2/local_snapshot.sha256
0a4b7b41f6bcbc1f4adbeea443d295c4d8c2a567f42fcfc3e94f82814ccf2c88  tests/test_registries.py
```

## Repair commits

- `f739404`: admit the three verified rice-comparator NCBI records to the exact Phase 2 allowlist and correct exclusion text.
- `99dbbb7`: correct frozen candidate accession.version identities and readiness states.
- `61f5c37`: correct public evidence audit, manifest, seed, README, and sanitized acquisition receipt.
- `507f89a`: seal registry semantics and redesign protected joins.
- `9a90dfb`: close the four Round 2/5 registry, protected-join, identity, and sample-semantics findings.

## SHA-256 manifest

```text
bcc7956eaf420fb86cb2d238edb17c8c42e9c816b54401f2e638b413c8de7df1  src/almondlab/registries.py
9ace0909444cf3456d85f9a1311e71864c642d824148c74d1d582f29bfe54a1a  src/almondlab/safe_data.py
68925e3862beb823c60a91842588f649c972f07d489a80d66fd51867583fcf05  data/evidence_registry.csv
877c7767719f307c19b75fc314e04229a329a6e3cb3cc385d76697c67ce28664  data/candidate_registry.csv
262a3b3210181d73bac416a6c0e09151de397fc8cc3752692a88d296a75f430a  data/reference_chemistry.csv
aea2d85924d9278285a9add201a04109285acbd706d3c7c0f007803e435eb3a0  tests/test_registries.py
ab33891bd64ff0a3f54bc00219da133affe94b5a1fa9fa544865d3228feb60e7  tests/test_safe_data.py
```

These hashes describe exact core commit `9a90dfb`. Any later change to an owned file requires a refreshed manifest and affected verification results before publication handoff.
