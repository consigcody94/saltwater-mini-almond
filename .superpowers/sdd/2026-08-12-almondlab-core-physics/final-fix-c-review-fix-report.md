# Final Core Fix C review follow-up report

## Outcome

Closed the reviewed shared-contract gaps without changing the mass-balance or
treatment kernels. External ledger rows now carry an explicit measured boundary
category with a category-specific sign convention; water rows enforce exact
zero amount/carrier equivalence; internal water rows carry a typed physical flow
kind pinned to the permitted material mode and operator phase; and internal
entity-only rows cannot be used as unprovenanced numerical closure.

The cursor's one-past sentinel is documented and observable through
`LedgerCursor.exhausted`. `finite_float` now translates expected scalar
conversion failures only, while propagating unexpected programming faults.
No treatment-model hash field was added to the ledger: immutable treatment
parameters plus fixture/policy hashes remain the authoritative provenance.

No biological candidate, empirical result, or validation claim was changed.

## Owned files

- `src/almondlab/contracts.py`
- `src/almondlab/errors.py`
- `tests/test_contracts.py`
- `.superpowers/sdd/2026-08-12-almondlab-core-physics/final-fix-c-review-fix-report.md`

Concurrent mass, treatment, fixture, verification, and concept-image changes
were preserved and excluded from this task's staging set.

## TDD evidence

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q
```

Result before the production patch:

```text
43 failed, 50 passed in 1.11s
```

The failures were the expected missing behaviors: no
`internal_water_flow_kind` constructor field, no `LedgerCursor.exhausted`, no
external category/sign gate, tolerant zero-water identity, permitted bare
entity-only closure, and `finite_float` swallowing a `RuntimeError` raised by a
broken real scalar.

### Focused GREEN

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q -p no:cacheprovider
```

Result:

```text
93 passed in 0.43s
```

### Repository-wide compatibility check

The requested full-suite command was run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Collection was blocked by the concurrent mass-balance TDD migration:

```text
ImportError: cannot import name 'CompartmentState' from 'almondlab.mass_balance'
1 error in 1.45s
```

To inspect the remainder without changing that owned work, the suite was run
with `tests/test_mass_balance.py` excluded:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mass_balance.py
```

Result:

```text
355 passed, 15 failed in 10.22s
```

Those 15 failures are in concurrent treatment/verification migration paths:
legacy verification fixture keys (`volumes_l`), legacy positional `ro_split`
and `ROResult` APIs, and in-progress treatment exact-float/immutability tests.
They do not originate in the focused contract slice, and no out-of-scope file
was changed to mask them.

`python -m compileall` on the owned Python files and `git diff --check` on the
owned implementation/test files both completed cleanly.

## Contract decisions implemented

- Every external row requires `boundary_category`. Source feed, external
  makeup, and amendment are nonnegative; every measured output category is
  nonpositive. Zero is accepted as an explicitly categorized no-event.
- Water has exact zero equivalence between signed amount magnitude and carrier
  volume. Nonzero water therefore has positive carrier volume, followed by a
  relative-tolerance mass-density identity with no absolute-zero loophole.
- Internal water rows require `InternalWaterFlowKind`. Aqueous transfer is
  advective and limited to irrigation, layer drainage, drainage/condensate
  return, or treatment blending. Evaporation/transpiration and condensate return
  are water-only and pinned to their respective phases.
- External and non-water rows reject internal water-flow metadata.
- Internal entity-only rows require a typed plant flux or reaction adapter;
  these provenance forms remain pinned to `plant_ion_transitions` and
  `reaction_adapters`, respectively.
- The exhausted cursor sentinel remains constructible only as the single
  one-past state, reports `exhausted=True`, and cannot issue an ID.
- Expected `float()` conversion errors remain structured `AlmondLabError`s;
  unexpected exceptions from a broken numeric implementation propagate for
  diagnosis.
