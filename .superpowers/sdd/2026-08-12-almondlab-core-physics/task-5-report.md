# Task 5 report — osmotic/hydraulic gate and core acceptance bundle

Implemented the physics-constrained osmotic/hydraulic gate and the core-owned verification bundle. The runner writes only tests `01`–`05`, `13`, `19`, and `20` beneath a caller-provided temporary run directory. It never creates publication-plan placeholders.

## TDD record

RED, before `src/almondlab/hydraulics.py` existed:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'; & 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_hydraulics.py -v -p no:cacheprovider
```

Observed expected `ModuleNotFoundError: No module named 'almondlab.hydraulics'` during collection.

RED, before `src/almondlab/verification.py` existed:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'; & 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_core_acceptance.py -v -p no:cacheprovider
```

Observed expected `ModuleNotFoundError: No module named 'almondlab.verification'` during collection.

RED, after adding the full acceptance-artifact requirement:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'; & 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_core_acceptance.py -v -p no:cacheprovider
```

Observed expected failure because Test 13 emitted only the ratio instead of all three fixed hydraulic values. A later RED run required Test 3 to represent a valid physical censored stop; it failed because `censored` was false.

GREEN focused verification:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'; & 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_hydraulics.py tests/test_core_acceptance.py -v -p no:cacheprovider
```

Result: `4 passed`.

## Complete verification

Required core plan command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'; & 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_contracts.py tests/test_schemas.py tests/test_chemistry.py tests/test_treatment.py tests/test_domains.py tests/test_mass_balance.py tests/test_hydraulics.py tests/test_core_acceptance.py -v -p no:cacheprovider
```

Result: `99 passed`.

Full suite:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'; & 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest -v -p no:cacheprovider
```

Result: `133 passed`.

## Fix round 1

Addressed the Task 5 review findings with failing tests first. The focused RED run exposed the missing `HydraulicDomain` and `load_physical_stops` interfaces; subsequent RED runs caught the stale Test 20 stop invocation and the invalid-record/pass inconsistency. The implementation now rejects nonfinite values in all numerical inputs, loads only `synthetic_only` or `hypothesis_prior` physical stops from configuration, applies both inclusive minimum and maximum censoring, and derives Test 3's censored state from the actual simulated concentration.

Test 19 now submits all six mismatched directional EC substitutions through an executable analysis boundary and records each `EC_TYPE_MISMATCH`; its accepted-record count is observed rather than stamped. Test 20 uses the independent all-conserved-entities fixture, names each entity's transfer and RO residuals, and carries hashes for every fixture it uses. Test 5 records raw SAR alongside the independent literal oracle.

Focused result: `13 passed`.

Required core suite result: `108 passed`.

Full suite result: `142 passed`.

The placeholder-pattern scan (`TODO|TBD|FIXME|placeholder|not implemented`) returned no matches in `src`, `tests`, or `configs` outside this report/checklist context. `git diff --check` was clean.
