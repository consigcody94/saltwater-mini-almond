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

The final exact-base rereview reproduced five further cases before repair: a
stateful artifact mapping whose repeated `items()` observations omitted later
checks, POSIX cleanup pathname replacement between identity checking and
deletion, Draft 2020-12 integral-float type semantics, an unbounded NumPy seed
pool allocation, and filesystem components exceeding portable UTF-8 limits.

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
- `artifact_paths` is observed exactly once at the public boundary. Its one
  `items()` result is materialized into a sorted immutable plain-string
  mapping; malformed pairs, non-string keys, non-string/`Path` values,
  duplicate items, and case-insensitive portable collisions fail before any
  hashing. Every later capture, held-handle check, and publication step uses
  only that snapshot, so caller mutation cannot remove a check.
- Windows file/directory cleanup uses delete-by-handle after identity matching;
  POSIX cleanup atomically renames the current descriptor-relative name, with
  no replacement, to an unguessable same-parent quarantine while the original
  handle remains open; it then opens and matches the quarantine handle before
  deletion. A mismatch never deletes the replacement. If no native no-replace
  primitive exists or quarantine deletion cannot be established, the source
  or quarantine is retained and the retained path is reported as uncertain.
- Canonical JSON and every manifest number use the finite interoperable
  magnitude `[-(2^53-1), 2^53-1]`; integers and floats outside it are rejected
  before hashing. The dependency-free validator matches Draft 2020-12's
  mathematical integer semantics (`1.0` is an integer; `1.5` is not), while
  the model's exact Python integer fields remain type-locked.
- This program registers NumPy `SeedSequence.pool_size` exactly as `4` in the
  model and schema and rejects any other value before invoking NumPy. Direct
  seed construction still validates the exact generated state.
- Every portable component is limited to 255 UTF-8 bytes and a complete
  portable artifact path to 1024 UTF-8 bytes. The dependency-free validator
  enforces the exact byte limits in addition to the schema's ASCII character
  bounds.
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

## Final verification after exact-base repair

Focused Task 1 suite after the final cleanup hardening:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_provenance.py -q
```

```text
150 passed, 3 skipped, 1 warning in 10.04s
```

The three skips are the deterministic POSIX file-replacement,
directory-replacement, and retained-quarantine cleanup tests on this Windows
host. They are platform-gated rather than claimed as executed here. The Windows
delete-by-handle race tests executed and passed. WSL and Docker are unavailable
in this environment; the POSIX implementation was source-audited against the
descriptor-relative quarantine design above, but still awaits independent
execution on a POSIX host.

Complete full repository suite on the final owned implementation plus the
then-current concurrent biology state:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```text
912 passed, 3 skipped, 1 warning in 114.28s
```

Dependency-free Draft 2020-12 schema check and optional external gate:

```text
dependency-free Draft 2020-12 subset: PASS
optional external jsonschema gate: NOT INSTALLED (not a locked dependency)
```

Python bytecode compilation passed for both implementation and tests. The only
pytest warning was a pre-existing environment permission warning while writing
`.pytest_cache`; test execution and temporary test directories were unaffected.
