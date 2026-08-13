# Paper 1 Task 4 Contract and Configuration Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every contract, physical-design, chemistry, scenario, and calibration blocker that must be resolved before the Task 4 synthetic discovery/confirmation generator can enter GREEN implementation.

**Architecture:** Keep the registered 720-plant discovery design immutable, add a separate confirmation-design contract, and require canonical whole-bundle revalidation before Task 4 creates RNG or files. Replace the v1.3 synthetic-scenario shape with an explicit v1.4 schema whose unit-bearing values, two-water forcing schedules, scenario edit paths, water-recipe lineage, and calibration registration are complete inputs rather than code defaults.

**Tech Stack:** Python 3.12, Pydantic 2, frozen/slots dataclasses, NumPy `SeedSequence`/`PCG64`, PyYAML strict loader, existing AlmondLab chemistry/domain/provenance APIs, pytest, and exact authoring/package resource mirrors.

## Global Constraints

- This plan repairs prerequisites only. It does not implement `src/almondlab/simulate.py`, generate a cohort, calibrate a mechanism, or claim any Acceptance 7/8/9/16 result.
- Every biological or generated value remains `hypothesis_prior` or `synthetic_only`. No gene efficacy, salt tolerance, survival, food-safety, containment, permit, author, institution, funding, or preferred-candidate claim is authorized.
- No result or serialized field may be named `winner` or `best_candidate`. The only non-negative-test filename exception is the addendum-required `winner_curse.yaml` input fixture; its serialized keys still obey the ban.
- The whole independently transformed composite-root plant is the construct-level biological unit; the run-qualified reservoir/loop is the water-treatment unit.
- Discovery remains exactly 9 groups × 2 waters × 2 runs × 4 reservoirs per water/run × 5 plants per group/reservoir = 720 plants.
- Confirmation contains one to four externally selected C1–C6 IDs in registered order plus `empty_vector`, exactly six reservoirs per water across at least two later runs, and one prospectively frozen cell size of exactly 5 or 6 plants.
- Discovery and confirmation must be disjoint in plant, physical transformation-batch, reservoir, water-batch, and run IDs; non-null event IDs are disjoint as defense in depth.
- A run name is not temporal evidence. `max(discovery.run_sequence_ordinal) < min(confirmation.run_sequence_ordinal)` is mandatory and ordinals are never parsed from `run_id`.
- Task 4 must call the final approved Task 3 canonical revalidation boundary before RNG construction or filesystem mutation.
- All synthetic constants live in versioned configuration with exact units and evidence labels. Python/Pydantic defaults are prohibited for scientific values.
- ECw is a measured typed field, never an ion generator or electroneutrality oracle. Bicarbonate and phosphate must not be double-counted when alkalinity is the charge term used by the approved core convention.
- Existing v1.3 water values are hypothesis-prior design anchors, not empirical measurements. They must be archived exactly; an active recipe may not inherit an `empirically_calibrated` label.
- All public inputs use exact primitive types, finite arithmetic, exact keys, canonical reconstruction, immutable nested values, and stable `AlmondLabError` codes.
- The approved program specification, Paper 1 global constraints, Task 1/2 approved APIs, Task 4 preflight addendum, and final approved Task 3 API control in that order.

---

## 1. Current-state evidence and start gate

The following current-state facts are authoritative as of this preflight:

| Authority | Current field/API | Evidence | Consequence |
|---|---|---|---|
| `configs/experiment_paper1.yaml` | `schema_version: "1.3"` and two inline `WaterChemistry` records | Raw SHA-256 `d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0` | Archive these exact bytes before changing an active recipe. |
| Same | control cation charge 21.0, anion charge 13.1 mmol_c/L | Independent formula and `charge_balance_error` both give +23.167155425219942% | Active use is blocked; the diagnostic deficit is 7.9 mmol_c/L of anionic equivalents, not permission to add a chosen ion. |
| Same | marine cation charge 61.0, anion charge 57.1 mmol_c/L | Independent formula and `charge_balance_error` both give +3.302286198137171% | Active use is blocked; the diagnostic deficit is 3.9 mmol_c/L of anionic equivalents, not a recipe amendment. |
| `configs/synthetic_scenarios.yaml` | `schema_version: "1.3.0"`, one `forcing`, eleven scalar `generator_parameters` | Raw SHA-256 `46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb` | Breaking, explicit migration is required. |
| `src/almondlab/paper1_contracts.py` | `SyntheticScenarioConfig.forcing: RootZoneForcing` and `Mapping[str, float]` generator | Required-key set contains only eleven names | It cannot represent two waters, units, schedules, censoring, drift, death heterogeneity, or calibration. |
| `Paper1DesignConfig` | discovery-only frozen identity | Nine groups, two discovery runs, four reservoirs/water/run, five plants/cell | Do not loosen it to represent confirmation. |
| Uncommitted `src/almondlab/design.py` | moving Task 3 implementation | During this review it gained provisional `run_sequence_ordinal` and `ConfirmationDesignConfig` while remaining uncommitted | No provisional name or behavior is a Task 4 dependency until the exact commit is independently approved. |
| `configs/model_domains.yaml` | `core_v1@1.0.0` allows only chassis `Vairo` | Raw SHA-256 `81bf2c2c442d07ec984010dd9c373d2da4fe776467b009246cd665609c159a71` | `chassis_interaction` must fail `DOMAIN_VIOLATION` until a second named synthetic chassis is prospectively added to a versioned `core_v1` policy. |
| `tests/fixtures/candidate_effects.yaml` | non-null C1–C6 hypothesis anchors | Raw SHA-256 `4e92c1567227b9e1f6e0713b79890bfc652a5b21a8de013769eaaa01ac939c21` | These cannot serve as the `perfect_control`/global-null identity without an explicit neutral effect record. |

Task 4 GREEN is forbidden until all of these gates are recorded:

1. The final Task 3 commit is stable, independently approved, and its public API hash is copied into the Task 4 report.
2. Discovery and confirmation roster/map/manifest/audit bundles exist, pass canonical revalidation, and have no retained same-run material.
3. The v1.4 scenario and generator contract change is separately committed and reviewed.
4. The protocol owner has supplied every value marked **new registration** below.
5. Both active full-ion recipes pass the independent signed-charge oracle, public `charge_balance_error`, and `core_v1` domain validation at the registered tolerance.
6. The known-effect candidate, primary parameter, trade-off values, bracket, tolerances, and fit/holdout panel identities are prospectively registered.

## 2. Locked target file map and ownership

| Owner | File | Change |
|---|---|---|
| Task 3 owner | `src/almondlab/design.py` | Finalize run ordinals, separate confirmation allocation, canonical whole-bundle revalidation, and exact discovery/confirmation identity audits. |
| Task 3 owner | `tests/test_design.py` | RED/GREEN tests for the above without weakening the 720-plant discovery oracle. |
| Coordinated Task 1 contract owner | `src/almondlab/paper1_contracts.py` | Add v1.4 strict quantity/generator/scenario/water-recipe contracts and explicit migration APIs. |
| Coordinated Task 1 contract owner | `tests/test_paper1_contracts.py` | Unit, schema, migration, edit-path, two-water, and copy-bypass RED tests. |
| Protocol/config owner | `configs/archive/experiment_paper1_v1_3.yaml` | Exact byte copy of the current v1.3 design; immutable historical hypothesis-prior anchor. |
| Protocol/config owner | `configs/archive/synthetic_scenarios_v1_3.yaml` | Exact byte copy of the current v1.3.0 scenario document; immutable migration source. |
| Protocol/config owner | `configs/paper1_water_recipes.yaml` | Historical recipe lineage plus two active, formula-resolved, charge-audited full-ion registrations. |
| Protocol/config owner | `configs/experiment_paper1.yaml` | Retain the frozen `Paper1DesignConfig` v1.3 shape/identity; replace only the two chemistry records with canonical active recipe chemistry and record the new raw hash externally. |
| Protocol/config owner | `configs/synthetic_scenarios.yaml` | Complete v1.4 `perfect_control` anchor, two-water forcings, and the nine exact non-anchor scenario records. |
| Coordinated packaging owner | `src/almondlab/resources/configs/**/*.yaml` | Exact runtime mirrors for every Task 4-consumed authoring config and the historical recipe archive. |
| Coordinated packaging owner | `tests/test_verification_resources.py` | Extend exact config/fixture inventories without weakening the existing core subset. |
| Task 4 owner, later | `src/almondlab/resources/fixtures/{global_null,known_effect,winner_curse}.yaml` and `tests/fixtures/...` | Exact-byte fixture mirrors only after the repaired contracts are approved. |

Task 4 does not modify candidate identities/H3 rules, biology equations, core chemistry or mass-balance semantics, decision rules, verification thresholds, manuscript claims, or physical observations.

## 3. Final Task 3 dependency contract

### 3.1 Public types and signatures

The current provisional Task 3 surface separates the discovery and confirmation **configuration types**, while retaining one type-dispatched allocation entry point. Approve and freeze this exact shape; do not add a parallel `randomize_confirmation` adapter:

```python
DesignConfig = Paper1DesignConfig | ConfirmationDesignConfig

def randomize(
    config: DesignConfig,
    root_seed: int,
    *,
    position_map: PositionMap,
    baseline_roster: BaselineRoster,
) -> RandomizationManifest: ...
```

`ConfirmationDesignConfig` is frozen, slots-based, and has no defaults. Its provisional schema string and field name are exactly `"1.0"` and `runs`:

```python
@dataclass(frozen=True, slots=True)
class ConfirmationDesignConfig:
    schema_version: str
    evidence_label: EvidenceLabel
    population: AnalysisPopulation
    selected_candidate_ids: tuple[str, ...]
    water_ids: tuple[str, ...]
    runs: tuple[str, ...]
    reservoirs_per_water: int
    independent_plants_per_group_reservoir: int
    balanced_transformation_batches: tuple[str, ...]
    construct_level_unit: Literal["independently_transformed_plant"]
    water_treatment_unit: Literal["reservoir"]
    discovery_max_run_sequence_ordinal: int
```

Runtime validation freezes `schema_version == "1.0"`, `synthetic_only`, `composite_root`, the two registered water IDs, at least two later runs, exactly six reservoirs per water **across all later runs**, cell size 5 or 6, and the two registered transformation-batch blocks. `full_allocation_groups` is a derived tuple of one to four selected C1–C6 IDs in registry order plus `empty_vector`; it is not caller-settable.

Add `run_sequence_ordinal: int` to `PositionSlot`, `AllocationRecord`, blinded projections, canonical payloads, fixture schemas, and position-map identity checks. The exact integer is positive and interoperable; one `run_id` maps to one ordinal and one ordinal maps to one `run_id`.

### 3.2 Canonical public revalidation

The current provisional Task 3 implementation exposes these exact boundaries. The final approved commit must preserve them, or this section must be updated from the approved diff before Task 4 starts:

```python
def revalidate_confirmation_design(
    config: ConfirmationDesignConfig,
) -> ConfirmationDesignConfig: ...
def revalidate_baseline_roster(roster: BaselineRoster) -> BaselineRoster: ...
def revalidate_position_map(position_map: PositionMap) -> PositionMap: ...
def revalidate_randomization_manifest(
    manifest: RandomizationManifest,
) -> RandomizationManifest: ...
def revalidate_cohort_identity_set(
    cohort: CohortIdentitySet,
) -> CohortIdentitySet: ...
def revalidate_experimental_unit_audit(
    audit: ExperimentalUnitAudit,
    *,
    records: tuple[AllocationRecord, ...],
    spec: ExperimentalUnitSpec,
) -> ExperimentalUnitAudit: ...

def cohort_identity_set(
    manifest: RandomizationManifest,
    *,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
) -> CohortIdentitySet: ...

def validate_cohort_separation(
    *,
    discovery_manifest: RandomizationManifest,
    discovery_roster: BaselineRoster,
    discovery_position_map: PositionMap,
    confirmation_manifest: RandomizationManifest,
    confirmation_roster: BaselineRoster,
    confirmation_position_map: PositionMap,
) -> tuple[CohortIdentitySet, CohortIdentitySet]: ...

def validate_experimental_units(
    records: tuple[AllocationRecord, ...],
    spec: ExperimentalUnitSpec,
    *,
    cohorts: tuple[CohortIdentitySet, ...] | None = None,
    observations: tuple[ObservationIdentityRecord, ...] = (),
) -> ExperimentalUnitAudit: ...
```

Each Task 3 function requires an exact outer type, reconstructs every nested dataclass/map/tuple from primitive fields, recomputes canonical hashes or the audit, and returns a detached canonical object. `cohort_identity_set` cross-binds the manifest to the complete physical roster/map. `validate_cohort_separation` derives—not accepts from a caller—the six identity namespaces and proves all are disjoint plus `max(discovery ordinal) < min(confirmation ordinal)`. Task 4 must not weaken these boundaries to `isinstance` checks or caller-authored identity sets.

Task 4 then owns the cross-object boundary:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class CohortDesignBundle:
    cohort_id: Literal["discovery", "confirmation"]
    baseline_roster: BaselineRoster
    position_map: PositionMap
    manifest: RandomizationManifest
    audit: ExperimentalUnitAudit

def assemble_cohort_design_bundle(
    *,
    cohort_id: Literal["discovery", "confirmation"],
    config: DesignConfig,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
    manifest: RandomizationManifest,
    audit: ExperimentalUnitAudit,
) -> CohortDesignBundle: ...

def revalidate_cohort_design_bundle(
    value: CohortDesignBundle,
    *,
    config: DesignConfig,
) -> CohortDesignBundle: ...
```

The assembler/revalidator calls the Task 3 boundaries, derives `ExperimentalUnitSpec.from_design(...)` or `from_confirmation_design(...)`, calls `cohort_identity_set`, and proves: roster plant IDs equal manifest plant IDs exactly; position IDs equal manifest position IDs exactly; each supplied plant and slot appears once; allocation fields agree with the physical roster/slot; no material remains; allocation/config/input hashes are correct; and the supplied audit equals a fresh audit by canonical content. Assembly of a discovery/confirmation pair additionally calls `validate_cohort_separation`. It rejects `isinstance`-only surrogates, `object.__setattr__` corruption, dataclass `replace` bypasses, and stale nested hashes.

### 3.3 Required Task 3 RED tests

```python
def test_confirmation_uses_six_loops_per_water_across_later_runs() -> None:
    config, roster, positions = _confirmation_inputs(
        selected_candidates=("C1", "C4", "C6"),
        plants_per_cell=5,
    )
    manifest = randomize(
        config, 20260813, baseline_roster=roster, position_map=positions
    )
    assert len(manifest.records) == 4 * 6 * 2 * 5 == 240
    assert len({
        (row.water_id, row.reservoir_id) for row in manifest.records
    }) == 12
    assert {row.run_sequence_ordinal for row in manifest.records} == {3, 4}
```

The independent literal oracle is 240 for three candidates plus empty vector.

```python
def test_confirmation_must_be_strictly_later() -> None:
    config, roster, positions = _confirmation_inputs(
        selected_candidates=("C1",), plants_per_cell=5
    )
    early_positions = PositionMap(tuple(
        replace(slot, run_sequence_ordinal=2)
        if slot.run_id == "confirmation_run_a"
        else slot
        for slot in positions.slots
    ))
    with pytest.raises(AlmondLabError) as caught:
        randomize(
            config, 7, baseline_roster=roster, position_map=early_positions
        )
    assert caught.value.code == "POSITION_MAP_INVALID"

def test_bundle_revalidation_detects_nested_manifest_corruption(
    manifest, config, full_spec, design_inputs
) -> None:
    audit = validate_experimental_units(manifest.records, full_spec)
    corrupted = revalidate_randomization_manifest(manifest)
    object.__setattr__(
        corrupted.records[0], "water_batch_id", "reused-or-unregistered-batch"
    )
    with pytest.raises(AlmondLabError) as caught:
        assemble_cohort_design_bundle(
            cohort_id="discovery",
            config=config,
            baseline_roster=design_inputs.baseline_roster,
            position_map=design_inputs.position_map,
            manifest=corrupted,
            audit=audit,
        )
    assert caught.value.code in {"RANDOMIZATION_INVALID", "EXPERIMENTAL_UNIT_INVALID"}
```

Also pin 1–4 candidates plus EV, both 5/6 cell sizes, zero leftovers, at least two new physical batches per group, balance, disjoint optional event IDs, and discovery max ordinal strictly below confirmation min ordinal.

## 4. Versioned v1.4 contract and migration API

### 4.1 No transparent compatibility adapter

The current document is `SyntheticScenarioConfig` v1.3.0. The new shape is v1.4.0 because fields and semantics change. Generation accepts v1.4 only:

```python
SCENARIO_SCHEMA_VERSION = "1.4.0"
GENERATOR_SCHEMA_VERSION = "1.0.0"
WATER_RECIPE_SCHEMA_VERSION = "1.0.0"

def load_synthetic_scenarios(
    path: str | Path,
) -> SyntheticScenarioRegistry: ...

def inspect_v13_scenario_migration(
    path: str | Path,
) -> ScenarioMigrationInventory: ...

def migrate_v13_scenario_document(
    source: ScenarioMigrationInventory,
    registration: ScenarioMigrationRegistration,
) -> SyntheticScenarioRegistry: ...
```

The migration report types are part of the public audit trail:

```python
class MigrationDisposition(StrEnum):
    PRESERVED = "preserved"
    RETYPED_WITH_UNIT = "retyped_with_unit"
    SPLIT_REQUIRES_REGISTRATION = "split_requires_registration"
    RETIRED = "retired"
    OWNER_REQUIRED = "owner_required"

class ScenarioMigrationItem(StrictPaper1Model):
    source_path: str | None
    source_canonical_json: str | None
    disposition: MigrationDisposition
    destination_paths: tuple[str, ...]
    owner_required_paths: tuple[str, ...]
    rationale: str

class ScenarioMigrationInventory(StrictPaper1Model):
    source_schema_version: Literal["1.3.0"]
    source_raw_sha256: str
    source_normalized_sha256: str
    items: tuple[ScenarioMigrationItem, ...]
    unclassified_source_paths: tuple[str, ...]
    multiply_classified_source_paths: tuple[str, ...]
```

`load_synthetic_scenarios` rejects v1.3 with `SCENARIO_SCHEMA_MIGRATION_REQUIRED`. `inspect_v13_scenario_migration` is read-only: it records raw/normalized hashes and classifies every old value as preserved, retyped, retired, or owner-required. `migrate_v13_scenario_document` succeeds only when the registration covers every owner-required field and never derives a control forcing, charge-closure ion, assay limit, or calibration bracket.

### 4.2 Unit-bearing primitives

```python
class RegisteredQuantity(StrictPaper1Model):
    value: float
    unit: str
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]

class RegisteredCount(StrictPaper1Model):
    value: int
    unit: Literal["count"]
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]
```

Prevalidators require `type(value) is float` for real-valued quantities and `type(value) is int` for counts unless the contract explicitly permits both int/float and canonicalizes to float. Booleans, numeric strings, NaN, infinities, whitespace units, unit aliases, unknown keys, and subclass instances fail before RNG. Section validators compare each field to one exact registered unit string.

### 4.3 Exact v1.4 scenario shape

```python
class SyntheticScenarioConfig(StrictPaper1Model):
    scenario_id: SyntheticScenarioId
    schema_version: Literal["1.4.0"]
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]
    parameters: Annotated[BiologyParameters, SkipValidation]
    initial_state: Annotated[PlantState, SkipValidation]
    forcings_by_water_id: Mapping[str, tuple[RootZoneForcing, ...]]
    generator: SyntheticGeneratorConfig
    mechanism: ScenarioMechanismConfig

class SyntheticScenarioRegistry(StrictPaper1Model):
    schema_version: Literal["1.4.0"]
    water_recipe_registry_sha256: str
    anchor: SyntheticScenarioConfig
    scenarios: tuple[SyntheticScenarioConfig, ...]

    @property
    def all_scenarios(self) -> tuple[SyntheticScenarioConfig, ...]: ...

class ScenarioMigrationRegistration(StrictPaper1Model):
    schema_version: Literal["1.0.0"]
    source_raw_sha256: Literal[
        "46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb"
    ]
    target_registry: SyntheticScenarioRegistry
    accepted_retired_source_paths: tuple[str, ...]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]
```

`ScenarioMechanismConfig` has required, explicitly empty-or-populated fields with no defaults:

- `biology_parameter_overrides`;
- `candidate_parameter_overrides_by_id`;
- `onset_time_days`, explicitly null except where registered;
- `post_onset_biology_parameter_overrides`;
- `chassis_id`;
- `candidate_chassis_mechanism_modifiers`.

All maps are copied to mapping proxies and all nested Task 2 dataclasses are canonically reconstructed. The registry requires `anchor.scenario_id == "perfect_control"` and the remaining nine IDs once each in the frozen order; `all_scenarios == (anchor, *scenarios)` is the exact ten-scenario view. The loader expands aliases, compares each canonical non-anchor scenario to the anchor, and validates the exact path whitelist in Section 7. `ScenarioMigrationRegistration.target_registry` is the fully expanded target, not a patch document; its retirement list must equal the inventory’s `RETIRED` source paths exactly. Migration verifies every source item against the target and returns a detached reconstruction, so the registration cannot omit an owner-required value behind a YAML default.

## 5. Complete generator field and unit registry

Every row below is required and has no code default.

| Section | Exact field | Exact unit | Migration status |
|---|---|---|---|
| hierarchy | `run_variance` | `log-ratio^2` | Preserve 0.02. |
| hierarchy | `batch_variance` | `log-ratio^2` | Preserve 0.02. |
| hierarchy | `reservoir_variance` | `log-ratio^2` | Preserve 0.04. |
| hierarchy | `plant_variance` | `log-ratio^2` | Preserve 0.10 anchor and 0.20 in `selection_bias_false_leader`. |
| climate | `temperature_ar1_phi` | `dimensionless` | **New registration.** |
| climate | `temperature_innovation_sd_k` | `K` | **New registration.** |
| climate | `apar_ar1_phi` | `dimensionless` | **New registration.** |
| climate | `apar_log_innovation_sd` | `log-ratio` | **New registration.** |
| climate | `matric_potential_ar1_phi` | `dimensionless` | **New registration.** |
| climate | `matric_potential_innovation_sd_mpa` | `MPa` | **New registration.** |
| climate | `potential_transpiration_log_innovation_sd` | `log-ratio` | **New registration.** |
| climate | `climate_initialization_burnin_steps` | `count` | **New exact-integer registration.** |
| chemistry | `common_ion_log_sd` | `log-ratio` | **New registration.** |
| chemistry | `boron_log_sd` | `log-ratio` | **New registration.** |
| chemistry | `ec_measurement_sd_ds_m` | `dS m^-1` | **New registration.** |
| chemistry | `osmolality_measurement_sd_osmol_kg` | `osmol kg^-1` | **New registration.** |
| chemistry | `ph_measurement_sd` | `pH` | **New registration.** |
| chemistry | `temperature_measurement_sd_k` | `K` | **New registration.** |
| chemistry | `charge_balance_tolerance_percent` | `percent` | **New registration; not the numerical-ledger tolerance.** |
| water_loop | `reservoir_initial_volume_l` | `L` | **New registration.** |
| water_loop | `water_batch_volume_l` | `L` | **New registration.** |
| water_loop | `irrigation_volume_l_per_plant_day` | `L plant^-1 day^-1` | **New registration.** |
| water_loop | `drainage_return_fraction` | `dimensionless` | **New registration in [0,1].** |
| water_loop | `purge_volume_l_day` | `L day^-1` | **New registration.** |
| water_loop | `sampling_volume_l_per_sample` | `L sample^-1` | **New registration.** |
| water_loop | `reservoir_min_volume_l` | `L` | **New registration.** |
| water_loop | `reservoir_max_volume_l` | `L` | **New registration, greater than minimum.** |
| water_loop | `operator_event_times_days` | `day` per ordered item | **New schedule registration.** |
| observation | `canopy_observation_error_sd` | `log-ratio` | Preserve 0.05 anchor and 0.12 drift/missingness scenario override. |
| observation | `ion_observation_error_sd` | `log-ratio` | Preserve 0.04. |
| observation | `h3_observation_error_by_endpoint` | endpoint analysis unit | Preserve 0.05 only for C1/C2/C4/C5/C6 log-ratio records; C3 native-unit SD is **new registration**. |
| observation | `canopy_heteroscedastic_log_slope` | `log-ratio per log-ratio` | **New registration and formula freeze.** |
| observation | `ion_heteroscedastic_log_slope` | `log-ratio per log-ratio` | **New registration and formula freeze.** |
| observation | `canopy_observation_times_days` | `day` per ordered item | **New schedule registration.** |
| observation | `ion_observation_times_days` | `day` per ordered item | **New schedule registration.** |
| observation | `h3_observation_times_days` | `day` per ordered item | **New schedule registration.** |
| censoring | `lod_by_endpoint` | native endpoint unit | **New endpoint-complete registration.** |
| censoring | `loq_by_endpoint` | native endpoint unit | **New endpoint-complete registration; LOQ >= LOD.** |
| censoring | `lod_log_sd_by_endpoint` | `log-ratio` | **New registration.** |
| censoring | `loq_log_sd_by_endpoint` | `log-ratio` | **New registration.** |
| drift | `canopy_drift_per_day` | `log-ratio day^-1` | **New registration.** |
| drift | `ion_drift_per_day_by_endpoint` | `log-ratio day^-1` | **New endpoint-complete registration.** |
| drift | `h3_drift_per_day_by_endpoint` | endpoint analysis unit per day | **New registration; C3 remains native-unit/day.** |
| drift | `calibration_interval_days` | `day` | **New registration.** |
| drift | `post_calibration_residual_sd_by_endpoint` | endpoint analysis unit | **New registration.** |
| death | `biomass_death_threshold_log_sd` | `log-ratio` | **New registration.** |
| death | `injury_death_threshold_log_sd` | `log-ratio` | **New registration.** |
| death | `sustained_injury_duration_log_sd` | `log-ratio` | **New registration.** |
| missingness | `missingness_intercept` | `logit` | Preserve -3.0. |
| missingness | `missingness_stress_slope` | `logit per standardized-proxy SD` | Preserve 0.20 anchor and 0.60 drift/missingness override. |
| missingness | `mnar_tipping_delta` | `logit per standardized-endpoint SD` | Preserve 0.10. |
| missingness | `observable_stress_proxy_fields` | controlled field IDs | **New exact enum registration.** |
| missingness | `observable_stress_proxy_center_by_field` | proxy native unit | **New registration.** |
| missingness | `observable_stress_proxy_scale_by_field` | proxy native unit | **New positive registration.** |
| missingness | `mnar_endpoints` | endpoint IDs | **New exact-set registration.** |
| calibration | `absolute_tolerance_log_ratio` | `log-ratio` | **New registration.** |
| calibration | `relative_tolerance` | `dimensionless` | **New registration.** |
| calibration | `max_iterations` | `count` | **New exact-integer registration.** |
| calibration | `fit_panel_size` | `count` | **New exact-integer registration.** |
| calibration | `holdout_panel_size` | `count` | **New exact-integer registration.** |
| calibration | `holdout_tolerance_log_ratio` | `log-ratio` | **New registration.** |
| design | `duration_days` | `day` | Preserve 84.0. |
| design | `confirmation_plants_per_group_reservoir` | `count` | **New exact choice: 5 or 6.** |

The H3 map contains six candidate-keyed records. Each record repeats the frozen `candidate_id`, `endpoint_id`, `analysis_scale`, and unit from `configs/candidates.yaml` so C1/C4/C6 cannot be accidentally collapsed into a different candidate gate. The five log-ratio records may carry forward 0.05; C3 must not receive a dimensionless 0.05 by copying.

Required generator classes are `HierarchyGeneratorConfig`, `ClimateGeneratorConfig`, `ChemistryGeneratorConfig`, `WaterLoopGeneratorConfig`, `ObservationGeneratorConfig`, `CensoringGeneratorConfig`, `DriftGeneratorConfig`, `DeathGeneratorConfig`, `MissingnessGeneratorConfig`, `CalibrationGeneratorConfig`, `GeneratorDesignConfig`, and their exact aggregate `SyntheticGeneratorConfig`. Each section is required even when a scenario uses explicit zero values.

Freeze the generator semantics with the fields: hierarchy effects are zero-mean intercepts at run, physical transformation-batch, run × water × reservoir, and plant levels; `common_ion_log_sd` drives one common positive multiplier on the already balanced charge-bearing recipe, with alkalinity/bicarbonate kept paired, while boron is separate; no ion receives an independent unbalanced draw. Death fields perturb registered thresholds only and never draw or write a death outcome. MAR covariates are restricted to registered analyst-observable fields; only `mnar_tipping_delta` may reference the hidden counterfactual endpoint, and only for `mnar_endpoints`.

### Generator migration RED test

```python
def test_v13_inventory_has_no_dropped_generator_value() -> None:
    source = Path(__file__).resolve().parents[1] / "configs" / "synthetic_scenarios.yaml"
    inventory = inspect_v13_scenario_migration(source)
    by_source = {
        item.source_path: item
        for item in inventory.items
        if item.source_path is not None
    }
    legacy_generator_paths = {
        f"generator_parameters.{name}"
        for name in {
            "run_variance", "batch_variance", "reservoir_variance",
            "plant_variance", "canopy_observation_error_sd",
            "ion_observation_error_sd", "h3_observation_error_sd",
            "missingness_intercept", "missingness_stress_slope",
            "mnar_tipping_delta", "duration_days",
        }
    }
    assert legacy_generator_paths <= set(by_source)
    assert inventory.unclassified_source_paths == ()
    assert inventory.multiply_classified_source_paths == ()
    h3 = by_source["generator_parameters.h3_observation_error_sd"]
    assert h3.disposition is MigrationDisposition.SPLIT_REQUIRES_REGISTRATION
    assert set(h3.destination_paths) == {
        f"generator.observation.h3_observation_error_by_endpoint.{candidate}"
        for candidate in ("C1", "C2", "C4", "C5", "C6")
    }
    assert h3.owner_required_paths == (
        "generator.observation.h3_observation_error_by_endpoint.C3",
    )
```

In the same test module, define `EXPECTED_OWNER_REQUIRED_PATHS` as a literal set copied from every **New registration** row in this section and assert exact equality with the inventory; do not import that oracle from production. Perturbation tests must prove that every field is consumed and changes only its registered mechanism.

## 6. Charge-balanced two-water recipe registration

### 6.1 Preserve history, do not “fix” an ion

Before changing `configs/experiment_paper1.yaml`:

1. Copy its current bytes exactly to `configs/archive/experiment_paper1_v1_3.yaml`.
2. Assert that archive SHA-256 is `d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0`.
3. Record both legacy recipe records in `configs/paper1_water_recipes.yaml` as immutable `LegacyWaterRecipeAnchor` values with `status: superseded_unbalanced_hypothesis_anchor`, their original field paths/hashes, current values, and computed signed charge errors.
4. Do not call the legacy values measured, empirical, calibrated, or physically prepared.

The 7.9 and 3.9 mmol_c/L deficits are diagnostics only. Increasing chloride by those amounts would mathematically close the current convention, but it is one of many chemically consequential choices and is expressly not authorized by this plan.

### 6.2 Active recipe schema

```python
class LegacyWaterRecipeAnchor(StrictPaper1Model):
    water_id: str
    source_design_raw_sha256: Literal[
        "d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0"
    ]
    source_field_path: str
    anchor_canonical_sha256: str
    chemistry: WaterChemistry
    signed_charge_error_percent: float
    status: Literal["superseded_unbalanced_hypothesis_anchor"]
    evidence_label: Literal[EvidenceLabel.HYPOTHESIS_PRIOR]

class FormulaResolvedAmendment(StrictPaper1Model):
    reagent_id: str
    amount: RegisteredQuantity
    stoichiometric_contributions_mmol_l: Mapping[str, RegisteredQuantity]
    alkalinity_contribution_mmol_c_l: RegisteredQuantity
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]

class DirectFullIonPreparation(StrictPaper1Model):
    preparation_basis: Literal["direct_full_ion_targets"]
    preparation_record_id: str
    registered_target_chemistry: WaterChemistry

class FormulaResolvedPreparation(StrictPaper1Model):
    preparation_basis: Literal["formula_resolved_amendment"]
    source_water_chemistry: WaterChemistry
    amendments: tuple[FormulaResolvedAmendment, ...]
    registered_nonstoichiometric_targets: Mapping[str, RegisteredQuantity]
    computed_target_chemistry: WaterChemistry

class ActivePaper1WaterRecipe(StrictPaper1Model):
    recipe_id: str
    revision: str
    water_id: str
    status: Literal["active"]
    supersedes_anchor_sha256: str
    preparation: DirectFullIonPreparation | FormulaResolvedPreparation
    chemistry: WaterChemistry
    charge_convention_id: Literal[
        "almondlab.chemistry.charge_balance_error@1"
    ]
    charge_balance_tolerance_percent: RegisteredQuantity
    evidence_label: Literal[
        EvidenceLabel.HYPOTHESIS_PRIOR,
        EvidenceLabel.SYNTHETIC_ONLY,
    ]

class Paper1WaterRecipeRegistry(StrictPaper1Model):
    schema_version: Literal["1.0.0"]
    historical_anchors: tuple[LegacyWaterRecipeAnchor, LegacyWaterRecipeAnchor]
    active_recipes: tuple[ActivePaper1WaterRecipe, ActivePaper1WaterRecipe]
```

The protocol owner chooses one of two defensible paths:

- **Direct full-ion targets:** register a **new** recipe ID/revision, all final Na, Cl, Ca, Mg, K, total B, sulfate, bicarbonate, nitrate, phosphate, alkalinity, pH, ECw, measured osmolality, and temperature values, and a protocol-owned preparation record ID. The active recipe points to the immutable legacy anchor hash but does not mutate or inherit its unsupported preparation history.
- **Formula-resolved amendment:** register source-water chemistry, every reagent amount, and each reagent’s stoichiometric element/charge/alkalinity contribution. Sum source plus amendments to compute the ionic target, then require exact agreement with the separately serialized active `chemistry`. pH, ECw, measured osmolality, and temperature are nonstoichiometric registered targets; the validator must not derive one from another.

For either path, `active_recipes` is a new two-record namespace keyed by the same approved water IDs; no active object is created by flipping a legacy status flag. `supersedes_anchor_sha256` must equal the corresponding historical canonical hash. A change to any ion, amendment, preparation basis, tolerance, or nonstoichiometric target requires a new recipe revision and new canonical hash. This preserves the published hypothesis recipe exactly while allowing a prospective, auditable full-ion recipe.

For the approved charge convention:

```text
cations = Na + K + 2*Ca + 2*Mg
anions  = Cl + 2*sulfate + alkalinity + nitrate
error%  = 100*(cations-anions)/(cations+anions)
```

`bicarbonate` and `phosphate` remain required full-ion analytes but are not added again to this diagnostic because their acid/base charge is represented by measured/registered alkalinity in `charge_balance_error@1`. A future convention change requires a new convention ID, tests, and protocol amendment.

The active loader:

```python
def load_paper1_water_recipes(
    path: str | Path,
) -> Paper1WaterRecipeRegistry: ...

def validate_active_paper1_water_recipes(
    registry: Paper1WaterRecipeRegistry,
    *,
    design: Paper1DesignConfig,
    domain: ModelDomain,
) -> tuple[ActivePaper1WaterRecipe, ActivePaper1WaterRecipe]: ...

def migrate_paper1_design_water_recipes(
    legacy_design: Paper1DesignConfig,
    registry: Paper1WaterRecipeRegistry,
) -> Paper1DesignConfig: ...
```

Validation requires exactly the two registered water IDs; exact canonical agreement with `design.water_conditions[*].chemistry`; exact source-plus-amendment reconciliation for formula-resolved preparations; independent signed-charge recomputation; the public chemistry API; and `validate_domain` with Vairo/juvenile/`synthetic_only`. `migrate_paper1_design_water_recipes` requires the canonical legacy design and registry, reconstructs `Paper1DesignConfig` with `schema_version == "1.3"`, preserves every non-chemistry discovery field exactly, and replaces only each water condition’s chemistry with the matching active recipe. This avoids changing the Task 3 design contract merely to version recipe content. The Task 4 assembly/report—not the frozen design shape—records registry raw/normalized hashes and the new design hash. Any active value, lineage hash, preparation contribution, tolerance, required analyte, EC kind, provenance, domain field, or non-chemistry design change fails before RNG.

### 6.3 Recipe RED tests

```python
def test_current_v13_recipes_remain_archived_but_are_not_active() -> None:
    root = Path(__file__).resolve().parents[1]
    archive = root / "configs" / "archive" / "experiment_paper1_v1_3.yaml"
    registry = load_paper1_water_recipes(
        root / "configs" / "paper1_water_recipes.yaml"
    )
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0"
    )
    assert {r.status for r in registry.historical_anchors} == {
        "superseded_unbalanced_hypothesis_anchor"
    }
    assert {r.supersedes_anchor_sha256 for r in registry.active_recipes} == {
        r.anchor_canonical_sha256 for r in registry.historical_anchors
    }

def test_active_recipe_charge_oracle_is_independent() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_paper1_water_recipes(
        root / "configs" / "paper1_water_recipes.yaml"
    )
    design = load_paper1_design(root / "configs" / "experiment_paper1.yaml")
    domain = load_model_domains(
        root / "configs" / "model_domains.yaml"
    ).get("core_v1")
    active = validate_active_paper1_water_recipes(
        registry, design=design, domain=domain
    )
    for recipe in active:
        water = recipe.chemistry
        cations = water.na_mmol_l + water.k_mmol_l + 2*water.ca_mmol_l + 2*water.mg_mmol_l
        anions = water.cl_mmol_l + 2*water.sulfate_mmol_l + water.alkalinity_mmol_c_l + water.nitrate_mmol_l
        independent = 100 * (cations - anions) / (cations + anions)
        assert independent == pytest.approx(charge_balance_error(water), abs=1e-15)
        assert abs(independent) <= recipe.charge_balance_tolerance_percent.value

def test_design_recipe_migration_changes_only_registered_chemistry() -> None:
    root = Path(__file__).resolve().parents[1]
    legacy = load_paper1_design(
        root / "configs" / "archive" / "experiment_paper1_v1_3.yaml"
    )
    registry = load_paper1_water_recipes(
        root / "configs" / "paper1_water_recipes.yaml"
    )
    migrated = migrate_paper1_design_water_recipes(legacy, registry)
    old = legacy.model_dump(mode="json")
    new = migrated.model_dump(mode="json")
    old_waters = old.pop("water_conditions")
    new_waters = new.pop("water_conditions")
    assert new == old
    assert migrated.schema_version == "1.3"
    assert [row["water_id"] for row in new_waters] == [
        row["water_id"] for row in old_waters
    ]
    assert [row["chemistry"] for row in new_waters] == [
        recipe.chemistry.model_dump(mode="json")
        for recipe in registry.active_recipes
    ]
```

Add mutation tests that change one serialized ion without its source/amendment contribution, alter a lineage hash, double-count bicarbonate/phosphate, change ECw without a new revision, and substitute a `synthetic_only`/`hypothesis_prior` label with a stronger label. Production GREEN remains blocked until the protocol-owned active numeric records exist; use a clearly named hand-balanced **validator-only** fixture to develop the arithmetic and never copy its values into the protocol registry.

## 7. Ten-scenario mechanism-path repair

The exact scenario set remains closed. Every scenario is compared with the canonical `perfect_control` anchor. Baseline `parameters`, `initial_state`, and two-water forcing schedules remain identical to the anchor; biological deltas occur only under `mechanism` and nuisance deltas only in their typed generator section. The loader materializes effective inputs after validating those deltas, so one value never has two competing serialized authorities.

| Scenario | Current v1.3 value that may be retained | Exact allowed v1.4 changed path(s) | Required repair |
|---|---|---|---|
| `perfect_control` | Baseline `BiologyParameters` and `PlantState` | Empty set | It is the scenario anchor. Neutral C1–C6 effects belong only in `global_null.yaml` as explicit identity-effect records; this scenario must not rewrite the approved candidate-effect registry. |
| `true_ion_exclusion` | `root_na_permeability_l_cm2_h = 0.0` | `mechanism.biology_parameter_overrides.root_na_permeability_l_cm2_h` | Retain external water/osmolality unchanged and prove the normal hydraulic penalty remains. |
| `root_na_accumulation` | `na_efflux_vmax_mmol_h = 0.10` | `mechanism.biology_parameter_overrides.na_efflux_vmax_mmol_h` | Retain 0.10 only. Any additional efflux, retrieval, injury, ion, or outcome path requires a separate prospective amendment; the scenario name cannot authorize it. |
| `marker_only` | `ros_clearance_h_inv = 0.40` | `mechanism.biology_parameter_overrides.ros_clearance_h_inv` | No ion, canopy, AUC, survival, or decision edit. |
| `nonsaline_penalty` | `mannitol_carbon_cost_mmol_c_mmol_inv = 0.80` | `mechanism.biology_parameter_overrides.mannitol_carbon_cost_mmol_c_mmol_inv` | Retire the v1.3 forcing-osmolality 0.05 edit from active semantics and archive it in the migration inventory. Both water forcings remain the registered anchors. |
| `chassis_interaction` | `root_conductance_l_day_mpa = 0.35` is only a migration candidate | `mechanism.chassis_id` and literal owner-registered leaves below `mechanism.candidate_chassis_mechanism_modifiers` | Register a second chassis ID in `core_v1.allowed_chassis`, bump that policy version from `1.0.0` to `1.1.0`, and register affected candidate/parameter leaves plus modifier semantics. Retain the existing chemistry/life-stage bounds unless the owner separately amends them. The 0.35 value may move to one named modifier leaf only if the owner explicitly registers that interpretation; it must not remain a global conductance main effect. Until complete, raise `DOMAIN_VIOLATION`. |
| `delayed_toxicity` | `senescence_h_inv = 0.06` | `mechanism.onset_time_days` and `mechanism.post_onset_biology_parameter_overrides.senescence_h_inv` | Register onset time and affirm whether senescence is the complete post-onset set. Before onset, the anchor is exact; no direct death/outcome edit. Any additional post-onset leaf is a new registration. |
| `sensor_drift_missingness` | canopy error 0.12 and missingness slope 0.60 | `generator.observation.canopy_observation_error_sd`, `generator.missingness.missingness_stress_slope`, and literal owner-registered leaves under `generator.drift` | Retain 0.12/0.60; register each nonzero drift/calibration leaf and MAR/MNAR covariate set. |
| `insufficient_purge` | v1.3 osmolality 0.30 is historical only | `generator.water_loop.purge_volume_l_day` | Register the reduced purge flow. Salt accumulation must emerge from the input-built mass ledger while both forcing schedules remain unchanged. |
| `selection_bias_false_leader` | `plant_variance = 0.20` | `generator.hierarchy.plant_variance` | Do not encode a selected ID, expected rank, candidate effect, or direct outcome. |

There are no runtime wildcard permissions. For the two owner-dependent scenarios, migration expands the prospectively registered leaf IDs into a literal immutable whitelist and stores that list in the normalized config hash.

The exact diff validator is:

```python
def validate_scenario_edit_paths(
    *,
    anchor: SyntheticScenarioConfig,
    scenario: SyntheticScenarioConfig,
) -> tuple[str, ...]: ...
```

It returns canonical changed paths only after validation and raises `UNREGISTERED_SYNTHETIC_PARAMETER` for a path outside the literal scenario whitelist. Any key containing `outcome`, `auc_effect`, `true_delta`, `target_delta`, `decision`, `eligible`, `advance`, `rank`, `selection_result`, or the two forbidden preferred-candidate output names is rejected. `mnar_tipping_delta` remains an allowed missingness logit shift.

### Scenario RED tests

```python
def _replace_path(payload: dict[str, object], path: str, value: object) -> None:
    parts = path.split(".")
    cursor: object = payload
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    if isinstance(cursor, list):
        cursor[int(parts[-1])] = value
    else:
        cursor[parts[-1]] = value

@pytest.mark.parametrize(
    ("scenario_id", "forbidden_path", "replacement"),
    [
        (
            "nonsaline_penalty",
            "forcings_by_water_id.nonsaline_nutrient_matched_control.0.measured_osmolality_osmol_kg",
            0.03,
        ),
        (
            "insufficient_purge",
            "forcings_by_water_id.pilot_selected_full_ion_marine_challenge.0.measured_osmolality_osmol_kg",
            0.16,
        ),
        ("sensor_drift_missingness", "parameters.senescence_h_inv", 0.02),
        (
            "selection_bias_false_leader",
            "parameters.root_na_permeability_l_cm2_h",
            0.02,
        ),
    ],
)
def test_scenario_edit_paths_fail_closed(
    scenario_id: str, forbidden_path: str, replacement: float
) -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_synthetic_scenarios(
        root / "configs" / "synthetic_scenarios.yaml"
    )
    scenario = next(s for s in registry.scenarios if s.scenario_id == scenario_id)
    payload = deepcopy(scenario.model_dump(mode="json"))
    _replace_path(payload, forbidden_path, replacement)
    corrupted = SyntheticScenarioConfig.model_validate(payload)
    with pytest.raises(AlmondLabError) as caught:
        validate_scenario_edit_paths(anchor=registry.anchor, scenario=corrupted)
    assert caught.value.code == "UNREGISTERED_SYNTHETIC_PARAMETER"
```

Also assert exactly ten IDs across `registry.all_scenarios`, no aliases, no extras, and deterministic `DOMAIN_VIOLATION` for an unregistered chassis.

## 8. Two-water forcing and observation registries

`forcings_by_water_id` has exactly:

- `nonsaline_nutrient_matched_control`;
- `pilot_selected_full_ion_marine_challenge`.

Each value is a nonempty ordered tuple of complete `RootZoneForcing` values whose exact finite durations sum to `84.0 * 24` hours. Schedule validation uses exact binary-rational accumulation consistent with the project’s finite arithmetic boundary.

The single v1.3 forcing record has these exact values: measured osmolality 0.15 osmol/kg, temperature 298.15 K, water density 0.997 kg/L, matric potential -0.10 MPa, leaf critical potential -2.00 MPa, APAR 1.0 mol/h, temperature factor 0.80, potential transpiration 1.0 L/day, and duration 0.25 h, plus the existing `paper1-biology-v1` hydraulic-domain record. These coordinates may be carried forward only as one **challenge-water step anchor** after the protocol owner affirms the mapping. The 0.25-hour duration is not an authorized instruction to repeat the step 8,064 times, and the record cannot be copied or derived into a control schedule.

The owner must register:

- the complete control schedule;
- the complete challenge schedule and duration partition;
- how scheduled forcing coordinates correspond to active water recipe IDs;
- the canopy, ion, and H3 observation times;
- operator-event times and water-loop volumes/flows.

Forcing schedule hashes enter both `config_sha256s` and calibration panel registration. The two waters need not have equal step counts or boundaries, but each independently covers exactly 2,016 hours and every objective panel contains both water IDs. Missing/extra water IDs, duration mismatch, recipe mismatch, or unregistered interpolation fails before RNG.

Create an exact `EndpointRegistry` from the frozen candidate H3 records plus the Task 4 canopy/ion measurement inventory. Each endpoint declares `endpoint_id`, `observation_type`, `analysis_scale`, `unit`, censoring applicability, and post-death semantics. LOD/LOQ, drift, error, and missingness maps must have the exact endpoint-key set.

## 9. Calibration registration

The only numeric calibration target already authorized is `log(1.30)`, the design alternative. It is not evidence of an almond effect.

The protocol owner must newly register:

- one candidate ID chosen before calibration outcomes;
- its frozen primary parameter ID;
- explicit trade-off values;
- lower and upper primary-mechanism bounds;
- absolute and relative solver tolerances;
- maximum iterations;
- fit and holdout panel sizes;
- holdout residual tolerance;
- exact fit/holdout two-water forcing-panel hashes.

The fixture contract is exact and contains no solver result:

```python
class KnownEffectCalibrationRegistration(StrictPaper1Model):
    schema_version: Literal["1.0.0"]
    candidate_id: str
    primary_parameter_id: str
    target_delta_log_ratio: RegisteredQuantity
    effects_template: CandidateEffects
    lower: RegisteredQuantity
    upper: RegisteredQuantity
    absolute_tolerance_log_ratio: RegisteredQuantity
    relative_tolerance: RegisteredQuantity
    max_iterations: RegisteredCount
    fit_panel_size: RegisteredCount
    holdout_panel_size: RegisteredCount
    holdout_tolerance_log_ratio: RegisteredQuantity
    fit_panel_sha256: str
    holdout_panel_sha256: str
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

def load_known_effect_registration(
    path: str | Path,
) -> KnownEffectCalibrationRegistration: ...
```

`effects_template` is canonically reconstructed through the Task 2 candidate-effect boundary and contains both the registered primary scalar and the explicit trade-off scalar. The loader proves `candidate_id`, `primary_parameter_id`, and template identity agree with `CandidateRegistry`; target/unit are exactly `log(1.30)`/`log-ratio`; bounds and tolerances are type-exact and ordered; panel hashes are distinct canonical SHA-256 strings; and none of the fields is a fitted value, residual, rank, decision, or preferred-candidate claim.

The corrected API is frozen:

```python
def calibrate_mechanism_to_estimand(
    candidate: CandidateSpec,
    target_delta_log_ratio: float,
    baseline: BiologyParameters,
    initial_state: PlantState,
    effects_template: CandidateEffects,
    fit_forcings_by_water: Mapping[str, tuple[RootZoneForcing, ...]],
    holdout_forcings_by_water: Mapping[str, tuple[RootZoneForcing, ...]],
    lower: float,
    upper: float,
    *,
    absolute_tolerance_log_ratio: float,
    relative_tolerance: float,
    max_iterations: int,
) -> MechanismCalibration: ...
```

The registration fixture must not choose a candidate or widen a bracket after seeing which solver succeeds. A deterministic pre-generation panel materialization step may compute panel hashes; the owner then freezes the registration before the known-effect generator is run.

### Calibration RED tests

```python
def test_known_effect_registration_is_complete_before_solver_call() -> None:
    root = Path(__file__).resolve().parents[1]
    registration = load_known_effect_registration(
        root / "tests" / "fixtures" / "known_effect.yaml"
    )
    candidates = load_candidate_specs(root / "configs" / "candidates.yaml")
    candidate_by_id = {
        candidate.candidate_id: candidate for candidate in candidates.candidates
    }
    assert registration.target_delta_log_ratio.value == pytest.approx(
        log(1.30), abs=1e-15
    )
    assert registration.target_delta_log_ratio.unit == "log-ratio"
    assert registration.candidate_id in {"C1", "C2", "C3", "C4", "C5", "C6"}
    assert registration.primary_parameter_id == candidate_by_id[
        registration.candidate_id
    ].primary_parameter_id
    assert registration.fit_panel_sha256 != registration.holdout_panel_sha256

def test_one_water_calibration_is_rejected_before_objective_evaluation(
    calibration_inputs,
) -> None:
    (
        candidate, baseline, initial, effects, fit_schedule, holdout_schedule,
        lower, upper, absolute_tolerance, relative_tolerance, max_iterations,
    ) = calibration_inputs
    with pytest.raises(AlmondLabError) as caught:
        calibrate_mechanism_to_estimand(
            candidate,
            log(1.30),
            baseline,
            initial,
            effects,
            {"salt": fit_schedule},
            {"salt": holdout_schedule},
            lower,
            upper,
            absolute_tolerance_log_ratio=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            max_iterations=max_iterations,
        )
    assert caught.value.code == "CALIBRATION_FORCING_INVALID"
```

Also pin endpoint roots, interior roots, missing brackets, nonconvergence, nonfinite biology, holdout mismatch, and proof that only the registered primary mechanism changes.

## 10. Paper1SimulationConfig assembly boundary

After all repaired inputs are approved, Task 4 creates:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Paper1SimulationConfig:
    design: Paper1DesignConfig
    candidates: CandidateRegistry
    candidate_effects: Mapping[str, CandidateEffects]
    model_domain: ModelDomain
    discovery_design: CohortDesignBundle
    confirmation_design: CohortDesignBundle | None
    generator: SyntheticGeneratorConfig
    config_sha256s: Mapping[str, str]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]
```

Only a factory may construct it:

```python
def assemble_paper1_simulation_config(
    *,
    design: Paper1DesignConfig,
    candidates: CandidateRegistry,
    candidate_effects: Mapping[str, CandidateEffects],
    model_domain: ModelDomain,
    water_recipes: Paper1WaterRecipeRegistry,
    scenario_registry: SyntheticScenarioRegistry,
    discovery_design: CohortDesignBundle,
    confirmation_design: CohortDesignBundle | None,
    raw_config_bytes_by_name: Mapping[str, bytes],
) -> Paper1SimulationConfig: ...
```

The factory canonically reconstructs every input, validates water recipe/design agreement, verifies the scenario registry’s recipe hash, validates both cohort bundles and their six identity namespaces (the five required physical namespaces plus non-null transformation events), checks root-seed separation, and builds raw plus normalized SHA-256 entries for every consumed config. No caller supplies a result hash or pass flag.

## 11. Implementation tasks

### Task 1: Freeze and review the final Task 3 dependency

**Files:**
- Modify only if absent after final Task 3 review: `src/almondlab/design.py`
- Test: `tests/test_design.py`

- [ ] **Step 1: Record the final Task 3 commit and public API inventory.**

Run:

```powershell
git status --short
git rev-parse HEAD
rg -n "^(class ConfirmationDesignConfig|def randomize|def revalidate_|def cohort_identity_set|def validate_cohort_separation)|run_sequence_ordinal" src/almondlab/design.py
```

Expected: clean Task 3-owned paths, approved commit, and every Section 3 boundary present.

- [ ] **Step 2: Add the Section 3 RED tests for any missing behavior.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_design.py -q`
Expected before repair: focused failures naming only the missing boundary/invariant.

- [ ] **Step 3: Implement only the missing Task 3 behavior and rerun focused tests.**

Expected: exact discovery oracle remains 720; confirmation 1–4+EV, 5/6, later-run, and no-leftover cases pass.

- [ ] **Step 4: Commit and obtain independent design/statistical review.**

Commit message: `feat: finalize confirmation design boundary`

### Task 2: Add strict v1.4 contracts and explicit migration inventory

**Files:**
- Create: `configs/archive/synthetic_scenarios_v1_3.yaml`
- Modify: `src/almondlab/paper1_contracts.py`
- Modify: `tests/test_paper1_contracts.py`

- [ ] **Step 1: Copy current scenario bytes to the archive and pin SHA-256 `46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb`.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paper1_contracts.py -q`
Expected: the archive/hash test passes before active migration work.

- [ ] **Step 2: Write RED tests for active v1.3 rejection, full migration inventory, exact units, missing/extra fields, and deep-copy bypasses.**

Expected: failures for missing v1.4 types/functions.

- [ ] **Step 3: Implement `RegisteredQuantity`, `RegisteredCount`, all generator section models, v1.4 scenario models, and read-only migration inventory.**

- [ ] **Step 4: Prove every old scalar/path is preserved, retyped, split, retired, or blocked exactly once.**

- [ ] **Step 5: Run contracts plus Task 2 biology tests.**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paper1_contracts.py tests/test_biology_surrogate.py -q`
Expected: PASS with no biology-equation change.

- [ ] **Step 6: Commit and obtain contract/security review.**

Commit message: `feat: version paper1 synthetic input contracts`

### Task 3: Register active water recipes without erasing history

**Files:**
- Create: `configs/archive/experiment_paper1_v1_3.yaml`
- Create: `configs/paper1_water_recipes.yaml`
- Modify: `configs/experiment_paper1.yaml`
- Modify: `src/almondlab/paper1_contracts.py`
- Test: `tests/test_paper1_contracts.py` and `tests/test_chemistry.py`

- [ ] **Step 1: Create and hash the exact historical archive.**

Expected SHA-256: `d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0`.

- [ ] **Step 2: Write RED tests for historical activation, unbalanced active recipes, silent single-ion changes, formula contribution mismatch, charge tolerance, domain validation, and design/registry disagreement.**

- [ ] **Step 3: Obtain the protocol-owned active recipe values and amendment/preparation records.**

This step cannot be replaced by implementation judgment. If the registration is absent, retain `WATER_RECIPE_REGISTRATION_REQUIRED` as the testable blocker and do not enter Task 4 GREEN.

- [ ] **Step 4: Implement the active recipe loader/validator and run chemistry/domain/design suites.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_chemistry.py tests/test_domains.py tests/test_paper1_contracts.py tests/test_design.py -q
```

- [ ] **Step 5: Commit separately and obtain chemistry/mass-balance review.**

Commit message: `feat: register charge-audited paper1 water recipes`

### Task 4: Populate the complete generator and two-water forcing configuration

**Files:**
- Modify: `configs/synthetic_scenarios.yaml`
- Modify: `src/almondlab/paper1_contracts.py`
- Test: `tests/test_paper1_contracts.py`

- [ ] **Step 1: Obtain all owner registrations in Sections 5 and 8.**

- [ ] **Step 2: Write the complete v1.4 anchor with all sections, exact units, both water schedules, and no YAML key omitted through merge inheritance.**

- [ ] **Step 3: Run exact-key, duration-sum, endpoint-coverage, and parameter-consumption tests.**

- [ ] **Step 4: Commit separately and obtain statistical/measurement review.**

Commit message: `feat: register paper1 generator inputs`

### Task 5: Repair all ten scenario paths

**Files:**
- Modify: `configs/synthetic_scenarios.yaml`
- Modify: `src/almondlab/paper1_contracts.py`
- Test: `tests/test_paper1_contracts.py`

- [ ] **Step 1: Add the Section 7 RED matrix and recursive forbidden-name scan.**

- [ ] **Step 2: Materialize the neutral anchor and migrate only the values marked retainable.**

- [ ] **Step 3: Add owner registrations for chassis/onset/drift/purge; fail closed when any is absent.**

- [ ] **Step 4: Prove each scenario differs only at its literal whitelist paths.**

- [ ] **Step 5: Commit and obtain independent scientific-boundary review.**

Commit message: `feat: freeze paper1 scenario mechanisms`

### Task 6: Freeze calibration registration

**Files:**
- Create later with Task 4 fixture slice: `tests/fixtures/known_effect.yaml`
- Create exact mirror later: `src/almondlab/resources/fixtures/known_effect.yaml`
- Test later: `tests/test_simulate.py`

- [ ] **Step 1: Materialize deterministic fit/holdout panels from the declared calibration seed children and record hashes.**

- [ ] **Step 2: Obtain the owner’s prospective candidate, trade-off, bracket, and tolerances.**

- [ ] **Step 3: Write RED contract tests before implementing the solver.**

- [ ] **Step 4: Approve the registration independently; do not run candidate-search or bracket expansion.**

### Task 7: Coordinate package resources and wheel smoke tests

**Files:**
- Modify: `pyproject.toml` only if the final resource pattern is insufficient
- Modify: `tests/test_verification_resources.py`
- Create exact mirrors under `src/almondlab/resources/configs/` and later `src/almondlab/resources/fixtures/`

- [ ] **Step 1: Extend exact resource inventories while preserving the existing core subset.**

The literal additions are:

```python
TASK4_RUNTIME_CONFIGS = frozenset({
    "candidates.yaml",
    "experiment_paper1.yaml",
    "model_domains.yaml",
    "paper1_water_recipes.yaml",
    "synthetic_scenarios.yaml",
})
TASK4_ARCHIVE_CONFIGS = frozenset({
    "archive/experiment_paper1_v1_3.yaml",
    "archive/synthetic_scenarios_v1_3.yaml",
})
TASK4_RUNTIME_FIXTURES = frozenset({
    "candidate_effects.yaml",
    "global_null.yaml",
    "known_effect.yaml",
    "winner_curse.yaml",
})
```

Use recursive relative paths for the config inventory so the archive is checked but cannot collide with the active design. Existing `CANONICAL_POLICIES` and `CANONICAL_FIXTURES` remain literal lower-bound subsets; the final exact set is their union with these additions.

- [ ] **Step 2: Assert authoring/package bytes are identical and LF-stable under Windows autocrlf.**

- [ ] **Step 3: Build/install a wheel in an isolated environment and load every Task 4 resource through `importlib.resources`.**

The current `pyproject.toml` recursive `resources/**/*.yaml`/`.json`/`.csv` patterns should already include these files. Change package data only if the built-wheel inventory test disproves that expectation.

- [ ] **Step 4: Record resource hashes and commit packaging separately.**

Commit message: `build: package paper1 generator resources`

### Task 8: Final pre-generator readiness audit

**Files:**
- Create: `.superpowers/sdd/2026-08-12-almondlab-paper1-statistics/task-4-contract-repair-report.md`
- Modify: `.superpowers/sdd/2026-08-12-almondlab-paper1-statistics/progress.md` only after approval

- [ ] **Step 1: Run focused Task 1/2/3/config/chemistry/domain/provenance/resource suites.**

- [ ] **Step 2: Run the complete non-publication suite in a stable worktree and record commit, counts, skips, duration, and dirty state.**

- [ ] **Step 3: Independently review chemistry/measurement semantics and contract/reproducibility semantics.**

- [ ] **Step 4: Confirm no Task 4 generator file or operating-characteristic acceptance artifact was created.**

- [ ] **Step 5: Mark the contract repair complete only when all protocol registrations exist and both reviews approve.**

## 12. Protocol-owner registration sheet

Every row is unresolved and blocks generation; “owner” means the protocol/config authority, not the implementer:

| Blocker | Authoritative destination file and exact field family | Required prospective choice |
|---|---|---|
| B01 | `configs/paper1_water_recipes.yaml::active_recipes[water_id=nonsaline_nutrient_matched_control]` | New recipe ID/revision, direct-vs-formula preparation basis, complete full-ion/nonstoichiometric targets, lineage hash, and preparation/amendment record. |
| B02 | `configs/paper1_water_recipes.yaml::active_recipes[water_id=pilot_selected_full_ion_marine_challenge]` | Same complete registration for the challenge water. |
| B03 | `active_recipes[*].charge_balance_tolerance_percent` and `configs/synthetic_scenarios.yaml::anchor.generator.chemistry.charge_balance_tolerance_percent` | One percent tolerance with exact agreement across both authorities; it is not the numerical ledger tolerance. |
| B04 | `configs/synthetic_scenarios.yaml::anchor.forcings_by_water_id` | Complete ordered control and challenge schedules covering 2,016 h independently and exact recipe mapping. |
| B05 | `anchor.generator.climate.*` | Three AR(1) coefficients, all innovation SDs, potential-transpiration innovation SD, and exact burn-in count. |
| B06 | `anchor.generator.chemistry.*` except B03 | Common-ion and boron perturbation SDs; ECw, osmolality, pH, and temperature measurement SDs. |
| B07 | `anchor.generator.water_loop.*` except the scenario delta in B19 | Initial/batch/min/max volumes, irrigation, return fraction, baseline purge, sampling volume, and ordered operator events. |
| B08 | `anchor.generator.observation.{canopy,ion,h3}_observation_times_days` and both heteroscedastic slopes | Exact ordered schedules and formulas. |
| B09 | `anchor.generator.observation.h3_observation_error_by_endpoint.C3` | Native-unit C3 SD; the dimensionless v1.3 0.05 is prohibited here. |
| B10 | `anchor.generator.censoring.{lod,loq,lod_log_sd,loq_log_sd}_by_endpoint` | Endpoint-complete limits and threshold variation, including equality semantics. |
| B11 | `anchor.generator.drift.*` | Canopy/ion/H3 drift, calibration interval, and endpoint-complete post-calibration residual SDs. |
| B12 | `anchor.generator.death.*` | Heterogeneity SDs for biomass threshold, injury threshold, and sustained duration on their registered scales; Task 2 baseline thresholds remain unchanged. |
| B13 | `anchor.generator.missingness.{observable_stress_proxy_fields,observable_stress_proxy_center_by_field,observable_stress_proxy_scale_by_field,mnar_endpoints}` | Exact analyst-observable MAR covariates, centers/scales, and MNAR endpoint set. |
| B14 | `anchor.generator.calibration.*` | Absolute/relative tolerances, max iterations, fit/holdout counts, and holdout tolerance. |
| B15 | `anchor.generator.design.confirmation_plants_per_group_reservoir` | Exact integer 5 or 6, frozen before confirmation generation. |
| B16 | `configs/model_domains.yaml::core_v1.{version,allowed_chassis}` and `scenarios[chassis_interaction].mechanism.*` | Secondary chassis ID, `core_v1` version bump `1.0.0 → 1.1.0`, and literal candidate × chassis parameter leaves/modifiers; affirm or retire the old 0.35 migration candidate. |
| B17 | `scenarios[delayed_toxicity].mechanism.{onset_time_days,post_onset_biology_parameter_overrides}` | Exact onset and whether 0.06 senescence is the complete post-onset set; any other leaf/value is new. |
| B18 | `scenarios[sensor_drift_missingness].generator.drift.*` | Exact nonzero drift/calibration overrides beyond retained canopy error 0.12 and missingness slope 0.60. |
| B19 | `scenarios[insufficient_purge].generator.water_loop.purge_volume_l_day` | Reduced purge flow; the old 0.30 osmolality edit is not reusable. |
| B20 | `tests/fixtures/known_effect.yaml` and exact packaged mirror | Candidate, canonical effects template/trade-off, primary-mechanism bracket, solver tolerances, panel counts, holdout tolerance, and frozen fit/holdout hashes. |

### 12.1 Numeric carry-forward ledger

The only unconditional numeric migrations are: hierarchy 0.02/0.02/0.04/0.10; canopy error 0.05; ion error 0.04; H3 error 0.05 for C1/C2/C4/C5/C6 only; missingness intercept -3.0; stress slope 0.20; MNAR tipping delta 0.10; and duration 84.0 days. Scenario-local migrations are limited to 0.0 root Na permeability, 0.10 Na efflux, 0.40 ROS clearance, 0.80 mannitol carbon cost, 0.06 post-onset senescence, 0.12 canopy error, 0.60 missingness slope, and 0.20 plant variance, each only at the Section 7 destination. The old 0.35 conductance is contingent on B16 and otherwise retired.

The two legacy water records—including every ion, ECw, pH, osmolality, and temperature value—are safe only as immutable historical anchors. None is safe to copy into an active recipe. The single v1.3 forcing coordinate is contingent on B04 and cannot be replicated or assigned to control by migration code. Frozen candidate/H3 identities, the two water IDs, and `log(1.30)` are contract identities/design targets rather than calibration or efficacy evidence. Every other numeric field in Sections 5–9 is a prospective registration.

## 13. Review and completion gates

The contract repair is ready for Task 4 only when:

- final Task 3 is committed/approved and its public API is copied verbatim;
- discovery and confirmation design bundles pass canonical whole-bundle revalidation;
- all five physical namespaces and optional event IDs are disjoint;
- v1.3 scenario loading fails with an explicit migration error;
- every old generator value has a documented destination and no new value is hidden;
- both active recipes pass independent and public charge checks plus domain validation;
- the v1.3 design archive retains the exact historical SHA-256;
- both water forcing schedules are explicit and cover exactly 84 days;
- all ten scenarios pass the literal path policy, with no inferred mechanism from a name;
- calibration registration is prospective and complete;
- exact config/fixture mirrors load from an installed wheel;
- focused and full non-publication tests pass;
- independent statistical/scientific and code/reproducibility reviews approve;
- no Acceptance 7/8/9/16 pass artifact, biological finding, or physical-compliance claim exists.

Until these statements are proved, Task 4 remains blocked at the contract/configuration gate rather than receiving guessed defaults.
