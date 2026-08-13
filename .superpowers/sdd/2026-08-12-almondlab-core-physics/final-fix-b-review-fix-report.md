# Final Fix B review-fix report — closed boundary escapes

## Outcome

Fixed the three defects found in independent review of `4e7e353` without
changing chemistry helper behavior, numerical formulas, verification code, or
fixtures.

- A required computed SAR that cannot be evaluated is now an auditable
  `DOMAIN_VIOLATION` item; direct chemistry calls still raise their precise
  `SAR_ZERO_DENOMINATOR` error.
- Every `StrictScientificModel` revalidates instances. The public domain and
  hydraulic boundaries explicitly revalidate copied policy/input objects and
  translate malformed nested values into stable `AlmondLabError` codes and
  dotted paths.
- Hydraulic policy and decision records now emit the canonical
  `permitted_evidence_label` name. A narrow input normalizer reads the legacy
  acceptance-fixture key but never emits it, preserving acceptance 13 without
  retaining a stale attribute alias.

## Owned files

- `src/almondlab/schemas.py`
- `src/almondlab/domains.py`
- `src/almondlab/hydraulics.py`
- `tests/test_schemas.py`
- `tests/test_domains.py`
- `tests/test_hydraulics.py`
- this report

Concurrent mass-balance fixture/test changes were preserved and excluded.

## TDD evidence

### RED

The initial domain/hydraulic command collected 78 tests and failed 27 before
production changes. The relevant failures included:

```text
SAR_ZERO_DENOMINATOR: Ca + Mg must be positive
TypeError: '<' not supported between instances of 'str' and 'float'
AttributeError: 'str' object has no attribute 'value'
```

Those failures proved that required SAR escaped aggregation, copied Pydantic
objects bypassed validation, and the hydraulic implementation did not yet use
the canonical evidence-policy field.

### Focused GREEN

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_schemas.py tests/test_domains.py tests/test_hydraulics.py -q -p no:cacheprovider
```

Result:

```text
114 passed in 0.98s
```

The new cases cover copied numeric strings, booleans, NaN/infinity, and invalid
enum labels in nested water records, domain policies, hydraulic inputs, and
hydraulic policies. Every public boundary returns its stable code and the exact
failing path.

### Acceptance 13 compatibility GREEN

Direct invocation of the independent acceptance function passed and retained:

```text
model_id: core_v1.acceptance_13
purpose: analytic_verification
scope: numerical_oracle_not_almond_applicability
```

The canonical `core_v1` domain remains unchanged at maximum osmolality 0.30;
only that analytical fixture permits 0.40.

## Full-suite status under concurrent migration

The requested complete-suite attempt reached two failures caused by another
agent's visible, uncommitted mass-balance fixture migration:

```text
tests/test_core_acceptance.py::test_core_acceptance_writes_only_owned_records_to_run_directory
tests/test_core_acceptance.py::test_default_runtime_policies_are_strict_hashed_and_packaged
KeyError: 'volumes_l' at verification.py::_state
```

At that moment `no_purge.yaml` and `sufficient_purge.yaml` had already moved to
a nested `initial.tank` representation while the unmodified verification
reader still requested `initial["volumes_l"]` and `initial["stocks_mmol"]`.
This boundary task did not edit or stage verification, mass balance, their
tests, or any fixture. The controller will rerun the complete suite after the
coordinated mass/treatment/verification migration reaches a compatible state.

`git diff --check` passed for all six implementation/test files owned here.
