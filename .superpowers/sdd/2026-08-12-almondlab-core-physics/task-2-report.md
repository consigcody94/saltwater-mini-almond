Verdict: Needs fixes

### Spec Compliance

- ✅ `WaterChemistry` requires the specified registered solute fields, rejects extras, rejects non-finite floats, and is frozen at the model attribute level.
- ✅ EC kind remains an explicit `ECKind`; the change introduces no EC-to-ion conversion. `ECw`, pore-water EC, and ECe therefore remain distinguishable.
- ✅ Domain range ordering permits equality, calibration values are checked as 64-hex-character SHA-256 digests, and extrapolation policy is closed to the three specified values.
- ✅ `DataOrigin` and `EvidenceLabel` remain separate fields, and `schemas.py` does not introduce `CandidateSpec` or `RunManifest`.
- ⚠️ The configured core domain has the requested ECw, 0.7–15.0 dS/m, osmolality, temperature, analyte, chassis, life-stage, label, and deny-extrapolation scope.
- ❌ An empty calibration map is accepted for non-physics labels, contrary to the fail-closed calibration rule.
- ❌ The schema permits negative charge-equivalent alkalinity and negative EC/osmolality domain bounds; it also stores temperature in Celsius rather than the binding canonical Kelvin unit.

### Strengths

- `StrictScientificModel` centralizes `extra="forbid"`, immutability, and finite-float handling.
- The YAML record and focused tests cover the intended conservation-core configuration and malformed calibration hashes.
- The provenance and evidence vocabulary is kept at the record boundary without conflating their meanings.

### Issues

#### Critical

- None.

#### Important

- `src/almondlab/schemas.py:83-87` — Empty `calibration_datasets` is rejected only for `EMPIRICALLY_CALIBRATED`; `HYPOTHESIS_PRIOR` and `SYNTHETIC_ONLY` domains can silently use an empty map. This violates the requirement that an empty map be allowed only for the physics-constrained conservation core, weakening evidence provenance. Reject every empty map unless the model is explicitly identified as that conservation core (or add an explicit, validated core flag), and add tests for the other two labels.

- `src/almondlab/schemas.py:25-28, 57-62` — `alkalinity_mmol_c_l` has no nonnegative constraint and domain EC/osmolality limits can be negative. These invalid states pass validation despite the strict finite/nonnegative scientific-boundary requirement. Add `ge=0` constraints to alkalinity and physically nonnegative domain quantities, with regression tests.

- `src/almondlab/schemas.py:25, 62-63` and `configs/model_domains.yaml:11-12` — Temperature is represented as `temperature_c` and Celsius bounds, whereas the binding canonical unit is Kelvin. This makes the persisted scientific record noncanonical and allows values below absolute zero. Store canonical Kelvin (`temperature_k` and Kelvin bounds) or convert at ingress while retaining only Kelvin internally; update the config and tests accordingly.

#### Minor

- `tests/test_schemas.py:104-111` — The core-YAML test verifies only EC bounds, evidence label, and an empty calibration map. It does not assert the full required-analyte list, Vairo/juvenile scope, osmolality/temperature bounds, or extrapolation policy. Assert the complete prescribed record so configuration drift fails immediately.

### Assessment

Needs fixes

## Fix round 1: calibration closure and canonical Kelvin

### RED

Command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_schemas.py -v -p no:cacheprovider
```

Output before the fix:

```text
collecting ... collected 22 items
FAILED tests/test_schemas.py::test_water_rejects_negative_alkalinity
FAILED tests/test_schemas.py::test_water_from_celsius_stores_only_kelvin
FAILED tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[ec_ds_m_min]
FAILED tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[ec_ds_m_max]
FAILED tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[osmolality_min]
FAILED tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[osmolality_max]
FAILED tests/test_schemas.py::test_only_conservation_core_allows_empty_calibration_data[alternate_core-physics_constrained]
FAILED tests/test_schemas.py::test_only_conservation_core_allows_empty_calibration_data[hypothesis_v1-hypothesis_prior]
FAILED tests/test_schemas.py::test_only_conservation_core_allows_empty_calibration_data[synthetic_v1-synthetic_only]
FAILED tests/test_schemas.py::test_core_domain_yaml_loads_with_exact_scope
======================== 12 failed, 10 passed in 1.11s ========================
```

### GREEN

Focused command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_schemas.py -v -p no:cacheprovider
```

Output:

```text
collecting ... collected 22 items
tests/test_schemas.py::test_water_requires_complete_registered_chemistry PASSED
tests/test_schemas.py::test_water_rejects_nonfinite_values PASSED
tests/test_schemas.py::test_water_rejects_negative_solute_stock PASSED
tests/test_schemas.py::test_water_rejects_negative_alkalinity PASSED
tests/test_schemas.py::test_water_from_celsius_stores_only_kelvin PASSED
tests/test_schemas.py::test_water_rejects_unknown_fields PASSED
tests/test_schemas.py::test_water_instances_are_immutable PASSED
tests/test_schemas.py::test_domain_bounds_are_ordered PASSED
tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[ec_ds_m_min] PASSED
tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[ec_ds_m_max] PASSED
tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[osmolality_min] PASSED
tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[osmolality_max] PASSED
tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[temperature_k_min] PASSED
tests/test_schemas.py::test_domain_rejects_negative_physical_bounds[temperature_k_max] PASSED
tests/test_schemas.py::test_domain_rejects_malformed_dataset_hash PASSED
tests/test_schemas.py::test_empirical_domain_requires_calibration_data PASSED
tests/test_schemas.py::test_only_conservation_core_allows_empty_calibration_data[alternate_core-physics_constrained] PASSED
tests/test_schemas.py::test_only_conservation_core_allows_empty_calibration_data[hypothesis_v1-hypothesis_prior] PASSED
tests/test_schemas.py::test_only_conservation_core_allows_empty_calibration_data[synthetic_v1-synthetic_only] PASSED
tests/test_schemas.py::test_core_domain_yaml_loads_with_exact_scope PASSED
tests/test_schemas.py::test_canonical_quantity_converts_to_requested_unit PASSED
tests/test_schemas.py::test_records_keep_data_origin_distinct_from_evidence_label PASSED
============================= 22 passed in 0.98s ==============================
```

Task 1 regression command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_contracts.py tests/test_cli.py -v -p no:cacheprovider
```

Output:

```text
collecting ... collected 3 items
tests/test_contracts.py::test_public_enums_and_stable_error_code PASSED
tests/test_contracts.py::test_error_serializes_structured_fields PASSED
tests/test_cli.py::test_public_cli_app_shows_help PASSED
============================== 3 passed in 0.55s ==============================
```

### Resolution

- Empty calibration datasets are allowed only when `model_id == "core_v1"` and
  the evidence label is `physics_constrained`; every other model requires a
  nonempty map of SHA-256 hashes.
- Alkalinity and all EC, osmolality, and Kelvin range endpoints validate at or
  above zero.
- Canonical schemas and serialized records use `temperature_k`,
  `temperature_k_min`, and `temperature_k_max`. `WaterChemistry.from_celsius`
  is the sole explicit Celsius ingress helper and converts by adding 273.15;
  the core YAML stores 291.15–303.15 K.
- The core-YAML test now asserts every required analyte, all three ranges,
  Vairo/juvenile scope, evidence label, empty core dataset map, and deny
  extrapolation policy.
