# Final Fix D review follow-up — numeric and audit authority hardening

## Outcome

Closed the independent review defects in the canonical mass-balance kernel.
All derived arithmetic now crosses a finite, structured error boundary, and
publication-facing ledger audits can consume caller-owned literal transaction
authority instead of trusting quantities emitted by the simulator under test.

This follow-up makes no biological efficacy, GMO-trait, or gene-effect claim.

## Owned files

- `src/almondlab/mass_balance.py`
- `tests/test_mass_balance.py`
- this report

Concurrent verification, fixture-migration, visual, treatment, contract, and
domain changes were preserved and excluded from staging.

## TDD evidence

The original focused suite was green at `83 passed`. Independent adversarial
probes then reproduced two concrete native/numerical escapes:

- a compartment with `1e308 / 1e-320` yielded infinite density/concentration;
- two finite `1e308` totals leaked native `OverflowError` from `math.fsum`.

The numeric RED matrix initially reported:

```text
2 failed, 10 passed, 83 deselected
```

The remaining failures were ledger accumulation overflow and analytical
closed-form overflow. The audit-authority RED batch independently reported:

```text
7 failed, 1 passed, 94 deselected
```

It proved missing transaction authority, explicit-empty ambiguity, evidence
drift, and the cross-loop selective-transfer auditor contradiction.

Final GREEN evidence:

```text
tests/test_mass_balance.py                                      104 passed
tests/test_contracts.py + tests/test_mass_balance.py            197 passed
chemistry/contracts/domains/hydraulics/mass/schemas/treatment   407 passed
full non-verification suite                                     441 passed
```

The verification files were intentionally excluded from the last command
because Final Fix F was concurrently migrating those owned files and fixtures.

## Repairs

- Added quantity-specific finite sum/product/ratio/multiply-divide helpers.
  Derived density, concentration, network totals, substep limits, event
  requests, water mass, advective concentrations, competing demand totals,
  state deltas, audit totals/residuals, and analytical outputs now raise
  `AlmondLabError(code="MASS_NUMERIC_INVALID")` at stable field paths instead
  of returning nonfinite values or leaking native arithmetic exceptions.
- Preserved mathematically finite extreme calculations by evaluating
  multiply/divide expressions in an overflow-resistant order.
- Added frozen, defensively copied `LedgerTransactionExpectation` records.
  Their independent literals pin transaction ID, event ID, interval, entity
  set, canonical units through the entity registry, and positive quantity
  magnitudes.
- `audit_ledger` now distinguishes `None` (no independent authority) from an
  explicit empty iterable (assert no events/transactions). Transaction
  authority requires explicit typed event authority.
- Literal audit authority covers internal advective and water-only paired
  rows, internal selective paired rows including requested/applied/cap
  metadata, and external one-sided rows including category direction, event
  rates, input density, and current-mixture literal inventories.
- Ordered source-to-target roles are checked, including zero-amount measured
  transactions. Event-rate mutations, swapped per-event solute quantities,
  and coordinated cap forgeries no longer self-validate.
- Row evidence is always tied to after-state evidence; explicit event authority
  also derives the exact conservative result label from the pre-state and all
  events. Empty-ledger evidence promotion is rejected.
- External boundary identifiers are disjoint from the compartment namespace,
  preventing one-sided boundary rows from laundering an internal endpoint.
- Cross-loop physical-transfer IDs remain required for water transfers only.
  Typed plant ion transfers can cross hydraulic/plant loop labels and now
  produce ledgers that audit successfully.

## Compatibility note

Existing closure-only calls remain valid with the default `None` authorities.
Publication verification should pass both typed `expected_events` and
fixture-owned `expected_transactions`; those literals must never be derived
from the observed ledger or `StepResult`.
