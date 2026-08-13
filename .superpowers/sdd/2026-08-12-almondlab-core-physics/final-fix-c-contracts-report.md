# Final Core Fix C report — shared conservation contracts

## Outcome

Implemented the immutable vocabulary required for the mass-balance and
treatment migrations without changing either numerical kernel. The shared
contracts now define canonical entity units and bases, the fixed core operator
schedule, typed compartments/boundaries/fluxes/material modes, deterministic
transaction namespaces, strict finite-number conversion, and a frozen ledger
row with coherent water-mass, capping, provenance, and reaction-adapter
metadata.

No biological candidate, empirical result, or validation claim was changed.

## Owned files

- `src/almondlab/contracts.py`
- `src/almondlab/errors.py`
- `tests/test_contracts.py`
- `.superpowers/sdd/2026-08-12-almondlab-core-physics/final-fix-c-contracts-report.md`

Concurrent chemistry, schema, domain, hydraulic, verification, config, and
fixture changes were preserved and excluded from this task's staging set.

## TDD evidence

### Initial RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q
```

Exit 1 during collection, as expected:

```text
ImportError: cannot import name 'CORE_V1_OPERATOR_SCHEDULE' from 'almondlab.contracts'
1 error in 0.52s
```

This established that the requested public contracts did not yet exist.

### Boundary RED

Self-review identified that the first cursor implementation made the final
12-digit ordinal unissuable. The test was corrected first to require issuance
of `999999999999` followed by an exhausted cursor. Before the implementation
repair, the focused case failed with:

```text
almondlab.errors.AlmondLabError: LEDGER_ORDINAL_OVERFLOW:
cannot advance beyond the 12-digit ledger namespace
1 failed in 0.56s
```

The cursor now emits every 12-digit ID and represents exhaustion with a
non-emitting sentinel.

### Final focused GREEN

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q -p no:cacheprovider
```

Result:

```text
54 passed in 0.42s
```

### Full-suite GREEN

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Result:

```text
316 passed in 8.34s
```

`git diff --check` on the three implementation/test files returned clean.

## Requirement audit

- Existing public enum values remain unchanged.
- `ENTITY_SPECS` is a read-only, exhaustive, one-to-one mapping. Water uses
  `kg` with no concentration unit; alkalinity uses `mmol_c`/`mmol_c/L`; all
  other registered entities use `mmol`/`mmol/L` with an explicit basis.
- `CORE_V1_OPERATOR_SCHEDULE` contains every phase once and in the exact
  required order. Mutable input is defensively copied; missing, duplicate,
  extra, or reordered phases fail with structured errors.
- Boundary, plant-ion, compartment, internal-water, material-mode, and ledger
  kind enums cover the treatment/water/plant interfaces needed by later tasks.
- `LedgerCursor` validates readable ASCII namespaces, rejects booleans and
  invalid ordinals, emits exact deterministic IDs, advances immutably, replays
  deterministically, and separates run/chain namespaces.
- `finite_float` rejects coercive booleans/strings/arbitrary objects,
  conversion overflow, NaN, infinity, and requested bound violations while
  preserving the caller's stable `AlmondLabError` code and field path.
- `LedgerEntry` is frozen and keyword-only. It requires typed event context,
  exact registry units, explicit evidence, and finite scalar metadata. Water
  rows require the identity `abs(amount_kg) = carrier_volume_L * density_kg_L`;
  solute rows forbid carrier metadata. Boundary/internal categories, transfer
  modes, cap metadata, and validated adapter references are cross-checked for
  coherence.

## Deferred intentionally

The existing `mass_balance.LedgerEntry` remains untouched in this contract-only
slice. Re-export/migration of that kernel and construction of treatment ledger
rows belong to the subsequent mass-balance and treatment tasks. The new shared
contract is independently usable by both.
