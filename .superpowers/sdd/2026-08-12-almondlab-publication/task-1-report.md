# Publication Task 1 report — deterministic provenance and atomic run directories

## Outcome

Task 1 provenance received an exact-commit adversarial repair. The repository
now binds generated run claims to their creation seed/config digest, captures
Git identity from raw HEAD/index/tracked bytes without diff filters or index
stat hints, validates authentic NumPy seed states, accepts only interoperable
JSON integers and portable paths, and publishes a manifest through an
in-create and post-commit validation protocol.

This work establishes software provenance and filesystem integrity only. It
does not establish biological, greenhouse, safety, or field efficacy.

## Owned files

- `src/almondlab/provenance.py`
- `tests/test_provenance.py`
- `schemas/run_manifest.schema.json`
- this report
- `progress.md`

Concurrent verification files and `.gitattributes` were preserved and excluded
from the Task 1 commit.

## TDD evidence

The first focused run failed during collection because
`almondlab.provenance` did not exist. Tests were then added and implemented in
small red/green slices for canonical JSON/atomicity, seed trees, file/Git
capture, immutable manifests/hashes, run-directory confinement, finalization,
and schema validation.

Adversarial review cases were also reproduced before fixes. These included a
linked file-parent escape, caller-invented/self-referential artifacts, direct
`RunDirectory` construction, hidden staged Git content, dirty submodule
ambiguity, artifact mutation during finalization, manifest overwrite races,
post-commit durability ambiguity, and nonportable file-identity paths.

The final focused suite contains 137 tests. Boundary tests reject boolean or
string numeric coercion, nonfinite numbers, non-string keys, path traversal,
links/reparse points, collisions, inconsistent seed trees, unavailable-state
inventions, hash corruption, and unsafe finalization.

## Implemented boundaries

- Canonical JSON is compact, sorted, UTF-8, finite-only, and recursively
  validates string mapping keys.
- Records defensively deep-freeze caller data. Numeric and boolean fields use
  exact Python types without coercion.
- Named seed children are sorted before spawning; every node records entropy,
  spawn key, pool size, child count, generated uint32 state, and its complete
  immutable child map. Recorded nodes reconstruct the exact `SeedSequence`.
- The canonical-science hash excludes only the declared volatile fields: run
  ID, timestamps, Git dirty flag, absolute interpreter path, OS text, and raw
  Bayesian draws. The manifest hash includes all of them plus the science hash.
- Available file provenance contains exact portable path, SHA-256, and byte
  size. Unavailable file/Git records contain no invented values and use stable
  reasons. Capture detects mutation during reads.
- Git provenance binds exact HEAD to two identical raw snapshots and a final
  HEAD reread. It compares raw HEAD tree and index entries, hashes every tracked
  working-tree object directly through no-follow handles, hashes raw index
  blobs without textconv/filters, and records exact untracked bytes. It rejects
  assume-unchanged/skip-worktree special flags, unsupported object formats,
  index locks, unmerged/special modes, and dirty or mismatched submodules.
- `RunDirectory` cannot be publicly constructed around an existing directory.
  Creation claims a new safe ID, refuses every collision/link/traversal, and
  binds the root/run directory identities. Artifacts remain beneath the claimed
  `outputs/runs/<run_id>`.
- POSIX run/file/temp operations use descriptor-relative traversal and
  `O_NOFOLLOW`; run publication uses an atomic no-replace rename. Windows uses
  random private claims, reparse rejection, and repeated directory-identity
  checks with identity-safe cleanup. Python lacks portable Windows
  handle-relative no-follow creation; this residual privileged concurrent
  reparse-swap limitation is explicitly exposed by
  `FILESYSTEM_CONFINEMENT_LIMITATION` and tested.
- Atomic replacement flushes file bytes and, where supported, directory
  metadata. Replace failures preserve an existing destination and all temporary
  files are cleaned. Failures after the destination commit raise
  `AtomicCommitUncertainError` with `committed = True`.
- `RunDirectory` immutably records `creation_root_seed` and
  `creation_config_sha256`; finalization requires the manifest's root seed and
  explicit `creation_config_sha256` to match the claim.
- Manifest finalization validates the complete emitted schema/cross-field/hash
  document, keeps artifact handles open, revalidates inside exclusive create,
  revalidates after link publication, and recaptures the manifest plus every
  held artifact after commit. A detected post-commit mismatch removes only the
  exact committed manifest identity; if safe removal cannot be established it
  raises `AtomicCommitUncertainError` with the retained path.
- Windows file/directory cleanup uses delete-by-handle after identity matching;
  POSIX cleanup is descriptor-relative. Cleanup never checks one pathname
  object and then unlinks an attacker replacement. If identity-safe cleanup is
  unavailable, the temporary/quarantine path is retained and reported.
- Canonical JSON and every manifest integer use the I-JSON interoperable range
  `[-(2^53-1), 2^53-1]`, so accepted values are total before hashing. Direct
  seed construction validates the exact NumPy `SeedSequence` state.
- The checked-in JSON Schema v1.1 declares Draft 2020-12, uses conditional
  available/unavailable state branches, exact uint32 bounds, timestamp format,
  ECMAScript-compatible end assertions, reserved-device/trailing-dot/empty
  segment path rejection, and closed object shapes. A strict dependency-free
  project validator covers the schema subset and manifest cross-field/hash
  semantics. The external `jsonschema` gate is optional and is not a locked
  dependency; the current locked environment does not install it.

## Independent golden identity

The tests contain a manually specified complete manifest document, seed states,
and fixed expected hashes rather than deriving their expected values from the
implementation:

```text
canonical_science_hash a996babe2890e75893eb1d51cc5499acd3d7cd4eaad4e214a10688bf73a00c40
manifest_hash          b235d72389fa7ef81433b11de1657ead4803907aba44f674caca0df2db121a78
```

## Final verification

Focused Task 1 suite after the final cleanup hardening:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_provenance.py -q
```

```text
137 passed, 1 warning in 9.91s
```

Complete full repository suite before the final narrow descriptor-wrapper
cleanup refactor:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```text
802 passed, 1 warning in 116.50s
```

The fresh full rerun after that narrow refactor was interrupted at collection
when concurrent Publication Task 2 added `tests/test_registries.py` and
`tests/test_safe_data.py` before adding their `almondlab.registries` and
`almondlab.safe_data` modules. It reported two import errors and no provenance
test failure. The fresh 137-test focused result above is authoritative for the
post-refactor owned state; the prior complete 802-test run is retained as
full-suite evidence rather than misreported as post-refactor.

Per coordination, the post-refactor repository rerun explicitly excluded only
those two not-yet-implementable concurrent Task 2 tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings `
  --ignore=tests\test_registries.py --ignore=tests\test_safe_data.py
```

It completed with `794 passed, 10 failed in 113.66s`. Every failure was in the
concurrently edited `tests/test_paper1_contracts.py`: Pydantic could not
serialize a newly introduced `mappingproxy` in
`src/almondlab/paper1_contracts.py`. No provenance or schema test failed. This
unrelated concurrent state is reported exactly and was not modified by Task 1.

Dependency-free Draft 2020-12 schema check and optional external gate:

```text
dependency-free Draft 2020-12 subset: PASS
optional external jsonschema gate: NOT INSTALLED (not a locked dependency)
```

Python bytecode compilation passed for both implementation and tests. The only
pytest warning was a pre-existing environment permission warning while writing
`.pytest_cache`; test execution and temporary test directories were unaffected.
