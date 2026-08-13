# Task 4 prospective-registration review repair report

**Status:** second-review findings repaired; awaiting a new independent read-only re-review
**Scope:** documentation/registration only; no production/config/test edit,
outcome generation, mechanism calibration, stage, or commit
**Evidence:** all choices remain `hypothesis_prior`; materialized schedules and
forcing panels remain `synthetic_only`

Repaired proposal SHA-256:
`646d61edbbec8d996977e18e560c4966ebfdb799bc34b68a0d20170bb05b7419`.

Final approved Task 3 dependency commit:
`d242473269803fa16461f78e8784813272912fbb`.

## Finding closure matrix

| Finding | Substantive repair location |
|---|---|
| C1 shared Task 3 batch identity/capacity | proposal §§20.3.1–20.3.3 preserve the existing IDs, group all debits by unique `(cohort_id, water_batch_id)`, register one 5,000-L inventory, and preflight four discovery or six confirmation loops jointly. Exact aggregate debit/remaining: 3,606.00/1,394.00 L; 4,048.20/951.80 L; 3,594.60/1,405.40 L. No rollover/runtime/shadow loop batch is allowed. |
| C2 event/sample/source-debit recurrence | §20.3.3: samples d0/14…70 precede the operator and are restored by `M=V0-(V_event_start-I+R-P)`; d84 is terminal and not a source debit. Exact per-loop source totals are 901.50, 674.70, and 599.10 L. Every literal 120 closure term is replaced by registered `V0`, including S013. |
| C3 chemistry key | §20.4.2: `M_ion`/`M_B` keyed once to `(cohort_id, water_batch_id)` and used in every feed/initial-state transaction |
| C4 generic 4-mM stop | §20.5.1: `paper1_task4_stop_policy@1.0.0`, exact analyte × compartment × phase set, root/tissue rule preserved, feed governed separately |
| C5 panel dimension/API | §§20.9.1–20.9.3: explicit `K`-panel bundle, two waters, 168 steps; primary requires `K=64`, S031 alone admits registered 32/128 prefixes. Runtime `canonical_sha256` authenticates the exact artifact payload that omits the hash field, preventing self-reference. |
| C6 B04/B20 schemas underdefined | §§20.8/20.9.3: exact outer/record/nested keys and types, full first records, order/canonicalization, regenerated hashes |
| C7 drift reset at observations | §20.7: sensor × endpoint × epoch key; B18 interval 14 and offset -7, producing seven elapsed days at 0/14…84 |
| C8 pH/TA physically incoherent | §20.2: computational synthetic target only; physicalization fails until batch-specific titrant/counterion/dose/final-volume/full-panel revision |
| C9 executable H3 endpoints | §20.6.1: all four endpoints are executable from `SimulationResult.states`, interval step diagnostics, and the typed network. It fixes the exact 0.25-hour 0…2016 grid, `math.fsum` trapezoids, terminal 24-hour applied outward Na rate/sign, synthetic root-mass definitions, H2O2 link, mannitol matched-EV difference, xylem Na stock/volume, units, positivity/finiteness, post-death undefined behavior, and physical assay block. The two link constants are explicitly `hypothesis_prior`, never empirical or physics-constrained. |
| I1 hierarchy parameterization | §20.4.1: each keyed `Z` is `StandardNormal`; `u=sqrt(configured_variance)*Z`, followed by the exact sum, RUE target, composition order, and pre-integration timing. |
| I2 censor vocabulary/bounds | §20.5.2: exact applicability, batch/sample keys, `below_lod`/`detected_below_loq`, interval bounds, missingness nulling |
| I3 MNAR matching | §20.6.2: exact cohort/run/water/reservoir/time/endpoint match, native arithmetic mean, positivity/failure, selection-model naming |
| I4 sensor/epoch keys | §20.7: exact logical sensor IDs, `(sensor, endpoint, epoch)` residual key and public epoch mapping |
| I5 initial fill/solute state | §20.3.2: t=-0.25 120-L paired feed/solute transaction; batch chemistry root-zone initial state; synthetic abstraction and physical block |
| I6 Brent units/rule | §20.9.1: dimensionless parameter `xtol`/`rtol`, SciPy 1.18 combined rule, separate log-ratio residual gate |
| I7 endpoint roots | §20.9.2: exact binary64 lower/upper root accepted with boundary status and zero iterations |
| I8 objective/aggregation | §20.9.2: positive AUC, `mu=log(AUC)`, four-cell DID, `math.fsum/64`, no nuisance/error processes |
| I9 provenance | §20.11: Paper 1 plan, extract, lock, pyproject, source materializer, exact NumPy/SciPy versions/hashes |
| I10 sensitivities and panel sizes | §20.10.2: every S001–S036 path is a complete document-qualified literal; S001, S012, S020, S021/S022, S024, S025, S031, and S034–S036 are fully expanded. S013 parameterizes all `V0` equations; the S014 low-return capacity failure is prospectively registered. S031 binds exact fixed-prefix 32/128 hashes and cannot replace primary 64. |
| Minor conductivity | §20.2: descriptive scratch only; constants forbidden from production without a new validated method |
| Minor burn-in mean | §20.4.1 and earlier direct correction: distributional expectation only, no finite-panel mean claim |
| Minor scenario whitelist | §§20.7/20.10.1: exact B18 paths reconciled with closed ten-scenario policy |
| Minor day-42 boundary | §20.6.3: integrate, calibrate, observe, onset, operator order; day-42 observation pre-onset |

## Independently regenerated registration artifacts

The materializer is a durable tracked implementation artifact at
`scripts/registration/task4_registration_hash_materializer.py`, SHA-256
`0397fb262931c08f197ea841c24e055bbb751cbdec06dbc7473a87c9981497d5`.
It makes one `standard_normal((128,4,232))` call per fit/holdout child, emits
literal leading 32/64/128 prefixes, asserts the prefix relation, and ran in
three clean processes under NumPy 2.5.2 with byte-identical output:

| Artifact | SHA-256 |
|---|---|
| nominal schedule | `329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96` |
| operator times | `33ab36479f1500aef066b0f495010ff73ea86c8a4a8c4c2bac78603deb8da224` |
| sample times | `5fc3952a1b60b5282a97543577b0ff6aaac6463b654cc5ba9fd59748d1ffae14` |
| fit-32 forcing panels | `8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3` |
| holdout-32 forcing panels | `80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a` |
| fit-64 forcing panels (**primary**) | `4e32c2831ea039c5a1939aed19091160f9c8c112d99a9e2bc937f05539b51eaf` |
| holdout-64 forcing panels (**primary**) | `d1f5b6b185458f50f6453391065e6af970ce5069921507431ce46fede0f9ca5a` |
| fit-128 forcing panels | `91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9` |
| holdout-128 forcing panels | `3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11` |

The materializer produces exogenous schedules/forcing only.  It contains no
plant outcome, solver call, calibrated mechanism value, rank, selection, or
acceptance result.

## Re-review request

The second review stated that C3–C8, I2–I9, and all minor findings were closed;
this repair does not weaken those clauses.  Please perform a fresh read-only
review of the complete proposal and materializer, concentrating on C1, C2,
C9, I1, and I10 while checking for interactions with every previously closed
finding.  Re-run the materializer in a clean process; independently audit
shared-batch volume arithmetic, all four H3 transforms, exact time-grid/AUC
semantics, every expanded path, prefix relations, primary/sensitivity
separation, and the runtime/artifact hash partition.  This report does not
assert approval.
