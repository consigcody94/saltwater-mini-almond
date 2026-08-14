# Paper 1 Task 4 — synthetic discovery and confirmation preflight addendum

This addendum refines `task-4-plan-extract.md`. It freezes the Task 4 trust
boundary, interfaces, generation order, configuration obligations, and test
oracles. It does not authorize a biological, efficacy, survival, food-safety,
regulatory, calibration, or preferred-candidate claim. Every generated datum
and every Task 4 verification result is `synthetic_only`.

**Runtime-alignment authority:** the LF rule committed at `608b761` and the
immutable runtime-authority amendment committed at `ec35d56`, whose exact
UTF-8/LF document SHA-256 is
`f3da58e10b0e051e181c80163d05c856a001f1f29e8c18383278ae63c7f9aeef`,
control the narrow runtime deltas identified below. This alignment does not
rewrite the approved prospective registration at `f200edd` + `d5412a9` and
does not create a second scientific authority.

## Status, precedence, and start gate

The approved program specification, Paper 1 global constraints, Task 1 and
Task 2 approved APIs, this addendum, and final Task 3 retain their existing
precedence, except for the single discovery-only start-gate exception in the
immutable runtime-authority amendment. Task 4 still does not create plants,
positions, physical batches, reservoirs, water batches, temporal runs, or a
confirmation family.

After this alignment receives its own diff review, Task 4 may enter GREEN only
for these discovery-only runtime boundaries:

1. construct and canonically revalidate the exact five-field
   `CohortDesignBundle` in the next section;
2. construct and canonically revalidate `Paper1SimulationConfig` only when
   both `confirmation_config` and `confirmation_design` are exactly `None`;
3. replay the registered Task 3 discovery allocation at root seed `20260812`
   only inside canonical revalidation, to compare the supplied and registered
   manifests; and
4. perform pure validation, hashing, capacity derivation, nominal-forcing
   derivation, and immutable-copy checks without Task 4 outcome RNG or
   filesystem output.

The mandatory frozen Task 3 replay is the sole permitted `SeedSequence`/PCG64
activity and is not authority to choose a seed or allocation. No Task 4 RNG,
synthetic discovery outcome, file creation, calibration, fit/holdout use,
confirmation construction or validation as production authority, ranking,
selection, tournament assembly, one-shot wrapper, or outcome generation may
enter GREEN under `ec35d56`. All broader start gates remain closed until a
later, separately approved authority exists.

The current specification has a single `## 11. Biosafety and regulatory
boundary` section containing two paragraphs; it does not contain §§11.1–11.3.
Task 4 must not cite nonexistent subsections or manufacture the missing third
requirement. For Task 4, the binding §11 consequences are only that no permit,
IBC determination, institution, containment approval, or regulator decision
may be generated, and synthetic containment/logistics fields cannot be
reported as physical compliance. A protocol owner must clarify the requested
§§11.1–11.3 reference before any traceability table claims subsection-level
coverage.

## Preflight findings that the terse plan leaves unresolved

The bullets below preserve the original preflight diagnosis. They are not
alternate runtime snapshots: where the approved prospective registration at
`f200edd` + `d5412a9` and its reviewed implementation prerequisites closed a
listed contract/configuration blocker, those later immutable authorities
control. The unresolved current blockers are the absent confirmation
registration and every generation/calibration/outcome boundary excluded by
`ec35d56`.

The original findings were:

- Final Task 3 is approved and immutable at
  `d242473269803fa16461f78e8784813272912fbb`; the earlier dependency
  observations in this addendum are retired. Its exact source pins
  are `src/almondlab/design.py` =
  `9ae36381d59c641728c01e1e04ef4a9f1106fc02332c9b352e3e71bc3ebf15b9`,
  `tests/test_design.py` =
  `05565f4ac926809df35a1b9a8fac10404e27e0b0fdc8f01e1afbdd627bf5ffb3`,
  and `tests/fixtures/paper1_small.yaml` =
  `beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6`.
- `Paper1DesignConfig` is intentionally frozen to discovery: nine groups, two
  discovery runs, four reservoirs per water per run, five plants per cell, and
  exactly 720 plants. It cannot represent a confirmation family of at most
  four selected candidates plus empty vector, six reservoirs per water, later
  runs, or a configurable five/six plants per cell.
- The pre-registration `SyntheticScenarioConfig` contained one
  `RootZoneForcing`. The registered
  estimand needs candidate and empty-vector trajectories under two distinct
  waters. Reusing one forcing for both waters or deriving an unregistered
  control forcing would invalidate calibration and the estimand.
- The pre-registration `generator_parameters` contained only eleven scalar
  floats. It had
  no observation schedule, chemistry covariance, charge tolerance, water-loop
  schedule, LOD/LOQ table, drift model, death-threshold variation,
  heteroscedasticity rule, H3-endpoint-specific error, calibration tolerance,
  or confirmation cell size. Those values cannot become code defaults.
- The archived v1.3 water recipes were not charge balanced under the approved
  `chemistry.charge_balance_error` convention. The nonsaline recipe returned
  `23.167155425219942%`; the marine challenge returned
  `3.302286198137171%`. Those bytes remain historical anchors and cannot enter
  active assembly; the later approved active recipes are separate authorities.
- The archived scalar `h3_observation_error_sd` was ambiguous because C1/C2/C4/
  C5/C6 use log-ratio H3 scales while C3 uses a native-unit difference. The
  approved registration resolved it with an endpoint-keyed, unit-bearing map.
- Several pre-registration scenarios did not encode their stated mechanism.
  `sensor_drift_missingness` lacked drift input; `insufficient_purge` replaced
  forcing osmolality instead of reducing a purge flow; `chassis_interaction`
  lacked a second chassis and candidate × chassis term; and
  `delayed_toxicity` lacked an onset-time input. The approved proposal's exact
  scenario registry supersedes those snapshots; names alone remain no
  authority to infer a mechanism.
- A run identifier cannot prove that confirmation occurred later. This finding
  motivated the final exact physical-schedule field
  `run_sequence_ordinal`; discovery's maximum ordinal must be less than
  confirmation's minimum ordinal. Values come from the supplied physical
  schedule, never from parsing `run_id` text.
- The one-call plan cannot perform outcome-dependent finalist selection
  without importing future Task 5/decision authority. Any future generation
  boundary must remain split around independent selection. No combined wrapper
  or generation boundary is currently authorized.

## Final Task 3 dependency contract

The public names below are the final approved Task 3 surface at immutable
commit `d242473269803fa16461f78e8784813272912fbb`. They are immutable
dependencies, and Task 4 may call but not shadow,
loosen, rename, or reconstruct their authority:

- `BaselinePlant`, `BaselineRoster`
- `PositionSlot`, `PositionMap`
- `AllocationRecord`, `RandomizationManifest`
- `CohortIdentitySet`
- `ExperimentalUnitSpec`, `ExperimentalUnitAudit`
- `randomize(...)`, `revalidate_confirmation_design(...)`,
  `revalidate_baseline_roster(...)`, `revalidate_position_map(...)`,
  `revalidate_randomization_manifest(...)`,
  `revalidate_cohort_identity_set(...)`,
  `revalidate_experimental_unit_audit(...)`, `cohort_identity_set(...)`,
  `validate_cohort_separation(...)`, and `validate_experimental_units(...)`.

Those final boundaries reconstruct and detach every nested value, derive
physical identities, and recompute the audit. Task 4 must call them; an
`isinstance` check, dataclass `replace`, Pydantic `model_copy(update=...)`, or
caller-authored identity/pass summary is insufficient.

Task 4 owns this wrapper, using the exact final Task 3 types:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class CohortDesignBundle:
    cohort_id: Literal["discovery", "confirmation"]
    baseline_roster: BaselineRoster
    position_map: PositionMap
    manifest: RandomizationManifest
    audit: ExperimentalUnitAudit
```

The exact public boundaries are:

```python
def assemble_cohort_design_bundle(
    *,
    cohort_id: Literal["discovery", "confirmation"],
    config: Paper1DesignConfig | ConfirmationDesignConfig,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
    manifest: RandomizationManifest,
    audit: ExperimentalUnitAudit,
) -> CohortDesignBundle: ...

def revalidate_cohort_design_bundle(
    value: object,
    *,
    config: Paper1DesignConfig | ConfirmationDesignConfig,
) -> CohortDesignBundle: ...
```

The design config remains an external validation authority; it is deliberately
not a sixth bundle field. The successful current role is discovery only and
requires `type(config) is Paper1DesignConfig`. Construction/revalidation calls
the final Task 3 boundaries, derives `ExperimentalUnitSpec.from_design`,
derives the cohort identity set, independently recomputes the audit, compares
the registered manifest to the deterministic Task 3 replay, and returns a
detached base object. It rejects mutable, subclass-surrogate, or corrupted
values and never trusts a caller `passed` flag or result hash.

Confirmation assembly fails
`CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` at `cohort_id`, with only
`details.required_authority ==
"task4_registered_confirmation_cohort_bundle"`, before reading `config`,
roster, map, manifest, or audit. Revalidation first requires an exact outer
`CohortDesignBundle` and exact primitive role; a confirmation role then fails
the same way before reading `config` or nested family values. The future-facing
union annotation does not authorize confirmation success.

Final Task 3 provides separate mechanical `ConfirmationDesignConfig` support
rather than loosening `Paper1DesignConfig`, but that type is not a Task 4
production registration. A future Task 4 confirmation amendment must
independently freeze the exact family and authorities before these mechanical
invariants can succeed at runtime:

- groups are one to four externally selected C1–C6 IDs, in registered order,
  plus `empty_vector`; no sham, unmodified, assay-positive, pilot, failed, or
  unselected candidate rows;
- at least two temporal runs, each strictly later by `run_sequence_ordinal`;
- exactly six distinct `(water_id, reservoir_id)` loops per water across those
  later runs; the split by run is explicit in `PositionMap`, not assumed equal;
- one scenario-frozen value, exactly integer 5 or 6, for plants per
  group × reservoir cell;
- every candidate and empty vector crosses at least two new physical
  transformation batches, balanced under the final Task 3 rule;
- the roster plant set equals the manifest plant set, the position-slot set
  equals the manifest position set, every supplied plant/slot is allocated
  exactly once, and no extra roster material is retained as confirmation data.

When a future confirmation amendment is separately approved, aggregate
assembly must revalidate each cohort audit independently with its own config
and spec, then call final Task 3 `validate_cohort_separation` on the two
canonical roster/map/manifests. It must not pass two cohort sets to one
single-cohort audit. That future check covers `plant_ids`,
`transformation_batch_ids`, `reservoir_ids`, `water_batch_ids`, `run_ids`, and
non-null transformation-event IDs, plus later ordinals and distinct Task 3
manifest seeds. It defines a future check only; it does not authorize a
confirmation family now.

## Task 4 public interfaces and immutable result structure

The current authorized aggregate is a frozen, slots-based, keyword-only
dataclass that retains every authority needed for canonical revalidation:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Paper1SimulationConfig:
    design: Paper1DesignConfig
    candidates: CandidateRegistry
    candidate_effects: Mapping[str, CandidateEffects]
    model_domain: ModelDomain
    water_recipes: Paper1WaterRecipeRegistry
    scenario_registry: SyntheticScenarioRegistry
    stop_policy: Task4StopPolicy
    discovery_design: CohortDesignBundle
    confirmation_config: ConfirmationDesignConfig | None
    confirmation_design: CohortDesignBundle | None
    generator: SyntheticGeneratorConfig
    config_sha256s: Mapping[str, str]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]
```

The exact current public signatures are:

```python
def assemble_paper1_simulation_config(
    *,
    design: Paper1DesignConfig,
    candidates: CandidateRegistry,
    candidate_effects: Mapping[str, CandidateEffects],
    model_domain: ModelDomain,
    water_recipes: Paper1WaterRecipeRegistry,
    scenario_registry: SyntheticScenarioRegistry,
    stop_policy: Task4StopPolicy,
    discovery_design: CohortDesignBundle,
    confirmation_config: ConfirmationDesignConfig | None,
    confirmation_design: CohortDesignBundle | None,
    raw_authority_bytes_by_name: Mapping[str, bytes],
) -> Paper1SimulationConfig: ...

def revalidate_paper1_simulation_config(
    value: object,
) -> Paper1SimulationConfig: ...
```

`generator` is derived internally from the canonically reconstructed
`scenario_registry.anchor.generator`; callers do not supply it. The factory
synthesizes `EvidenceLabel.SYNTHETIC_ONLY`, canonically reconstructs every
typed authority, and returns detached base objects. `candidate_effects` and
`config_sha256s` are new `MappingProxyType` instances. Direct dataclass
construction never proves that the factory ran, so every consumer first calls
`revalidate_paper1_simulation_config`.

`raw_authority_bytes_by_name` has exact outer runtime type `dict` or exact
`MappingProxyType`, exact primitive `str` keys, exact `bytes` values, and this
exact eight-key package-logical inventory, with no aliases, absolute/host
paths, missing keys, or extras:

```text
configs/candidates.yaml
configs/experiment_paper1.yaml
configs/model_domains.yaml
configs/paper1_task4_stop_policy.yaml
configs/paper1_water_recipes.yaml
configs/synthetic_scenarios.yaml
fixtures/candidate_effects.yaml
fixtures/paper1_small.yaml
```

The aggregate retains raw digests rather than source bytes. Neither aggregate
revalidation nor capacity preflight may reopen an authoring path, read a host
path, or load `almondlab.resources`; the factory hashes only the explicit bytes
supplied at its public boundary. `config_sha256s` is factory-computed and has
exactly these 16 immutable keys:

```text
configs/candidates.yaml:raw_sha256
configs/candidates.yaml:normalized_sha256
configs/experiment_paper1.yaml:raw_sha256
configs/experiment_paper1.yaml:normalized_sha256
configs/model_domains.yaml:raw_sha256
configs/model_domains.yaml::core_v1:normalized_sha256
configs/paper1_task4_stop_policy.yaml:raw_sha256
configs/paper1_task4_stop_policy.yaml:normalized_sha256
configs/paper1_water_recipes.yaml:raw_sha256
configs/paper1_water_recipes.yaml:normalized_sha256
configs/synthetic_scenarios.yaml:raw_sha256
configs/synthetic_scenarios.yaml:normalized_sha256
fixtures/candidate_effects.yaml:raw_sha256
fixtures/candidate_effects.yaml:normalized_sha256
fixtures/paper1_small.yaml:raw_sha256
paper1_nominal_forcing_schedule_v2:canonical_sha256
```

The exact C1–C6 `candidate_effects` order is revalidated only through the
private Task 4 wrapper authorized by runtime-amendment Section 6; Task 4 may
not call Task 2's private `_canonical_effects`. The wrapper requires an exact
`dict`/`MappingProxyType`, exact base `CandidateEffects`, exact four declared
fields, exact `MappingProxyType` parameter maps, primitive strings, finite
float parameter values, and key/value candidate agreement. It reconstructs
new base instances so public Task 2 validation runs again, normalizes ordinary
`Exception` failures (never `BaseException`) to
`CANDIDATE_PARAMETER_VIOLATION`, authenticates the complete normalized payload
against
`0d5b62381409a3ed814b4687291e7f4c4c987c8d84db63353b85c11789fe25e8`,
then calls public `apply_candidate_effects`. A structurally valid altered value
instead fails `PAPER1_CONFIG_AUTHORITY_MISMATCH` at
`fixtures/candidate_effects.yaml:normalized_sha256`. The wrapper returns only
detached base instances in a new `MappingProxyType` and creates no second
candidate-effect registry.

Confirmation pairing and precedence are exact:

| `confirmation_config` | `confirmation_design` | Current result |
|---|---|---|
| `None` | `None` | legal discovery-only assembly/revalidation |
| `None` | non-`None` | `PAPER1_SIMULATION_CONFIG_INVALID` at `confirmation_design` |
| non-`None` | `None` | `PAPER1_SIMULATION_CONFIG_INVALID` at `confirmation_design` |
| non-`None` | non-`None` | `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` at `confirmation_design` before family access |

An incomplete pair says `confirmation config and design must be absent or
present together`. A complete pair fails with message `confirmation design
requires separately approved registration` and only
`details.required_authority ==
"task4_registered_confirmation_cohort_bundle"`. Frozen raw, normalized, or
discovery literal drift fails `PAPER1_CONFIG_AUTHORITY_MISMATCH`; wrapper-shape
errors use `COHORT_DESIGN_INVALID` or
`PAPER1_SIMULATION_CONFIG_INVALID` at the narrowest field. Existing Task 1/2/3
and recipe/scenario/domain/capacity errors pass through unchanged.

### Deferred generation, calibration, and result surfaces

The following generation and result-model text remains future design context
only. It is not implementation authority under `ec35d56`; none of these
functions may be implemented, called as a production boundary, or used to
create RNG state, a file, a confirmation family, a tournament, or an outcome.
A future discovery decision would require split generation so it cannot give
Task 4 decision authority:

```python
def generate_discovery_synthetic(
    config: Paper1SimulationConfig,
    scenario: SyntheticScenarioConfig,
    *,
    root_seed: int,
) -> SyntheticDiscovery: ...

def generate_confirmation_synthetic(
    config: Paper1SimulationConfig,
    scenario: SyntheticScenarioConfig,
    discovery: SyntheticDiscovery,
    *,
    root_seed: int,
) -> SyntheticConfirmation: ...

def assemble_synthetic_tournament(
    discovery: SyntheticDiscovery,
    confirmation: SyntheticConfirmation,
    *,
    run_directory: RunDirectory,
) -> SyntheticTournament: ...

def generate_paper1_synthetic(
    config: Paper1SimulationConfig,
    scenario: SyntheticScenarioConfig,
    root_seed: int,
    *,
    run_directory: RunDirectory,
) -> SyntheticTournament: ...
```

The deferred wrapper would require a separately registered confirmation pair
and would never rank discovery data, choose IDs, change the family, or inspect
truth to allocate slots. No such registration currently exists.

Calibration is outside this runtime slice. The sole future calibration
authority is the approved proposal at `f200edd` + `d5412a9`, especially
§§20.9.1–20.9.3; the older mapping-of-one-sequence signature formerly printed
here is retired and must not be implemented. `Paper1SimulationConfig`
assembly accepts no fit/holdout panel, performs no root solving, and produces
no calibration result.

The following deferred result proposal would contain analyst data and audit
references, never hidden truth values. No class in this block is a result of
the currently authorized assembly/revalidation slice:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class AnalystCohortInputs:
    cohort_id: Literal["discovery", "confirmation"]
    allocation: ProvenanceFrame
    observations: ProvenanceFrame
    observed_water_batches: ProvenanceFrame
    manifest_sha256: str
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

@dataclass(frozen=True, slots=True, kw_only=True)
class AnalystTournamentInputs:
    discovery: AnalystCohortInputs
    confirmation: AnalystCohortInputs
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

@dataclass(frozen=True, slots=True, kw_only=True)
class HiddenTruthArtifactRef:
    relative_path: Literal["tournament/private/truth.parquet"]
    sha256: str
    row_count: int
    schema_version: Literal["1.0.0"]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

@dataclass(frozen=True, slots=True, kw_only=True)
class GeneratorAudit:
    seed_tree: SeedTree
    water_ledger_sha256: str
    root_ledger_sha256: str
    domain_validation_sha256: str
    calibration: tuple[MechanismCalibration, ...]
    input_sha256s: Mapping[str, str]
    truth_artifact: HiddenTruthArtifactRef
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

@dataclass(frozen=True, slots=True, kw_only=True)
class SyntheticTournament:
    schema_version: Literal["1.0.0"]
    analyst: AnalystTournamentInputs
    audit: GeneratorAudit
    run_id: str
    canonical_sha256: str
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]
```

`SyntheticDiscovery` and `SyntheticConfirmation` use the same sealed
`AnalystCohortInputs` plus a private publisher-owned truth handle; neither
exposes a truth dataframe. Later analysis accepts only
`AnalystTournamentInputs` or `AnalystCohortInputs`, never
`SyntheticTournament`, `GeneratorAudit`, a truth path, or a scenario object.

Any future result models must use exact-type checks, frozen slots, tuple conversion,
mapping proxies, and canonical reconstruction of nested objects. Dataframes
are accepted only as exact `pandas.DataFrame`, immediately copied into
`ProvenanceFrame`, and returned only through detached copies. Tests must attack
`object.__setattr__`, dataclass `replace`, Pydantic `model_copy(update=...)`,
mutable nested maps/lists, dataframe backing arrays, attrs, indexes, and
subclass instances. This future-facing language does not permit RNG creation
or file creation under the current authority.

All remaining outcome, truth-firewall, seed-tree, calibration, fixture,
publishing, performance, and generation-test sections below are likewise
future requirements. They do not broaden the current assembly/revalidation
slice or authorize their implementation under `ec35d56`.

## Analyst/truth firewall and record schema

Every generated table row has `source_type == "synthetic"`,
`data_origin == DataOrigin.SYNTHETIC` where that column is present, and
`evidence_label == EvidenceLabel.SYNTHETIC_ONLY`. Physics-constrained internal
ledgers do not promote the final synthetic record; the shared evidence
composer makes `synthetic_only` dominant.

Stable row IDs use only cohort, table kind, and canonical zero-based ordinal:

```text
SYN_D_ALLOC_000000000000
SYN_D_OBS_000000000000
SYN_D_WATER_000000000000
SYN_C_ALLOC_000000000000
SYN_C_OBS_000000000000
SYN_C_WATER_000000000000
```

The ordinal is assigned after sorting by the complete public semantic key. It
does not contain candidate effect, scenario, latent value, calibration target,
rank, or outcome. IDs are stable across caller row order, worker count, and
chunk boundaries for the same canonical inputs.

The analyst observation table has these exact public columns in this order:

```text
record_id, source_type, data_origin, evidence_label, schema_version,
cohort_id, allocation_id, plant_id, blinded_treatment_code, group_id,
water_id, run_id, run_sequence_ordinal, reservoir_id, water_batch_id,
transformation_batch_block, transformation_batch_id, position_id,
scheduled_time_days, endpoint_id, observation_type, reported_value, unit,
lod, loq, censor_code, missingness_code, death_status, qc_state
```

`group_id` is treatment allocation, not hidden truth; the blinded projection
omits it until the registered database-lock boundary. `reported_value` is
nullable. `lod`/`loq` are nullable only for endpoints explicitly registered as
uncensored. Controlled vocabularies and their exact allowed values live in
the typed config/schema, not free text.

Analyst parquet files use `preserve_index=False`, a fresh zero-based
`RangeIndex` in memory, the exact column order above, and no pandas attrs or
Parquet schema metadata except the schema version/evidence label allowlist.
Their fixed filenames are cohort/table names only. They contain no columns,
attrs, indexes, categories, filenames, paths, or dictionary metadata named or
valued with `truth`, `latent`, `true_effect`, `scenario_id`,
`calibration_target`, `winner`, or `best_candidate`. A scenario hash is also
excluded from analyst inputs because ten known hashes would reveal the
scenario by enumeration. Those hashes remain in the trusted run manifest.

Hidden truth is written only to the fixed literal
`private/truth.parquet`. The filename never encodes the scenario or candidate.
It contains latent mechanism parameters, zero-mean hierarchy effects,
pre-drift/pre-error values, counterfactual censor/missing values, missingness
probabilities/uniforms, death thresholds/times, calibration fit/holdout
estimands, and scenario ID. Only its detached hash, row count, schema version,
and relative path enter `SyntheticTournament`.

## Named SeedSequence authority

Task 4 creates its own `provenance.SeedTree`; it never borrows a Task 3 child
stream. The discovery Task 3 seed, confirmation Task 3 seed, and Task 4 root
seed must be pairwise-distinct exact interoperable nonnegative integers. This
numerical separation is required because names do not alter NumPy
`SeedSequence` state.

The root structure has exactly these children. Numeric prefixes make the
shared `SeedTree`'s sorted-name spawn order equal the protocol order:

1. `(0,) 00_climate`
2. `(1,) 01_chemistry`
3. `(2,) 02_run_effects`
4. `(3,) 03_batch_effects`
5. `(4,) 04_reservoir_effects`
6. `(5,) 05_plant_effects`
7. `(6,) 06_observation_noise`
8. `(7,) 07_censoring`
9. `(8,) 08_drift`
10. `(9,) 09_death`
11. `(10,) 10_missingness`
12. `(11,) 11_calibration`

Children 00–10 each have exactly `(0,) 00_discovery` and
`(1,) 01_confirmation`. `11_calibration` has exactly `(0,) 00_fit` and
`(1,) 01_holdout`. Each node calls `spawn` once with its complete child count;
no code path spawns lazily or according to present candidates. Use
`numpy.random.Generator(numpy.random.PCG64(seed_sequence))`, not an unpinned
default bit generator.

Within each leaf stream, the coordinator sorts the complete semantic key set,
draws one fixed-shape array once, and binds array positions to keys before any
parallel work. Workers receive values, never generators. Calibration panels
are drawn once and shared across candidates in registered C1–C6 order. Float
reductions use canonical ordering and deterministic accumulation. Completed
rows are stable-merge-sorted by the full public key before ID assignment and
serialization. Adding workers, changing chunks, permuting inputs, or selecting
a subset for execution cannot change an existing key's value or output bytes.

Module-global NumPy/Python RNGs, `random`, Python `hash()`, process IDs,
timestamps, filesystem enumeration order, and worker identity are forbidden as
scientific inputs. Cryptographic SHA-256 remains required for provenance; it
is not used as an unrecorded random-number source.

## Scenario/configuration contract expansion

The ten scenario IDs are exact and closed:

```text
perfect_control
true_ion_exclusion
root_na_accumulation
marker_only
nonsaline_penalty
chassis_interaction
delayed_toxicity
sensor_drift_missingness
insufficient_purge
selection_bias_false_leader
```

No aliases, extra scenarios, or scenario-derived output fields are accepted.
The loader compares every expanded scenario to the registered anchor and
allows differences only in these path classes:

- `mechanism`: approved `BiologyParameters` or candidate-effect whitelist
  fields;
- `forcing`: explicit per-water forcing schedule and water-loop inputs;
- `variance`: hierarchy, climate, chemistry, observation, drift, and
  death-threshold variance fields;
- `missingness`: MAR/MNAR probability-model fields.

Fields or keys containing `outcome`, `auc_effect`, `true_delta`,
`target_delta`, `decision`, `eligible`, `advance`, `rank`,
`selection_result`, `winner`, or `best_candidate` are forbidden in production
scenario edits. The already registered `mnar_tipping_delta` is a missingness
logit shift, not an outcome effect. A target estimand may appear only in a
calibration fixture/config section consumed by
`calibrate_mechanism_to_estimand`; it is never copied into an observation.

The exact scenario edit-path policy is:

| Scenario | Permitted differences from the anchor |
|---|---|
| `perfect_control` | none; every C1–C6 effect must reproduce its baseline |
| `true_ion_exclusion` | `mechanism.parameters.root_na_permeability_l_cm2_h` only |
| `root_na_accumulation` | registered Na efflux/retrieval/root-injury mechanism fields only |
| `marker_only` | registered ROS-clearance mechanism fields only; no ion/canopy edit |
| `nonsaline_penalty` | registered candidate trade-off/cost fields only; no water-forcing edit |
| `chassis_interaction` | an explicit registered candidate × chassis mechanism modifier and named synthetic chassis only; until the domain/config supplies both, the scenario must fail `DOMAIN_VIOLATION` rather than fake an interaction |
| `delayed_toxicity` | registered mechanism onset time and post-onset injury/senescence parameters only |
| `sensor_drift_missingness` | `drift` and `missingness` sections only |
| `insufficient_purge` | `water_loop.purge_volume_l_day` only; salt accumulation must emerge from the ledger |
| `selection_bias_false_leader` | hierarchy/observation variance fields only; no selected ID or effect edit |

Scenario-specific numeric values must remain explicit versioned config. This
table fixes writable paths, not their values.

The current configuration must be version-expanded before Task 4. Preserve
and consume all eleven existing generator inputs with these frozen meanings:

| Existing key | Meaning and unit |
|---|---|
| `run_variance` | variance of the zero-mean run intercept on log normalized-canopy trajectory, `log-ratio^2` |
| `batch_variance` | variance of the zero-mean physical transformation-batch intercept, `log-ratio^2` |
| `reservoir_variance` | variance of the zero-mean run × water × reservoir intercept, `log-ratio^2` |
| `plant_variance` | variance of the zero-mean independently transformed plant intercept, `log-ratio^2` |
| `canopy_observation_error_sd` | multiplicative canopy measurement SD on the log scale, `log-ratio` |
| `ion_observation_error_sd` | multiplicative ion measurement SD on the log scale, `log-ratio` |
| `h3_observation_error_sd` | legacy field to be replaced losslessly by endpoint-keyed errors; it cannot remain a scalar |
| `missingness_intercept` | baseline MAR log-odds, dimensionless logit |
| `missingness_stress_slope` | MAR log-odds per one SD of the registered observable stress proxy |
| `mnar_tipping_delta` | MNAR log-odds shift per one SD of the hidden counterfactual endpoint |
| `duration_days` | scheduled experiment duration, days |

No existing value may be parsed and ignored. The first six, the three
missingness fields, and duration retain their current numeric values during
the migration unless a protocol amendment changes them. The scalar H3 value
must be migrated explicitly to six endpoint records with declared analysis
scale/unit; copying `0.05` into incompatible units without protocol approval is
not allowed.

Every generator scalar becomes an exact record
`{value, unit, evidence_label}`. Counts additionally require exact integers.
The expanded `SyntheticGeneratorConfig` has these required sections and exact
field names; no field has a Python/Pydantic default:

- `hierarchy`: the four existing variance keys.
- `climate`: `temperature_ar1_phi`, `temperature_innovation_sd_k`,
  `apar_ar1_phi`, `apar_log_innovation_sd`, `matric_potential_ar1_phi`,
  `matric_potential_innovation_sd_mpa`,
  `potential_transpiration_log_innovation_sd`, and
  `climate_initialization_burnin_steps`.
- `chemistry`: `common_ion_log_sd`, `boron_log_sd`,
  `ec_measurement_sd_ds_m`, `osmolality_measurement_sd_osmol_kg`,
  `ph_measurement_sd`, `temperature_measurement_sd_k`, and
  `charge_balance_tolerance_percent`. Ion perturbation uses a common positive
  multiplier on the already balanced charge-bearing full-ion recipe;
  alkalinity and bicarbonate remain explicitly paired. EC, pH, osmolality,
  and temperature are separate measurements, never ion generators.
- `water_loop`: `reservoir_initial_volume_l`,
  `water_batch_volume_l`, `irrigation_volume_l_per_plant_day`,
  `drainage_return_fraction`, `purge_volume_l_day`,
  `sampling_volume_l_per_sample`, `reservoir_min_volume_l`,
  `reservoir_max_volume_l`, and an explicit ordered
  `operator_event_times_days` sequence.
- `observation`: the existing canopy/ion errors,
  `h3_observation_error_by_endpoint`,
  `canopy_heteroscedastic_log_slope`,
  `ion_heteroscedastic_log_slope`, exact ordered
  `canopy_observation_times_days`, `ion_observation_times_days`, and
  `h3_observation_times_days`.
- `censoring`: exact endpoint-keyed `lod_by_endpoint` and
  `loq_by_endpoint`, each with value and endpoint unit, plus
  `lod_log_sd_by_endpoint` and `loq_log_sd_by_endpoint` for the registered
  sample-specific threshold variation driven by `07_censoring`. Every LOQ is
  greater than or equal to its LOD after variation.
- `drift`: `canopy_drift_per_day`, `ion_drift_per_day_by_endpoint`,
  `h3_drift_per_day_by_endpoint`, `calibration_interval_days`, and
  `post_calibration_residual_sd_by_endpoint`.
- `death`: `biomass_death_threshold_log_sd`,
  `injury_death_threshold_log_sd`, and
  `sustained_injury_duration_log_sd`. These create plant-specific registered
  threshold heterogeneity; the death RNG never writes a death outcome.
- `missingness`: the three existing fields plus exact allowed observable
  stress-proxy fields, their centering/scaling values, and
  `mnar_endpoints`. The proxy may use water, scheduled time, or prior observed
  values, never current hidden truth; only the registered MNAR term may use the
  current counterfactual endpoint.
- `calibration`: `absolute_tolerance_log_ratio`, `relative_tolerance`,
  `max_iterations`, `fit_panel_size`, `holdout_panel_size`, and
  `holdout_tolerance_log_ratio`.
- `design`: existing `duration_days` and exact integer
  `confirmation_plants_per_group_reservoir`, restricted to 5 or 6.

The scenario contract must also replace the single `forcing` with an exact
`forcings_by_water_id` mapping. It has exactly the two registered water IDs;
each value is a nonempty ordered tuple of complete `RootZoneForcing` records
whose durations sum exactly to `duration_days * 24` under the project's finite
arithmetic rules. All chemistry, initial-state, forcing, and generator records
remain `hypothesis_prior` or `synthetic_only`. Missing/extra fields, units,
endpoint keys, water IDs, schedules, or scenario edit paths fail before RNG.

## Chemistry, domain, and ledger authority

For every physical `water_batch_id`, Task 4 creates a typed `WaterBatch` from
the corrected full-ion recipe and calls both `charge_balance_error` and
`validate_domain` against the approved `core_v1` domain. The `DomainRequest`
uses chassis `Vairo`, life stage `juvenile`, `requested_label=synthetic_only`,
and synthetic provenance/observations for every required chemistry field and
analyte. Missing required analytes, wrong EC kind, out-of-range values,
provenance mismatch, or absolute charge error above the registered tolerance
fails the batch before plant simulation.

ECw is a measured typed field. It is never converted into ion concentrations,
used to rescale ions, averaged during blending, substituted for pore-water EC
or ECe, or treated as an electroneutrality oracle. Ions come only from the
registered full-ion recipe and charge-neutral perturbation. EC, osmolality,
pH, and temperature receive their own measured/calibrated noise and drift.
Where blending is used, call `blend_by_volume` with an explicit
`BlendMeasurement`; never average EC.

Water-loop transactions are applied through `mass_balance.step_state` with
the canonical operator schedule and an explicit `LedgerCursor`. Expected
events/transactions are built from the input schedule before the step and
passed independently to `audit_ledger`; they are not reconstructed from the
result. Water and every registered ion must close at the core tolerance.

Root/plant transitions are generated only through approved Task 2 APIs:
`apply_candidate_effects`, `simulate_plant`, and `canopy_auc`. The complete
`SimulationResult.ledger` is retained as the root ledger and independently
audited. Task 4 cannot recreate §8.2.1 equations, mutate `PlantState`, bypass
the source caps, invent counter-ions/H+/pH/electrochemical results, or derive
post-death ion values from the conserved internal stocks.

Candidate mechanism parameters may change only through the Task 2 isolation
whitelist. Scenario nuisance variance may perturb registered initial states or
zero-mean trajectory coordinates, but it cannot set candidate AUC, survival,
death, decision, or family membership. Physical stocks remain available to
the hidden conservation audit after death; public canopy is exactly zero from
the adjudicated death time onward; public ion/H3 observations after death are
undefined, never zero or imputed.

## Latent-to-observed order and truth semantics

For each scheduled endpoint row, use this exact order:

1. Simulate the charge-audited water/root state and mechanism-linked plant
   trajectory. Store the latent physical value in private truth only.
2. Apply registered plant/run/batch/reservoir nuisance effects and determine
   true death from the Task 2 threshold rule. After true death, canopy truth
   is zero and ion/H3 truth is undefined.
3. Apply the time-indexed calibration/drift function to endpoints that remain
   defined. Store pre-drift and post-drift values in private truth.
4. Add heteroscedastic observation error using the observation-noise stream.
   Store the pre-censor signal in private truth.
5. Apply LOD/LOQ censoring using the censoring stream only where the registered
   assay model is stochastic. For signal below LOD, public value is null,
   `censor_code=below_lod`, and the public upper bound is LOD. For signal in
   `[LOD, LOQ)`, public value is null,
   `censor_code=detected_below_loq`, with public lower/upper bounds LOD/LOQ.
   For signal at or above LOQ, report the finite signal and
   `censor_code=quantified`. No LOD/2, LOQ/2, zero, or boundary substitution is
   allowed.
6. Draw missingness last. MAR probability is a registered logistic function
   of analyst-observable covariates only. MNAR adds the configured tipping term
   based on the standardized hidden counterfactual endpoint only for listed
   MNAR endpoints. If missing, public value and censor interval are null and
   `missingness_code` records only the registered public reason; the
   counterfactual value, censor state, probability, and uniform remain private.
7. Emit the public row and private truth row together, with a one-to-one
   internal record link. The analyst row never carries the private link.

Technical outage, containment termination, assay failure, MAR, MNAR, and
biological death have distinct codes. Death is never encoded as ordinary
missingness. A scheduled post-death ion/H3 row has
`death_status=postdeath_undefined`, null value/limits, and a death reason, not a
MAR/MNAR draw. Calibration samples are separate records and cannot be used as
plant replicates.

## Mechanism-to-estimand calibration

Calibration varies only the candidate's registered primary mechanism scalar.
All trade-off fields remain at the explicitly supplied fixture values. Each
objective evaluation:

1. calls `apply_candidate_effects` on a fresh canonical baseline;
2. simulates candidate and empty vector under both registered waters;
3. computes normalized canopy AUC through Task 2 `canopy_auc`; and
4. returns the exact log-scale difference in differences from §9.3.

It may not add an effect to canopy, AUC, the observation table, a death field,
or a decision field. Calibration uses the `00_fit` forcing panel only. Use a
bracketed deterministic root finder such as SciPy `brentq`; evaluate both
endpoints first and require finite values and an actual sign-changing bracket
or an exact endpoint root. No unconstrained optimizer or result-dependent
bracket expansion is allowed.

`MechanismCalibration` is a frozen exact record containing candidate and
primary parameter IDs, target, lower/upper bounds, calibrated mechanism value,
fit estimand/residual, held-out estimand/residual, iterations, solver status,
boundary status, fit/holdout panel hashes, tolerances, and `synthetic_only`.
A missing bracket raises `CALIBRATION_BRACKET_FAILURE`; iteration exhaustion
raises `CALIBRATION_NONCONVERGENCE`; nonfinite biology raises the original
stable biology error; a boundary root is returned with
`boundary_status="lower"` or `"upper"` and may not be silently called an
interior calibration. A fit is usable only if the independent `01_holdout`
panel residual is within the registered holdout tolerance; otherwise raise
`CALIBRATION_HOLDOUT_MISMATCH`. No dataset or manifest is published after any
of these failures.

The known-effect fixture uses the specification's synthetic design target
`log(1.30)`. The fixture must explicitly name its candidate, trade-off value,
bracket, tolerances, and fit/holdout forcing hashes. Those numeric bracket
values remain a protocol-owner registration blocker; Task 4 cannot guess them
or choose a candidate after observing which solver call succeeds.

## Fixtures and independent oracles

Create exact-byte mirrors in both `tests/fixtures/` and
`src/almondlab/resources/fixtures/` for:

- `global_null.yaml`: all six candidates' mechanism/trade-off inputs reproduce
  the scenario baseline exactly; discovery and confirmation remain independent.
- `known_effect.yaml`: one prospectively named candidate is calibrated through
  its registered mechanism to `log(1.30)` with explicit fit and held-out panels;
  no direct AUC value appears.
- `winner_curse.yaml`: candidates named prospectively in registered order have
  explicit equal/null or registered useful truths and discovery variance large
  enough to exercise selection; confirmation uses the same mechanism truths
  with independent new hierarchy draws and physical identities.

The fixtures contain inputs and truth declarations, not generated estimates,
selected IDs, pass flags, or expected winners. Tests maintain independent
code-owned literal oracles:

- hierarchy counts use §9.6 arithmetic, not dataframe group-bys treated as
  authority;
- disjointness compares the five literal identity sets and also calls the Task
  3 audit;
- charge balance independently sums signed charge using registered valences,
  then cross-checks the public chemistry API;
- calibration recomputes the four AUC terms from latent trajectories with an
  independent trapezoid implementation, not a summary returned by calibration;
- missingness/censoring uses a hand-authored row and injected fixed draws to
  pin the seven-stage order;
- a secret truth sentinel is placed in the fixture and scanned against every
  analyst column, value, attr, index, category, filename, and serialized byte;
- expected seed names/spawn keys are literals and are checked against a direct
  NumPy `SeedSequence` reference, not the generator's serializer;
- fixture mirrors are compared byte-for-byte and every anchor is recorded as
  consumed.

Acceptance tests 7, 8, 9, and 16 are not Task 4 self-tests:

- Task 4 supplies `global_null` inputs/truth for Acceptance 7; Task 8 owns the
  20,000-replicate family-wise false-selection calculation and Clopper–Pearson
  oracle.
- Task 4 supplies held-out `known_effect` inputs/truth for Acceptance 8; the
  independent analysis/recovery pipeline owns bias, coverage, and power.
- Task 4 supplies the discovery/confirmation data-generating conditions for
  Acceptance 9; `decisions.rank` and later selection-recovery code own finalist
  count, shrinkage, raw selected bias, and confirmation bias.
- Acceptance 16 is the later registered null/target operating-characteristic
  suite. Task 4 cannot write `test_07.json`, `test_08.json`, `test_09.json`, or
  `test_16.json`, set their pass state, or use truth to make their decisions.

Task 4 may publish structural fixture-validation evidence under Task 4-specific
names, but those records must say that operating characteristics are
`not_evaluated` at this stage.

## Publishing, hashing, and safe joins

Publish only into a caller-supplied `RunDirectory`. Stage the complete fixed
tree under a private child of that claimed run, fsync files/directories, and
atomically rename the child to `tournament/` only after every artifact is
closed and hashed. An injected failure leaves no `tournament/` directory and
no manifest. Individual final destinations use the public atomic provenance
writers; no overwrite is allowed.

The fixed artifact paths are:

```text
tournament/analyst/discovery_allocation.parquet
tournament/analyst/discovery_observations.parquet
tournament/analyst/discovery_water_batches.parquet
tournament/analyst/confirmation_allocation.parquet
tournament/analyst/confirmation_observations.parquet
tournament/analyst/confirmation_water_batches.parquet
tournament/audit/water_ledger.parquet
tournament/audit/root_ledger.parquet
tournament/audit/domain_validation.json
tournament/audit/calibration.json
tournament/private/truth.parquet
tournament/synthetic_tournament.json
```

`truth.parquet` is included in `RunManifest.artifact_hashes`; both Task 3
manifest hashes, raw/normalized config hashes, fixture hashes, candidate-effect
hash, model-domain hash, code/lock hashes, and Task 4 seed tree are recorded.
Call `finalize_manifest` only after repeated file-provenance capture proves no
artifact changed. The public tournament document contains the truth reference
hash, not truth values.

Use `safe_join` for compatible, bounded metadata joins and assert exact
cardinality. Synthetic/empirical mixing must raise `SYNTHETIC_CONTAMINATION`
with zero output rows. The current `safe_join` has an inclusive 10,000-row cap,
so Task 4 must not evade it with `pandas.merge`. Generate denormalized
observation rows directly from canonical allocation records; perform only
small allocation/metadata joins. Any future large-table join requires a
separately reviewed provenance-preserving partition/concatenation API.

## Performance and execution profiles

The publication envelope is 720 discovery plants plus 300–360 confirmation
plants at the maximum five-group family, before repeated observations. At a
0.25-hour biology step over 84 days, naïvely running both coarse and half-step
trajectories is millions of audited substeps. Task 4 must stream rows/ledgers to
the private staging area, bound memory, avoid quadratic dataframe appends, and
record elapsed time and peak-memory measurements without making them pass
oracles unless thresholds are registered.

Default Task 4 tests use three explicit profiles:

- pure unit tests: hand-sized typed states and injected fixed random arrays;
- quick integration: full valid roster/position/manifest cardinalities but a
  fixture-owned short forcing schedule and sparse observation schedule, clearly
  labeled non-publication;
- publication generation: full 84-day schedule and 720 + 300–360 plants,
  marked slow/manual until a later performance gate explicitly runs it.

No Task 4 test runs PyMC, REML/max-t, 50,000 bootstrap/max-t draws, 1,000 or
20,000 operating-characteristic replicates, or the 10,000-resample Type-M
bootstrap. Those belong to Tasks 5, 6, and 8. A quick profile can validate
structure/reproducibility only and cannot satisfy Acceptances 7/8/9/16.

## Adversarial test matrix

Task 4's focused suite must cover at least:

1. exact discovery hierarchy/counts and confirmation 1–4 candidates + EV,
   exactly six reservoirs/water, two or more later runs, and 5/6 plants/cell;
2. zero roster/position leftovers and exact one-to-one manifest use;
3. five-namespace discovery/confirmation disjointness plus optional event IDs;
4. rejection of equal/earlier run ordinals and same-run leftovers;
5. repeat-seed byte identity, changed-seed changed stochastic values, and
   invariant design cells;
6. input-order, worker-count, chunk-size, and completion-order invariance;
7. exact Task 4 seed tree, Task 3 seed separation, pinned PCG64, and refusal of
   global RNG/Python hash use;
8. every existing generator parameter is consumed and perturbing each changes
   only its registered mechanism;
9. missing/extra/unitless/coercive/nonfinite config values and forbidden
   scenario edits fail before RNG/output;
10. exactly ten scenario IDs and exact edit-path whitelist;
11. no truth/scenario/calibration sentinel in analyst attrs, indexes,
   filenames, dictionaries, columns, values, or bytes;
12. exact `SYN_` record IDs, uniqueness, canonical order, and evidence labels;
13. deep immutability and copy-bypass attacks on every public model;
14. full-ion presence, independent charge oracle, EC-kind refusal, no EC-to-ion
   conversion, domain bounds, units, and provenance;
15. water/root ledger closure, source caps, paired entries, and no result-built
   oracle;
16. death threshold heterogeneity, exact death time, canopy zero thereafter,
   persistent private stocks, and undefined public post-death ions/H3;
17. exact drift → error → censor → missingness order and distinct MAR/MNAR/
   outage/death reason codes;
18. LOD/LOQ boundary equality, no substitution, and counterfactual privacy;
19. calibration bracket failure, endpoint root, interior convergence,
   nonconvergence, nonfinite biology, and held-out mismatch;
20. proof that calibration changes only the registered primary mechanism and
   never AUC/outcome/decision fields;
21. global-null mechanism identity, known-effect held-out recovery input, and
   winner-curse equal-truth/independent-confirmation structure without claiming
   Acceptance 7/8/9/16;
22. exact authoring/package fixture mirrors, package discovery, consumed-anchor
   inventory, and wheel-installed-resource smoke test;
23. safe-join synthetic/empirical refusal, cardinality refusal, and no pandas
   merge bypass;
24. atomic publication failure at every stage, repeated hash capture,
   truth-parquet hash in the manifest, and no partial final directory;
25. recursive serialized-name scan forbidding `winner`, `best_candidate`,
   direct outcome-effect fields, unlabeled forecasts, physical claims, invented
   author/institution/permit/funding identities, and Task 7/8/9/16 pass outputs.

## Ownership map

| Owner | Permitted work |
|---|---|
| Task 3 | Final physical roster/position/manifest/audit APIs; confirmation-design support; run ordinals; fixture/package coordination for Task 3 resources |
| Coordinated Task 1 contract change | Versioned scenario schema expansion, exact-key/unit validation, two-water forcing schedules, preservation/migration of all eleven current generator fields |
| Protocol/config owner | Correct charge-balanced water recipes; all new numeric generator values; known-effect candidate/bracket/tolerances; publication observation/water-loop schedules |
| Task 4 current runtime slice | Only the assembly/revalidation boundaries in `src/almondlab/simulate.py` and `tests/test_simulate.py`, plus the narrowly coordinated capacity resource-read removal authorized by `ec35d56`; fixture parsing, RNG, outcomes, files, calibration, confirmation, tournament generation, and reports require separate authority |
| Tasks 5/6/7/8 | Discovery analysis, confirmation analysis, decisions/sensitivity, and operating-characteristic acceptance authority respectively |

Task 4 does not edit candidate identities/H3 rules, biology equations, core
mass/hydraulic/chemistry/domain semantics, Task 3 allocation outputs, decision
rules, verification thresholds, manuscript claims, or physical data.

## Run, commit, and review gates

1. Record import RED for exactly `CohortDesignBundle`,
   `Paper1SimulationConfig`, `assemble_cohort_design_bundle`,
   `revalidate_cohort_design_bundle`, `assemble_paper1_simulation_config`, and
   `revalidate_paper1_simulation_config` after this alignment is reviewed.
2. Implement only the discovery assembly/revalidation slice and the narrowly
   coordinated capacity resource-read removal authorized by `ec35d56`.
3. Pin the exact fields/signatures, registered Task 3 replay, eight raw inputs,
   16 hashes, CandidateEffects wrapper, capacity outcomes, confirmation
   precedence, deep detachment, and no-hidden-load behavior. Stop before Task 4
   outcome RNG, file output, calibration, confirmation, generation, or
   tournament work.
4. Run focused Task 4 + Task 1/2/3 + chemistry/domain/mass/provenance/safe-data
   tests. Run the full suite in a stable worktree and record exact counts,
   skips, duration, commit, and dirty state.
5. Do not run or claim the publication PyMC/20,000-replicate gates in Task 4.
   Record them as downstream-not-evaluated.
6. Before staging, inspect `git diff --name-only` and prove no unowned file was
   changed. Preserve concurrent Task 3 work.
7. Commit Task 4 owned files and separately authorized coordinated files with
   explicit hashes. Do not include generated run directories.
8. Request independent statistical/scientific-boundary review and code/
   reproducibility review. Review must inspect exact authority retention,
   confirmation precedence, capacity identities, CandidateEffects isolation,
   no hidden loads, deep detachment, and the absence of RNG/output/calibration/
   generation or Acceptance 7/8/9/16 self-authority.

The current runtime slice is complete only when its focused and full
non-publication suites pass and both reviews approve. That completion means
only that discovery assembly/revalidation is suitable for downstream TDD; it
does not mean a generator exists. Full Task 4 remains a future gate. Only after
a separate authority may it require fixture parsing, repeated generation,
atomic publication behavior, or generator-suitability claims. Neither kind of
completion means any candidate works or any physical experiment is safe,
permitted, successful, or confirmed.
