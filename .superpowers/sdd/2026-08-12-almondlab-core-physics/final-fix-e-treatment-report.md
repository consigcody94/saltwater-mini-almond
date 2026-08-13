# Final Core Fix E report — immutable treatment accounting

## Outcome

Implemented an ion-specific, density-aware reverse-osmosis and
remineralization API on the shared conservation ledger. RO now preserves water
mass and every represented stock by complementary subtraction, emits two
complete paired internal transactions, retains explicit model/version and
evidence metadata, and reports selective rejection only as a diagnostic whose
physical destination is the concentrate. Remineralization accepts only
formula-resolved water and stock additions and emits one typed external
amendment transaction per unique dose.

The result is a virtual accounting kernel. It does not establish plant or GMO
efficacy, seawater tolerance, greenhouse performance, or empirical validation.

## Owned files

- `src/almondlab/treatment.py`
- `tests/test_treatment.py`
- `tests/fixtures/ro_remineralization.yaml`
- `src/almondlab/resources/fixtures/ro_remineralization.yaml`
- `.superpowers/sdd/2026-08-12-almondlab-core-physics/final-fix-e-treatment-report.md`
- `.superpowers/sdd/2026-08-12-almondlab-core-physics/progress.md` (one ledger line)

Concurrent mass-balance implementation, mass fixtures/tests, verification,
public-data, and image changes were preserved and excluded from this task's
staging set.

## Shared prerequisite

The brief required treatment model/version metadata on the shared ledger, but
the original `LedgerEntry` had no such fields. A separately reviewed additive
prerequisite was completed test-first and committed as `508990c`:

```text
RED:   5 failed, 54 passed
GREEN: 59 passed
```

The later shared-contract review follow-up `1e1915c` added the required typed
internal water-flow metadata and external-boundary invariants. Treatment is
verified against that committed contract.

## TDD evidence

### Initial treatment RED

After writing the immutable public API tests and exact mirrored fixture, the
focused suite failed at collection because the new records did not exist:

```text
ImportError: cannot import name 'FormulaResolvedAmendment' from
'almondlab.treatment'
```

The first implementation run against the pre-follow-up shared contract then
produced `30 passed, 14 failed`; every failure was the expected missing
`LedgerEntry.internal_water_flow_kind` interface.

### Review-driven RED/GREEN cycles

- Derived density/water-mass and aggregate-overflow mutations: `44 passed,
  2 failed`; after stable numerical-boundary handling: `46 passed`.
- Audit-independence mutation (monkeypatched row generator): `1 failed` because
  the old audit self-validated; after direct equation/cursor/metadata
  reconstruction: the mutation and adversarial audit cases passed.
- Exact aggregate field-path mutations: volume case failed while water case
  passed; after separate handlers, both passed.
- The exact YAML test now pins every fixture literal independently and consumes
  every feed, parameter, expected RO, amendment, and final-product anchor. The
  packaged/test copies are byte-identical with SHA-256
  `47c6fe481b15565c3ee04b99a90fdbdb144869180b6f63660b4cac28f60eb8cb`.

### Final focused GREEN

```powershell
$env:UV_CACHE_DIR='C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\uv-cache'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_treatment.py -q -p no:cacheprovider --basetemp 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\pytest-treatment-final-focused'
```

```text
49 passed in 0.77s
```

### Shared-contract integration

```text
tests/test_contracts.py + tests/test_treatment.py
142 passed in 0.83s
```

### Relevant regression set

The CLI, schemas, chemistry, domains, hydraulics, contracts, treatment, and
Paper 1 contract tests were run together:

```text
337 passed in 2.26s
```

### Repository-wide compatibility check

The full repository command was run and stopped during collection at the known
concurrent mass/verification migration boundary:

```text
ImportError: cannot import name 'ExternalFlux' from 'almondlab.mass_balance'
1 error in 1.47s
```

`verification.py` is still importing the removed legacy mass API; Final Fix F
owns that migration after the mass and treatment commits. No verification file
was changed here to mask the incompatibility.

`python -m compileall` on the treatment module and `git diff --check` on every
owned implementation/test/fixture file both completed cleanly.

## Requirement audit

- All public records are frozen; caller mappings are copied into canonical
  enum order and exposed through mapping proxies; ledgers and dose collections
  are tuples.
- Every public number crosses `finite_float`; derived density, dose water mass,
  and `math.fsum` aggregates have stable structured overflow paths.
- WATER is excluded from dissolved-stock mappings. Canonical entity units come
  from the shared registry, including alkalinity as `mmol_c`.
- RO rejection keys must exactly cover feed stocks. EC/ECw/ECe/pore-water-EC
  aliases, string entities, missing/extra entities, and water rejection are
  refused.
- RO water, volume, and stock complements are constructed by subtraction.
  Rejection endpoints 0/1 and recovery values arbitrarily near the open 0/1
  boundaries are covered.
- Each RO branch uses one cursor ordinal and contains paired negative/positive
  rows in canonical water/entity order with aqueous-transfer, carrier,
  evidence, treatment-model, and version metadata.
- `audit_ro_ledger` independently derives split equations, branch rows,
  namespace IDs, signs, units, ordering, evidence, and metadata without calling
  the production row generator; deletion, duplication, mutation, and a
  systematically broken generator are rejected.
- Selective rejection is never posted as an additional loss. Its destination
  is the exact immutable concentrate stock mapping.
- Remineralization sorts unique dose IDs, aggregates with `math.fsum`, adds each
  already-resolved amount once, and issues one nonnegative external AMENDMENT
  transaction per dose. It performs no implicit formula expansion, reaction,
  charge balance, or invented sink/source.
- Conservative evidence composition is retained on streams, results, and
  ledger rows; mixed strong evidence weakens to `hypothesis_prior`, and
  synthetic evidence remains `synthetic_only`.
