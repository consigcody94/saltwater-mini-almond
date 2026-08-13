# Final Core Fix F report — independent verification migration

## Outcome

All eight core-owned acceptances (`1, 2, 3, 4, 5, 13, 19, 20`) now run on
the canonical density-aware mass/treatment contracts and write immutable,
hashed, wheel-portable verification artifacts. Pass state is caller-unsettable
and derived only by the central type-exact comparison evaluator. Acceptance 13
continues to name `core_v1.acceptance_13` and explicitly describes itself as a
numerical analytic oracle, not almond applicability or biological validation.

This work establishes virtual accounting and numerical verification only. It
does not establish almond, plant, GMO, kelp-trait, seawater-tolerance,
greenhouse, safety, or field efficacy.

## Owned files

- `src/almondlab/verification.py`
- `src/almondlab/verification_policy.py`
- verification fixture/manifests under `src/almondlab/resources/fixtures/`
- exact authoring mirrors under `tests/fixtures/`
- `tests/test_core_acceptance.py`
- `tests/test_verification_manifest.py`
- `tests/test_verification_resources.py`
- `pyproject.toml` (authorized JSON resource include only)
- `.gitattributes` (authorized LF rules for exact-byte verifier resources only)
- this report and one `progress.md` ledger line

Concurrent mass changes and `tests/test_mass_balance.py` were preserved and
excluded from this commit.

## TDD and migration evidence

The first collection attempt failed because the old verifier imported removed
`ExternalFlux`/`Flow` APIs. The first new record/policy RED milestone was:

```text
10 failed, 2 passed, 29 deselected
```

It covered caller-set pass state, boolean/string numeric coercion, scalar-kind
equality, non-string mapping keys, and complete policy authority. That slice
then reached `12 passed, 29 deselected`. Canonical acceptance 1/2 adversarial
tests reached `14 passed`; direct acceptances 3, 4, 5, 13, and 19 then passed.
The first combined manifest/resource/T20 run was `38 passed, 11 failed`; after
the manifest/resource and T20 migration it was `49 passed`. Later required
adversaries, exact policy locks, provenance, atomicity, and public provenance
API tests expanded the first committed focused suite to 99 tests.

An independent whole-core review of commit `716e4d4` then reproduced ten
false-positive/boundary classes. The follow-up RED matrix covered code-owned
all-entity scope, non-finite and malformed injected outputs, T13 domain
authority, explicit T20 volume literals, enum-derived T19 execution,
type-exact constructed policies, eager complete comparison-schema validation,
arbitrary-precision integers, resource-hash key/primary collisions, and
candidate-set membership. The initial new boundary slice failed 9/9 and the
reviewer blocker slice failed 10/12 before implementation; the combined
targeted matrix then passed 20/20.

The immutable-snapshot rereview of `778cfd6` passed its 122-test focused suite,
580-test committed-scope full suite, and 16-class exploit replay, but it found
two further false-pass/portability regressions: a boolean RO stock could be
coerced to numeric zero before validation, and Windows `core.autocrlf=true`
could change the frozen candidate bytes in a fresh checkout/archive. Both were
reproduced before the narrow fix. Model metrics are now type-checked before
arithmetic, and a temporary-repository checkout-index regression proves every
hash-locked YAML/JSON mirror materializes as the canonical LF bytes under
`core.autocrlf=true`.

Later immutable reviews found two final scalar-coercion edges. Matching floats
for frozen generator `seed`/`max_examples` fields compared equal to integers,
and falsy non-mappings in `auxiliary_artifacts_sha256s` silently selected the
empty default. Exact RED matrices of 12/12 and 4/4 reproduced them. Generator
metadata now passes exact positive-`int` validation before value comparison,
and only `None` selects the empty auxiliary-hash map. The final focused suite
contains 140 tests.

## Implemented authority

- `VerificationRecord.passed` is a read-only derived property and is not a
  dataclass field. JSON numbers are finite primitive `int|float` only (never
  bool/string coercions), `eq` is scalar-kind exact, and mapping keys must be
  strings. Optional hash maps default only on `None`; falsy non-mappings are
  rejected rather than erased.
- Schema-1 policy objects are revalidated against code-owned immutable values:
  all six physical min/max/label triples, numerical stops, ordered registry,
  artifact template, evidence label, and every tolerance. Constructed booleans
  cannot alias canonical numeric `0.0` or `1.0` values.
- Tests 1/2/20 use typed compartments/events/cursors, separate water kg and
  volume L, schema-v2 transaction IDs, canonical units (including alkalinity
  `mmol_c`), and fixture-literal transaction authority passed to
  `audit_ledger(..., expected_events=..., expected_transactions=...)`.
- Tests 1, 2, and 20 bind state, expected state, and ledger coverage to
  code-owned water-only/all-`ConservedEntity` registries, so a collectively
  shrunk fixture cannot shrink acceptance scope.
- The exact independent ledger oracle declares IDs, rows, ordered endpoints,
  phase/mode/evidence, carrier/density, per-entity amounts, audit quantities,
  every compartment × quantity branch, extrema, and next cursor without
  reading the observed audit.
- T20 uses immutable `TreatmentStream`/`ROParameters`, a complete paired RO
  ledger and selective-removal diagnostic with the concentrate destination.
- T13 observes both returned hydraulic domain decisions and compares them with
  a separate code-owned exact `core_v1.acceptance_13` policy/hash oracle.
- T19 executes the independently derived `ECKind` cross-product while its
  oracle remains a separate code-owned ordered six-pair tuple.
- T20 frozen cases report `counterexample`, never a falsely minimized result,
  with `hypothesis_shrunk: false`, exact first-in-manifest-order semantics,
  frozen input, and failing metrics. The candidate bytes are locked to SHA-256
  `6dadb7aaa883e113b28c6833ac544389a79c31c21b8b452097ddca3b17ef621e`,
  each selected input is verified as a candidate member, and explicit flow/RO
  volume-L errors are recorded separately from water-kg errors. Non-finite or
  malformed injected model output produces the first frozen counterexample;
  boolean model outputs are rejected before Python arithmetic can coerce them.
  Frozen generator seeds and example counts are exact positive integers before
  they are compared with the code-owned property settings.
- Exact-byte YAML and JSON verifier resources have repository-level `eol=lf`
  rules across authoring, packaged, and test mirrors. A clean-index
  materialization test runs with `core.autocrlf=true` and compares all resulting
  bytes with their canonical source bytes.
- Git provenance is associated only with the exact tracked loaded module;
  untracked status participates in dirty state and status-byte SHA-256. Public
  `capture_code_provenance()` and `code_version_from_provenance()` let
  downstream acceptances create truthful records with their own evidence
  labels without copying Git logic. Private aliases remain compatible.
- Auxiliary artifacts are hashed over exact written bytes and atomically
  replaced. Failure injection proves an existing target is preserved and temp
  files are cleaned.
- The resource-set test is deliberately exact. Future fixture additions must
  update both mirrors and the independent canonical set in one reviewed change.

## Exact mirrored bytes

```text
all_conserved_entities.yaml                    01fd37b1fd30472f3d78a45603697aaa14bf0639ce029f3ae1882e18c9d85da0
chemistry_handcheck.yaml                       8c7a93ce4becd6103fdb32d3baeca609b4304acd33abb1ed319e909eba3bc89c
conservation_case_manifest.yaml                a63f50c823c952f40501618fdb11edfc6c3b50abc530d398ae410f07015dd03f
conservation_case_manifest.candidates.json     6dadb7aaa883e113b28c6833ac544389a79c31c21b8b452097ddca3b17ef621e
ions_conservative.yaml                         4db1fdf3b689704b530985ab97aa8ed1f5cce6be9167a436bb8f1a64342ca7b4
no_purge.yaml                                  449d7b430b94cf8bab232dbf81856ab92248b1c7e14102a5308639d9fdf980fc
sufficient_purge.yaml                          7962129ab68292d0b5291d885b663bd46f7ea146ae86ea1d8abdf6bd3faeca05
water_one_day.yaml                             e0764def034695f840e2e9003b325d1c886bda446bec6c8cea4caf23471caaff
configs/thresholds.yaml                        8db94ecd637aac57b6f76d0d89dc9b68d90de59e1535cdaf8781a2714c4c7140
configs/verification.yaml                      64876d38c3bd90af141c76adcc2b7dc12e734b4fe6cd21d22235156b29fcc5f2
```

## Final verification after mass Fix G `aa8d303` and review repairs

Focused verification/policy/resource/adversarial suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_core_acceptance.py tests/test_verification_manifest.py tests/test_verification_resources.py -q -p no:cacheprovider --basetemp C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-f-aux-focused
```

```text
140 passed in 96.39s
```

Required core suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_schemas.py tests/test_chemistry.py tests/test_domains.py tests/test_hydraulics.py tests/test_contracts.py tests/test_mass_balance.py tests/test_treatment.py tests/test_core_acceptance.py tests/test_verification_manifest.py tests/test_verification_resources.py -q -p no:cacheprovider --basetemp C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-f-dda-final-core
```

```text
564 passed in 104.20s
```

Stable full repository suite after publication provenance commit `38f9631`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-f-dda-final-all
```

```text
710 passed in 111.59s
```

Before Fix G landed, the same required-core run was `505 passed, 14 failed`;
all 14 were the independently known mass-audit/underflow RED cases. They were
not hidden or patched in verification. The final counts above are post-commit.

## Installed-wheel isolation

The final offline wheel was built as:

```text
C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed\saltwater_mini_almond-0.1.0-py3-none-any.whl
SHA-256 C2A93F1B4E9AF3DF1F652011DECE9766C745CCE9A154000653770979396AFA0D
```

Exact build/install/path-isolation/smoke commands:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
git clone --no-local --no-checkout 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\outputs\saltwater-mini-almond' 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\fix-f-dda-fresh'
git -C 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\fix-f-dda-fresh' config core.autocrlf true
git -C 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\fix-f-dda-fresh' checkout --detach dda5490e087aa45ec9d92ee7d2af902f8c091769
Set-Location 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\fix-f-dda-fresh'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' build --wheel --offline --clear --python 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\outputs\saltwater-mini-almond\.venv\Scripts\python.exe' --out-dir 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed' .
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\outputs\saltwater-mini-almond\.venv\Scripts\python.exe' -m venv 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed-venv'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed-venv\Scripts\python.exe' -m pip install --no-deps --no-index 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed\saltwater_mini_almond-0.1.0-py3-none-any.whl'
$env:PYTHONPATH='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\outputs\saltwater-mini-almond\.venv\Lib\site-packages'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed-venv\Scripts\python.exe' -c "import almondlab, pathlib; p=pathlib.Path(almondlab.__file__).resolve(); print(p); assert 'wheel-f-dda-committed-venv' in str(p); assert 'saltwater-mini-almond\\src' not in str(p)"
Set-Location 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel-f-dda-committed-venv\Scripts\python.exe' 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\wheel_f_smoke.py'
```

It was installed with `--no-deps` into a fresh venv outside the checkout; the
existing locked project environment supplied third-party dependencies only via
`PYTHONPATH`. The loaded `almondlab.verification` path was inside that wheel
venv, not `src/`. The smoke enumerated and loaded 13 packaged fixtures, all
three packaged configs, ran all eight acceptances, validated each exact
auxiliary hash, and returned:

```text
WHEEL_SMOKE_OK 13 8 {'package_version': '0.1.0', 'git_sha': None,
'git_dirty': None, 'git_status_sha256': None,
'unavailable': ('git_sha', 'git_dirty', 'git_status_sha256')}
```

The wheel contains the JSON candidates file plus the 12 YAML fixtures and
`model_domains.yaml`, `thresholds.yaml`, and `verification.yaml`.

The detached build clone used `core.autocrlf=true`; the candidate bytes kept
their canonical digest and the manifest loader succeeded. All 16 packaged
YAML/JSON resources were LF-only. The three unrelated Paper-1 root configs had
`eol: unspecified`, proving the repository attributes remain verifier-scoped.

## Independent final verdict

The independent reviewer approved exact code SHA
`dda5490e087aa45ec9d92ee7d2af902f8c091769` with no remaining Critical,
Important, or Minor Fix-F code issues. Its immutable snapshot independently
passed focused `140/140`, required core `564/564`, Fix-F-scope full `598/598`,
and direct adversary `65/65` matrices. It replayed the four auxiliary-map,
twelve generator-integer, and RO-boolean exploits; all were rejected. Its
fresh `core.autocrlf=true` clone and Git archive retained canonical bytes, and
its independently built wheel had the same SHA-256
`c2a93f1b4e9af3df1f652011dece9766c745cce9a154000653770979396afa0d`.
The reviewer also confirmed the analytic-only/no-biological-claim boundary.

`git diff --check` was clean before final staging.
