# Task 2 report: units and validation schemas

## Result

Task 2 is complete. The scientific boundary now has one Pint registry,
immutable Pydantic input records, finite-number checks, complete registered
water chemistry, inclusive ordered model ranges, and calibration SHA-256
validation. `DataOrigin` remains distinct from `EvidenceLabel` on records.

## Files changed

- `src/almondlab/units.py`
- `src/almondlab/schemas.py`
- `tests/test_schemas.py`
- `configs/model_domains.yaml`

## RED

Command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_schemas.py -v -p no:cacheprovider
```

Output before `schemas.py` existed:

```text
collecting ... collected 0 items / 1 error
E   ModuleNotFoundError: No module named 'almondlab.schemas'
============================== 1 error in 0.63s ===============================
```

The record-provenance contract was also added test-first after temporarily
removing its two public classes. Its RED output was:

```text
collecting ... collected 0 items / 1 error
E   ImportError: cannot import name 'ObservationRecord' from 'almondlab.schemas'
============================== 1 error in 0.63s ===============================
```

## GREEN

Focused command:

```powershell
$env:UV_CACHE_DIR = 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_schemas.py -v -p no:cacheprovider
```

Output:

```text
collecting ... collected 11 items
tests/test_schemas.py::test_water_requires_complete_registered_chemistry PASSED
tests/test_schemas.py::test_water_rejects_nonfinite_values PASSED
tests/test_schemas.py::test_water_rejects_negative_solute_stock PASSED
tests/test_schemas.py::test_water_rejects_unknown_fields PASSED
tests/test_schemas.py::test_water_instances_are_immutable PASSED
tests/test_schemas.py::test_domain_bounds_are_ordered PASSED
tests/test_schemas.py::test_domain_rejects_malformed_dataset_hash PASSED
tests/test_schemas.py::test_empirical_domain_requires_calibration_data PASSED
tests/test_schemas.py::test_core_domain_yaml_loads_with_exact_scope PASSED
tests/test_schemas.py::test_canonical_quantity_converts_to_requested_unit PASSED
tests/test_schemas.py::test_records_keep_data_origin_distinct_from_evidence_label PASSED
============================= 11 passed in 0.78s ==============================
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
============================== 3 passed in 0.49s ==============================
```

## Commit

- `c69720a feat: add typed scientific schemas and units`

## Self-review

- `WaterChemistry` requires every registered chemistry input, forbids extras,
  rejects non-finite values, and constrains all stated solute concentrations
  and EC/osmolality to nonnegative values.
- `ModelDomain` accepts equality at range boundaries, rejects reversed ranges
  and malformed SHA-256 digests, and prevents an empirical label without
  calibration data. The conservation-law `core_v1` configuration is the
  required `physics_constrained` record with an explicitly empty dataset map.
- `WaterBatch` and `ObservationRecord` carry `DataOrigin` and `EvidenceLabel`
  separately; no calibration claim is implied by the core domain label.

## Concerns

None outstanding. `uv` is not on `PATH` in this environment, so the exact
`uv run` invocation used the existing bootstrap `uv.exe`; it used the required
task-local `UV_CACHE_DIR` and disabled pytest cache provider.
