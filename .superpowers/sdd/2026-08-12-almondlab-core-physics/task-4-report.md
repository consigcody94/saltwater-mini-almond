# Task 4 report — finite-volume engine and analytic accumulation fixtures

## Outcome

Implemented and committed the immutable, auditable finite-volume engine on
`build/virtual-lab` from reviewed baseline `416b71b`. Internal transfers debit
and credit water plus every registered entity atomically, external fluxes name
their physical boundary, cross-loop movement requires a physical transfer ID,
gross advective withdrawals drive adaptive subdivision, reaction sinks are
capped by available stock, and all output state values and balance residuals
are validated against the binding tolerances.

Implementation commit:

`43b26f9842a68315e40c5e5644b71053a8b81d0b feat: add auditable finite-volume state engine`

## Files

- `src/almondlab/mass_balance.py`
- `tests/test_mass_balance.py`
- `tests/fixtures/water_one_day.yaml`
- `tests/fixtures/ions_conservative.yaml`
- `tests/fixtures/no_purge.yaml`
- `tests/fixtures/sufficient_purge.yaml`

No visual asset was read, edited, staged, or committed.

## TDD evidence

The bare command name `uv` was initially absent from this PowerShell PATH. That
environment failure was not counted as RED. The same task-local bootstrap used
by Tasks 1–3 was then invoked explicitly, with the required cache directory.

### Initial RED — missing engine

Command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_mass_balance.py -v -p no:cacheprovider
```

Output (exit 1):

```text
collecting ... collected 0 items / 1 error

=================================== ERRORS ====================================
_________________ ERROR collecting tests/test_mass_balance.py _________________
tests\test_mass_balance.py:10: in <module>
    from almondlab.mass_balance import (
E   ModuleNotFoundError: No module named 'almondlab.mass_balance'
=========================== short test summary info ===========================
ERROR tests/test_mass_balance.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
============================== 1 error in 1.02s ===============================
```

This was the expected failure: the requested production module did not exist.

### Initial GREEN

The same focused command produced (exit 0):

```text
collecting ... collected 17 items
tests/test_mass_balance.py::test_internal_flow_is_equal_debit_and_credit PASSED
tests/test_mass_balance.py::test_state_is_immutable_including_nested_input_mappings PASSED
tests/test_mass_balance.py::test_cross_loop_flow_requires_physical_transfer_identifier PASSED
tests/test_mass_balance.py::test_external_flux_requires_named_boundary PASSED
tests/test_mass_balance.py::test_one_day_water_fixture_is_a_hand_literal PASSED
tests/test_mass_balance.py::test_every_registered_entity_is_advected_at_source_concentration PASSED
tests/test_mass_balance.py::test_excessive_fraction_is_subdivided_and_not_clipped PASSED
tests/test_mass_balance.py::test_nonfinite_and_materially_negative_states_are_rejected PASSED
tests/test_mass_balance.py::test_corrupted_ledger_is_detected_independently_for_one_entity PASSED
tests/test_mass_balance.py::test_no_purge_fixture_reaches_physical_censored_stop PASSED
tests/test_mass_balance.py::test_sufficient_purge_fixture_matches_closed_form_trajectory PASSED
tests/test_mass_balance.py::test_step_halving_converges_toward_purge_oracle PASSED
tests/test_mass_balance.py::test_property_internal_transfer_preserves_positivity_and_stock PASSED
tests/test_mass_balance.py::test_external_reaction_sink_is_capped_by_available_stock PASSED
tests/test_mass_balance.py::test_closed_form_oracle_uses_hand_derived_literals[values0] PASSED
tests/test_mass_balance.py::test_closed_form_oracle_uses_hand_derived_literals[values1] PASSED
tests/test_mass_balance.py::test_closed_form_oracle_uses_hand_derived_literals[values2] PASSED
============================= 17 passed in 0.72s ==============================
```

### Self-review RED — combined boundary effects

Self-review identified that one named boundary event containing both an
advective purge and a declared entity source could duplicate the debit and omit
the credit in its ledger. A real regression test was added before changing the
implementation.

Command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_mass_balance.py::test_one_boundary_flux_audits_advective_loss_and_declared_source_once -v -p no:cacheprovider
```

Output (exit 1):

```text
collecting ... collected 1 item
tests/test_mass_balance.py::test_one_boundary_flux_audits_advective_loss_and_declared_source_once FAILED

>       assert {1 if row.amount > 0.0 else -1 for row in entity_rows} == {-1, 1}
E       assert {-1} == {-1, 1}
E         Extra items in the right set:
E         1
============================== 1 failed in 0.51s ==============================
```

### Self-review GREEN

After ledger assembly emitted source and advective contributions independently,
the exact command above produced (exit 0):

```text
collecting ... collected 1 item
tests/test_mass_balance.py::test_one_boundary_flux_audits_advective_loss_and_declared_source_once PASSED
============================== 1 passed in 0.36s ==============================
```

## Final verification

### Task 4 focused suite

Command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_mass_balance.py -v -p no:cacheprovider
```

Output (exit 0, no warnings):

```text
collecting ... collected 18 items
tests/test_mass_balance.py::test_internal_flow_is_equal_debit_and_credit PASSED
tests/test_mass_balance.py::test_state_is_immutable_including_nested_input_mappings PASSED
tests/test_mass_balance.py::test_cross_loop_flow_requires_physical_transfer_identifier PASSED
tests/test_mass_balance.py::test_external_flux_requires_named_boundary PASSED
tests/test_mass_balance.py::test_one_day_water_fixture_is_a_hand_literal PASSED
tests/test_mass_balance.py::test_every_registered_entity_is_advected_at_source_concentration PASSED
tests/test_mass_balance.py::test_excessive_fraction_is_subdivided_and_not_clipped PASSED
tests/test_mass_balance.py::test_nonfinite_and_materially_negative_states_are_rejected PASSED
tests/test_mass_balance.py::test_corrupted_ledger_is_detected_independently_for_one_entity PASSED
tests/test_mass_balance.py::test_no_purge_fixture_reaches_physical_censored_stop PASSED
tests/test_mass_balance.py::test_sufficient_purge_fixture_matches_closed_form_trajectory PASSED
tests/test_mass_balance.py::test_step_halving_converges_toward_purge_oracle PASSED
tests/test_mass_balance.py::test_property_internal_transfer_preserves_positivity_and_stock PASSED
tests/test_mass_balance.py::test_external_reaction_sink_is_capped_by_available_stock PASSED
tests/test_mass_balance.py::test_one_boundary_flux_audits_advective_loss_and_declared_source_once PASSED
tests/test_mass_balance.py::test_closed_form_oracle_uses_hand_derived_literals[values0] PASSED
tests/test_mass_balance.py::test_closed_form_oracle_uses_hand_derived_literals[values1] PASSED
tests/test_mass_balance.py::test_closed_form_oracle_uses_hand_derived_literals[values2] PASSED
============================= 18 passed in 0.70s ==============================
```

### Tasks 1–3 regression suite

Command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_contracts.py tests/test_cli.py tests/test_schemas.py tests/test_chemistry.py tests/test_treatment.py tests/test_domains.py -v -p no:cacheprovider
```

Output (exit 0, no warnings):

```text
collecting ... collected 63 items
tests/test_contracts.py: 2 passed
tests/test_cli.py: 1 passed
tests/test_schemas.py: 22 passed
tests/test_chemistry.py: 8 passed
tests/test_treatment.py: 14 passed
tests/test_domains.py: 16 passed
============================= 63 passed in 2.54s ==============================
```

## Requirement audit and self-review

- `NetworkState` is a frozen dataclass and defensively copies every nested
  mapping into read-only proxies. Every compartment receives an explicit
  `loop_id`; omitted loop maps use the single-loop default required by the
  brief's introductory example.
- `Flow` is a volumetric movement. At every RK stage it derives every entity
  rate from the source state's current stock/volume concentration. Water and
  entity debit/credit rows are exactly paired under the same transaction ID.
- Cross-loop flows without a nonblank `physical_transfer_id` fail with
  `CROSS_LOOP_TRANSFER` before state mutation.
- `ExternalFlux` requires a nonblank boundary and explicitly records influx,
  purge, entity source, and capped entity sink rows. There is no unledgered
  state delta.
- The step operator limits every base substep to 0.25 hours and further reduces
  it until aggregate gross advective withdrawal is at most 10% of each source
  volume. It never clips internal water flow. A request that cannot finish
  without exhausting the source fails with `FLOW_EXCEEDS_SOURCE`.
- State construction and numerical stages reject nonfinite values and material
  values below `-1e-12`; roundoff inside tolerance is normalized to zero.
- `audit_ledger` computes independent absolute and relative residuals for water
  and each registered conserved entity, with `balanced` requiring every
  relative residual to be at most `1e-10`.
- The YAML oracles contain hand literals. Both accumulation cases are advanced
  only through `step_state`; the no-purge path terminates at the physical
  `2*C0` censoring threshold, and the purge path covers `12*V/q` and checks the
  closed-form trajectory plus `exp(-12)` terminal distance.
- Hypothesis generates valid water/entity states and requested transfers. The
  properties check positivity, unchanged total internal entity stock, atomic
  pair sums, and subdivision without clipping. No mocks are used.
- Mutation review: reversing a ledger sign, omitting an entity, treating a
  cross-loop flow as local, relaxing the 10% rule, clipping the 8 L transfer,
  failing to cap a reaction sink, corrupting one entity row, or replacing the
  analytic formula with either branch alone is caught by at least one test.

## Concerns

- No product concern remains for Task 4.
- The shared worktree contains unrelated untracked `data/` and `scripts/`
  directories. They were neither inspected for implementation purposes nor
  staged or committed by Task 4.
- Git reports a user-level global-ignore permission warning and possible future
  LF-to-CRLF normalization while staging. Neither warning appeared in pytest
  output or changed the committed Task 4 content.
