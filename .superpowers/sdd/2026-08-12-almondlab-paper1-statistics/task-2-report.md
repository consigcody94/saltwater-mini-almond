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

## Final rereview repair I - RED evidence

The next exact-commit rereview found five Important boundary classes still
open: zero-representable subnormal transfer amounts, public-step closure under
mandatory halving, an undeclared one-million-substep allocation cap, avoidable
trapezoid overflow, and non-total YAML graph/error handling. Tests were added
against public state, ledger/cursor authority, or structured errors before any
production edit. The exact RED selection was:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_paper1_contracts.py -q -k "mandatory_half_step or simulation_domain_preflight or simulate_preflights or unrepresentable_transition_amount or mixed_source_group or preserves_finite_result or representable_subnormal_exact or positive_exact_result or exactly_accumulates_mixed or translates_syntax_and_key or schema_version_uses_candidate or graph_beyond_code_owned or bounded_deep_graph or alias_expansion_bomb or parser_recursion_exhaustion or translates_malformed_parser or non_string_mapping_keys or depth_1500_recursion"
```

Result: exit 1; **27 failed, 3 passed, 140 deselected in 7.17 s**. The
failures reproduced all seven typed transition families and both shared-source
mixed cap groups, fine-step public reconstruction, absent coarse/fine/schedule
preflights, all requested AUC scale boundaries, and candidate/scenario YAML
syntax, key-type, schema, depth, alias, and recursion failures. The three
passing controls covered bounded-deep candidate traversal, exact mixed-scale
AUC accumulation, and one already-stable malformed-input path.

Three narrower RED additions then closed preflight-resource variants found
during implementation. A finite `1e308` forcing exposed float ratio overflow
instead of the structured domain error (**1 failed, 109 deselected in 1.03
s**); a generator that raises after its first invalid forcing exposed eager
schedule consumption (**1 failed, 110 deselected in 0.97 s**); and a shallow
10,001-element YAML sequence exposed the initially missing node budget (**1
failed, 111 deselected in 1.60 s**). Restoring the node budget made its exact
selection pass (**1 passed, 111 deselected in 0.82 s**). The complete original
round-I regression selection then passed **30 passed, 140 deselected in 1.38
s**.

The subsequent deterministic partition audit found an accepted pair at the
exact public cap that preflighted as 20,000 substeps but whose former
uniform-plus-tail construction attempted substep 20,001. Its public
counterexample (`duration_hours=0.005012190753747413`,
`maximum_step_hours=2.506095376873707e-7`) was captured first (**1 failed, 112
deselected in 1.03 s**) and then repaired. A fixed-seed audit of 5,000
factor-derived and 5,000 arbitrary accepted finite pairs subsequently verified
exact `fsum` duration authority, the public open lower bound, maximum-step
authority, and the 20,000-step cap.

### Final rereview repair I - implementation

- Rates whose duration product is exactly zero in binary64 are now removed
  before event namespacing or core invocation. They create no physical event,
  transaction, ledger rows, cursor ordinal, ATP charge, or synthetic minimum
  mass. Tests exercise uptake, efflux, sequestration, release, xylem loading,
  retrieval, and deposition independently, plus representable/underflow
  competitors sharing the symplast or xylem source cap.
- The public parameter contract remains the exact open bound
  `integrator_max_step_hours > 2e-14`. The mandatory half-step is now an
  internal solver setting rather than a reconstructed public
  `BiologyParameters`, so the next binary64 maximum above the boundary supports
  both trajectories and every fine step remains above the core-integrable
  minimum.
- `MAX_INTEGRATOR_SUBSTEPS = 20_000` is a code-owned public materialization
  limit. At the registered 0.25-hour coarse step it covers 208 days and at the
  required 0.125-hour fine step it covers 104 days, exceeding the registered
  84-day simulation. `validate_simulation_domain` eagerly validates each
  public forcing/parameter pair; `simulate_plant` additionally preflights whole
  coarse and fine schedules while consuming iterables only until the first
  decisive violation. Exact binary-rational ceiling counts handle all finite
  durations, including `1e308`, and raise
  `BIOLOGY_SIMULATION_DOMAIN_INVALID` before trajectory allocation, flux/core
  work, ledger mutation, cursor advance, or RNG use.
- The bounded partition now mixes only the two adjacent binary64 values around
  the exact rational average. It selects their counts with exact
  binary-rational arithmetic and requires `fsum(partition)` to equal the
  reported duration. This closes the exact-cap pair without allocating a
  forbidden extra step; cumulative public time targets now use each actual
  partition duration rather than assuming a uniform prefix.
- `canopy_auc` evaluates every finite input through the registered trapezoid
  formula using exact binary-rational products, endpoint sums, normalization,
  and accumulation, then rounds once to binary64. Finite normal and subnormal
  results succeed; a true overflow or a positive exact result that rounds to
  zero fails as `CANOPY_AUC_INVALID` with a stable reason. Thus the requested
  huge-canopy/tiny-width case returns `0.9999999999999999` without avoidable
  intermediate overflow.
- The shared strict YAML loader now applies code-owned pre-compose limits of
  `MAX_YAML_DEPTH = 64`, `MAX_YAML_NODES = 10_000`, and
  `MAX_YAML_ALIAS_REFERENCES = 256`, followed by iterative graph validation.
  Mapping keys must be exact primitive YAML strings apart from the legal merge
  tag. Duplicate keys, duplicate explicit merge keys, cycles, excessive depth,
  wide node graphs, and alias expansion bombs fail at every depth while one
  legal merge or merge sequence retains standard explicit-key override
  precedence. Scenario parse/resource failures become
  `SYNTHETIC_SCENARIO_INVALID`; every candidate payload or schema failure uses
  `CANDIDATE_PARAMETER_VIOLATION`. PyYAML, recursion, type, memory, encoding,
  value, and I/O exceptions are translated without catching `BaseException`.

### Final rereview repair I - GREEN and verification evidence

Fresh focused biology and Paper 1 contract verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_paper1_contracts.py -q
```

Result: exit 0; **174 passed in 4.00 s**.

Fresh expanded biology/core verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_hydraulics.py tests\test_mass_balance.py tests\test_paper1_contracts.py tests\test_contracts.py tests\test_core_acceptance.py tests\test_verification_resources.py -q
```

Result: exit 0; **548 passed in 104.97 s**.

Fresh complete repository verification against the stabilized shared live tree:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests -q
```

Result: exit 0; **1055 passed, 3 POSIX-only tests skipped in 124.66 s**.

Static verification passed over the two owned source modules and focused test
modules, and scoped `git diff --check` passed over all six owned paths. Only
Git's existing Windows line-ending conversion warnings were emitted. No
registry, public-data, provenance, visualization, mass-balance, or hydraulics
path was changed by this repair. No scientific efficacy, survival, yield,
food-safety, calibration, or preferred-candidate claim is made.

A fresh independent review will target the exact repair commit after it is
created.

## Final rereview repair J - expanded YAML merge work

The exact rereview confirmed all preceding numerical, ledger, simulation-domain,
canopy, schema, and basic YAML findings closed, but found that raw token, node,
alias, depth, and visited-once graph budgets did not bound PyYAML's recursive
merge flattening. A compact acyclic chain in which every mapping merged the
preceding mapping twice expanded exponentially while remaining below every
existing resource count.

### RED evidence

Candidate and scenario public-loader regressions were written before the
production change. The candidate compact 30-map chain reached the deterministic
construction hook once instead of failing before construction (**1 failed, 116
deselected in 1.11 s**). Its separate at/over-boundary selection produced **1
failed, 2 passed, 114 deselected in 1.13 s**: exactly 10,000 expanded pairs and
200 shared non-merge aliases were the passing controls, while 10,001 pairs did
not raise. The scenario selection similarly produced **2 failed, 2 passed, 60
deselected in 0.91 s**: its compact construction hook and 10,001-pair boundary
failed, while the exact-10,000 and legal merge-sequence/explicit-override
controls passed. A direct unguarded compact-chain run was deliberately stopped
after the 20-second command bound rather than allowing exponential allocation.

### Implementation

- `MAX_YAML_EXPANDED_MERGE_PAIRS = 10_000` now publishes and documents the
  code-owned maximum mapping-pair work for any mapping PyYAML may flatten.
- After iterative cycle, key, node, and depth validation but before
  `super().construct_document`, a second iterative DAG pass memoizes the
  expanded cost of each composed mapping. An explicit non-merge pair costs one;
  every mapping in a merge value or merge sequence contributes its expanded
  cost once per occurrence, including duplicate aliases. Nested mapping and
  sequence values are traversed without charging ordinary non-merge aliases.
  Legal explicit overrides remain explicit pairs and retain standard YAML
  precedence.
- Every addition saturates at `limit + 1`; over-budget graphs therefore reject
  as `YamlResourceLimitError(resource="expanded_merge_pairs", limit=10000,
  observed=10001)` without constructing a giant integer, mutating nodes, or
  invoking PyYAML mapping construction. Candidate payloads translate this to
  `CANDIDATE_PARAMETER_VIOLATION` at `candidate_effects`; scenarios translate
  it to `SYNTHETIC_SCENARIO_INVALID` at `yaml`. Existing cycle validation runs
  first and retains `YamlAliasCycleError` authority.

### GREEN and verification evidence

The combined merge-expansion, exact-boundary, ordinary-alias, legal-precedence,
and public-translation selection passed **8 passed, 173 deselected in 1.07 s**.
Fresh focused biology and Paper 1 contract verification passed **181 passed in
4.07 s**. Fresh expanded biology/core verification passed **555 passed in
103.72 s**.

A complete repository run was also executed after the independently owned
registry round-three commits but during the provenance agent's deliberate RED
window. It produced **1071 passed, 3 POSIX-only skips, and 6 provenance-only
failures in 122.65 s**. All six were the provenance agent's newly added
precommit-cleanup race regressions; that agent subsequently reported their
exact selection GREEN 6/6. There were no biology, Paper 1 contract, registry,
mass, or hydraulics failures. This report does not misstate the overlapping
run as a stable whole-repository pass; provenance will rerun full verification
after this biology commit on the stable combined tree.

Static verification passed over the owned source and tests, and scoped
`git diff --check` passed over all owned paths. No registry, public-data,
provenance, visualization, mass-balance, or hydraulics path was changed by this
repair. No scientific efficacy, survival, yield, food-safety, calibration, or
preferred-candidate claim is made. A fresh independent review will target the
exact repair commit.

## Final rereview repair

The exact rereview of `18724f4` plus `7d0a01a` found five remaining numerical
and input-boundary defects. This repair closes them without changing core
mass, hydraulics, provenance, registries, candidate identities, or scientific
claims:

- `advance_plant` now computes and validates the finite registered target time
  before partitioning, ledger authority, core evolution, or ODE work. A finite
  positive duration that cannot produce a representably greater public time
  fails `BIOLOGY_NUMERIC_INVALID` at `forcing.duration_hours`; every substep
  target must also increase strictly, and the last state is assigned the one
  prevalidated final target exactly.
- ATP limitation now branches on the exact interval ATP demand amount. Thus a
  zero ATP cost with nonzero Na-efflux demand gives `f_ATP = 1`, applies the
  requested transfer subject only to the canonical source cap, and consumes no
  energy. Zero ion demand remains separately covered.
- Step-halving convergence now includes type-exact alive/death semantics and
  exact trajectory adjudication time. No death-time tolerance is registered,
  so coarse and fine trajectories must record the same adjudication boundary;
  the reproduced 0.25 h versus 0.125 h death event is rejected.
- The synthetic-scenario loader uses a safe, merge-aware unique-key loader.
  Duplicate explicit keys are rejected at every mapping depth before YAML
  merge flattening can obscure them, including root, `scenario_id`, and nested
  parameter duplicates. The repository's legitimate anchors and single
  explicit merge overrides remain valid.
- Every convergence difference, scale, relative-tolerance product, and
  tolerance sum now passes through checked finite arithmetic. The undeclared
  `1e-30` denominator floor was removed. A coordinate whose two values are
  exactly zero uses the explicitly documented absolute-only rule; otherwise
  the actual nonzero magnitude is the relative scale. Overflowing registered
  tolerance arithmetic fails `BIOLOGY_NUMERIC_INVALID`.

### Final repair RED/GREEN evidence

Eight public-boundary regressions were written first. Before implementation,
the exact selection failed **8/8** for the intended reasons: time validation
occurred only after an overflowing flux, zero-cost nonzero demand emitted no
efflux, different death substeps converged, the hidden denominator floor
distorted the scaled difference, overflowing tolerance arithmetic was
accepted, and all three duplicate-YAML depths were collapsed before the
contract could inspect them. After the minimal changes, the same selection
passed **8/8** (114 deselected) in 0.73 s.

Fresh focused verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_paper1_contracts.py -q
```

Result: exit 0; **122 passed in 2.06 s**.

Fresh expanded biology/core verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_hydraulics.py tests\test_mass_balance.py tests\test_paper1_contracts.py tests\test_contracts.py tests\test_core_acceptance.py tests\test_verification_resources.py -q
```

Result: exit 0; **496 passed in 103.15 s**.

A combined-tree full run was also attempted while the independently owned
registry repair was deliberately in progress. It produced **942 passed, 3
POSIX-only skips, and 17 failures in 115.31 s**. Every failure was confined to
`tests/test_registries.py` and matched that agent's pending accession,
public-evidence, and content-freeze changes; there were no biology, Paper 1
contract, core, or provenance failures. This report does not misrepresent that
concurrent-state run as a whole-suite pass. A stable full run is required after
the registry repair lands.

No efficacy, survival, yield, food-safety, calibration, or preferred-candidate
claim is made. A fresh independent scientific/code rereview is requested for
the exact final repair commit.

## Final rereview repair H - RED evidence

The next fresh rereview identified five remaining boundary defects: binary64
partition authority, sub-core-minimum forcing durations, duplicate/cyclic YAML
graphs, candidate-effect loader strictness, and overflow-safe canopy AUC.
Behavioral regression tests were added before production changes. The exact RED
selection was:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_paper1_contracts.py -q -k "adversarial_partition or substep_partition_property or public_core_domain or immediately_above_public_core_minimum or normalizes_endpoints or candidate_effect_yaml_rejects_duplicate or candidate_effect_yaml_rejects_self or duplicate_explicit_merge or self_referential_merge or merge_sequence_with_explicit_override"
```

Result: exit 1; **13 failed, 2 passed, 122 deselected in 2.53 s**. The two
passing controls proved that the duration immediately above the intended open
minimum and a legal one-element merge sequence with explicit override already
worked. The 13 failures reproduced every defect. In particular, the exact
reviewer input integrated to `0.03496126797633996` rather than the reported
`0.03496126797633995`, and Hypothesis independently minimized another drift to
`maximum_step_hours=0.0010000000000000002`, `factor=13`.

One additional stable-boundary regression was then written before its minimal
production repair. It reproduced a derived time-width overflow escaping
`canopy_auc` as `BIOLOGY_NUMERIC_INVALID` (**1 failed, 83 deselected in
0.96 s**); after the full trapezoid computation was enclosed by the endpoint
translator, the focused suite verifies `CANOPY_AUC_INVALID` instead.

### Final rereview repair H - implementation

- `_substep_partition` now derives its residual with exact `Fraction` arithmetic
  over the accepted binary64 values and verifies that `fsum(partition)` is
  exactly the registered duration before returning. Every returned step is
  positive, at or below the registered maximum, and above the public core
  timestep minimum. The exact reviewer counterexample and a 60-example
  Hypothesis property over near-minimum, small, ordinary, and maximum step
  magnitudes protect the integrated-dt authority.
- `RootZoneForcing.duration_hours` now has an explicit public open domain
  `duration_hours > 1e-14`; `BiologyParameters.integrator_max_step_hours` has
  the paired open domain `> 2e-14`. The latter guarantees that every accepted
  forcing interval can be partitioned into core-integrable substeps. Inputs on
  or below either boundary fail immediately with the appropriate stable
  biology forcing/parameter code; the next binary64 duration above the forcing
  boundary advances successfully without cap underflow, division underflow,
  or hidden `FLOW_EXCEEDS_SOURCE`.
- One safe YAML graph loader is now shared by the scenario and candidate-effect
  boundaries. It rejects duplicate explicit keys at every mapping depth,
  treats repeated explicit `<<` merge keys as duplicates, and rejects cyclic
  aliases before recursive construction. Standard YAML precedence is retained:
  an explicit mapping key overrides a merged value, and legal merge sequences
  remain supported.
- `load_candidate_effects` now translates duplicate, cyclic, malformed, and
  unreadable YAML into stable `CANDIDATE_PARAMETER_VIOLATION` errors. Tests
  cover duplicate root, candidate-ID, and nested-parameter keys plus a nested
  self-referential merge alias.
- `canopy_auc` divides each endpoint by pretreatment canopy before endpoint
  addition. Thus `[1e308, 1e308] / 1e308` over `[0, 1]` returns exactly `1.0`
  under the registered normalized trapezoid, while genuinely invalid derived
  arithmetic remains a stable `CANOPY_AUC_INVALID` boundary.

### Final rereview repair H - GREEN and verification evidence

The final exact regression selection passed **17 passed, 122 deselected in
1.67 s**. Fresh focused verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_paper1_contracts.py -q
```

Result: exit 0; **140 passed in 2.43 s**.

Fresh expanded biology/core verification:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_biology_surrogate.py tests\test_hydraulics.py tests\test_mass_balance.py tests\test_paper1_contracts.py tests\test_contracts.py tests\test_core_acceptance.py tests\test_verification_resources.py -q
```

Result: exit 0; **514 passed in 102.52 s**.

Fresh complete repository verification after the independently owned registry
work stabilized:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests -q
```

Result: exit 0; **988 passed, 3 POSIX-only tests skipped in 119.80 s**.

Static verification also passed: `compileall` over both owned source modules
and focused test modules, and `git diff --check` over every owned tracked path.
Only Git's existing Windows line-ending conversion warnings were emitted. No
registry, public-data, provenance, visualization, core mass, or core hydraulic
path was changed by this repair. No scientific efficacy, survival, yield,
food-safety, calibration, or preferred-candidate claim is made.
