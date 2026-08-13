# Final Core Fix D report — canonical mass balance

## Outcome

Replaced the legacy volume/string-unit transport kernel with a canonical,
density-aware, immutable finite-volume state and typed event model. Water is
conserved as kilograms while hydraulic volume is audited independently in
liters. Dissolved entities use the shared registry, including `mmol_c` for
alkalinity. Plant uptake, efflux, retrieval, sequestration, release/loading,
and tissue deposition are represented only as paired internal transfers.

This implementation makes no biological efficacy or gene-effect claim.

## Owned files

- `src/almondlab/mass_balance.py`
- `tests/test_mass_balance.py`
- authoring/package mirrors of:
  - `entity_units_density.yaml`
  - `internal_plant_flux_cap.yaml`
  - `chained_transaction_ids.yaml`
  - migrated `no_purge.yaml`
  - migrated `sufficient_purge.yaml`
- this report

Concurrent treatment, domains, hydraulics, contracts, verification, Paper 1,
public data, and image edits were preserved and excluded from staging.

## TDD evidence

### Initial RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mass_balance.py -q -p no:cacheprovider
```

The rewritten test module failed during collection as intended:

```text
ImportError: cannot import name 'CompartmentState' from 'almondlab.mass_balance'
1 error in 0.61s
```

This proved the canonical state/event interface did not exist in the legacy
kernel.

### Integration RED after first implementation

The first implementation run produced:

```text
43 passed, 18 failed in 34.28s
```

Most failures correctly exposed the newly committed shared-ledger invariant
that `internal_water_flow_kind` belongs only on the paired water rows, not on
the solute rows in the same advective transaction. The Hypothesis property
test also exposed an actual bug: a small positive transported stock was being
rounded to zero by a symmetric tolerance clamp. The clamp now applies only to
tiny negative roundoff.

### Final focused GREEN

```text
83 passed in 1.47s
```

### Shared contracts + mass GREEN

```text
176 passed in 1.53s
```

### Core implementation modules GREEN

Command covered chemistry, domains, hydraulics, schemas, and mass balance:

```text
244 passed in 2.28s
```

### Full-suite compatibility status

The full suite stops during collection at the expected legacy verification
boundary:

```text
ImportError: cannot import name 'ExternalFlux' from 'almondlab.mass_balance'
1 error in 1.40s
```

This is the deliberate canonical-API break assigned to Final Fix F. No legacy
adapter was added because the task requires the public constructor to demand
water mass/density, typed compartments/events, evidence, and a ledger cursor.

## Requirement audit

- `CompartmentState` and `NetworkState` are frozen and recursively immutable;
  all nested input mappings are defensively copied.
- The canonical constructor requires typed compartment kind, loop ID, liters,
  kilograms, empty-reference density, exact tracked stocks, and evidence.
- `WATER` is forbidden in stock registries. Zero-volume carrier invariants and
  strict finite numeric boundaries raise structured `AlmondLabError` only.
- Internal water, external boundary, internal plant-entity, and disabled
  reaction-adapter events are frozen and typed.
- External identifiers reject normalized reaction aliases. Input/output sign is
  determined from the typed boundary category; aqueous inputs require complete
  inventory and density, and aqueous outputs require explicit current-mixture
  advection.
- Core-v1 phase order is fixed; events are sorted by stable event ID. Phase
  snapshots prevent within-phase reuse of incoming inventory, while later
  phases can use prior-phase delivery.
- Competing `(source, entity)` plant requests are capped proportionally with
  `math.fsum`; requested/applied/cap metadata is written on both reciprocal
  ledger rows.
- Advective water transfers source density, water kg, and all tracked entities;
  evaporation/transpiration is water-only and has typed endpoints.
- Every call requires and advances a `LedgerCursor`. Replay is deterministic,
  chained IDs continue, and separate runs are disjoint.
- Output/state/row evidence is conservatively composed. Hypothesis-prior plant
  events prevent a physics-only result label.
- `LedgerEntry` is the shared contract re-export; no second ledger type remains.
- Audit covers global/per-compartment water kg and solutes plus separate L
  closure, canonical units, transfer shapes, reciprocal pairs, duplicate IDs,
  boundary categories/signs, evidence, phase/event/mode/cap/endpoint/adapter
  metadata, and water carrier identities.
- `audit_ledger(..., expected_events=...)` accepts independent event authority.
  Adversaries prove that generator-valid but systematically wrong event IDs,
  phases, physical-transfer IDs, water-flow kinds, endpoints, quantities,
  evidence, cap metadata, and carrier/density metadata do not self-validate.
- The three required independent fixtures contain the exact hand literals, and
  hash guards also cover migrated analytic fixtures and packaged mirrors.
- The no-purge physical stop and sufficient-purge hand-derived analytical
  trajectory remain tested; step halving reduces the split-phase numerical
  error.

## Deliberately deferred

- Verification acceptance callers and their schema-2 literal ledger oracles are
  migrated in Final Fix F.
- Treatment has its own immutable stream/RO/remineralization task and was not
  modified here.
- Reaction adapters remain disabled in core v1. No transformation, sorption,
  precipitation, or biological kinetic effect was invented.
