# Paper 1 Task 1 — TDD and verification evidence

## Scope

Frozen Paper 1 candidate/H3 contracts, the primary composite-root allocation,
and complete labeled virtual-scenario inputs. These configurations are
`hypothesis_prior` or `synthetic_only`; they do not validate a biological
mechanism, construct, or candidate in almond.

## RED

Test written first: `tests/test_paper1_contracts.py::test_candidate_registry_freezes_order_h3_rules_and_decision_thresholds`.

Command (with `UV_CACHE_DIR=C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache`):

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_paper1_contracts.py
```

Result: exit 1 during collection, as intended before implementation:

```text
ModuleNotFoundError: No module named 'almondlab.paper1_contracts'
```

The requested `uv run` launcher was unavailable on PATH, so the project-managed
`.venv` interpreter was used with the specified UV cache variable.

## GREEN

Implemented `paper1_contracts.py` and the three versioned configs only after
the RED result. The focused contract suite then passed:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_paper1_contracts.py -v
```

Result: exit 0; 5 passed in 0.55s.

The suite covers candidate order/H3 boundaries and thresholds; C2's blocked
sequence/build status with no accession; C3's mechanistic mapping; C4's
risk-bearing xylem warning; the two-water composite-root hierarchy; fail-closed
scenario completeness; registered labels; and recursively serialized forbidden
output keys.

## Regression and self-review

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_contracts.py tests/test_schemas.py tests/test_chemistry.py tests/test_domains.py tests/test_treatment.py tests/test_cli.py -v
```

Result: exit 0; 63 passed in 1.45s.

`git diff --check` returned exit 0. The concurrent `mass_balance` worktree
changes were deliberately not staged or included in this regression slice.

Final fresh full-suite verification after the report and ledger update:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v
```

Result: exit 0; 94 passed in 1.79s. `git diff --check` again returned exit 0.

## Constraints checked

- Candidate sequence data match the approved v1.3 candidate/H3 section; C2 has
  an empty accession list and a machine-readable `sequence_build: blocked` gate.
- C3 targets `mannitol_vmax_multiplier`, not osmotic potential; C4 preserves
  the source-reported elevated xylem/stem sodium warning.
- Every synthetic numeric generator input is supplied by
  `configs/synthetic_scenarios.yaml`; missing required input raises structured
  `INCOMPLETE_SYNTHETIC_SCENARIO` with all missing names.
- No candidate directly targets survival, canopy AUC, kernel yield, or generic
  salt tolerance; serialized contract/config keys exclude `winner` and
  `best_candidate`.

## Fix round 1/5 — addressed pending re-review

Three review findings were addressed without changing core physics or public
data paths. All values remain virtual-design contracts labeled
`hypothesis_prior` or `synthetic_only`; this fix does not add biological
validation.

### RED evidence

1. An independent literal v1.3 candidate oracle failed with 1 failure and 11
   passes because C1, C2, C4, C5, and C6 used nonregistered mechanism IDs.
   After correcting only those IDs, the focused suite reported 12 passes.
2. Candidate-level mutation cases then failed as intended: 9 failures and 12
   passes showed that fabricated C2 accessions, inconsistent C2 audit/build
   state, and mutated C1–C6 identity/H3/gates were still accepted.
3. The extra-key test failed because `unregistered_growth_magic` was accepted
   in a complete synthetic scenario.
4. Six design-mutation cases failed with 23 passes because renamed/reordered
   design identities and changed allocation counts were accepted.

The H3 scale, direction, and probability-bound cases passed immediately as
characterization coverage of validation that was already present; no
production change was attributed to those tests.

### GREEN and regression evidence

Candidate validation now freezes the independent v1.3 module, donor,
accessions, audit status, evidence tier, registered mechanism parameter, H3
rule, and exact safety gates for each C1–C6 identity. C1 and C4 intentionally
share `na_efflux_vmax_multiplier` while retaining distinct donor, module,
evidence, and C4 cortex-localization identity. Synthetic scenarios reject both
missing and extra parameter names; extras raise structured
`UNREGISTERED_SYNTHETIC_PARAMETER`. Design validation freezes allocation
identity without embedding the configurable synthetic water chemistry values
in code.

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_paper1_contracts.py -q
```

Result: exit 0; 33 passed in 0.75s.

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -v
```

Result: exit 0; 129 passed in 1.97s. `git diff --check` returned exit 0 during
the focused verification pass.
