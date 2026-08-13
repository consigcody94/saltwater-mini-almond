# Final whole-core fix B report: strict boundaries and evidence semantics

## Scope and scientific claim boundary

This change enforces numeric, domain, provenance, evidence-label, and hydraulic
API boundaries. It does not establish biological validity or almond
applicability. Acceptance test 13 is explicitly identified as a numerical
oracle under `core_v1.acceptance_13`, not as a crop/calibration domain.

The controller authorized the minimal compatibility migration in
`verification.py::_acceptance_13`, the two `perfect_na_exclusion.yaml` copies,
and the directly corresponding acceptance assertions. No other verification
record schema or acceptance path was changed.

## RED evidence

All commands used the task-local bootstrap UV, a task-local UV cache, and
`-p no:cacheprovider`.

Representative boundary RED after test collection was clean:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest -p no:cacheprovider tests/test_schemas.py::test_water_rejects_non_real_or_nonfinite_numeric_inputs tests/test_schemas.py::test_domain_rejects_coercive_or_nonfinite_bounds tests/test_chemistry.py::test_evidence_composition_truth_table_covers_all_sixteen_pairs tests/test_domains.py::test_physics_domain_accepts_in_domain_claim_at_or_below_its_label tests/test_hydraulics.py::test_hydraulic_inputs_require_explicit_evidence_label tests/test_core_acceptance.py::test_core_acceptance_writes_only_owned_records_to_run_directory -q --basetemp 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-final-fix-b-red'
```

Result: `26 failed, 6 passed`. Failures demonstrated boolean/numeric-string
coercion, the absent evidence-composition policy, name-set-only domain input,
default hydraulic evidence/domain behavior, and absent acceptance-13 domain
metadata.

Adversarial review added two more failing regressions:

```powershell
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest -p no:cacheprovider tests/test_domains.py::test_hard_chemistry_failure_stops_before_evidence_label_resolution tests/test_chemistry.py::test_sar_rejects_finite_inputs_whose_intermediate_sum_overflows -q --basetemp 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-final-fix-b-adversarial-red'
```

Result: `2 failed`. The old branch resolved a label after a hard missing-field
failure, and SAR returned a finite zero after an overflowing Ca+Mg sum.

Canonical-field RED (`permitted_evidence_label`): `4 failed`; structured
hydraulic-decision-detail RED: `1 failed`.

## GREEN evidence

The targeted adversarial cycles passed after the minimal fixes:

- hard-field-before-label and SAR overflow: `2 passed`
- canonical `permitted_evidence_label`: `4 passed`
- structured immutable hydraulic decision details: `2 passed`

Final focused command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest -p no:cacheprovider tests/test_schemas.py tests/test_chemistry.py tests/test_domains.py tests/test_hydraulics.py tests/test_core_acceptance.py -q --basetemp 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-final-fix-b-focused-final'
```

Result: `180 passed in 6.62s`.

Final complete-suite command:

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest -p no:cacheprovider -q --basetemp 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-final-fix-b-full-final'
```

Result: `316 passed in 8.23s`.

The complete suite includes acceptance output derivation. Test 13 retains its
independent values (`0.888212`, `0.455696`, ratio `0.513049`) and now records
the analytic domain identifier, purpose, scope disclaimer, and canonical
domain SHA-256.

## Adversarial and compatibility review

- Every scoped scientific numeric model uses a real-number-before-float gate:
  booleans, strings, nonfinite values, and conversion overflow are rejected;
  ordinary integer literals normalize to finite floats.
- Chemistry and hydraulic computation boundaries translate malformed numeric
  values to stable `AlmondLabError` codes and field paths.
- Required chemistry/analyte observations carry method, value, evidence label,
  source identifier, and source hash. Missing/wrong/unmeasured/mismatched facts
  are hard failures before evidence resolution.
- Physics and empirical strong claims are incomparable; weaker in-domain
  requests retain their requested label. Extrapolation requires the exact
  configured weak label and retains every extrapolatable violation.
- The conservative composition operator covers all 16 pairs and is commutative
  and associative without an adapter. Mixed physics/empirical evidence falls
  to `hypothesis_prior`; an explicitly validated adapter is the only strong
  bridge.
- Hydraulic inputs and policy are explicit, and output plus its nested domain
  decision are immutable.
- Repository and packaged `model_domains.yaml` are byte-identical at SHA-256
  `81bf2c2c442d07ec984010dd9c373d2da4fe776467b009246cd665609c159a71`.
  The two acceptance-13 fixtures are byte-identical at SHA-256
  `07f6b1085e08da7da5c5f600a813ddc1205e90f3380d2727f608d00fd627dbd1`.
- Compatibility concern: callers must migrate from `permitted_label` to the
  canonical `permitted_evidence_label`; `DomainRequest` now requires actual
  hashed observations instead of `available_analytes`; and
  `hydraulic_uptake` requires explicit validated `HydraulicInputs.evidence_label`
  and `HydraulicDomain`. Acceptance 13 and all direct hydraulic tests were
  migrated in this change.

`git diff --check` on the owned file set exited 0. Line-ending notices are Git's
existing Windows LF-to-CRLF normalization warning, not whitespace errors.
