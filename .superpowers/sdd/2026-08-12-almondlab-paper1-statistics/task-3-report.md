# Paper 1 Task 3 report — restricted randomization and unit audit

## Status

Implementation is complete in the working tree at base commit
`5818eeb09f69c7e17e743561927325a67e7d99a9`. Nothing was added to the Git
index or committed. The Paper 1 progress ledger was intentionally not edited;
the controller must obtain shared-index authorization before staging.

This work validates allocation and inference structure only. Every manifest,
audit, fixture, and acceptance record is `synthetic_only`. The implementation
makes no construct-performance, survival, salt-tolerance, yield, biosafety,
regulatory, or preferred-candidate claim.

## Implemented public boundary

`src/almondlab/design.py` now supplies:

- exact, frozen physical inputs: `BaselinePlant`, `BaselineRoster`,
  `PositionSlot`, and `PositionMap`;
- exact `run_sequence_ordinal` values on physical slots and allocation rows;
- a discovery-only `Paper1DesignConfig` consumer and a separate frozen
  `ConfirmationDesignConfig`, without loosening the discovery contract;
- frozen `AllocationRecord`, literal-order `Task3SeedTree`,
  `RandomizationManifest`, `BlindedProjection`, `ExperimentalUnitSpec`,
  `ExperimentalUnitAudit`, `ObservationIdentityRecord`, and
  `CohortIdentitySet` models;
- the authoritative signature
  `randomize(config, root_seed, *, position_map, baseline_roster)`;
- `validate_experimental_units(records, spec, *, cohorts=None,
  observations=())` with reservoir-level water replication and mandatory
  `PSEUDOREPLICATION` refusal for plant/pot/observation aliases;
- canonical reconstruction boundaries for discovery config, confirmation
  config, rosters, position maps, manifests, cohort sets, specs, and audits;
- `cohort_identity_set(...)` and `validate_cohort_separation(...)`, which
  derive exhaustive identity sets from canonical manifest/roster/map inputs,
  check plants, physical batches, reservoirs, water batches, runs, and
  non-null transformation events, and enforce
  `max(discovery ordinal) < min(confirmation ordinal)` from the actual physical
  schedules;
- a separate staff-facing blinded projection which omits group, water, batch,
  and event identities;
- strict loaders for the full physical randomization fixture and literal
  shared-reservoir trap CSV;
- `publish_design_acceptance(...)`, which evaluates public
  `VerificationRecord` objects for Acceptances 6 and 14 before staging one
  fresh `verification/` directory and renaming it only after all four files
  are complete and hashed.

The Task 3 seed representation is deliberately separate from
`provenance.SeedTree`. It records one `SeedSequence(root_seed).spawn(7)` call
in this literal order: `run_block_ordering`, `reservoir_identity`,
`transformation_batch`, `plant_identity`, `position`, `blind_code`, and
`movement_schedule`, with exact spawn keys `(0,)` through `(6,)`, pool size 4,
and pinned `PCG64` generators.

## Discovery and confirmation designs

The discovery fixture remains the registered 720-plant design:

- 9 groups × 2 waters × 2 runs × 4 reservoirs/run/water × 5 plants = 720;
- 16 independent water loops and 45 plants per loop;
- 560 candidate/empty-vector rows with physical batch identities;
- 160 sham/unmodified rows with batch and event identity not applicable;
- every candidate and empty vector is globally 40/40 across `batch_a` and
  `batch_b`, with each five-plant cell split 3/2 or 2/3;
- all 720 plant IDs and all 720 positions come from the supplied physical
  inputs and are used exactly once.

The separate confirmation contract accepts one to four selected C1–C6 IDs in
registered order plus `empty_vector`. It requires at least two physical runs,
exactly six `(water_id, reservoir_id)` loops per water total across those runs,
and exactly 5 or 6 plants per group/reservoir cell. Tests cover the boundary
families directly:

- one candidate + empty vector at 5 plants/cell: 120 plants;
- four candidates + empty vector at 6 plants/cell: 360 plants.

Every confirmation arm crosses two new physical batches with exact global
balance. Confirmation randomization can consume a caller-supplied discovery
maximum as an early local check, but the authoritative cohort boundary ignores
that claim and recomputes later-run authority from both actual manifests and
position maps.

## Strictness and canonical reconstruction

Public identity strings require exact primitive `str`, are trim-free,
nonempty, and control-character-free. Exact integer fields reject booleans,
numeric strings, floats, negatives, and values outside the interoperable JSON
safe-integer range. Pretreatment canopy accepts only primitive `int`/`float`,
uses guarded conversion, and requires a finite positive result; a valid
`1.0e100` measurement is accepted while an overflowing huge integer is
rejected structurally.

Canonical boundaries reconstruct every nested plant, slot, allocation record,
seed child, seed tree, cohort identity, and spec before RNG or audit work.
They reject dataclass `object.__setattr__` forgeries, subclass-surrogate
strings, equality-compatible `4.0` seed pool sizes, wrong seed names/spawn
keys/entropy, stale allocation hashes, wrong manifest versions, mutable
movement schedules, and copied Pydantic discovery configs that bypassed field
validation.

Physical validation occurs before creating `SeedSequence`. It checks exact
capacity, group/batch/stratum crossing, globally unique physical batch IDs,
unique non-null transformation event IDs, exact loop membership, one
water-batch identity per physical loop, one-to-one run/ordinal authority, and
roster/position cohort agreement.

## Fixture and package coordination

Exact authoring/runtime mirrors were added for:

- `paper1_small.yaml`: 528,427 bytes,
  SHA-256 `beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6`;
- `shared_reservoir_trap.csv`: 1,626 bytes,
  SHA-256 `989f31f87278703841334459ad73780b4164e6f3eac675b253976ec11c7438e1`.

The loader also records independent raw section hashes:

- baseline roster raw bytes:
  `c3ff338bbd91f915d2aabb57e69ea1f642c550008e7416426d7cd690d756a97b`;
- position map raw bytes:
  `6d16d016df97cff2b60ee86062333ec5c22fa18e76487b0df49b0b17a34d50e5`.

The raw discovery config hash is
`d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0`.
CSV package inclusion was added to `pyproject.toml`; exact CSV LF attributes
were added to `.gitattributes`; and the verification-resource registry and LF
materialization test now include both new fixtures while preserving the frozen
core set. The main specification already named `shared_reservoir_trap.csv`, so
no trace filename edit was necessary.

## TDD evidence

The controller witnessed the required initial RED:

```text
.venv\Scripts\python.exe -m pytest tests\test_design.py
0 collected / 1 collection error
ModuleNotFoundError: No module named 'almondlab.design'
```

The expanded behavior test initially produced the same missing-module import
failure. The coordinated Task 1 boundary was independently RED with 2 failures
and 6 passes: numeric strings `"4"` and `"5"` were being coerced into the two
allocation-count integers.

Subsequent adversarial RED/GREEN cycles caught and repaired:

- missing global batch balance, physical position metadata correspondence, and
  recursive audit-map freezing (3 expected failures before repair);
- cross-group reuse of a physical batch ID before RNG creation (1 failure);
- the absent confirmation config/revalidation API (collection ImportError);
- missing confirmation run ordinals and discovery/confirmation order authority;
- caller-authored cohort sets capable of omitting physical identity reuse;
- seed child/root pool values accepting `4.0`, unfrozen manifest versions, and
  an unpermitted movement schedule (5 expected failures before repair);
- duplicate transformation event IDs and per-position loop water-batch
  relabeling (1 expected failure before repair).

Two test-harness defects were corrected transparently: a huge integer needed
an explicit pytest ID to avoid Python's integer-to-string safety limit, and a
water-batch reuse mutation was changed from one slot to its whole physical
loop after loop-consistency validation correctly began failing earlier.

## Verification evidence

Fresh final commands after the last production/test correction:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_design.py -q
71 passed in 8.84s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
1164 passed, 3 skipped in 127.71s
```

The three skips are the existing Windows skips for POSIX descriptor-relative
cleanup in `tests/test_provenance.py` at lines 4002, 4047, and 4093.

Earlier post-confirmation/revalidation focused gates were also green:

```text
design + contracts + provenance + verification resources
363 passed, 3 skipped in 21.17s

design + Paper 1 contracts + biology + core acceptance
+ verification manifest/resources
399 passed in 112.64s
```

`python -m compileall -q src/almondlab` completed successfully, and
`git diff --check` returned no whitespace errors.

## Wheel and installed-resource smoke

The project `.venv` does not expose `pip`, `build`, `hatch`, or `uv`, so the
first ordinary `pip wheel` attempt could not start. The controller supplied a
no-network cached Hatchling backend. With a task-scoped `PYTHONPATH` containing
only that cached backend and its cached dependencies, this command succeeded
without mutating site-packages:

```text
.venv\Scripts\python.exe -m hatchling build -t wheel -d work/task3-wheel-hatch/dist
```

The resulting wheel was 206,530 bytes with SHA-256
`5ecfadd94db7cf9d8efe1a6528c4aeaedf9fef8410fbc63c8909930be920a64e`.
It was extracted into an isolated task directory, and Python imported
`almondlab.design` from that extracted wheel path. `importlib.resources`
returned exact byte matches for both new packaged fixtures (528,427 and 1,626
bytes). After recording those results, only the explicitly generated
`work/task3-wheel` and `work/task3-wheel-hatch` directories were removed;
`work/` has no remaining Task 3 artifacts.

## Adversarial matrix self-review

1. Exact full 720 allocation and independent literal arithmetic: covered.
2. Repeat-seed and permuted-input canonical bytes: covered.
3. Changed seed changes plants/positions/blinds, not design cells: covered.
4. Literal seven-child seed tree and refusal of module-global RNG: covered.
5. Five plants in every discovery group/water/run/reservoir cell: covered.
6. Candidate/EV two-batch crossing, per-cell ≤1, and exact global balance:
   covered for discovery and confirmation cell sizes 5/6.
7. Sham/unmodified fictional batch/event identities: rejected.
8. Unique allocation, plant, position, blind, and movement assignments:
   covered.
9. Reservoir water `n` and exact structured pseudoreplication refusal:
   covered before row inspection/artifact creation.
10. Technical/subsample observations do not inflate either `n`: covered.
11. Missing/duplicate/reused/off-grid/relabelled records: fail closed.
12. Discovery/confirmation plant, batch, reservoir, water-batch, run, and
    non-null event reuse: authoritative factory-derived rejection covered.
13. Exact ≤1 balance and row-count-preserving corruptions: covered, including
    cell-balanced but globally imbalanced batches.
14. Wrong population/unit model: exact `MODEL_POPULATION_MISMATCH` covered.
15. Bool/string/nonfinite/coercive/overflow/subclass boundaries: covered.
16. Deep immutability and copy/`object.__setattr__` revalidation: covered.
17. Exact fixture mirrors, anchor consumption, LF, and wheel resources:
    covered.
18. Central `VerificationRecord` pass derivation and all-or-none atomic 6/14
    directory publication: covered with injected failure.
19. No `winner`, `best_candidate`, `salt_tolerance`, or
    `survival_prediction` output fields: recursively covered.

Follow-up Task 4 load-bearing additions are also covered: exact discovery run
ordinals; 1–4 candidate confirmation families plus EV; six loops/water total;
5/6 plants/cell; no roster/position leftovers; new/disjoint physical material;
canonical whole-manifest and audit revalidation; exact seed-tree
reconstruction; exhaustive cohort identity derivation; and authoritative
later-run ordering that rejects a lying confirmation config maximum.

## Changed-file scope

Created:

- `src/almondlab/design.py`
- `tests/test_design.py`
- both authoring/package copies of `paper1_small.yaml`
- both authoring/package copies of `shared_reservoir_trap.csv`
- this report

Authorized coordinated edits:

- `src/almondlab/paper1_contracts.py`
- `tests/test_paper1_contracts.py`
- `tests/test_verification_resources.py`
- `pyproject.toml`
- `.gitattributes`

Not edited: biology, provenance, core registries/data, verification.py,
verification-policy registry, candidate data, the progress ledger, or generated
run outputs. No file is staged and no commit was created.

## Review request and residual concerns

Independent statistical/scientific-boundary review should inspect the
reservoir-level replication calculation, exact confirmation six-loop
interpretation, 5/6 cell batch algorithm, and factory-derived cohort ordering.
Independent code/reproducibility review should inspect canonical reconstruction,
literal seed order, atomic verification publication, blinded projection, and
wheel resource inclusion.

There are no known source or test failures. The only expected test exclusions
are the three POSIX-only cleanup tests skipped on Windows. Acceptance 6/14 are
structural design evidence only; downstream operating characteristics and
biological outcomes remain unevaluated.

## Independent-review fix round 1

The first independent specification review returned `FAIL` / quality
`NOT APPROVED` with eight findings. The following repair was completed
test-first in the existing unstaged working tree. During the repair, the root
controller committed an unrelated/shared asset change at `56839a9`; the Task 3
working tree carried forward without being staged.

### Finding-by-finding repair

1. **Opaque staff projection.** The staff export now contains only four
   code-owned `OPQ-<32 uppercase hex>` aliases: staff allocation, specimen,
   location, and blinded-treatment codes. It contains no allocation, plant,
   group, water, run, reservoir, position, bench, compartment, cohort, batch,
   stratum, or movement identifier. The aliases are HMAC-SHA-256 values keyed
   from the private blind-child seed authority, so their source identifiers
   cannot be recovered or correlated without the escrow manifest/root seed.
   The public projection records the exact private-manifest hash and its own
   record hash; public revalidation regenerates the expected crosswalk from the
   private manifest and requires exact equality.
2. **Registered spatial blocking.** Position assignment no longer shuffles a
   full 45-slot loop. A code-owned spatial allocator balances groups within
   temporal-run/compartment/water/reservoir/bench/row blocks and permits a group
   at most once in each physical column block. In the registered 5×9 discovery
   grid this gives exactly one of all nine groups per row and five distinct
   columns per group. The audit independently recomputes row, column, and
   compartment checks after physical-slot correspondence validation.
   Acceptance 6 now includes literal `spatial_blocking: true` in both observed
   and oracle payloads.
3. **Exact stratum authority.** `AllocationRecord` freezes the vocabulary to
   `lower_canopy` and `upper_canopy`. The independent audit requires both
   literal categories in every group/water/run/reservoir cell and requires the
   two counts to differ by at most one. All-lower and fictional-category
   adversaries fail.
4. **Confirmation water/run crossing.** Each of the six loops for each
   registered water must now be represented across every configured later run,
   not merely somewhere in the later-run set. Both the physical input boundary
   and the record audit enforce this. A literal all-control-in-run-A and
   all-challenge-in-run-B corruption fails.
5. **Exact confirmation configuration.** Confirmation waters and order are
   frozen to `nonsaline_nutrient_matched_control` then
   `pilot_selected_full_ion_marine_challenge`. Reservoir count is the exact
   primitive integer `6`; schema and unit literals require exact primitive
   strings. `6.0`, hostile `str` subclasses, and arbitrary waters fail with
   stable `CONFIRMATION_DESIGN_INVALID` paths.
6. **Record-only water-batch audit.** Even without a supplied `PositionMap`,
   the audit requires exactly one `water_batch_id` for every
   `(run_id, water_id, reservoir_id)` loop. A one-plant relabel fails at
   `records.water_batch_id`.
7. **Strict blinded public models.** `BlindedAllocationRecord` and
   `BlindedProjection` are frozen, type-exact models with frozen schema/model
   versions, exact evidence label, tuple-only records, unique opaque fields,
   lowercase SHA-256 metadata, and a hash over every public record field.
   `revalidate_blinded_projection(..., manifest=...)` reconstructs every record
   and verifies the exact manifest-derived projection, including after
   `object.__setattr__` copy bypass.
8. **Bounded YAML fixture loader.** A pre-construction event pass bans anchors
   and aliases (therefore cycles), rejects non-core/unsafe construction through
   the safe loader, limits nesting depth to 24, and limits scalar/collection
   nodes to 36,000. The exact 720 fixture uses 33,149 nodes at depth 4. Mapping
   construction rejects non-primitive-string keys before membership tests, and
   parser/construction recursion, type, value, and overflow failures are
   translated to stable `RANDOMIZATION_FIXTURE_INVALID` errors. Compact alias,
   cycle, hostile-tag, non-string-key, depth, and 40,000-item node-budget
   adversaries all fail closed.

### Fix-round RED evidence

The first regression run established the missing public reconstruction
boundary before production edits:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_design.py -q
ImportError: cannot import name 'revalidate_blinded_projection'
1 collection error in 0.82s
```

After implementing only that boundary and enough projection structure to
collect all tests, the remaining behavioral regressions were directly visible:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_design.py -q
7 failed, 82 passed in 10.57s
```

Those failures were the unconstrained spatial assignment, missing exact
stratum-category audit, water/run-confounded confirmation, record-only
water-batch relabel, and native YAML `TypeError`, plus two test-harness
assertions corrected before the final GREEN (a chance two-character match
inside a cryptographic digest and a constructor rejection occurring before the
`pytest.raises` context). No production behavior was weakened to accommodate
those harness corrections.

### Fix-round GREEN and broad verification

Fresh commands after the final source change:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_design.py -q
89 passed in 11.70s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider \
  tests\test_design.py tests\test_paper1_contracts.py tests\test_provenance.py \
  tests\test_verification_resources.py -q
382 passed, 3 skipped in 24.14s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider \
  tests\test_design.py tests\test_paper1_contracts.py \
  tests\test_biology_surrogate.py tests\test_core_acceptance.py \
  tests\test_verification_manifest.py tests\test_verification_resources.py -q
418 passed in 112.71s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
1182 passed, 3 skipped in 130.95s
```

The three skips remain the existing Windows exclusions for POSIX
descriptor-relative cleanup at `tests/test_provenance.py:4002`, `:4047`, and
`:4093`. `python -m compileall -q src/almondlab` and `git diff --check` both
exited 0; the latter reported only Git's informational CRLF checkout warnings,
not whitespace errors.

### Fix-round wheel/resource smoke

The same no-network cached Hatchling backend described above rebuilt the wheel.
The first combined inspection command used the nonexistent PowerShell option
`Select-Object -Single`; Hatchling had produced the wheel, but that shell
inspection step exited 1 before hashing/extraction. The corrected inspection
used `Select-Object -First 1` and passed:

```text
wheel: saltwater_mini_almond-0.1.0-py3-none-any.whl
size: 209,713 bytes
SHA-256: b4cbed32bdbdb2501c415b8d0583eb6fdb9e47448a6d5a9bfb80b5f1afefdcf1
imported module: <isolated extracted wheel>/almondlab/design.py
paper1_small.yaml: 528,427 bytes
paper1_small.yaml SHA-256:
  beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6
shared_reservoir_trap.csv: 1,626 bytes
shared_reservoir_trap.csv SHA-256:
  989f31f87278703841334459ad73780b4164e6f3eac675b253976ec11c7438e1
```

The package and authoring copies have those same hashes. After capture, the
resolved target was verified under the repository `work/` directory and only
`work/task3-wheel-review1` was recursively removed. There are zero remaining
`work/task3-wheel*` directories.

### Scoped rereview request

Rereview the unstaged working-tree fix delta since the first independent
verdict, concentrating on:

- `src/almondlab/design.py`: registered constants/imports;
  `ConfirmationDesignConfig`; `AllocationRecord`; both blinded models,
  opaque-code generation, projection generation/revalidation; YAML preflight
  and unique-map constructor; confirmation physical input validation; the
  spatial allocator and `randomize` slot assignment; independent spatial,
  stratum, water-batch, and water/run audit; Acceptance 6 spatial oracle;
- `tests/test_design.py`: the review regressions beginning with
  `test_staff_projection_uses_only_opaque_codes_bound_to_manifest`, the
  strengthened Acceptance 6 assertion, and all subsequent fix-round
  adversaries.

The fixtures, package metadata, Paper 1 contract coordination, and other Task 3
implementation remain in the overall review scope, but their bytes/behavior
were unchanged by this repair round. Nothing is staged or committed, and the
Paper 1 progress ledger remains untouched pending a passing rereview and shared
index authorization.

## Independent-review fix round 2

The second scoped review accepted findings 3–8 from round 1 and left two
findings open: staff-row ordering/key secrecy and joint spatial restriction.
Both were repaired test-first. The shared index remained empty throughout.

### Private blinding authority and keyed staff order

`BlindingEscrowAuthority` is a frozen exact boundary containing exactly 32
primitive bytes. Bytearrays, strings, wrong lengths, all-zero keys, repeated
one-byte keys, subclasses, and copy-bypass corruption fail with
`BLINDING_ESCROW_INVALID`. The key is excluded from `repr`, has no serialization
method, never appears in staff projection JSON, manifest/hash metadata, or
structured error text, and is independent of `root_seed`.

Production key generation uses `generate_blinding_escrow_authority()`, backed
by `secrets.token_bytes(32)`. The literal deterministic authority in
`tests/test_design.py` is test material only. Operationally, a statistician or
data-manager custodian generates the authority, stores it separately from
greenhouse-staff artifacts in access-controlled encrypted escrow, and withholds
the authority, private manifest, root seed, and crosswalk until the registered
database lock/unblinding event. Only the opaque staff projection is released.
At authorized unblinding, the custodian reconstructs and validates the exact
projection against the private manifest and key, then generates the immutable,
exhaustive, bijective `BlindingEscrowRecord` crosswalk. Greenhouse staff never
receive the authority as part of routine operations.

All four staff aliases are HMAC-SHA-256 values under that authority. Staff row
order is a separate keyed HMAC rank over private allocation identity, not
manifest/allocation order. The same authority deterministically regenerates
identical bytes; a different authority changes codes and order; a root-seed
dictionary probe does not reproduce either. The projection revalidator
regenerates exact keyed order and rejects a caller who reverses or restores
manifest-order rows even after recomputing the public projection hash. The
registered fixture has absolute row-index/private-index correlation below
0.10, no more than five chance same-index matches, maximum same-group run four,
and maximum same-cell run three; the assertions use the private escrow
crosswalk and are not exposed staff metadata.

### Joint group/stratum/batch spatial restriction

The allocator now assigns the complete category
`group × baseline_canopy_stratum × transformation_batch_block`, with explicit
`NA` for sham and unmodified controls, into physical row/column/compartment
blocks. It does not place a group and then arbitrarily pop a plant. Group
layout is seed-derived; the category-to-slot assignment satisfies literal
integer lower/upper bounds simultaneously. The audit independently derives all
maxima from reconstructed allocation records and does not call the allocator.

The exact discovery bounds follow from the registered physical design rather
than unexplained tolerances:

- one loop has `9 groups × 5 plants = 45` positions in a 5-row × 9-column
  grid;
- every 9-position row therefore has exactly one of each group (group row
  difference 0), each group's five positions use five distinct columns
  (column maximum 1), and the one loop compartment contains five of each group
  (compartment difference 0);
- the 45 canopy strata divide 22/23, each 9-position row divides 4/5, and each
  5-position column divides 2/3, so the exact feasible stratum difference is 1
  in row, column, and compartment blocks;
- seven transformed groups supply `7 × 5 = 35` transformed records. Their two
  batch blocks divide 17/18 in the compartment, 3/4 among the seven transformed
  records in each row, and floor/ceiling among the 3–5 transformed records in
  a column; thus every transformed-batch difference is exactly bounded by 1;
- the two nontransformed groups supply explicit batch `NA`: one record from
  each group per row gives exactly 2 N/A records per row; neither group repeats
  in a column, giving a column maximum of 2; and `2 groups × 5 plants` gives
  exactly 10 N/A records in the loop compartment. N/A is never compared to the
  transformed A/B counts.

Acceptance 6 now reports `spatial_group_balance`,
`spatial_stratum_balance`, and `spatial_batch_balance` separately plus all 12
observed maxima. Its independent literal oracle pins exactly:

```text
row_group_count_difference = 0
column_group_max_count = 1
compartment_group_count_difference = 0
row_stratum_count_difference = 1
column_stratum_count_difference = 1
compartment_stratum_count_difference = 1
row_transformed_batch_count_difference = 1
column_transformed_batch_count_difference = 1
compartment_transformed_batch_count_difference = 1
row_not_applicable_max_count = 2
column_not_applicable_max_count = 2
compartment_not_applicable_max_count = 10
```

Coordinated adversaries exchange stratum or physical batch fields between two
same-group records in one loop. They preserve group/cell/row totals and global
marginals while breaking local spatial balance; the independent audit rejects
them at `records.spatial_stratum_block` or `records.spatial_batch_block`.
Confirmation boundary tests still cover one candidate plus EV at 5/cell and
four candidates plus EV at 6/cell.

### Round-2 RED evidence

The first new boundary test established the missing private authority:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_design.py -q
ImportError: cannot import name 'BlindingEscrowAuthority'
1 collection error in 0.85s
```

After the authority/keyed projection collected, the remaining behavioral RED
was:

```text
3 failed, 94 passed in 13.55s
```

The failures were the absent joint-spatial maxima and coordinated stratum/batch
corruptions that still passed the group-only audit. Strengthening the private
crosswalk from an allocation-only mapping to an exhaustive frozen record also
produced a focused `2 failed` RED before the escrow record implementation.

### Performance repair and cache safety

The correct first joint implementation used one dense SciPy MILP per physical
loop. It was scientifically green but caused the direct suite to regress from
roughly 12 seconds to:

```text
97 passed in 102.35s
```

Profiling/static inspection identified repeated dense matrix construction and
solver startup as the dominant cost. The optimized path derives one seeded
group layout per randomization and caches only an immutable primitive
category-count/normalized-geometry → integer-index template. Cache size is
bounded at 256. It stores no plant IDs, position IDs, physical objects, mutable
arrays, authorities, keys, or manifests. Each call binds fresh physical
plants/slots and revalidates the cached bijection and category/group
correspondence before producing records.

A fresh-process timing probe measured:

```text
cold 720 randomize: 0.207 s
repeat randomize:   0.153 s
allocation SHA-256:
  bd4cb366ac9c3144ab881af29615311839f1fc0a9a881645ba4995dcab7b7c3f
```

Both calls produced the same hash and the independent audit produced all exact
maxima above. This is a recorded sanity measurement, not a brittle CI timing
threshold. Cache adversaries cover different seeds, reversed caller order,
same normalized shape with changed semantic compartment/bench/row/column
labels, copy-bypass input, discovery followed by confirmation, bounded eviction
(test max size 2 exercises the production eviction path corresponding to
`>256`), primitive-only cache contents, and sequential-versus-fresh-process
manifest identity. The two cache-focused tests passed in 7.50 seconds.

### Round-2 final verification

Fresh post-optimization results:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_design.py -q
99 passed in 18.53s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider \
  tests\test_design.py tests\test_paper1_contracts.py tests\test_provenance.py \
  tests\test_verification_resources.py -q
392 passed, 3 skipped in 30.89s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider \
  tests\test_design.py tests\test_paper1_contracts.py \
  tests\test_biology_surrogate.py tests\test_core_acceptance.py \
  tests\test_verification_manifest.py tests\test_verification_resources.py -q
428 passed in 119.16s

.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
1192 passed, 3 skipped in 141.76s
```

The skips are the same existing POSIX-only cleanup tests on Windows.
`python -m compileall -q src/almondlab` and `git diff --check` exited 0.

The isolated cached-backend wheel/resource smoke passed from the extracted
wheel:

```text
wheel size: 212,547 bytes
wheel SHA-256:
  10b0e34c7fb26c0da16d74b9bf1951746c8deff9cf43d80ccd4bfc742b52ef64
paper1_small.yaml: 528,427 bytes
paper1_small.yaml SHA-256:
  beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6
shared_reservoir_trap.csv: 1,626 bytes
shared_reservoir_trap.csv SHA-256:
  989f31f87278703841334459ad73780b4164e6f3eac675b253976ec11c7438e1
```

Only the verified `work/task3-wheel-review2` target was removed afterward;
zero `work/task3-wheel*` directories remain.

### Round-2 scoped rereview request

Rereview the round-2 working-tree delta in `src/almondlab/design.py` and the
corresponding final block of `tests/test_design.py`, focusing on:

- exact private-key construction/generation, absence from all staff/error
  surfaces, keyed aliases/order, projection regeneration, and exhaustive
  private crosswalk;
- joint category construction, integer assignment constraints, independent
  maxima derivation, explicit N/A treatment, Acceptance 6 separate observed
  values/literal oracles, and marginal-preserving corruption refusal;
- primitive cache-key completeness, bounded eviction, fresh physical-object
  binding/post-validation, caller-order/semantic-label/copy-bypass isolation,
  discovery/confirmation isolation, multiple seeds, and fresh-process
  determinism.

No ambiguous `water_batch_id` rename or preparation-batch API was made: a
brief cross-task concern was explicitly retracted after the higher-precedence
Task 4 addendum confirmed that Task 4 types each Task 3 `water_batch_id` and
requires one sufficiently large predeclared batch per loop without rollover.
Nothing is staged or committed, and the progress ledger remains untouched.

## Cache-authority repair and resumed finalization

A later independent cache-authority review found that a process-local primitive
template cache could still be treated as scientific authority if its value was
poisoned. The repair was performed test-first in the existing unstaged working
tree. The first regression set produced four expected failures for unsigned
value poison (including category-preserving permutation), incomplete
stratum/batch/N/A post-binding validation, and leaked internal exceptions. The
minimal repair replaced the module dictionary with a private slots-only cache,
generated an independent 32-byte process HMAC key, sealed every
schema/key/template payload with HMAC-SHA-256, used `hmac.compare_digest`,
evicted and deterministically rederived invalid entries, and added a complete
post-binding spatial oracle independent of the optimizer/cache. The inherited
targeted cache set was then nine tests green.

During resumed independent inspection, a serialization probe found one
remaining key-exposure path: Python's default slot pickling serialized the
private cache HMAC key. A new behavioral regression was written first and
witnessed failing:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider \
  tests\test_design.py -k "cache_secret_is_absent" -q
1 failed, 107 deselected in 1.63s
```

The minimal production change makes the process-private cache explicitly
non-serializable through `__reduce_ex__`, with a constant error message that
contains no key material. The same regression then passed:

```text
1 passed, 107 deselected in 1.04s
```

The expanded cache matrix covers digest-only poison, value poison,
value-plus-digest poison, category-preserving permutation, stratum,
transformed-batch and N/A corruption, an independently bypassed integrity
layer, bounded eviction, input-order/geometry/cohort isolation,
fresh-process determinism, and absence of the process key from repr,
serialization, and error text. Its fresh result was:

```text
11 passed, 97 deselected in 12.72s
```

### Resumed fresh verification

All commands below were run after the serialization repair:

```text
direct design:
108 passed in 25.27s

design + contracts + provenance + verification resources:
401 passed, 3 skipped in 38.59s

design + Paper 1 contracts + biology + core acceptance
+ verification manifest/resources:
437 passed in 138.81s

full repository:
1201 passed, 3 skipped in 159.04s

resource mirrors/materialization:
3 passed in 1.15s
```

The three full/focused skips are the existing Windows exclusions for POSIX
descriptor-relative cleanup at `tests/test_provenance.py:4002`, `:4047`, and
`:4093`. `python -m compileall -q src/almondlab` and `git diff --check` both
exited 0; Git emitted only the existing informational LF/CRLF checkout
warnings.

A fresh single-process 720-record timing probe cleared the cache before its
first call and measured:

```text
cold:   0.218583 s
repeat: 0.212891 s
allocation SHA-256:
  bd4cb366ac9c3144ab881af29615311839f1fc0a9a881645ba4995dcab7b7c3f
canonical bytes identical: true
```

The no-network cached Hatchling backend produced a fresh isolated wheel. The
smoke test imported `almondlab.design` from the extracted wheel and read both
fixtures through `importlib.resources`:

```text
wheel size: 214,749 bytes
wheel SHA-256:
  c14a45cbff989f56b4ba1565ed38801a19df304b3200739c9a5f0d770ea7dea3
paper1_small.yaml: 528,427 bytes
paper1_small.yaml SHA-256:
  beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6
shared_reservoir_trap.csv: 1,626 bytes
shared_reservoir_trap.csv SHA-256:
  989f31f87278703841334459ad73780b4164e6f3eac675b253976ec11c7438e1
```

Only the verified Task 3 scratch directories `work/pytest-root-direct` and
`work/task3-wheel-final` were removed afterward. The unrelated Task 4 material
`work/task4_registration_hash_materializer.py` was not read, edited, removed,
staged, or included in Task 3 scope. Nothing is staged or committed pending a
fresh read-only approval and controller authorization.

### Exact-primitive ingress follow-up

A final controller probe found that the coordinated Task 1 design validators
used `isinstance` at ingress. Pydantic consequently accepted hostile `str`
subclasses for nested water, group, run, and batch IDs and hostile `list`
subclasses for all three ID collections before canonicalizing them to ordinary
strings/tuples. Seven regressions were written first and witnessed failing:

```text
.venv\Scripts\python.exe -m pytest -p no:cacheprovider \
  tests\test_paper1_contracts.py -k "subclass" -q
7 failed, 72 deselected in 0.79s
```

The minimal fix changed only the before-validator gates to
`type(value) is str`, `type(item) is str`, and
`type(value) in (list, tuple)`. The regressions and combined direct boundary
gate then passed:

```text
7 passed, 72 deselected in 0.53s
187 passed in 29.38s  # paper1 contracts + design
```

Broad/full results recorded earlier in this report predate this last source
change and therefore are not completion evidence; fresh broad/full gates and
fresh read-only review are required before staging.

Fresh post-fix gates subsequently completed:

```text
design + contracts + provenance + verification resources:
408 passed, 3 skipped in 39.90s

design + Paper 1 contracts + biology + core acceptance
+ verification manifest/resources:
444 passed in 151.84s

full repository:
1208 passed, 3 skipped in 191.48s
```

`python -m compileall -q src/almondlab` and `git diff --check` again exited 0.
The post-fix isolated wheel imported `almondlab.design` from its extracted
tree and preserved the two fixture hashes above; the wheel was 214,752 bytes
with SHA-256
`b1c39c17a3f6c48978c524bc92aedeade83b58ea0f394793612a1d213f298920`.
After verifying their resolved paths beneath `work/`, only Task 3 wheel scratch
and the controller's `work/pytest-root-rootcheck` test scratch were removed.
`work/task4_registration_hash_materializer.py` remains the sole `work/` entry
and was preserved.

## Final independent review verdict

The fresh read-only Task 3 review explicitly rechecked the complete unstaged
implementation, cache-authority repairs, exact-primitive ingress repair,
blinding boundary, joint spatial restriction, experimental-unit audit,
fixtures/resources, and the authoritative Task 3 brief/addendum. It also
adjudicated the cross-task `water_batch_id` question: Task 3 requires exactly
one internally consistent water-batch identity within each physical loop and
does not require that identity to be globally unique across loops. Reuse in
the discovery fixture is therefore not a Task 3 specification mismatch.

Exact independent verdict:

```text
Spec: APPROVED
Quality: APPROVED
Substantive findings: none
```

No Critical, Important, or Minor findings remained. The reviewer returned the
required terminal approval:

```text
APPROVED
```
