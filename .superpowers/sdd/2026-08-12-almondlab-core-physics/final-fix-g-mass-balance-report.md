# Final Fix G report — mass authority and floating-point edge hardening

## Outcome

Closed the independent post-fix review defects in the canonical mass-balance
kernel. Core event authority now rejects constructor-valid provenance metadata
that is not authorized by the corresponding typed event, including coordinated
forgeries copied to every row. Derived product, ratio, and multiply/divide
arithmetic now preserves every representable nonzero binary64 result and maps
nonzero underflow or overflow to a structured `MASS_NUMERIC_INVALID` error at
the caller quantity path.

This patch makes no biological efficacy, GMO-trait, salt-tolerance, or plant
survival claim.

## Owned files

- `src/almondlab/mass_balance.py`
- `tests/test_mass_balance.py`
- this report

Concurrent verification, fixture, packaging, biology, contract, treatment,
and publication changes were preserved and excluded from staging.

## Test-first evidence

The pre-follow-up focused baseline was:

```text
104 passed in 1.96s
```

The independent-review regression selection was then run before production
changes. It reported:

```text
14 failed, 1 passed, 104 deselected in 1.34s
```

The failures reproduced all four constructor-valid metadata forgeries, density
and concentration underflow, positive flow underflow, both signed
multiply/divide ordering failures, the unrepresentably large safe substep
limit, three exact zero-time analytical failures, and the small-positive-time
cancellation failure. The one passing case showed that one narrow minimum
subnormal path already happened to survive; it did not cover the failing
adjacent arithmetic.

After implementation, that regression selection was green:

```text
15 passed, 104 deselected in 0.74s
```

Two additional explicit tests cover minimum-subnormal and underflow behavior
for the multiply/divide primitive through its public analytical caller. Final
verification was:

```text
tests/test_mass_balance.py                                      121 passed
chemistry/contracts/domains/hydraulics/mass/schemas/treatment   424 passed
full non-verification suite                                     458 passed
full suite with stable in-flight Final Fix F                    556 passed
compileall                                                       PASS
git diff --check                                                 PASS
```

The full-suite run was coordinated after the Final Fix F owner declared its
in-flight verifier tree stable. Final Fix F files remain outside this patch's
ownership and commit.

## Repairs

### Typed ledger authority

- `InternalWaterFlow` authority pins the exact physical-transfer ID and typed
  water-flow kind, requires water carrier metadata only on water rows, and
  forbids boundary, internal-flux, cap, adapter, and treatment metadata.
- `InternalEntityFlux` authority pins the exact plant-flux kind, requires the
  complete requested/applied/cap triplet, and forbids physical-transfer,
  water-flow, carrier, boundary, adapter, and treatment metadata. Literal
  transaction authority independently pins the numerical cap values.
- `ExternalBoundaryFlux` authority pins its typed category, endpoints,
  direction, and mode while forbidding physical-transfer, cap, internal,
  adapter, and treatment metadata. Literal transaction authority independently
  pins rates/current-mixture quantities, carrier, density, and signed amounts.
- Reaction events remain rejected by the disabled core-v1 adapter gate.
- Regression tests use both independent `expected_events` and
  `expected_transactions`, so generator-consistent but unauthorized metadata
  no longer self-validates.

### Numerical boundary

- Products, ratios, and combined multiply/divide expressions are evaluated as
  exact rationals of their binary64 operands using `Fraction.from_float`, then
  converted once with correctly rounded binary64 conversion.
- An exact zero remains an allowed zero. An exact nonzero that rounds to zero
  raises `MASS_NUMERIC_INVALID`; an unrepresentable large result is mapped to
  the same structured boundary rather than leaking a native exception.
- Signed finite extreme-scale multiply/divide calculations are preserved; the
  previous candidate-order choice that erased `1e-300` has been removed.
- The conservative substep limiter compares its exact safe limit with the
  requested interval before conversion. If the safe limit is enormous, it
  returns the already-safe requested interval without materializing infinity.
- Tests cover underflow and minimum-subnormal preservation separately for
  ratio, product, and multiply/divide caller paths.

### Stable analytical tank oracle

- Exact `time == 0` returns `c0` before any subtractive expression.
- Positive-time purge uses `-expm1(-purge*time/volume)` and the stable form
  `c0 + (c_in-c0)*fraction + (m_dot/purge)*fraction`.
- Every derived exponent, transition fraction, departure, contribution, and
  result crosses the structured finite/underflow boundary.

## Review status

Implementation and tests are ready for independent scoped review. This report
does not self-approve the patch.
