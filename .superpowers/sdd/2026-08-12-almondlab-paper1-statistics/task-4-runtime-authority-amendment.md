# Paper 1 Task 4 runtime-authority amendment

**Status:** DRAFT FOR INDEPENDENT REVIEW; NOT APPROVED; NOT IMPLEMENTATION AUTHORITY

**Scope:** This document proposes one narrow amendment to the Task 4 preflight
start gate and closes the runtime assembly interfaces needed to enforce that
gate. It does not amend any scientific value, synthetic mechanism, physical
design, decision rule, evidence claim, or physical-use restriction.

**Prospective effect:** None unless and until the exact bytes of this document
are committed and independently receive both Spec APPROVED and Quality
APPROVED. Drafting, hashing, or reviewing this document is not approval.

## 1. Controlling authorities and precedence

The following approved authorities remain controlling:

1. Final Task 3 is committed at
   `d242473269803fa16461f78e8784813272912fbb`. The approved raw SHA-256
   values are:
   - `src/almondlab/design.py`:
     `9ae36381d59c641728c01e1e04ef4a9f1106fc02332c9b352e3e71bc3ebf15b9`
   - `tests/test_design.py`:
     `05565f4ac926809df35a1b9a8fac10404e27e0b0fdc8f01e1afbdd627bf5ffb3`
   - `tests/fixtures/paper1_small.yaml`:
     `beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6`
2. `task-4-prospective-registration-proposal.md` is independently approved
   at immutable registration commit `f200edd`, together with LF-portability
   commit `d5412a9`. Its approval is recorded in
   `task-4-registration-review-fix-report.md`.
3. The approved program specification, Paper 1 global constraints, Task 1
   and Task 2 approved APIs, the Task 4 preflight addendum, and final Task 3
   API retain their existing precedence except for the single explicit start
   gate exception in Section 2 below.

This amendment, if independently approved, controls only these five deltas:

- a discovery-only assembly/revalidation exception to the all-or-nothing
  Task 4 preflight start gate;
- the exact aggregate fields, supplied raw-authority bytes, hashes, and
  signatures required to retain validation authority;
- the registered discovery capacity outcomes that assembly must witness,
  including the one prospectively required structural rejection;
- error precedence at the absent-confirmation boundary; and
- an exact Task 4 wrapper around the existing Task 2 `CandidateEffects`
  constructor and `apply_candidate_effects` boundary.

No duplicated statement in this document displaces a scientific or physical
registration in the approved proposal. If text outside those five deltas
appears to conflict with an approved authority, the earlier approved
authority controls and implementation remains blocked.

## 2. Sole start-gate exception

After this amendment is independently approved, Task 4 may implement and
exercise only the following discovery-only runtime assembly boundary:

- `CohortDesignBundle` construction and canonical revalidation;
- `Paper1SimulationConfig` construction and canonical revalidation with both
  `confirmation_config` and `confirmation_design` exactly `None`;
- deterministic replay of the already registered Task 3 discovery allocation
  at root seed `20260812`, solely to compare its canonical manifest with the
  supplied manifest; and
- pure validation, hashing, capacity derivation, and immutable-copy checks
  that create no outcome data and write no files; and
- pure derivation and authentication of the already registered nominal forcing
  artifact from the retained scenario and recipe authorities, without RNG.

This narrowly supersedes the statement in the Task 4 preflight addendum that
no Task 4 implementation may enter GREEN before a confirmation bundle exists.
It supersedes that statement only for the two assembly/revalidation objects
and functions frozen in Sections 3 and 4, and only while the confirmation pair
is exactly absent.

This amendment does **not** authorize:

- production selection or construction of a new random seed or allocation;
- Task 4 synthetic outcome RNG, discovery outcome generation, or outcome
  simulation of any kind;
- calibration, root solving, fit/holdout use, or candidate ranking;
- selection, construction, validation as production authority, or generation
  of a confirmation family;
- tournament assembly or a one-shot discovery/confirmation wrapper;
- run-directory creation, package/resource mutation, or any filesystem output;
- manuscript, efficacy, safety, containment, regulatory, or physical-use
  claims; or
- physical preparation of either registered water recipe.

The deterministic Task 3 replay permitted above is not authority to choose a
seed. Any production replay other than the frozen discovery inputs is outside
this exception. Reject-only adversarial Task 3 objects created inside the test
harness under Section 11 are not production replay and confer no authority.
The mandatory registered replay necessarily constructs Task 3's
`SeedSequence`/`PCG64` machinery; it is the sole production RNG activity
authorized by this amendment. Every temporal RNG statement below refers
specifically to **Task 4 outcome-generation RNG**, after the mandatory
frozen-manifest replay.

## 3. Cohort bundle boundary

The bundle retains the exact five fields already frozen by the preflight
addendum. It deliberately does not contain a caller-authored design config,
registration flag, pass flag, or result hash:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class CohortDesignBundle:
    cohort_id: Literal["discovery", "confirmation"]
    baseline_roster: BaselineRoster
    position_map: PositionMap
    manifest: RandomizationManifest
    audit: ExperimentalUnitAudit
```

The contract-repair plan's external `config` parameter supplies the authority
needed to derive `ExperimentalUnitSpec` and independently recompute the audit.
The exact public signatures are:

```python
def assemble_cohort_design_bundle(
    *,
    cohort_id: Literal["discovery", "confirmation"],
    config: Paper1DesignConfig | ConfirmationDesignConfig,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
    manifest: RandomizationManifest,
    audit: ExperimentalUnitAudit,
) -> CohortDesignBundle: ...

def revalidate_cohort_design_bundle(
    value: object,
    *,
    config: Paper1DesignConfig | ConfirmationDesignConfig,
) -> CohortDesignBundle: ...
```

The union annotations are deliberately future-facing, but the current runtime
role behavior is exact:

- `cohort_id == "discovery"` requires
  `type(config) is Paper1DesignConfig`;
- `assemble_cohort_design_bundle(cohort_id="confirmation", ...)` fails
  `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` before reading or canonicalizing
  `config`, roster, map, manifest, or audit;
- `revalidate_cohort_design_bundle` first requires an exact outer
  `CohortDesignBundle` and an exact primitive `cohort_id`; when that role is
  `"confirmation"`, it raises the same registration-required error before
  reading `config` or any nested family value; and
- subclasses, proxy objects, `isinstance`-only surrogates, booleans in integer
  fields, and mutated frozen objects are rejected.

The current successful boundary is discovery-only. It reconstructs the config,
roster, position map, manifest, and audit into detached base objects through
the final Task 3 APIs. It derives the cohort identity set, derives
`ExperimentalUnitSpec.from_design`, and calls
`revalidate_experimental_unit_audit` with the canonical manifest records and
derived spec. For the registered discovery bundle, it also reruns
`randomize(config, manifest.root_seed, baseline_roster=..., position_map=...)`
and requires byte-for-byte equality of canonical manifests.

A generic mechanically valid **discovery** `CohortDesignBundle` may pass this
generic mechanical bundle boundary; that success is not a prospective
registration. The generic boundary does not replay an alternate allocation or
promote it. Only the exact registered discovery seed, config, roster, map,
manifest, audit, and hashes in Sections 7 and 8 may pass
`Paper1SimulationConfig` assembly/revalidation. A mechanically self-consistent
alternate discovery bundle therefore fails at the aggregate authority boundary.
No confirmation bundle may pass the current generic boundary.

## 4. Paper 1 simulation assembly boundary

The aggregate must retain every typed authority required for later canonical
revalidation. Retaining these objects avoids hidden package loads and avoids
changing the approved future generation signatures merely to recover omitted
authority.

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Paper1SimulationConfig:
    design: Paper1DesignConfig
    candidates: CandidateRegistry
    candidate_effects: Mapping[str, CandidateEffects]
    model_domain: ModelDomain
    water_recipes: Paper1WaterRecipeRegistry
    scenario_registry: SyntheticScenarioRegistry
    stop_policy: Task4StopPolicy
    discovery_design: CohortDesignBundle
    confirmation_config: ConfirmationDesignConfig | None
    confirmation_design: CohortDesignBundle | None
    generator: SyntheticGeneratorConfig
    config_sha256s: Mapping[str, str]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]
```

The exact public signatures are:

```python
def assemble_paper1_simulation_config(
    *,
    design: Paper1DesignConfig,
    candidates: CandidateRegistry,
    candidate_effects: Mapping[str, CandidateEffects],
    model_domain: ModelDomain,
    water_recipes: Paper1WaterRecipeRegistry,
    scenario_registry: SyntheticScenarioRegistry,
    stop_policy: Task4StopPolicy,
    discovery_design: CohortDesignBundle,
    confirmation_config: ConfirmationDesignConfig | None,
    confirmation_design: CohortDesignBundle | None,
    raw_authority_bytes_by_name: Mapping[str, bytes],
) -> Paper1SimulationConfig: ...

def revalidate_paper1_simulation_config(
    value: object,
) -> Paper1SimulationConfig: ...
```

`generator` is derived internally and must equal the canonically reconstructed
`scenario_registry.anchor.generator`. No independent generator argument is
accepted. `evidence_label` is synthesized internally as
`EvidenceLabel.SYNTHETIC_ONLY`; no caller supplies or promotes it.

The factory and revalidator require exact base types, canonically reconstruct
all Pydantic and dataclass inputs, detach every tuple and mapping, validate the
active water recipes against the discovery design and `core_v1` domain with
`physical_use=False`, verify the scenario registry's normalized recipe digest,
verify the exact scenario and sensitivity inventories, and verify every raw
and canonical authority in Section 8. The returned `candidate_effects` and
`config_sha256s` are `MappingProxyType` instances over new dictionaries.

The factory derives the exact `paper1_nominal_forcing_schedule_v2` payload
purely from the retained scenario registry's two ordered 168-step forcing
schedules and the retained active recipe identities. It authenticates that
336-record payload against
`329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96`
through the registered nominal-forcing boundary. This derivation creates no
RNG and accepts no caller-supplied forcing artifact or forcing hash. Primary
fit/holdout and S031 calibration-panel artifacts are not inputs to this
discovery-only aggregate; their `CalibrationForcingPanelBundle` boundaries
remain the separate authority of the approved calibration interface.

Direct dataclass construction is never evidence that the factory ran. Every
public consumer must first call `revalidate_paper1_simulation_config`; an outer
subclass or a direct object whose retained authorities, normalized hashes, or
frozen raw-hash entries disagree is rejected.

The factory performs the registered discovery nominal and every registered
water-loop one-at-a-time shared-source capacity derivation with the retained
stop policy, recipe registry, manifest authorities, and generator water-loop
values. It must obtain the exact outcomes below for each of the four registered
discovery water-batch identities:

| Authority and selected value | Required aggregate debit per batch | Required result |
|---|---:|---|
| nominal | 3,606.00 L | four passing audits |
| S013 `100.0` / `140.0` | 3,526.00 / 3,686.00 L | four passing audits for each value |
| S014 `0.50` | 5,420.40 L | exact registered `WATER_BATCH_CAPACITY_EXCEEDED` rejection |
| S014 `0.90` | 1,791.60 L | four passing audits |
| S015 `0.40` / `0.80` | 2,698.80 / 4,513.20 L | four passing audits for each value |
| S016 `0.60` / `2.40` | 3,404.40 / 4,009.20 L | four passing audits for each value |
| S017 `0.025` / `0.100` | 3,605.40 / 3,607.20 L | four passing audits for each value |
| S036 `0.00` / `0.30` | 3,202.80 / 3,303.60 L | four passing audits for each value |

The S014 `0.50` rejection is a prospectively registered structural outcome of
preflight, not an aggregate-assembly failure. Assembly catches only that exact
`AlmondLabError` identity:

```text
code: WATER_BATCH_CAPACITY_EXCEEDED
field_path: manifest.records
details: {
  "cohort_id": "discovery",
  "water_batch_id": "disc-r1-w1-water-batch",
  "aggregate_expected_debit_l": 5420.4,
  "capacity_l": 5000.0,
}
```

The details mapping has exactly those four primitive key/value pairs, with no
missing or additional key. The registered manifest and sorted capacity
preflight make `disc-r1-w1-water-batch` the deterministic first failing batch;
the other three registered batches have the same prospectively registered
per-batch debit but produce no passing audit after this structural exception.
Only after matching the complete identity above may assembly record no physical
or outcome artifact and continue validation. If S014 `0.50` instead passes,
reports another code, field path, detail key, debit, capacity, cohort, or batch,
or fails after Task 4 outcome-generation RNG or filesystem output, assembly
fails `PAPER1_CONFIG_AUTHORITY_MISMATCH` at
`scenario_registry.sensitivities.S014_return_fraction`. Every unexpected
capacity failure for nominal or another registered value remains fatal and its
existing capacity error passes through unchanged. S033 changes only an
unregistered future confirmation cell size and does not enter discovery
capacity ingress. The other non-water-loop sensitivities receive complete
registry/path validation but do not trigger a capacity calculation because
they cannot change a shared-source debit.

These are pure preflight calculations. They do not authorize a physical batch,
outcome generation, or output.

## 5. Confirmation pairing and error precedence

The current `CohortDesignBundle` confirmation boundary is fail-closed even
though its type union is retained for a future amendment. Its exact error is:

```text
code: CONFIRMATION_DESIGN_REGISTRATION_REQUIRED
field_path: cohort_id
message: confirmation design requires separately approved registration
details.required_authority: task4_registered_confirmation_cohort_bundle
```

For assembly, the primitive `cohort_id == "confirmation"` discriminator causes
that error before any access to the supplied config or family objects. For
revalidation, exact outer-bundle and primitive-role checks occur first; an exact
confirmation role then causes that error before config or nested-family access.
This is not an invalid role/config-pair error and must not be collapsed to
`COHORT_DESIGN_INVALID`.

The pairing invariant is exact:

| `confirmation_config` | `confirmation_design` | Result |
|---|---|---|
| `None` | `None` | Legal discovery-only assembly/revalidation |
| `None` | non-`None` | Fail `PAPER1_SIMULATION_CONFIG_INVALID` |
| non-`None` | `None` | Fail `PAPER1_SIMULATION_CONFIG_INVALID` |
| non-`None` | non-`None` | Fail `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` until a later authority is approved |

For an incomplete pair, the error has field path `confirmation_design` and
message `confirmation config and design must be absent or present together`.

For a complete but presently unregistered pair, the error is raised before
inspecting, canonicalizing, or revealing anything about the proposed family:

```text
code: CONFIRMATION_DESIGN_REGISTRATION_REQUIRED
field_path: confirmation_design
message: confirmation design requires separately approved registration
details.required_authority: task4_registered_confirmation_cohort_bundle
```

The same registration-required error is mandatory if a future public
confirmation-generation or one-shot tournament boundary is called with a
discovery-only config. The existing capacity-specific
`WATER_BATCH_CONFIRMATION_AUTHORITY_UNAVAILABLE` remains correct for a direct
attempt to preflight an unregistered confirmation water batch; this amendment
does not rename or weaken it.

Other wrapper error semantics are frozen as follows:

| Condition | Error code | Field path |
|---|---|---|
| Non-exact bundle, invalid role/config pair, or canonical replay disagreement | `COHORT_DESIGN_INVALID` | Narrowest `cohort_id`, `config`, or `manifest` path |
| Non-exact aggregate or incomplete confirmation pair | `PAPER1_SIMULATION_CONFIG_INVALID` | Narrowest aggregate field |
| Frozen raw, normalized, or discovery literal mismatch | `PAPER1_CONFIG_AUTHORITY_MISMATCH` | Exact logical resource or discovery field |
| Current confirmation bundle request | `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` | `cohort_id` |
| Complete aggregate confirmation pair without registration | `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` | `confirmation_design` |

Errors raised by final Task 3 and existing Task 1/2 contract boundaries are
not collapsed. Their existing codes, including `DESIGN_CONFIG_INVALID`,
`DESIGN_INPUT_INVALID`, `RANDOMIZATION_INVALID`,
`EXPERIMENTAL_UNIT_INVALID`, `COHORT_IDENTITY_INVALID`,
`COHORT_IDENTITY_REUSE`, `CANDIDATE_PARAMETER_VIOLATION`, and the recipe,
scenario, domain, and capacity codes, pass through unchanged.

## 6. CandidateEffects wrapper authority

No Task 4 code may call the private Task 2 `_canonical_effects` helper or rely
on its `isinstance` check. This amendment authorizes one private Task 4 wrapper
with the following exact behavior; it does not create a second scientific
candidate-effect registry:

1. Require the containing C1-C6 mapping to have exact runtime type `dict` or
   `type(MappingProxyType({}))`. Require primitive string keys in the exact
   iteration order `("C1", "C2", "C3", "C4", "C5", "C6")`; missing,
   additional, reordered, subclassed, lazy, or custom mappings are rejected.
2. Require `type(value) is CandidateEffects` for every value, and require each
   containing key to equal the value's `candidate_id`.
3. Require exact primitive `candidate_id` and `schema_version` strings, exact
   `EvidenceLabel`, and an exact `MappingProxyType` parameter mapping. Require
   every parameter key to have exact type `str` and every already-normalized
   parameter value to have exact type `float`; booleans, integers, non-finite
   values, subclasses, and custom numeric objects are rejected.
4. Copy the parameter mapping into a new plain `dict` and construct a new base
   `CandidateEffects` instance from the four declared fields so the approved
   Task 2 validation runs again. All ordinary access, iteration, copy, and
   constructor failures—including hostile mapping behavior—are caught as
   `Exception` (never `BaseException`) and normalized to
   `CANDIDATE_PARAMETER_VIOLATION` at the narrowest candidate-effect field.
   Existing `AlmondLabError` values from the public Task 2 boundary pass
   through unchanged.
5. Compute the complete ordered C1-C6 normalized payload from the reconstructed
   base instances. A structurally valid but altered effect registry fails
   `PAPER1_CONFIG_AUTHORITY_MISMATCH` at
   `fixtures/candidate_effects.yaml:normalized_sha256` before mechanism
   application unless its digest is exactly
   `0d5b62381409a3ed814b4687291e7f4c4c987c8d84db63353b85c11789fe25e8`.
6. Only after that normalized authority matches, call public
   `apply_candidate_effects` for every reconstructed effect and matching
   canonical `CandidateSpec` against the canonical anchor biology parameters.
   This proves candidate ID, registered primary mechanism, and isolation
   compatibility without copying Task 2's private mechanism table.
7. Return only reconstructed base instances in a new `MappingProxyType`.

Structural subclass, hostile mapping, invalid `object.__setattr__`, shared
mapping, non-finite, boolean, omitted-key, extra-key, wrong-candidate, and
wrong-primary attempts fail `CANDIDATE_PARAMETER_VIOLATION`. By contrast, a
`dataclasses.replace` or `object.__setattr__` change that still produces an
exact base `CandidateEffects` with structurally valid finite registered fields
is unregistered value drift: reconstruction may succeed, but the aggregate
must reject it with the normalized-hash authority error above. A same-value
reconstruction is detached and accepted; provenance is established by exact
canonical content, not by object identity.

If an independent reviewer rejects this wrapper as an ownership violation,
production remains blocked until the Task 2 owner instead approves and exposes
an exact public `revalidate_candidate_effects(value: object) ->
CandidateEffects` boundary. Implementation must not silently choose between
those alternatives.

## 7. Registered discovery binding

The approved Task 3 source authority remains immutable:

| Authority | SHA-256 or value |
|---|---|
| Final Task 3 commit | `d242473269803fa16461f78e8784813272912fbb` |
| Task 3 discovery fixture raw | `beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6` |
| Task 3 discovery root seed | `20260812` |

The following active-design binding is a **draft snapshot, not effective
registration**. Every value in this table must be recomputed from the final
committed authoring and packaged bytes, copied into the final amendment review
record, and independently re-frozen before production implementation:

| Discovery binding | Draft snapshot value |
|---|---|
| Active `configs/experiment_paper1.yaml` raw | `a40c28829c4ca3dadb3a87a3f6e8731b73ab9d38a53f2dae9b4c26657ac8ab18` |
| Active design normalized | `f5911a6a63d7444575c2013d9737b9219ef21fb1f5c58dcc5fd633bcde38f5c9` |
| Baseline roster canonical | `f34dc944bf951fc8c2f752d981433482d475a4c4f3091e6d8d8f2e7d0df719d8` |
| Position map canonical | `fed49c40785388661b46a0ee5c174617e39230fac80171677cfdcca9b9d9cbea` |
| Allocation SHA-256 | `bd4cb366ac9c3144ab881af29615311839f1fc0a9a881645ba4995dcab7b7c3f` |
| Manifest canonical SHA-256 | `dea12ab75748223c01e24accbe92eca153a7da90aa3b1235294e75699ad7516f` |

The active design intentionally differs from the archived Task 3 config only
by the prospectively migrated water chemistry. The approved physical Task 3
roster, map, seed, and allocation identity remain unchanged. A mutually
self-consistent regeneration with seed `0`, `1`, or `20260813`, temperature
`298.16 K`, alternate same-count IDs, or altered raw source bytes is not the
registered discovery authority and must fail closed.

## 8. Raw inputs and config hash inventory

`raw_authority_bytes_by_name` has exactly this package-logical key set, with no
absolute paths, drive letters, backslashes, aliases, missing keys, or extras:

```python
{
    "configs/candidates.yaml",
    "configs/experiment_paper1.yaml",
    "configs/model_domains.yaml",
    "configs/paper1_task4_stop_policy.yaml",
    "configs/paper1_water_recipes.yaml",
    "configs/synthetic_scenarios.yaml",
    "fixtures/candidate_effects.yaml",
    "fixtures/paper1_small.yaml",
}
```

Each key has exact type `str`; each value has exact type `bytes`.
`bytearray`, `memoryview`, subclasses, path-like keys, and lazy/custom mapping
surrogates are rejected. The outer mapping has exact type `dict` or exact type
`MappingProxyType`; subclasses and all other `Mapping` implementations are
rejected. The factory hashes the bytes supplied at this boundary; it never
records a host filesystem path. In particular, the supplied
`fixtures/paper1_small.yaml` bytes must hash exactly to the approved Task 3
source authority before the discovery bundle or any capacity result can enter
the aggregate.

`Paper1SimulationConfig` retains the fixture's raw digest, not its complete
source bytes. Revalidation checks that pinned digest together with the exact
typed roster, map, seed, allocation, manifest, and Task 3 input hashes. It must
not reopen an authoring path or read `almondlab.resources` to recover source
authority. The currently visible package-resource read inside the discovery
capacity canonicalizer must therefore be removed by the narrowly coordinated
prerequisite change in Section 11; raw-source verification moves to this
aggregate boundary and is not duplicated inside arithmetic preflight.

`config_sha256s` has exactly the following 16 immutable keys:

```text
configs/candidates.yaml:raw_sha256
configs/candidates.yaml:normalized_sha256
configs/experiment_paper1.yaml:raw_sha256
configs/experiment_paper1.yaml:normalized_sha256
configs/model_domains.yaml:raw_sha256
configs/model_domains.yaml::core_v1:normalized_sha256
configs/paper1_task4_stop_policy.yaml:raw_sha256
configs/paper1_task4_stop_policy.yaml:normalized_sha256
configs/paper1_water_recipes.yaml:raw_sha256
configs/paper1_water_recipes.yaml:normalized_sha256
configs/synthetic_scenarios.yaml:raw_sha256
configs/synthetic_scenarios.yaml:normalized_sha256
fixtures/candidate_effects.yaml:raw_sha256
fixtures/candidate_effects.yaml:normalized_sha256
fixtures/paper1_small.yaml:raw_sha256
paper1_nominal_forcing_schedule_v2:canonical_sha256
```

All values are lowercase 64-character hexadecimal SHA-256 strings computed by
the factory; callers do not supply a result hash or pass flag. Normalized
digests are SHA-256 over `canonical_json_bytes` of the canonically
reconstructed typed payload. Candidate effects use an exact C1-C6 mapping of
the four declared fields; the model-domain normalized digest covers the
selected `core_v1` `ModelDomain`; scenario normalization covers the complete
typed `SyntheticScenarioRegistry`. The fixture entry is the SHA-256 of the
exact supplied Task 3 source bytes. The nominal-forcing entry is the canonical
SHA-256 of the derived 336-record artifact described in Section 4, not a raw
file hash and not a calibration-panel hash.

The following hash inventory is also a **draft snapshot, not effective
registration**. It must be recomputed and independently re-frozen after the
final implementation-prerequisite commit and exact authoring/package mirror
review:

| Logical authority | Draft raw SHA-256 | Draft normalized/canonical SHA-256 |
|---|---|---|
| `configs/candidates.yaml` | `f4eb6c496ddfce2fb7077db34a03e6836da2cd4c62ad21d504b0227a277c5a05` | `4e401c13ebfd97544a7f5bf7e7c967637dbf8329f0650dae7676c4656968f0ca` |
| `configs/experiment_paper1.yaml` | `a40c28829c4ca3dadb3a87a3f6e8731b73ab9d38a53f2dae9b4c26657ac8ab18` | `f5911a6a63d7444575c2013d9737b9219ef21fb1f5c58dcc5fd633bcde38f5c9` |
| `configs/model_domains.yaml` / `core_v1` | `0cac0e90c7746e4897f760d2ff87a57d2ddceb175690d51be1beb31f41719411` | `f6e80805ac05a2059baae3e9a05dab1c89b988911b34a366a46249bb9fac8ee0` |
| `configs/paper1_task4_stop_policy.yaml` | `03e07ee719e5e376e9c03202be945c6b02d77a7373a3bdb164d5c08f7427ee34` | `94c1aee1bc6b5547973e29d201373dfbe2f545ec694ac5dc9b836b40fa0127a9` |
| `configs/paper1_water_recipes.yaml` | `d46a0e4dc02cd74cfa5b4f437f367009301d4aab8cad9a1115ec6be37afa24d3` | `8a902441d143017fddfddf5b174302187dd8da1d9a46f98af9a94d18e317b1bd` |
| `configs/synthetic_scenarios.yaml` | `fdc7b4068d80a9d5e42f7c2c5322d7a79b076951b1cccc3ba674af91a53d56d6` | `4229e855bcf783d994ce24f6dc98d1dc8eded92f5134f854880cb44204f6150a` |
| `fixtures/candidate_effects.yaml` | `4e92c1567227b9e1f6e0713b79890bfc652a5b21a8de013769eaaa01ac939c21` | `0d5b62381409a3ed814b4687291e7f4c4c987c8d84db63353b85c11789fe25e8` |
| `fixtures/paper1_small.yaml` | `beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6` | not a separate normalized entry; roster/map/manifest canonical hashes are frozen in Section 7 |
| `paper1_nominal_forcing_schedule_v2` | not a raw file | `329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96` |

The scenario loader's separately frozen canonical source-mapping digest
`36033d8d58b65cc5647c0139ba4bebf92250cf9d8a7c08eba81f54b89ea10e51`
remains an existing scenario-contract check. It is not an additional
`config_sha256s` entry and is not redefined here. It also does not replace the
separately required nominal-forcing entry.

## 9. Cross-object invariants

Assembly/revalidation requires all of the following without trusting a caller
boolean or digest:

- discovery design, candidate registry, C1-C6 effects, `core_v1` domain,
  recipe registry, scenario registry, stop policy, and discovery bundle are
  exact, detached canonical base objects;
- candidate-effect mapping keys and candidate IDs agree, and each effect is
  compatible with the matching candidate's registered primary parameter;
- the active design's two water records canonically equal the active recipe
  registry records;
- `validate_active_paper1_water_recipes` succeeds with
  `physical_use=False`; `physical_use=True` remains blocked;
- the scenario registry's recipe-registry digest equals the normalized recipe
  authority;
- the retained generator equals the anchor scenario's canonical generator;
- the exact supplied Task 3 fixture bytes hash to the Section 7 raw-source
  authority without a package or filesystem read during revalidation;
- the retained scenario schedules and recipe identities derive and
  authenticate the exact nominal-forcing canonical hash;
- the exact registered scenario and 36-record sensitivity inventories remain
  complete;
- nominal and all eleven non-structural-failure registered discovery
  water-loop sensitivity values return the exact passing audits in Section 4;
- S014 `0.50` produces exactly the registered structural capacity rejection in
  Section 4 before Task 4 outcome-generation RNG or filesystem output, which
  assembly witnesses and does not mislabel as a successful sensitivity run;
  and
- the discovery bundle revalidates against `design` and the frozen discovery
  source, root seed, roster, map, allocation, manifest, and input hashes.

When a future, separately approved confirmation registration exists, config
assembly must revalidate each cohort audit independently with its own design
config/spec, then call final Task 3 `validate_cohort_separation` on the two
canonical roster/map/manifests. It must not pass two cohort sets to a
single-cohort audit, because Task 3 requires supplied cohort IDs to correspond
exhaustively to that audit's records. The later review must prove disjoint
plant, physical transformation-batch, reservoir, water-batch, run, and
non-null transformation-event IDs, plus strictly later confirmation run
ordinals and distinct Task 3 manifest seeds. This paragraph defines the future
check but does not authorize a confirmation family now.

## 10. Explicit confirmation fail-closed boundary

No externally selected confirmation candidate family, primary N=6 config,
new-material roster, position map, manifest, audit, root seed, or complete hash
authority is approved at the time of this draft. Therefore:

- no non-`None` confirmation pair can be returned by
  `assemble_paper1_simulation_config`;
- no copied, subclassed, structurally valid, or test-generated confirmation
  object can substitute for registration;
- no same-count alternate identity family can substitute for exact physical
  identity authority; and
- no Task 4 discovery result can select or manufacture the missing family.

A future confirmation amendment must independently freeze, at minimum: one to
four externally selected C1-C6 IDs in registered order plus `empty_vector`;
the primary cell size of exactly six; the exact `ConfirmationDesignConfig`;
new-material roster/map/manifest/audit bytes and canonical hashes; root seed;
allocation and manifest hashes; input hash mapping; all six physical identity
namespaces; later run ordinals; shared-source capacity results; and exact
authoring/package resource bytes. Until that amendment is committed and
independently approved, `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` is the
only production result for a complete confirmation pair.

## 11. Required TDD and adversarial review

After this amendment is independently approved and the documentation alignment
in Section 12 is complete, runtime assembly implementation is owned by new
`src/almondlab/simulate.py` and `tests/test_simulate.py`. One coordinated
prerequisite change is additionally authorized in
`src/almondlab/paper1_contracts.py` and the existing recipe/capacity tests: the
discovery capacity canonicalizer must stop reading
`almondlab.resources/fixtures/paper1_small.yaml` and must rely on its already
frozen typed config, roster, map, manifest, seed, allocation, and canonical
input-hash checks. The aggregate factory alone hashes the supplied Task 3 raw
fixture bytes, and aggregate revalidation uses the retained digest. That
coordinated edit may not change capacity arithmetic, water-loop identities,
error codes, confirmation blocking, sensitivity bindings, or any scientific
value.

No other change to Task 3, approved proposal bytes, existing contract modules,
configs, fixtures, or package resources is authorized by this amendment.
Every prerequisite package mirror and authoring resource must land and receive
its own review before implementation begins.

The implementation review must show this exact progression:

1. Import RED for `CohortDesignBundle`, `Paper1SimulationConfig`,
   `assemble_cohort_design_bundle`, `revalidate_cohort_design_bundle`,
   `assemble_paper1_simulation_config`, and
   `revalidate_paper1_simulation_config`.
2. Signature/field RED tests pin the exact definitions in Sections 3 and 4.
3. The approved discovery fixture produces exactly 720 biological units and
   16 run-qualified water loops, round-trips canonically, and returns detached
   objects.
4. Tests reject subclasses and structurally invalid `object.__setattr__`,
   `model_copy(update=...)`, and `dataclasses.replace` corruption at every
   nested boundary. Candidate-effect tests separately prove that structurally
   valid altered base values fail the normalized authority digest with the
   exact Section 6 code and field path.
5. Aggregate tests reject stale root seed, config, roster, map, allocation,
   manifest, and raw-source hashes; seeds `0`, `1`, and `20260813`; a
   regenerated `298.16 K` design; relabeled water/run/batch/event IDs;
   same-count alternate IDs; and omitted or added plants/slots. A generic
   mechanically valid discovery bundle may pass the generic bundle boundary,
   but none of these alternates may pass aggregate assembly/revalidation.
   Alternate-seed or regenerated manifests created by the test harness are
   reject-only Task 3 adversaries: they are never returned, persisted, or
   treated as Task 4 production authority, and do not authorize production
   selection of another seed or allocation.
6. Audit tests prove that counts and checks are recomputed from canonical
   records/spec rather than trusted from the caller.
7. Candidate tests reject missing/extra/reordered/miskeyed C1-C6 effects,
   subclasses, non-exact or hostile outer/parameter mappings, shared mutable
   parameter mappings, nonprimitive keys or values, booleans, integers,
   non-finite values, candidate mismatch, and primary-mechanism mismatch with
   `CANDIDATE_PARAMETER_VIOLATION`. Separate cases mutate an exact base effect
   to another structurally valid finite value and require
   `PAPER1_CONFIG_AUTHORITY_MISMATCH` at
   `fixtures/candidate_effects.yaml:normalized_sha256` before mechanism
   application.
8. Raw-authority tests pin the exact eight-key set and reject missing/extra
   keys, path aliases, non-string keys, `bytearray`, `memoryview`, subclasses,
   raw/normalized swaps, and one-byte mutations. They prove the Task 3 fixture
   raw digest is retained while neither aggregate revalidation nor capacity
   preflight reads a package resource or host path.
9. Registry tests reject design/recipe mismatch, scenario/recipe digest
   mismatch, incomplete/extra scenario or sensitivity records, generator
   divergence from the anchor, stop-policy drift, model-domain drift, and a
   nominal-forcing payload or canonical hash mismatch. They prove nominal
   derivation is pure and uses no fit/holdout bundle or RNG.
10. Confirmation precedence tests prove: both aggregate fields absent succeeds;
    one absent fails `PAPER1_SIMULATION_CONFIG_INVALID`; both present fail
    `CONFIRMATION_DESIGN_REGISTRATION_REQUIRED` before family inspection.
    Bundle tests additionally prove that confirmation assembly and exact-outer
    revalidation fail the same code at `cohort_id`, with only
    `details.required_authority ==
    "task4_registered_confirmation_cohort_bundle"`, before config or nested
    family access. The future-facing union itself does not authorize success.
11. Mapping-mutation tests prove that mutating caller-owned inputs after
    assembly cannot alter the result.
12. Import-order tests load `almondlab.design`,
    `almondlab.paper1_contracts`, and `almondlab.simulate` in both relevant
    orders and prove no import cycle. `simulate.py` may import Task 3 and
    contract modules; neither module may import `simulate.py`.
13. Capacity-outcome tests pin all Section 4 nominal and water-loop sensitivity
    debits. They prove S014 `0.50` is witnessed as the exact registered
    structural rejection while assembly continues. The accepted exception must
    have code `WATER_BATCH_CAPACITY_EXCEEDED`, field path `manifest.records`,
    and exactly the four registered detail key/value pairs in Section 4. Any
    altered code, path, detail key, cohort, batch, debit, capacity, unexpected
    failure, or unexpected S014 pass fails
    `PAPER1_CONFIG_AUTHORITY_MISMATCH` at
    `scenario_registry.sensitivities.S014_return_fraction` before Task 4
    outcome-generation RNG or filesystem output.

Task 3's approved confirmation mechanical tests remain the oracle for one to
four candidates plus empty vector, N=5/N=6 formulas, 12 water loops, later run
ordinals, balanced physical batches, and zero leftovers. This amendment does
not authorize copying those test-generated families into a Task 4 production
config or injecting a test-only registration switch.

Focused review must run `tests/test_simulate.py`, then the final Task 3 suite
and the Task 4 contract, recipe/capacity, scenario, forcing, and package
resource suites. A timeout, skipped authority test, test-only bypass, or
partial run is not a GREEN result.

## 12. Approval and documentation sequence

The required sequence is strict:

1. Finish and independently review the implementation-prerequisite commits
   that own the active scenario/forcing authorities and every exact
   authoring/package resource mirror. At the time of this draft, those
   authorities and mirrors are not all committed and this condition is not
   satisfied; no hash snapshot below is immutable merely because it currently
   recomputes.
2. Recompute every draft snapshot hash in Sections 7 and 8 from those final
   committed bytes and record the commands and results in a review note.
3. Before freezing this amendment, add the exact repository attribute
   `/.superpowers/sdd/2026-08-12-almondlab-paper1-statistics/task-4-runtime-authority-amendment.md text eol=lf`
   in a separately reviewed prerequisite change. Recompute the amendment's raw
   SHA-256 from the resulting LF-only UTF-8 bytes. This draft requests that
   future rule but does not itself modify `.gitattributes`.
4. Review this amendment read-only against the immutable Task 3 commit and
   approved Task 4 registration. Any substantive finding returns the amendment
   to DRAFT.
5. Commit the exact reviewed amendment bytes separately from production code.
6. Obtain fresh independent Spec and Quality verdicts against that immutable
   amendment commit. Record its raw SHA-256 and commit ID.
7. Only after both verdicts are APPROVED, align the Task 4 preflight addendum's
   start-gate/interface text and the contract-repair plan's Sections 3.2 and
   10 with this amendment. Those documentation changes require their own diff
   review.
8. Do not rewrite the already approved
   `task-4-prospective-registration-proposal.md` or
   `task-4-registration-review-fix-report.md`. The later alignment documents
   must reference the approved amendment commit instead.
9. Only after the alignment review may the narrowly coordinated capacity
   resource-read removal in Section 11 and `src/almondlab/simulate.py` /
   `tests/test_simulate.py` enter TDD implementation.

No checkbox, signature, hash, or prose in this draft self-approves a step. The
document is ready for a fresh read-only review only after its byte-level audit
is reported; it remains non-authoritative until the sequence above completes.
