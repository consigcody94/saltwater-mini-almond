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

The last narrow rereview then reproduced two remaining boundaries before
repair: replacement of a verified POSIX quarantine name after its handle
`fstat` but before pathname deletion, and case variants of the reserved
`run_manifest.json` name in model, snapshot/finalize, document-validator, and
schema paths. File and directory race regressions fail if a pathname delete is
attempted after verification.

The first identity/phase rereview of the no-replace-rename repair then exposed
two high-priority publication windows and one test-platform gap. The staged
descriptor was not held through native publication, a native helper that
renamed and then raised could escape with the wrong phase classification, and
the legacy hardlink-failure test was not restricted to the Windows fallback.
The deterministic file schedule was RED with 9 failures and 2 controls passing;
the equivalent run-directory schedule was RED with 8 failures. Later narrow
RED slices reproduced a setup-time run-claim cleanup leak (1 failure, 1 control
pass), three `fdopen`-failure descriptor leaks, and two stale recovery-path
reports after an fsync-time target disappearance. Each slice was made green
before the combined suite ran. A final audit also reproduced two successful
native returns that left both target and staged names bound to the same inode;
both file and run-directory paths now refuse that non-consuming publication.

The final focused suite has 202 passing cases on this Windows host. Boundary
tests reject boolean or string numeric coercion, nonfinite numbers, non-string
keys, path traversal, links/reparse points, collisions, inconsistent seed
trees, unavailable-state inventions, hash corruption, unsafe finalization,
and every case-insensitive reserved-manifest artifact component.

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
- POSIX file publication holds the descriptor returned by exclusive temporary
  creation through write, flush, file `fsync`, both validation phases, native
  publication, and target reconciliation. Immediately before rename it opens
  the temporary name descriptor-relative with `O_NOFOLLOW|O_CLOEXEC`, requires
  a regular file, and matches the held `(st_dev, st_ino)` identity. Immediately
  after rename it opens the target the same way, matches that identity, and
  keeps the verified target handle through post-publication validation and
  directory `fsync`. The committed-identity out-parameter is populated only
  after a final target-name identity proof. Run-directory claims use the same
  protocol with directory descriptors and retain their child/target handles
  through `_from_claim` validation and root-directory `fsync`.
- Every return and exception from the native POSIX rename helper is reconciled
  against both names and the held staged identity. An exact target is
  classified as published; an absent or provably different target together
  with the exact staged temporary is prepublication; all other combinations
  are committed-uncertain. Thus a helper that renames and then raises cannot
  leak a raw exception, an exception before rename and an ordinary collision
  remain `committed=False`, an unrelated concurrent target is preserved, and
  missing/replaced/ambiguous names never yield success or a stale committed
  identity. Recovery paths are reported only after handle-based observation of
  the object currently at that name.
- Atomic replacement flushes file bytes and, where supported, directory
  metadata. Replace failures preserve an existing destination. Cleanup prefers
  retaining recoverable bytes to deleting an object through a name that could
  have been replaced. Failures after destination publication raise
  `AtomicCommitUncertainError` with `committed = True`.
- `RunDirectory` immutably records `creation_root_seed` and
  `creation_config_sha256`; finalization requires the manifest's root seed and
  explicit `creation_config_sha256` to match the claim.
- Manifest finalization validates the complete emitted schema/cross-field/hash
  document, keeps artifact handles open, revalidates inside exclusive create,
  publishes the temporary manifest with the platform's secure atomic
  no-replace rename (`renameat2(RENAME_NOREPLACE)` on Linux or
  `renameatx_np(RENAME_EXCL)` on macOS), revalidates after publication, and
  recaptures the manifest plus every held artifact after commit. Successful
  publication consumes the temporary name, so the normal path neither creates
  a hardlink nor invokes identity-safe quarantine cleanup. If the secure
  no-replace primitive is unavailable, publication fails in the pre-commit
  phase. A detected post-commit mismatch removes only the exact committed
  manifest identity; if safe removal cannot be established it raises
  `AtomicCommitUncertainError` with the retained path.
- `artifact_paths` is observed exactly once at the public boundary. Its one
  `items()` result is materialized into a sorted immutable plain-string
  mapping; malformed pairs, non-string keys, non-string/`Path` values,
  duplicate items, and case-insensitive portable collisions fail before any
  hashing. Every later capture, held-handle check, and publication step uses
  only that snapshot, so caller mutation cannot remove a check.
- `run_manifest.json` is reserved as an artifact component by ASCII-portable
  casefold on every platform. `RunManifest`, the one-shot artifact snapshot,
  finalization rechecks, the semantic document validator, and the artifact-only
  JSON Schema reject `RUN_MANIFEST.JSON`, mixed-case variants, and the same
  component nested within a path. Config/input provenance paths are not
  over-restricted by the artifact-only schema rule.
- Windows file/directory cleanup uses delete-by-handle after identity matching;
  POSIX cleanup atomically renames the current descriptor-relative name, with
  no replacement, to an unguessable same-parent quarantine while the original
  handle remains open. It opens and matches the quarantine handle, but performs
  no later `unlink` or `rmdir` by name because that name can be replaced after
  `fstat`. The verified quarantine is therefore retained deliberately; a
  mismatch likewise never deletes the replacement.
- Cleanup phase is explicit. Before publication, retained staging/temp data
  raises `AtomicCleanupRetainedError` with `committed = False`. After any target
  publication, retention or identity ambiguity raises
  `AtomicCommitUncertainError` with `committed = True`. Both expose exact
  recovery locations; post-commit errors expose all locations through
  `retained_paths` and the first through `retained_path`. Recovery must stop
  concurrent writers, preserve and independently inspect the reported paths,
  reconcile the destination according to `committed`, and only then remove
  retained names through an operator-controlled offline procedure.
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

## Final verification after identity-bound phase repair

Focused Task 1 suite, with the cache plugin disabled to avoid the workspace's
pre-existing `.pytest_cache` permission warning:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_provenance.py -q -p no:cacheprovider
```

```text
202 passed, 3 skipped in 11.01s
```

The three skips are real-filesystem POSIX integration cases for replacement
immediately before quarantine rename and verified-quarantine retention. They
are platform-gated and are not claimed as executed on this Windows host. The
new file and directory post-`fstat`/pre-delete regressions execute on Windows
through deterministic syscall emulation and passed; they assert that neither
pathname `unlink` nor `rmdir` is invoked. Phase-aware retained cleanup for both
files and run directories also executed through the real state machines with
controlled syscall boundaries. Deterministic forced-POSIX schedules additionally
exercised normal `atomic_create_bytes`, `finalize_manifest`, and `RunDirectory`
publication. They proved held staged and verified-target descriptors, exact
pre/post identity checks, two file-validation phases, successful no-replace
rename with no hardlink and no retained temporary, same-byte new-inode swaps,
directory/symlink swaps, the precheck-to-rename race, helper exceptions before
and after rename, collisions, target replacement, both names missing, and
fsync-time target disappearance. The unavailable-native-primitive schedule
failed before publication with `committed=False` and an exact retained recovery
path. The legacy `os.link` failure regression is now Windows-only, while the
forced-POSIX suite fails immediately if `os.link` is invoked. Four forced-POSIX
replacement schedules additionally prove successful overwrite, exception
before replacement with the old target preserved, exception after replacement,
and post-replacement target substitution.

WSL, Docker, and another POSIX runtime are not available here. The three real
POSIX integration cases therefore remain platform-skipped on this Windows host;
Linux `renameat2(RENAME_NOREPLACE)` and macOS `renameatx_np(RENAME_EXCL)` still
require fresh native-POSIX execution/review rather than being claimed here.

The combined repository suite was also run against the current concurrent
biology/registry repair worktree:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

```text
1063 passed, 3 skipped in 120.58s
```

This final combined run used committed biology and registry repairs plus the
unstaged Task 1 provenance diff. Exact-index verification, native-POSIX
execution, and a fresh independent Task 1 rereview remain required.

Dependency-free Draft 2020-12 schema coverage is included in the focused suite.
The optional external gate remains unavailable:

```text
dependency-free Draft 2020-12 subset: PASS
optional external jsonschema gate: NOT INSTALLED (not a locked dependency)
```

Python bytecode compilation and owned-file diff checks passed after the narrow
repair. No biological model, evidence registry, candidate registry, or core
contract file is part of this Task 1 change.
