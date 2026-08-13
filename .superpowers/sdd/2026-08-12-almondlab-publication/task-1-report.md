# Publication Task 1 report — deterministic provenance and atomic run directories

## Outcome

Task 1 is complete. The repository now has strict immutable run-provenance
records, deterministic named NumPy `SeedSequence` trees, exact file/lock/Git
identity capture, separate canonical-science and whole-manifest hashes, and
collision-safe run directories with atomic artifact/manifest commits.

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

The final focused suite contains 112 tests. Boundary tests reject boolean or
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
- Git provenance binds exact HEAD to two identical snapshots and a final HEAD
  reread. Dirty identity hashes porcelain status, staged binary diff, unstaged
  binary diff, and exact untracked-file hashes. Dirty or mismatched submodules
  fail closed.
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
- Manifest finalization verifies every declared artifact, requires key/path
  identity, re-captures artifacts immediately before commit, excludes the
  manifest from its own artifact set, and exclusively creates
  `run_manifest.json` without overwrite.
- The checked-in JSON Schema declares Draft 2020-12, uses conditional
  available/unavailable state branches, exact uint32 bounds, timestamp format,
  portable path patterns, and closed object shapes. A strict dependency-free
  project validator covers the schema subset and manifest cross-field/hash
  semantics. An independent `jsonschema` 4.26 validator was used as a
  publication verification gate without adding an undeclared dependency.

## Independent golden identity

The tests contain a manually specified complete manifest document, seed states,
and fixed expected hashes rather than deriving their expected values from the
implementation:

```text
canonical_science_hash 3469c461bc90cbdcf077d595935f14ba6294b142e201c5212d632dc350c830ff
manifest_hash          1c11151c196dcb8650fd5b462260eddcdee8277435aeb6f4ee03c81943fdcbf4
```

## Final verification

Focused Task 1 suite after the final defensive edit:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_provenance.py -q
```

```text
112 passed in 7.08s
```

Full repository suite before the final narrow Windows file-identity recheck:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

```text
694 passed in 110.33s
```

The fresh post-edit, cache-disabled full suite then produced `693 passed, 1
failed in 111.54s`. The only failure was the separately owned verifier's
Windows autocrlf resource-materialization regression. Its immediate isolated
rerun, with no edit, passed `1 passed in 0.72s`; this is recorded as a transient
concurrent shared-worktree verifier failure, not hidden as a clean full result.
The post-edit Task 1 suite above is the authoritative focused result.

Independent Draft 2020-12 schema check using the preinstalled external runtime:

```text
jsonschema 4.26.0 Draft202012Validator.check_schema + FormatChecker
Draft202012Validator schema+golden: PASS
```

Python bytecode compilation passed for both implementation and tests. The only
pytest warning was a pre-existing environment permission warning while writing
`.pytest_cache`; test execution and temporary test directories were unaffected.
