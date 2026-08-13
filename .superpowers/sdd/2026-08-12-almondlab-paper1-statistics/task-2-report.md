# Paper 1 Task 2 - transparent synthetic biology surrogate

## Scope and claim boundary

Task 2 implements the complete Section 8.2.1 synthetic biology surrogate and
the preflight-addendum overrides. It is a deterministic, inspectable design
model for hypothesis generation. Its candidate anchors are
`synthetic_design_input_only` and `hypothesis_prior`; neither the inputs nor
the outputs establish efficacy, a winner, salt tolerance, survival, kernel
yield, or biological validation in almond.

The implementation owns the biology surrogate, its tests, the full typed
synthetic-scenario inputs, the exact candidate-effect fixture and runtime
mirror, and the minimal Paper 1 contract hardening needed to expose those
inputs. The parent explicitly authorized registering the new candidate fixture
in the existing exact mirror/LF resource test. Core mass, hydraulics,
provenance, candidate identity/H3, treatment, public-data, verifier-policy, and
registry work were not changed by this task.

## RED-to-GREEN evidence

The first module-availability test was written before implementation. It failed
during collection with the expected boundary:

```text
ModuleNotFoundError: No module named 'almondlab.biology_surrogate'
```

Tests were then added in the brief's 17 required groups before their production
behavior: exact C1-C6 isolation; malformed effects; APX ion isolation; bounded
C3 internal osmotic adjustment and carbon cost; separate C4 efflux/leak
directions; conservative C5 redistribution; source-capped paired transactions
and event-order invariance; the hydraulic osmotic oracle; stress isolation;
hand-computed ROS/injury/energy/growth/canopy/mannitol; nonnegative states and
overflow refusal; death/post-death semantics; strict AUC; step-halving
convergence; conservative labels; byte-identical fully consumed fixtures; and
forbidden-output-key exclusion.

The final deep-immutability RED exposed that `CandidateSpec.gates` could be
made read-only only at the cost of breaking JSON serialization: 10 failures,
92 passes. An explicit field serializer preserved both contracts. The fresh
Paper 1 plus biology pair then passed:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_paper1_contracts.py tests\test_biology_surrogate.py -q
```

Result: exit 0; **102 passed in 1.47s** (45 Paper 1 contract tests and 57
biology tests).

## Implemented scientific and numerical contract

- Frozen, slots-based public biology records reject booleans, strings,
  non-finite numbers, invalid copied objects, and derived overflow. Nested
  mappings and sequences are copied into immutable representations.
- Every equation input is explicit, versioned, and unit-named in
  `BiologyParameters`, `PlantState`, or `RootZoneForcing`. Synthetic scenarios
  now provide a fully typed initial `NetworkState`, validated hydraulic domain,
  external forcing, and explicit generator parameters; legacy aggregate knobs
  are absent.
- `shoot_partition_fraction` must equal 1.0. There is no reproductive state or
  yield/survival prediction state.
- The seven Na/Cl/K transitions use canonical `InternalEntityFlux` values and
  `step_state`: root-zone uptake enters root symplast, vacuolar transfers are
  internal, xylem loading/retrieval are explicit, and deposition is
  xylem-to-shoot tissue. No H+, pH, charge, or electrochemical adapter is
  invented; unavailable gates remain `not_evaluable`.
- Each substep independently constructs literal
  `LedgerTransactionExpectation` authority before core execution. The result is
  audited against both expected events and expected transactions and must be
  balanced. Authority is never reconstructed from returned state or ledger.
- Biology uses pre-step explicit Euler with substeps no larger than 0.25 h and
  a registered coarse/fine step-halving convergence result. Source competition
  is capped literally, and Na-efflux ATP cost uses applied rather than requested
  flux.
- C3 changes only the internal osmotic adjustment, bounded to +/-0.50 MPa; it
  cannot mutate external forcing, bulk osmolality, water potential, density, or
  hydraulic-domain applicability. All registered carbon, energy, ROS, injury,
  death, post-death missingness, and canopy-AUC rules are explicit.
- Candidate effects accept exactly C1-C6 and only their registered whitelist.
  Every one of the 12 fixture anchors is asserted as consumed by a concrete
  adjusted parameter.

The hydraulic acceptance-13 oracle is exercised through the validated core
domain: fresh uptake 0.888212, saline uptake 0.455696, ratio 0.513049 (absolute
tolerance 1e-6). Perfect Na exclusion still retains the registered bulk osmotic
penalty.

## Fresh verification

Expanded biology/core integration:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_hydraulics.py tests\test_mass_balance.py tests\test_paper1_contracts.py tests\test_contracts.py tests\test_core_acceptance.py tests\test_verification_resources.py -q
```

Result: exit 0; **476 passed in 103.76s**.

Scoped full suite after concurrent coordination:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests --ignore=tests\test_registries.py --ignore=tests\test_safe_data.py -q
```

Result: exit 0; **804 passed in 112.18s**. The two ignored files were explicitly
excluded by the parent because a separate agent was in an intentional import
RED while authoring them; they are outside Task 2 ownership. This report does
not represent that scoped run as an unqualified whole-suite pass.

Static and resource checks:

- `compileall` over the two implementation modules and their focused tests:
  exit 0.
- Candidate fixture test/runtime mirrors: byte-identical, 574 bytes, LF-only.
- `git diff --check` over every tracked owned path: exit 0. The repository's
  existing Windows line-ending warning appeared for tracked text files; the
  portable hash-locked YAML mirrors themselves contain no carriage returns.

## Independent review

A fresh independent scientific/code review will target the path-explicit owned
commit immediately after it is created. Its result and any resulting fix
evidence will be recorded as a follow-up rather than asserted in advance.

## Review repair for `18724f4`

The first independent review found three blocking correctness issues. The
repair was implemented test-first without changing any core, verifier,
registry, provenance, or candidate-identity implementation:

- Biology intervals used repeated floating subtraction plus undeclared
  `1e-15`/`1e-14` tail thresholds. An ordinary 1.0 h interval with a 0.1 h
  maximum step was rejected after advancing almost the entire interval. The
  repair uses an integer `ceil(duration / maximum_step)` plan and a
  deterministic positive partition whose exact `fsum` is the requested
  duration; every substep is at or below the registered maximum. Final time,
  state history, ledger entries, transaction authority, and cursor progression
  are asserted for 0.1/1.0, 0.2/(2/10), and 0.1/(1.1/10) plans. The remaining
  undeclared `1e-15` metadata tolerance was separately put through RED/GREEN
  and removed.
- **Specification dimensional erratum:** Section 8.2.1 wrote an ATP-equivalent
  amount `E_available` over a denominator formed from an ATP-equivalent demand
  rate. For an integration substep of `dt` hours, the dimensionally consistent
  limiter is
  `f_ATP = min(1, E_available / (atp_cost_per_na * J_efflux_demand * dt + energy_epsilon_atp_eq))`.
  The epsilon is now explicitly an ATP-equivalent amount, renamed from
  `energy_epsilon_atp_eq_h` to `energy_epsilon_atp_eq` throughout the dataclass,
  scenario fixture, contracts, and tests. Zero demand returns `f_ATP = 1`.
  Flux calculation consumes the actual substep duration, while energy is still
  charged once from the core-applied, source-capped efflux amount. Hand oracles
  cover `E=0.1`, `J=0.2`, cost 2 at 0.25 h and 0.125 h, together with the
  existing source-competition oracle.
- The YAML scenario document exposed four anchor templates plus `scenarios`,
  while the loader inspected only `scenarios`. The loader now requires exactly
  the five registered string root keys (`biology_parameters`, `initial_state`,
  `forcing`, `generator_parameters`, `scenarios`), validates every template
  against its exact typed schema, validates every scenario expansion, requires
  a nonempty list, and requires every template anchor to be consumed by at
  least one scenario. Missing, extra, non-string, detached, or drifting root
  inputs fail closed with structured errors.

### Repair RED/GREEN evidence

The initial exact regression selection failed **11/11** for the expected
reasons: the renamed amount field was absent and root mutations/templates were
ignored. A direct pre-repair reproduction also raised
`BIOLOGY_NUMERIC_INVALID` for 1.0 h at a 0.1 h maximum step. After the minimal
implementation, the same 11 cases passed. A separate regression for the final
undeclared `1e-15` half-step slack failed before its removal and passed after.

Fresh focused verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_paper1_contracts.py -q
```

Result: exit 0; **114 passed in 1.98s**.

Fresh expanded biology/core verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_hydraulics.py tests\test_mass_balance.py tests\test_paper1_contracts.py tests\test_contracts.py tests\test_core_acceptance.py tests\test_verification_resources.py -q
```

Result: exit 0; **488 passed in 101.74s**.

The concurrently owned provenance repair agent also ran the complete repository
suite against the combined working tree after these changes: exit 0;
**912 passed, 2 POSIX-only tests skipped, 1 pytest cache warning in 115.90s**.
That full-run evidence is attributed to that agent rather than represented as
this task's own command.

Static/resource checks passed: `compileall` over the two owned implementation
modules and focused tests; scoped `git diff --check`; absence of hidden
`1e-15`/`1e-14` values in owned code/config/tests; and byte-identical,
LF-only candidate fixture mirrors (574 bytes). No efficacy, survival, yield,
food-safety, calibration, or preferred-candidate claim is made.

A fresh independent review will target the exact repair commit after it is
created.
