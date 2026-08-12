# Task 3 report: chemistry, RO treatment, and domain refusal

## Result

Task 3 is implemented on `build/virtual-lab` in feature commit
`91a0a5e83eba5f7e46dfd108d0b79bfeef1403ee`. The final focused suite passes
35 tests and the Tasks 1-2 regression suite passes 25 tests. Both final pytest
commands use the required task-local UV cache and disabled pytest cache
provider, with no warnings or cache artifacts in their output.

## Files changed

- `src/almondlab/chemistry.py`
- `src/almondlab/treatment.py`
- `src/almondlab/domains.py`
- `src/almondlab/errors.py` (backward-compatible optional structured details
  argument for `fail()`)
- `tests/test_chemistry.py`
- `tests/test_treatment.py`
- `tests/test_domains.py`
- `tests/fixtures/chemistry_handcheck.yaml`
- `.superpowers/sdd/2026-08-12-almondlab-core-physics/task-3-report.md`

No visual asset was read, edited, staged, or committed.

## RED

Initial command, run before any Task 3 production module existed:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_chemistry.py tests/test_treatment.py tests/test_domains.py -v -p no:cacheprovider
```

Exact result:

```text
collecting ... collected 0 items / 3 errors
E   ModuleNotFoundError: No module named 'almondlab.chemistry'
E   ModuleNotFoundError: No module named 'almondlab.treatment'
E   ModuleNotFoundError: No module named 'almondlab.domains'
=========================== short test summary info ===========================
ERROR tests/test_chemistry.py
ERROR tests/test_treatment.py
ERROR tests/test_domains.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 3 errors in 0.56s ==============================
```

The three collection failures were the expected missing-module failures, not
test syntax or fixture errors.

### Follow-up RED: provenance retention and exhaustive empty-analyte reporting

Command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_chemistry.py::test_blend_sums_every_registered_analyte_and_alkalinity_by_mass tests/test_domains.py::test_allowed_extrapolation_reports_every_analyte_when_none_are_available -v -p no:cacheprovider
```

Exact result:

```text
collected 2 items
tests/test_chemistry.py::test_blend_sums_every_registered_analyte_and_alkalinity_by_mass FAILED [ 50%]
tests/test_domains.py::test_allowed_extrapolation_reports_every_analyte_when_none_are_available FAILED [100%]
E   AttributeError: 'BlendResult' object has no attribute 'measurement_data_origin'
E   pydantic_core._pydantic_core.ValidationError: 1 validation error for DomainRequest
E   available_analytes
E     Frozenset should have at least 1 item after validation, not 0
============================== 2 failed in 0.62s ==============================
```

After the minimal implementation change, the same command returned:

```text
collected 2 items
tests/test_chemistry.py::test_blend_sums_every_registered_analyte_and_alkalinity_by_mass PASSED [ 50%]
tests/test_domains.py::test_allowed_extrapolation_reports_every_analyte_when_none_are_available PASSED [100%]
============================== 2 passed in 0.48s ==============================
```

### Follow-up RED: charge-equivalent alkalinity

Command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_chemistry.py::test_charge_balance_uses_explicit_valence_and_measured_alkalinity -v -p no:cacheprovider
```

Exact result before the correction:

```text
collected 1 item
tests/test_chemistry.py::test_charge_balance_uses_explicit_valence_and_measured_alkalinity FAILED [100%]
E       assert -77.33333333333333 == 6.25 +/- 6.2e-06
E         Obtained: -77.33333333333333
E         Expected: 6.25 +/- 6.2e-06
============================== 1 failed in 0.88s ==============================
```

The failure proved the diagnostic was reconstructing anion charge from
bicarbonate/phosphate instead of consuming the canonical measured
`alkalinity_mmol_c_l`. After the one-formula correction, the same command
returned `1 passed in 0.48s`.

## GREEN

Final Task 3 command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_chemistry.py tests/test_treatment.py tests/test_domains.py -v -p no:cacheprovider
```

Exact output:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\fowlb\Documents\Codex\2026-08-12\lets\outputs\saltwater-mini-almond\.venv\Scripts\python.exe
hypothesis profile 'default'
rootdir: C:\Users\fowlb\Documents\Codex\2026-08-12\lets\outputs\saltwater-mini-almond
configfile: pyproject.toml
plugins: hypothesis-6.165.5
collecting ... collected 35 items

tests/test_chemistry.py::test_sar_hand_oracle_uses_charge_concentrations PASSED [  2%]
tests/test_chemistry.py::test_sar_water_wrapper_applies_divalent_ca_and_mg PASSED [  5%]
tests/test_chemistry.py::test_sar_refuses_zero_divalent_charge PASSED    [  8%]
tests/test_chemistry.py::test_blend_sums_every_registered_analyte_and_alkalinity_by_mass PASSED [ 11%]
tests/test_chemistry.py::test_blend_refuses_to_average_ec_without_validated_measurement PASSED [ 14%]
tests/test_chemistry.py::test_blend_refuses_mixed_ec_kinds_even_with_measurement PASSED [ 17%]
tests/test_chemistry.py::test_blend_refuses_measurement_of_different_ec_kind PASSED [ 20%]
tests/test_chemistry.py::test_charge_balance_uses_explicit_valence_and_measured_alkalinity PASSED [ 22%]
tests/test_treatment.py::test_ro_hand_oracle_and_each_entity_conservation PASSED [ 25%]
tests/test_treatment.py::test_ro_property_conserves_water_and_entity PASSED [ 28%]
tests/test_treatment.py::test_ro_refuses_nonphysical_recovery[0.0] PASSED [ 31%]
tests/test_treatment.py::test_ro_refuses_nonphysical_recovery[1.0] PASSED [ 34%]
tests/test_treatment.py::test_ro_refuses_nonphysical_recovery[-0.1] PASSED [ 37%]
tests/test_treatment.py::test_ro_refuses_nonphysical_recovery[1.1] PASSED [ 40%]
tests/test_treatment.py::test_ro_refuses_nonphysical_ion_rejection[-0.01] PASSED [ 42%]
tests/test_treatment.py::test_ro_refuses_nonphysical_ion_rejection[1.01] PASSED [ 45%]
tests/test_treatment.py::test_ro_refuses_ec_rejection_key[ec] PASSED     [ 48%]
tests/test_treatment.py::test_ro_refuses_ec_rejection_key[ECw] PASSED    [ 51%]
tests/test_treatment.py::test_ro_refuses_ec_rejection_key[ec_ds_m] PASSED [ 54%]
tests/test_treatment.py::test_ro_refuses_ec_rejection_key[pore_water_EC] PASSED [ 57%]
tests/test_treatment.py::test_ro_refuses_ec_rejection_key[ECe] PASSED    [ 60%]
tests/test_treatment.py::test_ro_requires_one_rejection_for_every_tracked_entity PASSED [ 62%]
tests/test_domains.py::test_domain_boundaries_are_inclusive[ec_ds_m-1.0] PASSED [ 65%]
tests/test_domains.py::test_domain_boundaries_are_inclusive[ec_ds_m-10.0] PASSED [ 68%]
tests/test_domains.py::test_domain_boundaries_are_inclusive[measured_osmolality_osmol_kg-0.05] PASSED [ 71%]
tests/test_domains.py::test_domain_boundaries_are_inclusive[measured_osmolality_osmol_kg-0.25] PASSED [ 74%]
tests/test_domains.py::test_domain_boundaries_are_inclusive[temperature_k-290.0] PASSED [ 77%]
tests/test_domains.py::test_domain_boundaries_are_inclusive[temperature_k-305.0] PASSED [ 80%]
tests/test_domains.py::test_denied_domain_reports_every_violation_in_structured_error PASSED [ 82%]
tests/test_domains.py::test_missing_analyte_is_refused PASSED            [ 85%]
tests/test_domains.py::test_dataset_hash_mismatch_is_refused PASSED      [ 88%]
tests/test_domains.py::test_allowed_extrapolation_returns_weak_label_and_all_violations[hypothesis_prior-hypothesis_prior] PASSED [ 91%]
tests/test_domains.py::test_allowed_extrapolation_returns_weak_label_and_all_violations[synthetic_only-synthetic_only] PASSED [ 94%]
tests/test_domains.py::test_allowed_extrapolation_never_preserves_strong_requested_label PASSED [ 97%]
tests/test_domains.py::test_allowed_extrapolation_reports_every_analyte_when_none_are_available PASSED [100%]

============================= 35 passed in 0.80s ==============================
```

Tasks 1-2 regression command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_contracts.py tests/test_cli.py tests/test_schemas.py -v -p no:cacheprovider
```

Exact result:

```text
collecting ... collected 25 items
tests/test_contracts.py::test_public_enums_and_stable_error_code PASSED
tests/test_contracts.py::test_error_serializes_structured_fields PASSED
tests/test_cli.py::test_public_cli_app_shows_help PASSED
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
============================= 25 passed in 1.04s ==============================
```

`python -m compileall -q src` and `git diff --check` also exited zero. The Git
client emitted only workstation configuration warnings about an inaccessible
global ignore file and future LF-to-CRLF normalization; neither appeared in
pytest output or changed repository content.

## Commit

- `91a0a5e83eba5f7e46dfd108d0b79bfeef1403ee` — `feat: add conservative
  chemistry treatment and domain checks`
- The report itself is committed separately in the commit containing this
  file.

## Self-review

- Blending uses `volume * concentration` stocks for every registered analyte
  and alkalinity, then divides by total volume. EC, pH, osmolality, and Kelvin
  temperature come only from a validated `BlendMeasurement`; mixed EC kinds
  and absent/mismatched EC measurement contracts fail closed.
- Blend results retain all source origins/labels, the measurement ID and
  measurement origin, mark the derived record `model_derived`, and choose the
  weakest participating evidence label.
- SAR's scalar interface names and accepts only mmol_c/L. The
  `WaterChemistry` wrapper converts Ca and Mg mmol/L to mmol_c/L with valence
  two explicitly. Charge balance likewise applies explicit monovalent/divalent
  factors and consumes measured alkalinity charge equivalents.
- RO requires exactly one rejection for each entity, refuses EC rejection
  keys and nonphysical values, conserves every entity as feed = permeate +
  concentrate, conserves water, and has no hidden loss/sink path.
- Domain ranges are inclusive. EC kind, all ranges, every required analyte and
  corresponding chemistry field, chassis, life stage, exact dataset IDs and
  hashes, and the requested evidence label are checked before returning the
  requested label.
- Denied extrapolation raises `DOMAIN_VIOLATION` with every violation in
  structured details. Allowed extrapolation returns only `hypothesis_prior` or
  `synthetic_only`, retains the strong requested label separately, and returns
  all violations, including an entirely empty analyte set.
- Mutation checks are represented by explicit rejection tests, a Hypothesis
  RO conservation/positivity property, mixed-EC tests, domain endpoint tests,
  exact hash mismatch tests, and the bicarbonate/phosphate decoy in the charge
  hand oracle.

## Concerns

No implementation concern remains. The only environment note is the existing
Git global-ignore/line-ending warning described above; test output is pristine
and the feature commit contains no visual files.
