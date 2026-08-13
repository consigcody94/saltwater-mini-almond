### Task 4: Generate synthetic discovery and independent confirmation cohorts

**Files:**
- Create: `src/almondlab/simulate.py`
- Create: `tests/test_simulate.py`
- Create: `tests/fixtures/global_null.yaml`
- Create: `tests/fixtures/known_effect.yaml`
- Create: `tests/fixtures/winner_curse.yaml`

**Interfaces:**
- Consumes: randomization manifest, biology surrogate, root seed, scenario config.
- Produces: `SyntheticTournament`, `generate_paper1_synthetic(config: Paper1SimulationConfig, scenario: SyntheticScenarioConfig, root_seed: int) -> SyntheticTournament`, `calibrate_mechanism_to_estimand(candidate_id: str, target_delta: float, baseline: BiologyParameters, forcing: Sequence[RootZoneForcing], lower: float, upper: float) -> MechanismCalibration`.

- [ ] **Step 1: Write failing hierarchy/isolation tests**

```python
from almondlab.simulate import generate_paper1_synthetic

def test_confirmation_ids_are_independent(global_null_config) -> None:
    data = generate_paper1_synthetic(global_null_config, root_seed=20260812)
    for column in ("plant_id", "batch_id", "reservoir_id", "water_batch_id", "run_id"):
        discovery = set(data.discovery_allocation[column])
        confirmation = set(data.confirmation_allocation[column])
        assert discovery.isdisjoint(confirmation)

def test_synthetic_ids_and_labels(global_null_config) -> None:
    data = generate_paper1_synthetic(global_null_config, root_seed=20260812)
    assert data.observations["record_id"].str.startswith("SYN_").all()
    assert set(data.observations["evidence_label"]) == {"synthetic_only"}
```

- [ ] **Step 2: Verify generator is absent**

Run: `uv run pytest tests/test_simulate.py -v`

Expected: FAIL on import.

- [ ] **Step 3: Implement hidden-truth generation with SeedSequence children**

Generate AR(1) climate, charge-balanced water batches, run/batch/reservoir/plant effects, heteroscedastic observations, LOD/LOQ censoring, drift, death, MAR and registered MNAR cases. Keep `truth.parquet` outside analyst inputs and hash it in the run manifest. Sort replicate/component outputs before concatenation so worker scheduling cannot change bytes.

- [ ] **Step 4: Implement the ten scenario enum values**

Use exact IDs: `perfect_control`, `true_ion_exclusion`, `root_na_accumulation`, `marker_only`, `nonsaline_penalty`, `chassis_interaction`, `delayed_toxicity`, `sensor_drift_missingness`, `insufficient_purge`, and `selection_bias_false_leader`. Scenario configuration modifies only registered parameters.

- [ ] **Step 5: Run generator tests and commit**

Run: `uv run pytest tests/test_simulate.py -v`

Expected: PASS for hierarchy, disjoint cohorts, death semantics, IDs, labels, truth isolation, seed reproducibility, and all scenario IDs.

```powershell
git add src/almondlab/simulate.py tests/test_simulate.py tests/fixtures configs/synthetic_scenarios.yaml
git commit -m "feat: generate auditable paper1 synthetic cohorts"
```
