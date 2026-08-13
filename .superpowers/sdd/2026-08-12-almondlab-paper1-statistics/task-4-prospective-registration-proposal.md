# Paper 1 Task 4 prospective synthetic-only registration proposal

**Status:** second-review-repaired proposal awaiting a fresh independent read-only review; not yet an accepted configuration, protocol, recipe, assay, or physical-use authorization
**Prepared:** 2026-08-13
**Scope:** prospective closure of Task 4 blockers B01–B20
**Evidence semantics:** every numerical choice introduced here is `hypothesis_prior`; every generated material, forcing, trajectory, observation, scenario, and calibration panel is `synthetic_only`

**Normative repair precedence:** Section 20 is a substantive repair after an
independent `CHANGES REQUIRED` review.  Its exact schemas, keys, units, event
order, formulas, hashes, and failure policies supersede every inconsistent
earlier sentence or table in this proposal.  In particular, the 250 L source
batch/rollover model, the mistaken per-loop interpretation of Task 3 shared
water batches, the old forcing/operator/panel hashes, generic 4 mmol/L
stop applicability, zero-at-observation drift construction, generic H3
schedule, under-specified calibration API, and any implication that the
formula target is physically preparable are retired.  They must not be
implemented or retained as alternate authorities.

## 1. Interpretation and non-claims

This document freezes one internally complete proposal before any Task 4 outcome generation. It does not report, estimate, or imply empirical almond efficacy, tolerance, safety, construct performance, assay sensitivity, or field relevance. The words “control,” “challenge,” “confirmation,” “known effect,” and “calibration” name synthetic design objects only. No value below may be relabeled as `observed`, `measured_in_almond`, `validated`, or `physics_constrained` merely because it passes an arithmetic or software check.

The proposed water pair is a new formula-resolved synthetic nutrient solution and the same solution plus a sodium-chloride increment. It is not raw seawater, a reconstruction of a natural marine matrix, or a silent revision of either v1.3 water. The existing contract water ID `pilot_selected_full_ion_marine_challenge` is retained only as a compatibility key; “pilot selected” and “marine” are not evidence claims.

Physical preparation or use requires institution-specific safety, environmental, engineering, analytical, greenhouse, and—where genetically modified material is involved—biosafety/regulatory review. Pilot measurements must establish actual pH, electrical conductivity (EC), osmolality, total alkalinity/speciation, analyte concentrations, stability, compatibility, plant exposure limits, containment, and disposal. A physical batch that misses an acceptance criterion must be rejected or handled through a prospective amendment; it must not be repaired by an unrecorded addition. The [Almond Board/UC ANR salinity guide](https://www.almonds.com/sites/default/files/2024-02/Salinity%20Management%20Guide%20for%20Almond%20Growers.pdf) is useful context for EC, SAR, complete-ion analysis, and almond salinity sensitivity, but it does not validate this synthetic recipe or authorize its use.

## 2. Authority and freeze rules

If adopted, this proposal supplies prospective values to the authorities named in the Task 4 repair plan. It does not itself mutate them. Implementation must:

1. create new recipe records rather than change a v1.3 recipe in place;
2. keep `hypothesis_prior` on design/configuration values and `synthetic_only` on generated rows;
3. preserve the exact units and endpoint IDs below;
4. refuse omitted fields, unknown endpoint keys, implicit defaults, independent ion perturbations, hidden water top-ups, outcome-driven bracket changes, and post hoc scenario edits;
5. fail closed when a registered domain, charge, schedule, hash, seed, convergence, or holdout check fails; and
6. require a new versioned prospective amendment for any changed number.

The following resolution matrix is normative.

| Blocker | Prospective resolution | Evidence label |
|---|---|---|
| B01 | New control recipe `paper1_base_nutrient_control_v1@1.0.0`, formula-addition basis, complete targets and lineage | `hypothesis_prior` |
| B02 | New challenge recipe `paper1_base_plus_nacl40_challenge_v1@1.0.0`, exact base plus 40.000 mmol NaCl L^-1 | `hypothesis_prior` |
| B03 | Charge-balance tolerance 1.00% in both recipe and generator authorities | `hypothesis_prior` |
| B04 | Two complete ordered 84-day/2,016-hour schedules, 168 twelve-hour steps per water | `synthetic_only` |
| B05 | AR(1), innovation, and 64-step burn-in values in §5 | `hypothesis_prior` |
| B06 | Chemistry perturbation and measurement-error values in §6 | `hypothesis_prior` |
| B07 | Explicit recirculating-water ledger and 84 daily operator events in §7 | `hypothesis_prior` / generated rows `synthetic_only` |
| B08 | Canopy, ion, and H3 schedules and heteroscedastic formulas in §8 | `hypothesis_prior` |
| B09 | C3 observation SD = 2.0 nmol g_root_fresh_mass^-1 | `hypothesis_prior` |
| B10 | Endpoint-complete LOD/LOQ registration and equality semantics in §9 | `hypothesis_prior` |
| B11 | Zero anchor drift, 7-day calibration, endpoint-complete residuals in §10 | `hypothesis_prior` |
| B12 | Three independent log-scale threshold heterogeneity SDs = 0.10 in §11 | `hypothesis_prior` |
| B13 | Three observable MAR fields, exact standardization, and five-endpoint MNAR set in §12 | `hypothesis_prior` |
| B14 | Calibration tolerances 1e-6/1e-6, 100 iterations, primary 64/64 panels, registered fixed-prefix 32/64/128 sensitivity artifacts, 0.02 holdout tolerance | `hypothesis_prior` |
| B15 | Six confirmation plants per group/reservoir; 84 days | `hypothesis_prior` |
| B16 | `core_v1@1.1.0`, synthetic second chassis, literal C5 × chassis modifier; old 0.35 edit retired | `hypothesis_prior` / chassis `synthetic_only` |
| B17 | Onset day 42; complete post-onset set `{senescence_h_inv: 0.06}` | `hypothesis_prior` |
| B18 | Nonzero endpoint drift and 14-day calibration overrides in §15 | `hypothesis_prior` |
| B19 | Purge = 0.12 L day^-1; no forcing/osmolality edit | `hypothesis_prior` |
| B20 | C2 known-effect target, bracket, solver, seeds, panels, and hashes in §17 | `hypothesis_prior` / panels `synthetic_only` |

### 2.1 Epistemic classification and uncertainty

“High implementation confidence” below means that the proposal is sufficiently explicit to encode and test; it does **not** mean high biological or physical confidence. All B01–B20 numerical values are code-owner synthetic choices made without outcome data. Literature supports only the stated general constraint or method, never the chosen almond effect, recipe performance, variance, threshold, or scenario magnitude.

| Blocker | Primary status | Literature-backed constraint, if any | Implementation confidence | External/physical uncertainty and remaining gate |
|---|---|---|---|---|
| B01 | Code-owned synthetic recipe choice | Equivalent cation/anion balance and complete water characterization are standard water-quality constraints (USDA ARS); compound identities/MWs are authoritative PubChem records | High for formula and arithmetic | High uncertainty for actual pH, EC, osmolality, alkalinity/speciation, purity, stability, plant compatibility, containment, and disposal; institutional review and analytical pilot required |
| B02 | Code-owned synthetic NaCl-challenge choice | Same charge/characterization constraints; extension guidance supports treating EC/SAR/full ions as relevant descriptors, not the selected concentration | High for increment and arithmetic | High uncertainty for exposure safety and almond response; engineering/safety review and pilot required |
| B03 | Code-owned software acceptance tolerance | Charge balance in equivalents is literature-backed; the plan-prescribed 1.00% is not presented as a universal laboratory criterion | High | A laboratory may require a different analytical balance criterion; prospective amendment required |
| B04 | Code-owned synthetic forcing schedule | None used to set the numbers | High | External validity of day/night conditions is unknown; any physical schedule needs site/chamber review |
| B05 | Code-owned stochastic prior | AR(1) form is an authoritative statistical method; coefficients/SDs/burn-in are not literature-derived | High | Climate covariance and transferability are unknown; sensitivity grid only |
| B06 | Code-owned stochastic/measurement prior | Charge-preserving common-ion construction follows the B03 constraint | High | Actual instrument precision and batch variability are unknown; instrument and batch pilot required |
| B07 | Code-owned operator/ledger schedule | Conservation and explicit transaction accounting are contract constraints, not empirical flow recommendations | High | Hydraulic capacity, return fraction, sampling loss, and waste handling require engineering review |
| B08 | Code-owned observation schedule/error prior | None used to set times or SDs | High | Instrument precision, tissue sampling feasibility, and destructiveness require assay pilot |
| B09 | Code-owned native-unit C3 error prior | Unit consistency is contract-backed; 2.0 is not literature-derived | High | Assay-specific repeatability unknown; pilot required |
| B10 | Code-owned synthetic LOD/LOQ placeholders | EPA requires laboratory/method-specific verification and supports keeping detection/quantitation concepts distinct | High for equality/censoring semantics; deliberately no physical confidence | Every physical endpoint limit must be demonstrated by the performing laboratory |
| B11 | Code-owned drift/reset prior | None used to set rates, interval, or residuals | High | Actual sensor drift/calibration performance unknown; equipment qualification required |
| B12 | Code-owned threshold-heterogeneity prior | Positive log-scale construction is statistical bookkeeping, not a death distribution claim | High | Biological threshold variability unknown; no physical inference allowed |
| B13 | Code-owned missingness selection model | General prospective missingness-sensitivity rationale only; fields/slopes/delta are not literature-derived | High | Real missingness mechanism unidentified; results must be reported as sensitivity analyses |
| B14 | Code-owned numerical/calibration contract | Official SciPy documentation supports the registered bracketing algorithm | High | Tolerances/panel sizes do not demonstrate biological calibration; independent reproduction required |
| B15 | Code-owned synthetic confirmation size | None used to establish power or efficacy | High | Six plants is not an empirical power calculation and cannot authorize a physical study |
| B16 | Code-owned secondary synthetic chassis semantics | None; `SYNTHETIC_VAIRO_B` has no biological identity | High | No external validity; validator must bar stronger evidence labels |
| B17 | Code-owned delayed-onset scenario | None used to set day 42 or 0.06 h^-1 | High | Timing and magnitude have no empirical almond basis |
| B18 | Code-owned adverse sensor scenario | None used to set drift values | High | Hardware-specific behavior unknown; scenario is stress testing only |
| B19 | Code-owned purge stress scenario | Mass/volume conservation is contract-backed; 0.12 L day^-1 is not a physical recommendation | High | Accumulation, plumbing, exposure, and disposal behavior require engineering/pilot review |
| B20 | Code-owned synthetic positive-control/calibration choice | Official NumPy stream documentation and SciPy bracketing documentation support reproducibility mechanics, not the target or effect | High if hashes reproduce | Bracket closure and holdout acceptance remain computational gates; no biological positive-control claim |

Overall confidence is high that the registered values are explicit and mechanically testable, moderate that the simple chemistry screens are internally plausible, and intentionally low/undefined for empirical almond transfer. No cited source closes a physical-validation gate.

## 3. B01–B03 — new formula-resolved water registrations

### 3.1 Identity, basis, and lineage

| Field | Control | Challenge |
|---|---:|---:|
| `water_id` | `nonsaline_nutrient_matched_control` | `pilot_selected_full_ion_marine_challenge` |
| `recipe_id` | `paper1_base_nutrient_control_v1` | `paper1_base_plus_nacl40_challenge_v1` |
| `revision` | `1.0.0` | `1.0.0` |
| `status` | `active` | `active` |
| `preparation.preparation_basis` | `formula_resolved_synthetic_target` | `formula_resolved_synthetic_target` |
| `preparation.source_water_chemistry` | explicit synthetic blank described below | exact control `computed_target_chemistry` |
| `preparation.amendments` | seven base-reagent records in §3.2 | one 40.000 mmol NaCl L^-1 final-volume record in §3.2 |
| `charge_convention_id` | `almondlab.chemistry.charge_balance_error@1` | `almondlab.chemistry.charge_balance_error@1` |
| `evidence_label` | `hypothesis_prior` | `hypothesis_prior` |
| generated batch label | `synthetic_only` | `synthetic_only` |

The control’s `source_water_chemistry` is a bookkeeping object with all registered analytes, EC, and osmolality equal to zero, pH 7.00, temperature 298.15 K, and `ec_kind = ECw`. It is never an active recipe, never sent through `core_v1`, and never interpreted as laboratory water. All control amounts below are applied per final litre to that blank. The challenge’s source is an exact detached reconstruction of the control `computed_target_chemistry`, followed by its single NaCl amendment per final litre. No background-ion subtraction, purity correction, hydrate correction, stock-solution carryover, pH titrant, or density correction is implicit.

Read-only provenance anchors link the new records to the previously active `WaterCondition` objects without making the old recipes chemical parents:

| Water ID | `source_field_path` | Signed legacy charge error | Canonical legacy-anchor SHA-256 / active `supersedes_anchor_sha256` |
|---|---|---:|---|
| `nonsaline_nutrient_matched_control` | `water_conditions[0].chemistry` | +23.167155425219942% | `a804553ff5d1e0c9938a10d14430d593cde2c5cbddd0a00c3e5460f884c61e1f` |
| `pilot_selected_full_ion_marine_challenge` | `water_conditions[1].chemistry` | +3.302286198137171% | `bef482128d45eff8a42593b9a19534f847858a265814edf627b8421d3e3b08a4` |

Both historical anchors have `source_design_raw_sha256 = d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0`, `status = superseded_unbalanced_hypothesis_anchor`, and `evidence_label = hypothesis_prior`. For these two anchors only, “canonical” means SHA-256 of `canonical_json_bytes(w.model_dump(mode="json"))` using the repository implementation read for this proposal. An implementation must reproduce those bytes before accepting the link. The anchors document identity continuity; they do not authorize reusing or editing v1.3 concentrations.

### 3.2 Base reagents per final litre

Formula masses use the displayed formula molecular weights; implementation must store formula, hydrate state, mmol L^-1, molecular weight, and mg L^-1, then verify `mg/L = mmol/L × g/mol`. Compound identity and molecular-weight cross-checks were made against the corresponding PubChem records for [sodium chloride](https://pubchem.ncbi.nlm.nih.gov/compound/Sodium-Chloride), [calcium nitrate tetrahydrate](https://pubchem.ncbi.nlm.nih.gov/compound/Calcium-nitrate-tetrahydrate), [magnesium sulfate heptahydrate](https://pubchem.ncbi.nlm.nih.gov/compound/Epsom%20salt), [potassium nitrate](https://pubchem.ncbi.nlm.nih.gov/compound/Potassium-nitrate), [potassium bicarbonate](https://pubchem.ncbi.nlm.nih.gov/compound/Potassium-Bicarbonate), [monobasic potassium phosphate](https://pubchem.ncbi.nlm.nih.gov/compound/potassium%20phosphate), and [boric acid](https://pubchem.ncbi.nlm.nih.gov/compound/boric-acid). Those records are identity references, not endorsements of grade or use.

| `reagent_id` / formula | `amount` (mmol L^-1) | Formula MW (g mol^-1) | Mass screen (mg L^-1) | `stoichiometric_contributions_mmol_l` | `alkalinity_contribution_mmol_c_l` |
|---|---:|---:|---:|---|---:|
| `sodium_chloride` / NaCl | 4.000 | 58.440 | 233.76000 | `{na: 4.000, cl: 4.000}` | 0.000 |
| `calcium_nitrate_tetrahydrate` / Ca(NO3)2·4H2O | 2.000 | 236.150 | 472.30000 | `{ca: 2.000, nitrate: 4.000}` | 0.000 |
| `magnesium_sulfate_heptahydrate` / MgSO4·7H2O | 1.000 | 246.480 | 246.48000 | `{mg: 1.000, sulfate: 1.000}` | 0.000 |
| `potassium_nitrate` / KNO3 | 1.000 | 101.103 | 101.10300 | `{k: 1.000, nitrate: 1.000}` | 0.000 |
| `potassium_bicarbonate` / KHCO3 | 0.750 | 100.115 | 75.08625 | `{k: 0.750, bicarbonate: 0.750}` | 0.750 |
| `monobasic_potassium_phosphate` / KH2PO4 | 0.250 | 136.086 | 34.02150 | `{k: 0.250, phosphate: 0.250}` | 0.250 |
| `boric_acid` / H3BO3 | 0.050 | 61.840 | 3.09200 | `{total_b: 0.050}` | 0.000 |

Every `amount`, contribution, and alkalinity contribution above is a `RegisteredQuantity` with the exact displayed unit and `evidence_label = hypothesis_prior`; each amendment record also has that label. Valence-charge contributions are independently recomputed from the analyte map under the registered charge convention rather than stored as a second authority.

The challenge adds exactly:

| `reagent_id` / formula | `amount` (mmol L^-1) | Formula MW (g mol^-1) | Mass screen (mg L^-1) | `stoichiometric_contributions_mmol_l` | `alkalinity_contribution_mmol_c_l` |
|---|---:|---:|---:|---|---:|
| `sodium_chloride_challenge_increment` / NaCl | 40.000 | 58.440 | 2337.60000 | `{na: 40.000, cl: 40.000}` | 0.000 |

Thus total NaCl is 4.000 mmol L^-1 (233.760 mg L^-1) in control and 44.000 mmol L^-1 (2571.360 mg L^-1) in challenge. The salt set is a prospective synthetic design, not a Hoagland recipe; the [UC Agricultural Experiment Station archive of Hoagland and Arnon’s water-culture method](https://digicoll.lib.berkeley.edu/record/320585?ln=en&v=pdf) is cited only as primary historical context for using explicitly formulated nutrient salts.

### 3.3 Complete final targets

| Field and unit | Control | Challenge |
|---|---:|---:|
| `ec_kind` | `ECw` | `ECw` |
| `ec_ds_m` (dS m^-1 at registered temperature) | 1.50 | 6.00 |
| `temperature_k` (K) | 298.15 | 298.15 |
| `measured_osmolality_osmol_kg` (osmol kg^-1) | 0.0200 | 0.1000 |
| `ph` | 6.50 | 6.50 |
| `alkalinity_mmol_c_l` (mmol_c L^-1) | 1.000 | 1.000 |
| `na_mmol_l` | 4.000 | 44.000 |
| `cl_mmol_l` | 4.000 | 44.000 |
| `ca_mmol_l` | 2.000 | 2.000 |
| `mg_mmol_l` | 1.000 | 1.000 |
| `k_mmol_l` | 2.000 | 2.000 |
| `total_b_mmol_l` | 0.050 | 0.050 |
| `sulfate_mmol_l` | 1.000 | 1.000 |
| `bicarbonate_mmol_l` | 0.750 | 0.750 |
| `nitrate_mmol_l` | 5.000 | 5.000 |
| `phosphate_mmol_l` | 0.250 | 0.250 |
| `sar` ((mmol_c L^-1)^0.5) | 2.3094 | 25.4034 |
| `charge_balance_tolerance_percent` | 1.00 | 1.00 |
| `model_domain_id` | `core_v1` | `core_v1` |
| `model_domain_version` | `1.1.0` | `1.1.0` |
| `evidence_label` | `hypothesis_prior` | `hypothesis_prior` |

EC, osmolality, pH, alkalinity, and temperature are synthetic final-state targets, not knobs that permit unregistered formulation changes. No pH-adjustment reagent is registered, so this record is not physically preparable: physical use fails `PHYSICAL_RECIPE_NOT_REGISTERED` pending the batch-specific acid/base, counterion, final-volume, and analytical revision in Section 20.2. Bicarbonate and phosphate remain explicit analytes, but the core contract’s charge computation uses `alkalinity_mmol_c_l` once; it must not double-count bicarbonate or phosphate. Analytical total alkalinity and species distribution are not established by this bookkeeping convention.

For each synthetic target, `computed_target_chemistry` is exactly the final table above. `registered_nonstoichiometric_targets` contains exactly `{ec_ds_m, measured_osmolality_osmol_kg, ph, temperature_k, alkalinity_mmol_c_l}` with the displayed values, exact native units, and `hypothesis_prior`; `ec_kind = ECw` is fixed separately. Formula summation supplies the displayed ion totals under the software convention, but it does not derive physical pH, speciation, or analytical alkalinity. The separately serialized synthetic `chemistry` must be canonically equal to `computed_target_chemistry`.

### 3.4 Independent arithmetic and plausibility checks

The USDA Agricultural Research Service explains that irrigation-water cations and anions should balance when expressed as equivalents and treats EC as a salinity indicator ([USDA ARS, *Classification and Use of Irrigation Waters*](https://www.ars.usda.gov/arsuserfiles/20361500/pdf_pubs/P0192.pdf)). Applying the registered core formula:

`cation mmol_c/L = Na + K + 2Ca + 2Mg`

`anion mmol_c/L = Cl + nitrate + 2sulfate + alkalinity`

| Check | Control | Challenge |
|---|---:|---:|
| Cations (mmol_c L^-1) | 4 + 2 + 4 + 2 = 12 | 44 + 2 + 4 + 2 = 52 |
| Anions (mmol_c L^-1) | 4 + 5 + 2 + 1 = 12 | 44 + 5 + 2 + 1 = 52 |
| Charge-balance error | 0.000% | 0.000% |
| Ideal fully dissociated particle screen (osmol L^-1) | 0.02005 | 0.10005 |
| Registered osmolality target (osmol kg^-1) | 0.0200 | 0.1000 |
| Ionic-strength screen (mol L^-1) | 0.016 | 0.056 |
| Limiting-conductivity screen (dS m^-1) | 1.55585 | 6.61185 |
| Registered EC target (dS m^-1) | 1.50 | 6.00 |

The particle screen assumes complete dissociation and approximately 1 kg water L^-1. The conductivity screen is a dilute-limit sum, not an EC prediction or calibration, so finite-concentration ion interactions can make observed EC lower. These checks show internal order-of-magnitude plausibility only. They do not establish activity coefficients, fertilizer purity, pH, EC, osmolality, biological suitability, or disposal safety. Both active targets are inside the currently registered numeric EC, osmolality, and temperature bounds; all required analytes are present. The challenge’s high prospective SAR flags a sodium-dominant hazard hypothesis rather than safety.

The B03 1.00% tolerance is identical in both recipe objects and `anchor.generator.chemistry.charge_balance_tolerance_percent`. It is distinct from numerical mass-ledger tolerance. Registered sensitivity values are 0.10%, 0.50%, and 2.00%; sensitivity runs are separate synthetic scenarios and cannot replace the anchor.

## 4. B04 — complete two-water forcing schedules

The nominal schedule expands deterministically for `d = 0,…,83`. Each water has 168 ordered records and exactly 2,016 hours. Record `2d` starts at `24d` hours; record `2d+1` starts at `24d+12` hours. Both have `duration_hours = 12.0`. Control records map only to `paper1_base_nutrient_control_v1@1.0.0`; challenge records map only to `paper1_base_plus_nacl40_challenge_v1@1.0.0`.

| Field | Day record | Night record |
|---|---:|---:|
| `temperature_k` | 297.15 | 293.15 |
| `water_density_kg_l` | 0.9973 | 0.9982 |
| `matric_potential_mpa` | -0.080 | -0.040 |
| `leaf_critical_potential_mpa` | -1.80 | -1.80 |
| `apar_mol_h` | 0.80 | 0.00 |
| `temperature_factor` | 0.85 | 0.65 |
| `potential_transpiration_l_day` | 0.80 | 0.15 |
| `duration_hours` | 12.0 | 12.0 |
| `evidence_label` | `synthetic_only` | `synthetic_only` |
| `hydraulic_domain` | `paper1-biology-v1@1.0.0` | `paper1-biology-v1@1.0.0` |

`measured_osmolality_osmol_kg` is 0.0200 in every control record and 0.1000 in every challenge record. All other nominal forcing fields are identical across waters; therefore water is not confounded with nominal climate. The final record ends exactly at hour 2,016.

The exact self-contained 336-record schema and sample record are in Section 20.8. Its regenerated canonical SHA-256 is `329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96`. The previous `0e7256…` value is retired because its record schema was underdefined.

## 5. B05 — climate generator

### 5.1 Required hierarchy variance carry-forward

The structured generator also preserves the four v1.3 variances as explicit, no-default fields:

| Machine field | Value | Unit |
|---|---:|---|
| `hierarchy.run_variance` | 0.02 | log-ratio^2 |
| `hierarchy.batch_variance` | 0.02 | log-ratio^2 |
| `hierarchy.reservoir_variance` | 0.04 | log-ratio^2 |
| `hierarchy.plant_variance` | 0.10 | log-ratio^2 |

Each is the variance—not the SD—of an independent zero-mean normal draw at, respectively, run, physical-transformation batch, cohort × run × water × reservoir, and plant level. Section 20.4.1 fixes the immutable keys, sum, target (`radiation_use_efficiency_g_mol_apar_inv`), composition order, and pre-integration timing. They are not observation error and never draw or edit an outcome. The `selection_bias_false_leader` scenario changes only `plant_variance` to 0.20 log-ratio^2. All four values are `hypothesis_prior`; generated effects are `synthetic_only`.

### 5.2 Climate process

NIST’s description of an AR(1) process provides the statistical form used here ([NIST/SEMATECH e-Handbook](https://www.itl.nist.gov/div898/handbook/pmc/section4/pmc446.htm)). For the anomaly `u`, initialize `u = 0`, then apply `u_t = phi u_(t-1) + sigma_epsilon Z_t`, with independent standard-normal innovations in a registered keyed stream. Run 64 twelve-hour burn-in updates and discard them before the first 84-day record.

| Machine field | Value | Unit/scale |
|---|---:|---|
| `temperature_ar1_phi` | 0.70 | dimensionless |
| `temperature_innovation_sd_k` | 0.35 | K |
| `apar_ar1_phi` | 0.60 | dimensionless |
| `apar_log_innovation_sd` | 0.10 | log-ratio |
| `matric_potential_ar1_phi` | 0.80 | dimensionless |
| `matric_potential_innovation_sd_mpa` | 0.006 | MPa |
| `potential_transpiration_log_innovation_sd` | 0.08 | log-ratio |
| `climate_initialization_burnin_steps` | 64 | count |
| `evidence_label` | `hypothesis_prior` | label |

Temperature and matric potential add `u_t` to the day/night nominal. APAR multiplies its nominal by `exp(u_t - 0.5 sigma_u^2)`, where `sigma_u^2 = sigma_epsilon^2/(1-phi^2)`; zero nighttime APAR therefore remains exactly zero. Potential transpiration has no AR coefficient in the contract: it uses independent log innovations (`phi = 0` mathematically) and multiplier `exp(u_t - 0.5×0.08^2)`. The corrections make the multiplier's theoretical expectation one only under the stated stationary Gaussian distribution; they do not force a finite burn-in or realized panel to have its nominal arithmetic mean. Both waters in the same panel share climate anomalies.

Sensitivity grid: each AR coefficient 0.40 and 0.90; each innovation SD one-half and twice its anchor; burn-in 32 and 128. Each sensitivity changes one field group prospectively and remains `synthetic_only`.

## 6. B06 — chemistry generator

| Machine field | Value | Unit/scale |
|---|---:|---|
| `common_ion_log_sd` | 0.03 | log-ratio |
| `boron_log_sd` | 0.08 | log-ratio |
| `ec_measurement_sd_ds_m` | 0.05 | dS m^-1 |
| `osmolality_measurement_sd_osmol_kg` | 0.002 | osmol kg^-1 |
| `ph_measurement_sd` | 0.03 | pH |
| `temperature_measurement_sd_k` | 0.20 | K |
| `charge_balance_tolerance_percent` | 1.00 | percent |
| `evidence_label` | `hypothesis_prior` | label |

For each predeclared physical Task 3 `water_batch_id`, one multiplier `M_ion = exp(0.03 Z - 0.5×0.03^2)` multiplies Na, Cl, Ca, Mg, K, sulfate, nitrate, phosphate, bicarbonate, and alkalinity together. Bicarbonate and alkalinity use the same draw and remain paired. No ion gets an independent draw, so exact charge balance is preserved. Total B alone uses `M_B = exp(0.08 Z_B - 0.5×0.08^2)`. The exact `(cohort_id, water_batch_id)` key and transaction use are fixed in Section 20.4.2; transformation-batch keys are prohibited.

EC, osmolality, pH, and temperature measurement errors are independent additive zero-mean normal errors with the displayed native-unit SDs. They change observation-view fields only; the mechanistic forcing uses the registered latent recipe/forcing value and the domain validator is applied to that latent input. An observed value outside the mechanistic domain is retained with an out-of-domain observation flag and is never fed back into the state update. There is no clipping, resampling, or outcome-dependent repair.

Sensitivity values are one-half and twice every SD. The charge-tolerance sensitivity is the B03 grid.

## 7. B07 — recirculating-water forcing and ledger

| Machine field | Value | Unit |
|---|---:|---|
| `reservoir_initial_volume_l` | 120.0 | L |
| `water_batch_volume_l` | 5000.0 | L |
| `irrigation_volume_l_per_plant_day` | 0.60 | L plant^-1 day^-1 |
| `drainage_return_fraction` | 0.70 | dimensionless |
| `purge_volume_l_day` | 1.20 | L day^-1 |
| `sampling_volume_l_per_sample` | 0.050 | L sample^-1 |
| `reservoir_min_volume_l` | 80.0 | L |
| `reservoir_max_volume_l` | 160.0 | L |
| `operator_event_times_days` | `[0.25 + i for i in 0..83]` | days |
| `evidence_label` | `hypothesis_prior` | label |

The operator-time list contains exactly 84 strictly increasing values from 0.25 through 83.25. Its expanded canonical SHA-256 is `33ab36479f1500aef066b0f495010ff73ea86c8a4a8c4c2bac78603deb8da224` under the payload `{"schema_version":"1.0.0","operator_event_times_days":[...]}` and repository `canonical_json_bytes`.

Samples on days 0–70 occur before the same-day operator event; day 84 is terminal. At every operator event and for each water × reservoir, let `V0 = generator.water_loop.reservoir_initial_volume_l`, compute `I_d = 0.60 × N_assigned`, `R_d = 0.70 × I_d`, `P_d = 1.20`, and `M_d = V0 - (V_event_start - I_d + R_d - P_d)`, then execute external makeup first, irrigation, drainage return, purge, and closure. `N_assigned` comes from the frozen design manifest and does not fall after death. Section 20.3 fixes the complete transaction/solute order, initial fill, six restored samples plus the un-restored terminal sample, shared-batch capacity arithmetic, and final `V0 - 0.050 L` state.

Exactly one 0.050 L reservoir sample is withdrawn per water × reservoir at each ion-observation day in §8; canopy and H3 measurements do not withdraw reservoir water. Every withdrawal, return, purge, sample, makeup addition, and initial fill is a ledger transaction. Task 3 shares one predeclared physical `water_batch_id` across four discovery loops or six confirmation loops in the registered maps. Its 5,000.0 L inventory is debited jointly by every loop bearing that ID; rollover and runtime-generated batch IDs are prohibited. No hidden top-up is allowed. Transaction states use the exact Section 20.3 bounds/order; failure is fatal, not clipped.

Water-loop sensitivity values: initial volume 100/140 L; return fraction 0.50/0.90; irrigation 0.40/0.80 L plant^-1 day^-1; baseline purge 0.60/2.40 L day^-1; sample volume 0.025/0.100 L. B19 has its own purge grid and takes precedence only in that scenario.

## 8. B08–B09 — observation registry and schedules

### 8.1 Endpoint registry

| Endpoint ID | Unit | Family | Scale | Candidate use |
|---|---|---|---|---|
| `green_canopy_area` | cm^2 | canopy | log | shared outcome |
| `root_zone_na_concentration` | mmol Na L^-1 | ion | log | shared outcome |
| `root_zone_cl_concentration` | mmol Cl L^-1 | ion | log | shared outcome |
| `root_zone_k_concentration` | mmol K L^-1 | ion | log | shared outcome |
| `xylem_sap_na_concentration` | mmol Na L^-1 | ion | log | shared outcome |
| `drainage_total_b_concentration` | mmol B L^-1 | ion | log | shared outcome |
| `root_surface_outward_na_flux_per_root_dry_mass` | umol Na g_root_dry_mass^-1 h^-1 | H3 | log | C1, C4, C6 |
| `root_h2o2_concentration_time_auc` | umol H2O2 g_root_fresh_mass^-1 h | H3 | log | C2 |
| `root_mannitol_concentration_above_empty_vector` | nmol g_root_fresh_mass^-1 | H3 | difference | C3 |
| `xylem_sap_na_concentration_time_auc` | mmol Na L^-1 h | H3 | log | C5 |

The four H3 endpoint definitions merely materialize already registered candidate rules. They are not new mechanistic or efficacy claims.

### 8.2 Ordered schedules and error values

| Machine field | Exact value |
|---|---|
| `canopy_observation_times_days` | `[0, 3, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84]` |
| `ion_observation_times_days` | `[0, 14, 28, 42, 56, 70, 84]` |
| `h3_observation_times_days_by_endpoint` | all four exact H3 endpoint IDs map to terminal `[84.0]`; see Section 20.6.1 |
| `canopy_observation_error_sd` | 0.05 log-ratio |
| `ion_observation_error_sd` | 0.04 log-ratio |
| `canopy_heteroscedastic_log_slope` | 0.10 log-ratio per absolute log-ratio |
| `ion_heteroscedastic_log_slope` | 0.08 log-ratio per absolute log-ratio |

H3 candidate error map:

| Candidate key | SD | Unit/scale |
|---|---:|---|
| C1 | 0.05 | log-ratio |
| C2 | 0.05 | log-ratio |
| C3 | 2.0 | nmol g_root_fresh_mass^-1 |
| C4 | 0.05 | log-ratio |
| C5 | 0.05 | log-ratio |
| C6 | 0.05 | log-ratio |

B09 is thereby closed with a native-unit C3 SD. The v1.3 dimensionless 0.05 is prohibited for C3.

For a living plant, canopy log-error SD at time `t` is `0.05 + 0.10 × abs(log(C_t/C_0))`. Ion endpoint `e` uses `0.04 + 0.08 × abs(log((Y_e,t + LOQ_e)/(Y_e,0 + LOQ_e)))`; the registered endpoint LOQ is the only offset and no hidden epsilon is permitted. H3 uses the fixed candidate error above. Canopy is public zero after death with no additional random error. Post-death ion and H3 values are structurally undefined, not zeros. Observation error is drawn before censoring and missingness.

Sensitivity values: error SD and heteroscedastic slope one-half/twice anchor; schedules remain fixed.

## 9. B10 — censoring

The four required machine maps are `lod_by_endpoint`, `loq_by_endpoint`, `lod_log_sd_by_endpoint`, and `loq_log_sd_by_endpoint`. Each has exactly the ten endpoint keys in §8; table columns below are the corresponding map values. Null is an explicit value, not a missing key.

| Endpoint ID | LOD | LOQ | `lod_log_sd` | `loq_log_sd` |
|---|---:|---:|---:|---:|
| `green_canopy_area` | null | null | null | null |
| `root_zone_na_concentration` | 0.010 mmol Na L^-1 | 0.030 mmol Na L^-1 | 0.05 | 0.05 |
| `root_zone_cl_concentration` | 0.010 mmol Cl L^-1 | 0.030 mmol Cl L^-1 | 0.05 | 0.05 |
| `root_zone_k_concentration` | 0.010 mmol K L^-1 | 0.030 mmol K L^-1 | 0.05 | 0.05 |
| `xylem_sap_na_concentration` | 0.005 mmol Na L^-1 | 0.015 mmol Na L^-1 | 0.05 | 0.05 |
| `drainage_total_b_concentration` | 0.0005 mmol B L^-1 | 0.0015 mmol B L^-1 | 0.05 | 0.05 |
| `root_surface_outward_na_flux_per_root_dry_mass` | 0.005 umol Na g_root_dry_mass^-1 h^-1 | 0.015 same unit | 0.05 | 0.05 |
| `root_h2o2_concentration_time_auc` | 0.10 umol H2O2 g_root_fresh_mass^-1 h | 0.30 same unit | 0.05 | 0.05 |
| `root_mannitol_concentration_above_empty_vector` | null | null | null | null |
| `xylem_sap_na_concentration_time_auc` | 0.10 mmol Na L^-1 h | 0.30 same unit | 0.05 | 0.05 |

For an exact `(assay_batch_id, endpoint_id, matrix_compartment_id, assay_phase_id)`, use the same normal draw for both thresholds: `LOD_b = LOD × exp(0.05Z)` and `LOQ_b = LOQ × exp(0.05Z)`. This preserves the registered 3:1 LOQ/LOD ratio. Classification is exact: `y < LOD_b` → `below_lod`; `LOD_b <= y < LOQ_b` → `detected_below_loq`; `y >= LOQ_b` → `quantified`. Thus equality at LOD is detected and equality at LOQ is quantified. Uncensored endpoints require all four nulls and state `uncensored`. Section 20.5.2 governs applicability, exact public interval bounds, sample keys, missingness nulling, and vocabularies.

EPA guidance emphasizes that an LLOQ is laboratory- and method-specific and must be demonstrated ([US EPA SW-846 detection and quantitation](https://www.epa.gov/hw-sw846/detection-quantitation); [EPA environmental chemistry method guidance](https://www.epa.gov/sites/default/files/2015-08/documents/ftt_env_chem_methods.pdf)). The numbers above are therefore synthetic placeholders only. They must not be used as physical assay claims; each institution/laboratory must validate real limits before use.

Sensitivity: all non-null LOD/LOQ values 0.5× and 2× anchor; threshold log SD 0.00, 0.025, and 0.10.

## 10. B11 — anchor drift and calibration

All anchor drift rates are exactly zero. `calibration_interval_days = 7.0`. The table materializes `canopy_drift_per_day`, the endpoint-complete `ion_drift_per_day_by_endpoint`, the candidate-complete `h3_drift_per_day_by_endpoint`, and the endpoint-complete `post_calibration_residual_sd_by_endpoint`; no key may be omitted because its value is zero.

| Endpoint/family | Drift rate | Post-calibration residual SD | Scale/unit |
|---|---:|---:|---|
| `green_canopy_area` | 0.0 | 0.005 | log-ratio |
| each of five ion endpoints | 0.0 | 0.010 | log-ratio |
| H3 C1, C2, C4, C5, C6 | 0.0 | 0.010 | log-ratio |
| H3 C3 | 0.0 | 0.25 | nmol g_root_fresh_mass^-1 |

For interval `I`, phase offset `o`, and `k = floor((t-o)/I)`, drift state is `b_e(t) = r_e × [t-(o+kI)] + eta_sensor,e,k`. At an exact reset boundary, a newly keyed `eta` is drawn and elapsed time is zero. The key, sensor assignment, public epoch ID, and B18 phase offset are fixed in Section 20.7. Log endpoints are multiplied by `exp(b_e)`; C3 receives additive `b_e`. A calibration never sees, edits, or is triggered by a biological outcome.

Anchor sensitivity: interval 3.5 and 14 days; residual SD one-half/twice; generic drift-rate checks at ±0.001 log day^-1 (C3 ±0.05 native units day^-1) as separate synthetic runs.

## 11. B12 — death-threshold heterogeneity

Task 2 baseline values remain unchanged: `biomass_death_threshold_g = 0.05`, `injury_death_threshold = 5.0`, and `sustained_injury_duration_hours = 24.0`. Only the prospective between-plant threshold heterogeneity is added:

| Machine field | Value | Scale |
|---|---:|---|
| `biomass_death_threshold_log_sd` | 0.10 | log-ratio |
| `injury_death_threshold_log_sd` | 0.10 | log-ratio |
| `sustained_injury_duration_log_sd` | 0.10 | log-ratio |

Each plant receives three independent keyed draws. For baseline threshold `theta_0`, `theta_i = theta_0 × exp(sigma Z_i)`; this is median-preserving and always positive. These draws set thresholds only and never draw a death event or edit a trajectory. Sensitivity SDs are 0.00, 0.05, 0.20, and 0.30.

## 12. B13 — MAR and MNAR missingness

| Machine field | Exact value |
|---|---|
| `missingness_intercept` | -3.0 logit |
| `missingness_stress_slope` | 0.20 logit per standardized-proxy SD |
| `mnar_tipping_delta` | 0.10 logit per standardized-endpoint SD |
| `observable_stress_proxy_fields` | `[challenge_water_indicator, scheduled_time_days, prior_observed_canopy_log_ratio]` |
| `observable_stress_proxy_center_by_field` | `{challenge_water_indicator: 0.5, scheduled_time_days: 42.0, prior_observed_canopy_log_ratio: 0.0}` |
| `observable_stress_proxy_scale_by_field` | `{challenge_water_indicator: 0.5, scheduled_time_days: 42.0, prior_observed_canopy_log_ratio: 0.25}` |
| `mnar_endpoints` | `[green_canopy_area, root_surface_outward_na_flux_per_root_dry_mass, root_h2o2_concentration_time_auc, root_mannitol_concentration_above_empty_vector, xylem_sap_na_concentration_time_auc]` |

Define `z_water = (challenge_indicator-0.5)/0.5`, `z_time = (scheduled_day-42)/42`, and `z_canopy = -(prior_observed_canopy_log_ratio-0)/0.25`. At the first scheduled observation or if the preceding canopy observation is itself missing, the prospectively registered carry value is zero, so `z_canopy = 0`; no hidden canopy truth may be substituted. `z_stress = (z_water + z_time + z_canopy)/3`.

For endpoint `e`, `logit(p_missing) = -3.0 + 0.20 z_stress + I(e in mnar_endpoints) × 0.10 z_hidden,e`. The hidden adverse scores are:

* canopy: `-log(C/EV)/log(1.20)`;
* greater-is-better log H3: `-log(Y/EV)/log(1.20)`;
* less-is-better log H3: `log(Y/EV)/abs(log(0.80))`; and
* C3 difference: `-(Y-EV)/10`.

Here `EV` is the exact matched-empty-vector aggregate defined in Section 20.6.2. The public row records only `scheduled_measurement_missing` and never exposes `z_hidden`. Only the listed endpoints may use the hidden term. This is a prospective logistic **selection-model** sensitivity construction; it is not a pattern-mixture model and is not a claim that real missingness follows this model.

Sensitivity: intercept -4/-2; MAR slope 0/0.40/0.80; MNAR delta -0.20/-0.10/0/0.10/0.20.

## 13. B14–B15 — calibration and confirmation design

| Machine field | Value | Unit |
|---|---:|---|
| `parameter_xtol` | 1.0e-6 | dimensionless primary-parameter units |
| `parameter_rtol` | 1.0e-6 | dimensionless |
| `objective_residual_tolerance_log_ratio` | 1.0e-6 | log-ratio |
| `max_iterations` | 100 | count |
| `fit_panel_size` | 64 | count |
| `holdout_panel_size` | 64 | count |
| `holdout_tolerance_log_ratio` | 0.020 | log-ratio |
| `confirmation_plants_per_group_reservoir` | 6 | count |
| `duration_days` | 84.0 | day |
| `maximum_confirmation_family_size` | 360 | plants |
| `evidence_label` | `hypothesis_prior` | label |

Parameter absolute and relative tolerances are both required and use SciPy's combined parameter-space rule; the separately registered objective-residual tolerance is checked after the solver. Fit panels determine the root; holdout panels are immutable and used once. No fit/holdout exchange or redraw is allowed. Section 20.9 defines the explicit panel API, primary 64-panel objective, and registered fixed-prefix 32/128 sensitivity artifacts. Confirmation size is six—not a range—and is frozen before confirmation generation. The existing maximum family cap remains 360 and is never a target sample size.

Sensitivity: Section 20.10.2 is the sole authority. It registers dimensionless parameter `xtol`/`rtol`, paired fit/holdout panel counts 32/32 and 128/128, holdout tolerance 0.01 and 0.05 log-ratio, and confirmation plants 5 as non-colliding one-at-a-time runs.

## 14. B16–B17 — chassis and delayed-onset scenarios

### 14.1 Secondary synthetic chassis

`core_v1` is prospectively bumped from `1.0.0` to `1.1.0`; `allowed_chassis` becomes exactly `[Vairo, SYNTHETIC_VAIRO_B]`. `SYNTHETIC_VAIRO_B` is a simulation label with `evidence_label: synthetic_only`, not a genotype, rootstock, cultivar, biological material, or empirical comparison.

The `chassis_interaction` mechanism is exactly:

| Field | Value |
|---|---|
| `mechanism.chassis_id` | `SYNTHETIC_VAIRO_B` |
| `mechanism.candidate_chassis_mechanism_modifiers` | exact one-key map `{C5: {xylem_na_retrieval_multiplier: {operation: multiply_candidate_effect, factor: 0.80}}}` |
| composition order | candidate template first, then multiply its primary scalar by 0.80 |
| C5 trade-off | unchanged `root_na_injury_multiplier = 1.10` |
| empty-vector modifier | identity 1.00 |
| other candidates | identity; do not serialize unused leaves |

Thus the current C5 hypothesis template primary value 1.50 would become 1.20 in this scenario only. The old v1.3 `root_conductance_l_day_mpa = 0.35` scenario edit is explicitly retired and must not be migrated. Sensitivity modifiers are 0.60, 0.80, and 1.00. A task-specific validator must refuse `SYNTHETIC_VAIRO_B` for any evidence tier stronger than synthetic design.

### 14.2 Delayed toxicity

| Field | Value |
|---|---|
| `onset_time_days` | 42.0 days |
| `post_onset_biology_parameter_overrides` | `{senescence_h_inv: 0.06}` |
| boundary semantics | day-42 observation is pre-onset; override applies to subsequent intervals with `t > 42.0 days` per Section 20.6.3 |
| completeness | this is the entire post-onset override set |

Before onset, the exact anchor biology applies. At the event-aligned boundary, only `senescence_h_inv` changes; no other parameter, forcing, observation, or outcome changes. Sensitivity onset days are 28, 42, and 56.

## 15. B18–B19 — drift/missingness and purge scenarios

### 15.1 `sensor_drift_missingness`

Retain `canopy_observation_error_sd = 0.12` and `missingness_stress_slope = 0.60`. Override `calibration_interval_days = 14.0` and `calibration_phase_offset_days = -7.0`, then use:

| Endpoint | Drift rate | Post-calibration residual SD | Scale/unit |
|---|---:|---:|---|
| `green_canopy_area` | +0.0025 day^-1 | 0.020 | log |
| `root_zone_na_concentration` | +0.0015 day^-1 | 0.025 | log |
| `root_zone_cl_concentration` | -0.0010 day^-1 | 0.025 | log |
| `root_zone_k_concentration` | +0.0008 day^-1 | 0.025 | log |
| `xylem_sap_na_concentration` | +0.0020 day^-1 | 0.025 | log |
| `drainage_total_b_concentration` | -0.0012 day^-1 | 0.025 | log |
| H3 C1 | +0.0015 day^-1 | 0.025 | log |
| H3 C2 | -0.0010 day^-1 | 0.025 | log |
| H3 C3 | +0.080 nmol g_root_fresh_mass^-1 day^-1 | 0.75 | native |
| H3 C4 | +0.0015 day^-1 | 0.025 | log |
| H3 C5 | +0.0018 day^-1 | 0.025 | log |
| H3 C6 | +0.0015 day^-1 | 0.025 | log |

This scenario changes only the expanded literal observation/missingness/drift paths in Section 20.7. It may not edit latent biological outcomes. The -7-day phase gives seven elapsed drift days at every 14-day ion/H3 observation, so the nonzero rates are exercised.

### 15.2 `insufficient_purge`

Set only `generator.water_loop.purge_volume_l_day = 0.12 L day^-1`, 90% below the 1.20 anchor. Both water recipes and every forcing field remain unchanged. The old v1.3 `measured_osmolality_osmol_kg = 0.30` edit is prohibited. Any accumulation must emerge from the registered mass/volume ledger. Sensitivity purge values are 0.00, 0.12, and 0.30 L day^-1.

### 15.3 Other scenario carry-forward

| Scenario | Only retained non-anchor change |
|---|---|
| `perfect_control` | none |
| `true_ion_exclusion` | `root_na_permeability_l_cm2_h = 0.0` |
| `root_na_accumulation` | `na_efflux_vmax_mmol_h = 0.10` |
| `marker_only` | `ros_clearance_h_inv = 0.40` |
| `nonsaline_penalty` | `mannitol_carbon_cost_mmol_c_mmol_inv = 0.80`; no forcing edit |
| `selection_bias_false_leader` | `plant_variance = 0.20` |

All scenario rows remain `synthetic_only`.

## 16. Machine-ready value table

This compact table is normative for scalar implementation. Lists, endpoint maps, formulas, and scenario maps are normative in their dedicated sections.

| Path suffix | Value | Unit | Evidence |
|---|---:|---|---|
| `active_recipes[control].charge_balance_tolerance_percent` | 1.00 | percent | `hypothesis_prior` |
| `active_recipes[challenge].charge_balance_tolerance_percent` | 1.00 | percent | `hypothesis_prior` |
| `anchor.generator.hierarchy.run_variance` | 0.02 | log-ratio^2 | `hypothesis_prior` |
| `anchor.generator.hierarchy.batch_variance` | 0.02 | log-ratio^2 | `hypothesis_prior` |
| `anchor.generator.hierarchy.reservoir_variance` | 0.04 | log-ratio^2 | `hypothesis_prior` |
| `anchor.generator.hierarchy.plant_variance` | 0.10 | log-ratio^2 | `hypothesis_prior` |
| `anchor.generator.climate.temperature_ar1_phi` | 0.70 | dimensionless | `hypothesis_prior` |
| `anchor.generator.climate.temperature_innovation_sd_k` | 0.35 | K | `hypothesis_prior` |
| `anchor.generator.climate.apar_ar1_phi` | 0.60 | dimensionless | `hypothesis_prior` |
| `anchor.generator.climate.apar_log_innovation_sd` | 0.10 | log-ratio | `hypothesis_prior` |
| `anchor.generator.climate.matric_potential_ar1_phi` | 0.80 | dimensionless | `hypothesis_prior` |
| `anchor.generator.climate.matric_potential_innovation_sd_mpa` | 0.006 | MPa | `hypothesis_prior` |
| `anchor.generator.climate.potential_transpiration_log_innovation_sd` | 0.08 | log-ratio | `hypothesis_prior` |
| `anchor.generator.climate.climate_initialization_burnin_steps` | 64 | count | `hypothesis_prior` |
| `anchor.generator.chemistry.common_ion_log_sd` | 0.03 | log-ratio | `hypothesis_prior` |
| `anchor.generator.chemistry.boron_log_sd` | 0.08 | log-ratio | `hypothesis_prior` |
| `anchor.generator.chemistry.ec_measurement_sd_ds_m` | 0.05 | dS m^-1 | `hypothesis_prior` |
| `anchor.generator.chemistry.osmolality_measurement_sd_osmol_kg` | 0.002 | osmol kg^-1 | `hypothesis_prior` |
| `anchor.generator.chemistry.ph_measurement_sd` | 0.03 | pH | `hypothesis_prior` |
| `anchor.generator.chemistry.temperature_measurement_sd_k` | 0.20 | K | `hypothesis_prior` |
| `anchor.generator.chemistry.charge_balance_tolerance_percent` | 1.00 | percent | `hypothesis_prior` |
| `anchor.generator.water_loop.reservoir_initial_volume_l` | 120.0 | L | `hypothesis_prior` |
| `anchor.generator.water_loop.water_batch_volume_l` | 5000.0 | L | `hypothesis_prior` |
| `anchor.generator.water_loop.irrigation_volume_l_per_plant_day` | 0.60 | L plant^-1 day^-1 | `hypothesis_prior` |
| `anchor.generator.water_loop.drainage_return_fraction` | 0.70 | dimensionless | `hypothesis_prior` |
| `anchor.generator.water_loop.purge_volume_l_day` | 1.20 | L day^-1 | `hypothesis_prior` |
| `anchor.generator.water_loop.sampling_volume_l_per_sample` | 0.050 | L sample^-1 | `hypothesis_prior` |
| `anchor.generator.water_loop.reservoir_min_volume_l` | 80.0 | L | `hypothesis_prior` |
| `anchor.generator.water_loop.reservoir_max_volume_l` | 160.0 | L | `hypothesis_prior` |
| `anchor.generator.observation.canopy_observation_error_sd` | 0.05 | log-ratio | `hypothesis_prior` |
| `anchor.generator.observation.ion_observation_error_sd` | 0.04 | log-ratio | `hypothesis_prior` |
| `anchor.generator.observation.canopy_heteroscedastic_log_slope` | 0.10 | log/log | `hypothesis_prior` |
| `anchor.generator.observation.ion_heteroscedastic_log_slope` | 0.08 | log/log | `hypothesis_prior` |
| `anchor.generator.observation.h3_observation_error_by_endpoint.C3` | 2.0 | nmol g_root_fresh_mass^-1 | `hypothesis_prior` |
| `anchor.generator.observation.h3_measurement_links.root_dry_matter_fraction` | 0.20 | dimensionless | `hypothesis_prior` |
| `anchor.generator.observation.h3_measurement_links.h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless` | 1.0 | umol H2O2 g_root_fresh_mass^-1 per ros_dimensionless | `hypothesis_prior` |
| `anchor.generator.drift.calibration_interval_days` | 7.0 | days | `hypothesis_prior` |
| `anchor.generator.death.biomass_death_threshold_log_sd` | 0.10 | log-ratio | `hypothesis_prior` |
| `anchor.generator.death.injury_death_threshold_log_sd` | 0.10 | log-ratio | `hypothesis_prior` |
| `anchor.generator.death.sustained_injury_duration_log_sd` | 0.10 | log-ratio | `hypothesis_prior` |
| `anchor.generator.missingness.missingness_intercept` | -3.0 | logit | `hypothesis_prior` |
| `anchor.generator.missingness.missingness_stress_slope` | 0.20 | logit per standardized-proxy SD | `hypothesis_prior` |
| `anchor.generator.missingness.mnar_tipping_delta` | 0.10 | logit per standardized-endpoint SD | `hypothesis_prior` |
| `anchor.generator.calibration.parameter_xtol` | 1.0e-6 | dimensionless primary-parameter units | `hypothesis_prior` |
| `anchor.generator.calibration.parameter_rtol` | 1.0e-6 | dimensionless | `hypothesis_prior` |
| `anchor.generator.calibration.objective_residual_tolerance_log_ratio` | 1.0e-6 | log-ratio | `hypothesis_prior` |
| `anchor.generator.calibration.max_iterations` | 100 | count | `hypothesis_prior` |
| `anchor.generator.calibration.fit_panel_size` | 64 | count | `hypothesis_prior` |
| `anchor.generator.calibration.holdout_panel_size` | 64 | count | `hypothesis_prior` |
| `anchor.generator.calibration.holdout_tolerance_log_ratio` | 0.020 | log-ratio | `hypothesis_prior` |
| `anchor.generator.design.duration_days` | 84.0 | day | `hypothesis_prior` |
| `anchor.generator.design.confirmation_plants_per_group_reservoir` | 6 | count | `hypothesis_prior` |
| `scenarios[chassis_interaction].mechanism.candidate_chassis_mechanism_modifiers.C5.xylem_na_retrieval_multiplier.factor` | 0.80 | dimensionless | `hypothesis_prior` |
| `scenarios[delayed_toxicity].mechanism.onset_time_days` | 42.0 | days | `hypothesis_prior` |
| `scenarios[delayed_toxicity].mechanism.post_onset_biology_parameter_overrides.senescence_h_inv` | 0.06 | h^-1 | `hypothesis_prior` |
| `scenarios[sensor_drift_missingness].generator.drift.calibration_interval_days` | 14.0 | days | `hypothesis_prior` |
| `scenarios[insufficient_purge].generator.water_loop.purge_volume_l_day` | 0.12 | L day^-1 | `hypothesis_prior` |

## 17. B20 — prospective C2 known-effect registration

### 17.1 Target, template, and solver

| Field | Registered value |
|---|---|
| `schema_version` | `1.0.0` |
| `candidate_id` | `C2` |
| `primary_parameter_id` | `ros_clearance_multiplier` |
| `effects_template.candidate_id` | `C2` |
| `effects_template.schema_version` | `1.0.0` |
| `effects_template.parameters.ros_clearance_multiplier` | 1.000000 dimensionless |
| `effects_template.parameters.redox_growth_penalty` | 0.015 h^-1 |
| `effects_template.evidence_label` | `hypothesis_prior` |
| target statistic | Paper 1 primary green-canopy-area AUC salt-by-construct interaction `delta[C2]` |
| `target_delta_log_ratio` | `log(1.30) = 0.26236426446749106` log-ratio |
| bracket | `[1.000000, 4.000000]` dimensionless |
| solver | `scipy.optimize.brentq` |
| parameter `xtol` | 1.0e-6 dimensionless |
| parameter `rtol` | 1.0e-6 dimensionless |
| objective residual tolerance | 1.0e-6 log-ratio |
| max iterations | 100 |
| fit/holdout panels | 64 / 64 |
| holdout tolerance | 0.020 log-ratio |
| SciPy version | 1.18.0 |
| registration evidence | `synthetic_only`; nested effect-template values remain `hypothesis_prior`; forcing panels and later generated rows are `synthetic_only` |

Section 20.9.2 defines `AUC`, `mu = log(AUC)`, exact four-cell difference-in-differences, `math.fsum` panel aggregation, positivity, endpoint-root handling, and separate fit/holdout residual checks. No direct AUC value, fitted multiplier, or solver result appears in the registration fixture. The trade-off remains fixed while `m` varies. Evaluate both bracket endpoints once. If they are non-finite or do not bracket a sign change or exact endpoint root, fail; do not widen, search, redraw, switch candidate, or edit the target. Brent’s method, its bracket requirement, and its combined parameter-space tolerance are documented by the [official SciPy reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.brentq.html). C2 is chosen prospectively because its registered primary multiplier maps relatively directly to the surrogate ROS-clearance leaf; that is a software-identifiability rationale, not a biological-effect claim or a guarantee that the bracket closes.

### 17.2 Frozen panel materialization

Use root seed `420260813`. Invoke `SeedSequence(420260813).spawn(12)` exactly once and take child 11 as the calibration family. Invoke `.spawn(2)` on that child; child spawn key `(11,0)` is fit and `(11,1)` is holdout. Use NumPy `2.5.2`, `Generator(PCG64(child))`, and exactly one C-order call `standard_normal((128,4,232))` per panel kind. Variable order is `[temperature, APAR, matric_potential, potential_transpiration]`; 232 equals 64 burn-in plus 168 retained steps. The registered 32-, 64-, and 128-panel artifacts are the literal leading panel-index prefixes `0..31`, `0..63`, and `0..127` of this one 128-panel family; smaller artifacts are never redrawn. NumPy documents reproducible parallel stream construction with `SeedSequence` spawning ([parallel random-number generation](https://numpy.org/doc/stable/reference/random/parallel.html); [`SeedSequence`](https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.SeedSequence.html)). NumPy does not promise version-stable transformed normal variates, so the NumPy version, bit generator, algorithm, prefix rule, and hashes are all part of this registration.

For each panel and variable, initialize anomaly zero and apply §5 in step order; potential transpiration uses phi zero. Discard the first 64 values, pair the retained 168 anomalies with the nominal schedule, and share each panel’s climate path across the two waters. Order output records by panel index, then `[nonsaline_nutrient_matched_control, pilot_selected_full_ion_marine_challenge]`, then step index.

The exact outer/record/nested schemas, types, order, sample records, and canonicalization are in Section 20.9.3. They set schema 1.1.0, algorithm `paper1_calibration_forcing_panel_v2`, PCG64, NumPy 2.5.2, explicit `forcing_schema_version`, 32/64/128 fixed-prefix panels, two water IDs, and 10,752/21,504/43,008 records per kind. The 64-panel artifacts are the immutable primary registration; 32 and 128 are S031-only artifacts and cannot silently replace primary.

| Panel artifact | Spawn key | Records | SHA-256 | Authority |
|---|---|---:|---|---|
| fit-32 | `(11,0)` | 10,752 | `8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3` | S031 sensitivity only |
| holdout-32 | `(11,1)` | 10,752 | `80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a` | S031 sensitivity only |
| fit-64 | `(11,0)` | 21,504 | `4e32c2831ea039c5a1939aed19091160f9c8c112d99a9e2bc937f05539b51eaf` | **primary** |
| holdout-64 | `(11,1)` | 21,504 | `d1f5b6b185458f50f6453391065e6af970ce5069921507431ce46fede0f9ca5a` | **primary** |
| fit-128 | `(11,0)` | 43,008 | `91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9` | S031 sensitivity only |
| holdout-128 | `(11,1)` | 43,008 | `3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11` | S031 sensitivity only |

These are hashes of prospectively materialized exogenous forcing payloads, not hashes of calibration outcomes. The range audit is descriptive validation of those payloads and contains no plant outcome. Adoption requires an independent implementation to reproduce both hashes exactly before any solver call.

## 18. Source and local-input ledger

### 18.1 Authoritative external references actually consulted

Only primary, official, or authoritative extension materials were used: USDA ARS water-quality guidance; UC/California Agricultural Experiment Station’s Hoagland-Arnon archive; the Almond Board/UC ANR salinity guide; US EPA detection/quantitation guidance; NIST’s AR(1) reference; official SciPy and NumPy manuals; and PubChem compound records linked near the relevant claims. Access date: 2026-08-13. No hash is asserted for a web representation because its retrieved bytes were not frozen as a local source artifact. The missingness coefficients and selection-model construction are code-owned synthetic choices, not claims derived from an external missing-data paper.

### 18.2 Exact SHA-256 for local source material read

| Local source | SHA-256 |
|---|---|
| `task-4-contract-repair-plan.md` | `b8a8c5cb53390946e56c10f1b5cf80fdc05448b4ba6421feca87f157fadef23e` |
| `task-4-preflight-addendum.md` | `b337bf3e2012e0d92fb5431757cc0fae7d9b15a9e5a49c7ac2364d12bfd2657c` |
| `2026-08-12-saltwater-mini-almond-program-design.md` | `53ab0c973a05a36014555fd855b8201adb4fe9bab1b4641837524adf1c9f0c79` |
| `configs/experiment_paper1.yaml` | `d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0` |
| `configs/synthetic_scenarios.yaml` | `46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb` |
| `configs/candidates.yaml` | `f4eb6c496ddfce2fb7077db34a03e6836da2cd4c62ad21d504b0227a277c5a05` |
| `configs/model_domains.yaml` | `81bf2c2c442d07ec984010dd9c373d2da4fe776467b009246cd665609c159a71` |
| `configs/thresholds.yaml` | `8db94ecd637aac57b6f76d0d89dc9b68d90de59e1535cdaf8781a2714c4c7140` |
| `tests/fixtures/candidate_effects.yaml` | `4e92c1567227b9e1f6e0713b79890bfc652a5b21a8de013769eaaa01ac939c21` |
| `src/almondlab/paper1_contracts.py` | `69bf97ffa65668715a76197a43c86ebe61960fcff05bd18b65bace254bad0b19` |
| `src/almondlab/biology_surrogate.py` | `8030cd84c89b8b3d9deb82904de26d4adc5cde68383e0b1b805ab4473b1cc268` |
| `src/almondlab/domains.py` | `1af62ef6e673af7ac400707e7404e889d1fe071bea55e1c5d90240a8de199b76` |
| `src/almondlab/chemistry.py` | `0a3b45ea2c5a1eb3fce1babfb01466d7ca1604237c07d188a126366a2ce26e1a` |
| `src/almondlab/schemas.py` | `d61fad98148b35401ffaa5303925c82dbdaf2debcd8cc6a06216781684ef8188` |
| `src/almondlab/contracts.py` | `4d111c69fa8ac4b2399a04a8177b3c2931a3d5f9c070b25a86c43f91ab1d2992` |

These hashes identify the material consulted; they do not claim that the proposal has already been implemented in those files.

## 19. Acceptance gates and unresolved dependencies

B01–B20 have a proposed numeric, unit, label, boundary, and failure-policy resolution. They remain unresolved operationally until all of the following occur:

1. The protocol owner and independent reviewer explicitly approve or amend this prospective proposal before any Task 4 config, fixture, or outcome is generated.
2. Task 3 is independently approved and committed at
   `d242473269803fa16461f78e8784813272912fbb`; implementation must pin that
   exact API/source authority and construct actual canonically revalidated
   cohort bundles.  This proposal does not invent or modify Task 3 artifacts.
3. New recipe, generator, scenario, domain, endpoint, censoring, drift, death, missingness, calibration, and known-effect contract models, migrations, loaders, and validators are implemented and reviewed.
4. A clean independent materializer reproduces the nominal schedule, operator-event, fit-panel, and holdout-panel hashes exactly under the registered canonicalization and NumPy runtime.
5. The installed package lock and wheel/mirror tests are frozen. In particular, NumPy 2.5.2 and the solver runtime must be available without silently substituting another normal transform or solver behavior.
6. The program design’s cited example subsections §11.1–§11.3 were not present in the source read for this proposal; subsection-level traceability cannot be asserted until the owner resolves that documentary mismatch.
7. Any physical use remains blocked until institution-specific review and pilot analytical measurements validate actual reagent identity/purity, preparation, EC, osmolality, pH, total alkalinity/speciation, ion concentrations, LOD/LOQ, containment, compatibility, exposure, and disposal. Failed pilot criteria require a prospective amendment, never a retrospective outcome-preserving tweak.

Until those gates pass, the correct interpretation is: **prospective synthetic registration proposal awaiting independent re-review, not an accepted protocol and not empirical almond evidence.**

---

## 20. Normative independent-review repair

### 20.1 Retired clauses and replacement authority

The following values and interpretations in Sections 3–19 are withdrawn, not
deprecated aliases:

| Retired item | Replacement in this section |
|---|---|
| `water_batch_volume_l = 250.0`, runtime rollover IDs, and the mistaken one-batch-per-loop interpretation | preserve every Task 3 shared `water_batch_id`; one 5,000.0-L source inventory is aggregated by exact `(cohort_id, water_batch_id)` with no rollover |
| irrigation-first daily event order | sample, when scheduled, before the same-day event; then external feed, irrigation, drainage return, purge, closure |
| chemistry perturbation keyed to transformation batch | one `M_ion` and one `M_B` keyed to physical `water_batch_id` |
| generic `concentration_mmol_l.maximum = 4.0` | versioned analyte × compartment × phase applicability in Section 20.5 |
| one forcing sequence per calibration kind or a hard-coded 64-only materializer | explicit fixed-prefix 32/64/128-panel × 2-water × 168-step fit and holdout artifacts, with 64 primary |
| `absolute_tolerance_log_ratio` as a Brent parameter tolerance | dimensionless `parameter_xtol`; separate log-ratio objective-residual tolerance |
| reset-at-observation B18 drift | phase-offset calibration epochs that give nonzero elapsed drift at registered observations |
| H3 observations at day zero for cumulative-AUC endpoints | terminal day-84 H3 view; no logarithm of a zero AUC |
| old canonical artifacts | nominal `0e7256…`, operator `a75178…`, fit `613460…`, holdout `3c3559…` are invalid and must fail a stale-hash check |

No compatibility loader may accept a retired item.  A document containing both
a retired and replacement authority fails `REGISTRATION_AUTHORITY_CONFLICT`.
All values in this section remain `hypothesis_prior`; every materialized row
remains `synthetic_only`.

### 20.2 B01–B03 physicalization and acid/base accounting

The ion table in Section 3 is a **formula-resolved synthetic target**, not a
physical preparation protocol.  The amounts of KHCO3 and KH2PO4 are sufficient
to reproduce the software convention's registered analyte totals, but they do
not uniquely fix pH 6.50 and analytical total alkalinity 1.000 mmol_c/L.  The
software charge convention is a diagnostic convention and is not an acid-base
speciation model.  No unlisted acid, base, counterion, dilution water, density
correction, or final-volume adjustment may be inferred.

Accordingly, both active records use:

```text
preparation_basis = formula_resolved_synthetic_target
physicalization_status = blocked_pending_batch_specific_titration_revision
```

The registered `ph = 6.50` and `alkalinity_mmol_c_l = 1.000` are synthetic
state coordinates only.  They are not said to result from the listed masses.
A physical recipe revision must contain all of these exact fields before a
batch can be prepared:

```text
titration_protocol_id
titrant_reagent_id
titrant_formula
titrant_stock_concentration_mol_l
titrant_density_kg_l_or_null
titrant_lot_id
titrant_actual_volume_l
titrant_actual_amount_mol
counterion_contributions_mmol_l
water_contribution_l
pre_titration_volume_l
final_volume_l
final_volume_adjustment_water_l
measured_ph
measured_temperature_k
measured_total_alkalinity_mmol_c_l
measured_complete_ion_panel
post_titration_charge_balance_error_percent
evidence_label
```

The exact titrant dose is a batch record, not a default: actual pH and
alkalinity vary with reagent purity, water, carbon dioxide exchange, and
temperature.  HCl changes chloride; HNO3 changes nitrate; KOH changes
potassium and alkalinity; NaOH changes sodium and alkalinity.  The selected
titrant's counterion and water must therefore be included in final-volume and
complete-ion accounting.  After titration, the software reconstructs a new
batch-specific chemistry, repeats the independent charge oracle and public
`charge_balance_error`, checks exact final volume, and calls domain validation.
It must not overwrite the synthetic target.  Until such a revision and
physical pilot are approved, `PHYSICAL_RECIPE_NOT_REGISTERED` is mandatory.

The limiting-conductivity numbers in Section 3.4 are frozen as descriptive
scratch checks only and are not configuration.  Their constants may not be
copied into production.  Any implemented conductivity model requires a new
versioned method, temperature convention, constants with provenance, and
validation data; otherwise EC remains a registered or measured field.

### 20.3 B07 one-batch loop and canonical daily event order

#### 20.3.1 Physical identity and capacity

Each Task 3 physical `(cohort_id, run_id, water_id, reservoir_id)` loop has
exactly one predeclared `water_batch_id` already present in the approved Task 3
position map/manifest.  The generator may not construct, suffix, increment,
roll over, replace, or split that ID.  Task 3 intentionally reuses one such
physical ID across four discovery loops or six confirmation loops: in the
registered discovery position map it is shared by the four reservoirs in one
`run_id × water_id` cell, and in the registered confirmation map it is shared
by all six reservoirs for one `water_id` across the later runs.  This is one
shared source inventory, not four or six relabelled batches.

Every source debit is therefore accumulated by exact
`(cohort_id, water_batch_id)`, with the cohort key preventing cross-cohort
aliasing.  Each unique key has a prospectively registered capacity of exactly
5,000.0 L.  The initial fills and daily makeups of every loop carrying that
key debit that single inventory.  The terminal day-84 sample debits the
reservoir only and is not restored from the source.  There is no second batch,
per-loop shadow balance, runtime ID, or partial rollover transaction.

The physical `water_batch_id` also keys the chemistry draws in Section 20.4.
It is distinct from `transformation_batch_id` and `assay_batch_id`.

#### 20.3.2 Initial fill and initial solutes

Let `V0 = generator.water_loop.reservoir_initial_volume_l`; the anchor has
`V0 = 120.0 L`, while sensitivity S013 supplies 100.0 or 140.0 L.  At
`t = -0.25 day`, before any plant integration or observation, one
`external_feed_amendment` transaction per loop debits exactly `V0` from its
shared 5,000.0-L source batch and credits that loop reservoir.  For every
tracked aqueous analyte `j`, the paired amount is exactly

`V0 × C_batch[j] mmol/L`.

`C_batch[j]` is the batch-specific perturbed chemistry in Section 20.4, not
the unperturbed recipe and not an EC-derived concentration.  The initial
reservoir state is therefore `V0` with exactly those paired analyte stocks.
No treatment, uptake, reaction, evaporation, purge, or hidden top-up occurs
between `t = -0.25` and the day-zero sample.

The per-plant one-litre `root-zone` objects in the current surrogate are
normalized computational initial conditions, not additional source-batch
withdrawals.  At `t = 0`, their Na, Cl, and K concentrations are set to the
assigned `C_batch` values and their stocks are concentration × 1.0 L; their
initial-state provenance records the same recipe and `water_batch_id`.  This
is an explicit synthetic abstraction, not a literal physical equilibration
claim.  Because it does not provide a physical pre-study media-charging
ledger, physical use remains blocked until a separate protocol registers
media pore volume, preparation feed, drainage, equilibration duration, and
the paired initial-stock transfers.  The synthetic generator must still
include these initial root-zone stocks in `DeltaS_total` and may not count
them as an experimental-period external input.

#### 20.3.3 Samples and operator events

Reservoir samples occur at exact days `[0, 14, 28, 42, 56, 70, 84]`, each
0.050 L.  Samples on days 0–70 occur before that day's operator event at
`d + 0.25`.  The day-84 sample is terminal and occurs after the last operator
event at day 83.25; there is no day-84 makeup event.

Let `V0 = generator.water_loop.reservoir_initial_volume_l`,
`i = irrigation_volume_l_per_plant_day`, `r = drainage_return_fraction`,
`P = purge_volume_l_day`, and `s = sampling_volume_l_per_sample`; anchor values
are 120.0 L, 0.60 L plant^-1 day^-1, 0.70, 1.20 L, and 0.050 L.  Let
`V_event_start` be reservoir volume after a same-day sample, if any;
`N_assigned` is the frozen number of positions in the Task 3 loop and never
falls after death; `I = i × N_assigned` L and `R = r × I` L.  Calculate,
before mutating state,

`M = V0 - (V_event_start - I + R - P)` L.

Equivalently, for the anchor and a day without a sample,
`M_d = 0.18*N_assigned + 1.20` L.  On the six restored sample days
`d in {0,14,28,42,56,70}`, the sample occurs first and
`M_d = 0.18*N_assigned + 1.20 + s` L.  The day-84 terminal sample has no
operator event and contributes no source debit.

Each event at `d + 0.25`, for integer `d = 0,…,83`, then executes exactly:

1. debit `M` and its complete solute vector from the predeclared source batch,
   credit the reservoir, and fail if source remaining would become negative;
2. debit `I` and its complete solute vector from the reservoir for irrigation;
3. credit `R` and mechanistically returned solutes to the reservoir;
4. debit `P` and its current-reservoir solute vector to captured purge;
5. run numerical volume/entity closure and require reservoir volume exactly
   `V0` within the registered numerical tolerance.

Treatment/blending, evaporation/transpiration, layer drainage, plant
transitions, and reaction phases may have internal ledger rows between steps
2 and 3, but no second external feed is permitted and the externally visible
order above cannot change.  Sample, purge, irrigation, and return use current
reservoir concentrations; external makeup uses `C_batch`.  Expected
transactions are constructed from this schedule before execution and are not
reconstructed from results.

The exact anchor source demands are:

| Design case | `N_assigned` per loop | Initial fill | 84 base makeups | 6 restored samples | Source demand per loop |
|---|---:|---:|---:|---:|---:|
| discovery, 9 groups × 5 | 45 | 120.00 | 781.20 | 0.30 | **901.50 L** |
| maximum confirmation, 4+EV × 6 | 30 | 120.00 | 554.40 | 0.30 | **674.70 L** |
| maximum confirmation, 4+EV × 5 | 25 | 120.00 | 478.80 | 0.30 | **599.10 L** |

For arbitrary registered water-loop values, the per-loop identity is
`V0 + 84 × [i*N*(1-r)+P] + 6*s`.  The terminal sample is a
seventh reservoir withdrawal but not a source makeup.  After it, reservoir
volume is exactly `V0 - s` (119.95 L in the anchor).

The aggregate preflight groups manifest loops by unique
`(cohort_id, water_batch_id)`, verifies that every grouped loop has the same
registered water and chemistry identity, and computes the expected debit with
`math.fsum` in canonical loop order before RNG or output.  The registered
worst-case checks are:

| Shared Task 3 batch case | Loops sharing the ID | Aggregate debit | Remaining from 5,000 L |
|---|---:|---:|---:|
| discovery, 45 plants/loop | 4 | **3,606.00 L** | **1,394.00 L** |
| maximum confirmation, 30 plants/loop | 6 | **4,048.20 L** | **951.80 L** |
| maximum confirmation, 25 plants/loop | 6 | **3,594.60 L** | **1,405.40 L** |

Any unique `(cohort_id, water_batch_id)` whose aggregate expected debit
exceeds 5,000.0 L fails `WATER_BATCH_CAPACITY_EXCEEDED` before RNG or output.
A per-loop capacity check is insufficient and prohibited.

The exact operator-time artifact remains schema 1.0.0 and hashes to
`33ab36479f1500aef066b0f495010ff73ea86c8a4a8c4c2bac78603deb8da224`.
The separately registered sample artifact hashes to
`5fc3952a1b60b5282a97543577b0ff6aaac6463b654cc5ba9fd59748d1ffae14`.
Both were reproduced twice by the saved materializer in Section 20.11.

### 20.4 B05–B06 hierarchy and chemistry equations

#### 20.4.1 Executable hierarchy effects

The four configured quantities are variances, not SDs.  To remove all
parameterization ambiguity, draw independent unit normals first and transform
them explicitly before state integration:

```text
Z_run[r], Z_batch[transformation_batch], Z_reservoir[c,r,w,q],
Z_plant[plant_id] ~ StandardNormal independently
u_run[r]                      = sqrt(run_variance)       * Z_run[r]
u_batch[transformation_batch] = sqrt(batch_variance)     * Z_batch[transformation_batch]
u_reservoir[c,r,w,q]          = sqrt(reservoir_variance) * Z_reservoir[c,r,w,q]
u_plant[plant_id]             = sqrt(plant_variance)     * Z_plant[plant_id]
H_i = u_run + u_batch + u_reservoir + u_plant
RUE_i = RUE_anchor * exp(H_i)
```

Here `(c,r,w,q)` is the exact `(cohort_id, run_id, water_id, reservoir_id)`
key.  The run key is `(cohort_id, run_id)`; transformation-batch and plant
keys are their immutable physical IDs.  Each key is sorted canonically and
drawn once from its named Task 4 stream.  The values modify only
`radiation_use_efficiency_g_mol_apar_inv` on a detached per-plant parameter
object.  Construction order is: canonical scenario baseline, registered
scenario mechanism override, hierarchy RUE multiplier, then candidate-effect
application.  The effects exist before the first integration step and are
constant for the trajectory.  They never edit canopy, AUC, death, a decision,
or an observation directly.  Calibration panels set all four hierarchy draws
to exactly zero, so they identify the registered mechanism rather than a
nuisance realization.

The log multipliers have mean zero; no `-variance/2` mean correction is used.
Thus the old statement that finite burn-in or this construction exactly
preserves a realized sample mean is withdrawn.  The climate lognormal
correction preserves the distributional expectation conditional on the
specified stationary variance, not the mean of any finite 64-step burn-in or
panel.

#### 20.4.2 Chemistry key and transaction use

For each physical Task 3 `water_batch_id`, and only once for that ID, draw

```text
M_ion = exp(0.03 * Z_ion - 0.5 * 0.03^2)
M_B   = exp(0.08 * Z_B   - 0.5 * 0.08^2)
```

from the chemistry stream keyed by `(cohort_id, water_batch_id)`.  `M_ion`
multiplies Na, Cl, Ca, Mg, K, sulfate, nitrate, phosphate, bicarbonate, and
alkalinity together.  `M_B` multiplies total B only.  The challenge NaCl
increment is already part of its recipe and receives the same `M_ion`; it does
not receive an independent perturbation.  This exact construction preserves
the registered software charge convention.  Every initial fill, makeup, and
root-zone initial chemistry uses the resulting `C_batch`.  A transaction may
not relabel the batch or redraw chemistry.

EC, osmolality, pH, and temperature errors remain observation-only.  They do
not alter `C_batch`, transaction solute amounts, mechanistic forcing, or the
domain input.  A water-batch public row contains its predeclared
`water_batch_id`, recipe/revision, both multiplier audit hashes (not hidden Z
values), complete latent chemistry in private truth, measured view, and
domain-validation reference.

### 20.5 B10 and physical-stop applicability

#### 20.5.1 Versioned physical-stop policy

The generic concentration stop in the currently committed
`configs/thresholds.yaml` is not applicable to incoming challenge water.  It
is migrated, without changing its 4.0 value, to
`paper1_task4_stop_policy@1.0.0` with this literal applicability set:

```text
analyte_ids = [na, cl, k]
compartment_kinds = [root_apoplast, root_symplast, root_vacuole,
                     xylem, shoot_tissue]
phase_ids = [initialization, state_transition, terminal]
maximum = 4.0
unit = mmol L^-1
boundary = stop when value > maximum; equality is accepted
```

It does not apply to source water, irrigation reservoir, root zone,
drainage/return, treatment, condensate, or concentrate compartments.  Those
locations remain governed by exact recipe/domain validation, nonnegative
stocks, ledger closure, and their own explicitly applicable policies.  An
absent applicability triple means **not applicable**, not infinity and not a
waived check.  The validator requires exact `(policy_id, analyte_id,
compartment_kind, phase_id)` lookup and records the matched rule or explicit
non-applicability.  This preserves every root/tissue stop while avoiding the
invalid conclusion that a 44 mmol/L registered feed has already crossed a
tissue threshold.

The other v1 physical stops are also versioned with literal scope:

| Rule | Applicability | Boundary |
|---|---|---|
| ECw 10.0 dS/m | source/reservoir measured ECw, all operational sample phases | stop above; equality accepted |
| osmolality 0.40 osmol/kg | mechanistic water forcing, all integration phases | stop above; equality accepted |
| loop-compartment volume 0.1–1,000.0 L | irrigation reservoirs, root-zone and other non-source physical aqueous compartments only | stop outside; both boundaries accepted |
| shared source-batch volume 0.0–5,000.0 L | the exact predeclared `(cohort_id, water_batch_id)` source inventory only | stop outside; both boundaries accepted; aggregate debit preflight applies |
| injury 1.0 | plant state transition/terminal | stop above; equality accepted |
| containment discharge 0.0 L | external unauthorized-discharge ledger category | any positive amount stops |

The 1.0 injury stop remains separate from the Task 2 death threshold 5.0; the
former is a valid censored physical-stop trajectory and the latter is the
surrogate death rule.  An implementation must not silently choose one based
on outcome.

#### 20.5.2 Assay applicability and public censor vocabulary

LOD/LOQ values are looked up by exact
`(assay_policy_id, endpoint_id, matrix_compartment_id, assay_phase_id)`, where
`assay_policy_id = paper1_synthetic_assay@1.0.0`.  The registered triples are:

| Endpoint | Matrix compartment | Phase | Limit applicability |
|---|---|---|---|
| `green_canopy_area` | `shoot_tissue` | `longitudinal` | uncensored |
| root-zone Na/Cl/K concentration | `root_zone` | `longitudinal` | corresponding Section 9 limits |
| `xylem_sap_na_concentration` | `xylem` | `longitudinal` | Section 9 limit |
| `drainage_total_b_concentration` | `drainage_return` | `longitudinal` | Section 9 limit |
| root-surface Na flux | `root_surface` | `terminal` | Section 9 limit |
| root H2O2 AUC | `root_symplast` | `terminal` | Section 9 limit |
| root mannitol above EV | `root_symplast` | `terminal` | uncensored |
| xylem Na AUC | `xylem` | `terminal` | Section 9 limit |

No limit may be reused for another matrix or phase.  A physical assay requires
laboratory- and method-specific replacement values before use.

For each non-null limit, one standard-normal draw is keyed to
`(assay_batch_id, endpoint_id, matrix_compartment_id, assay_phase_id)` and is
shared by all samples in that exact assay batch.  It is not keyed to
transformation batch, water batch, or plant.  `assay_batch_id` must be listed
in a prospective sample manifest before observation RNG.  The immutable
sample key is exactly

```text
(cohort_id, plant_id, scheduled_time_days, endpoint_id, observation_type,
 assay_batch_id, matrix_compartment_id, assay_phase_id)
```

The same batch draw multiplies both LOD and LOQ, preserving their registered
ratio.  The exact public `censor_code` vocabulary is
`uncensored`, `below_lod`, `detected_below_loq`, `quantified`, and
`not_applicable`.  The exact representation is:

| State | `reported_value` | `censor_lower_bound` | `censor_upper_bound` | Interval semantics |
|---|---:|---:|---:|---|
| uncensored | finite | null | null | exact reported value |
| below LOD | null | null | LOD | `(-inf, LOD)` |
| detected below LOQ | null | LOD | LOQ | `[LOD, LOQ)` |
| quantified | finite | null | null | value `>= LOQ` |
| not applicable | null | null | null | missing or structurally undefined |

Equality at LOD is `detected_below_loq`; equality at LOQ is `quantified`.
Missingness is applied last.  If missing, value and both bounds are null and
`censor_code = not_applicable`; the counterfactual censor state remains
private.  The exact public `missingness_code` vocabulary is `not_missing`,
`scheduled_measurement_missing`, `technical_outage`, `assay_failure`,
`containment_termination`, and `not_applicable_postdeath`.  MAR versus MNAR is
not revealed publicly.  Death is never ordinary missingness.

The analyst observation schema in the addendum is prospectively versioned to
1.1.0 by inserting these required columns after `unit`:

```text
sample_id, assay_batch_id, sensor_id, calibration_epoch_id,
matrix_compartment_id, assay_phase_id, lod, loq,
censor_lower_bound, censor_upper_bound, censor_code,
missingness_code, death_status, qc_state
```

`death_status` is exactly `alive_at_sample`, `dead_canopy_zero`, or
`postdeath_undefined`; `qc_state` is exactly `accepted`, `censored`, `missing`,
or `postdeath`.  Nullability and controlled vocabularies are schema rules, not
free-text conventions.

### 20.6 B08, H3 terminal semantics, MNAR matching, and event boundaries

#### 20.6.1 Observation schedules

The canopy and ion schedules in Section 8 remain exact.  The generic H3 list
is replaced by an endpoint-keyed schedule:

```text
root_surface_outward_na_flux_per_root_dry_mass: [84.0]
root_h2o2_concentration_time_auc: [84.0]
root_mannitol_concentration_above_empty_vector: [84.0]
xylem_sap_na_concentration_time_auc: [84.0]
```

All four endpoints are now executable from existing `SimulationResult`
state/diagnostic quantities plus exactly two prospectively registered
synthetic measurement-link constants:

```text
generator.observation.h3_measurement_links.root_dry_matter_fraction
    = 0.20 dimensionless, hypothesis_prior
generator.observation.h3_measurement_links.
    h2o2_umol_g_root_fresh_mass_inv_per_ros_dimensionless
    = 1.0 umol H2O2 g_root_fresh_mass^-1 per ros_dimensionless,
      hypothesis_prior
```

These constants are synthetic assay mappings, not measured conversion factors,
almond allometry, or physics constraints.  A physical assay must replace them
with validated tissue mass and calibration records; the physical-use block
below remains.  The H2O2 link is required even though it cancels in a pure
candidate/EV ratio, because absolute censor limits and serialized endpoint
values do not cancel it.

For each canonical state `s`, define the synthetic root-mass convention

```text
root_dry_mass_g(s)
  = (1 - BiologyParameters.leaf_allocation_fraction) * s.biomass_g
root_fresh_mass_g(s)
  = root_dry_mass_g(s) / root_dry_matter_fraction
```

Both masses must be finite and strictly positive whenever an H3 value uses
them.  `leaf_allocation_fraction` must be in `[0,1)` for this endpoint view;
no epsilon, absolute value, clipping, or alternate biomass fraction is
allowed.  This is a synthetic interpretation of the existing state scalar,
not a new plant state or empirical root/shoot model.

The canonical time authority is `SimulationResult.states` from the accepted
coarse trajectory.  It must contain one state at every registered 0.25-hour
substep, begin at exactly `0.0 h`, end at exactly
`84.0*24.0 = 2016.0 h`, and have strictly increasing `time_hours` with exact
adjacent difference `0.25 h`.  Let `(t_i,y_i)` be those ordered nodes.  Every
cumulative endpoint uses hours directly and exactly

```text
trapezoid_auc(t,y)
  = math.fsum(0.5*(y_i + y_(i+1))*(t_(i+1)-t_i)
              for i in range(len(t)-1))
```

with terms supplied in increasing `i`.  No day-valued abscissa, interpolation,
endpoint duplication, NumPy reduction, or observation schedule may replace
this grid.  The endpoint definitions are:

1. `root_surface_outward_na_flux_per_root_dry_mass`: flatten
   `SimulationResult.intervals` and each interval's ordered `.steps`.  Select
   exactly diagnostics whose closed step lies in terminal hours
   `[1992.0,2016.0]`, using
   `start_time_hours >= 1992.0` and
   `start_time_hours + duration_hours <= 2016.0`; require their ordered
   durations to `math.fsum` to exactly `24.0 h`.  The only numerator is the
   nonnegative `BiologyStepDiagnostics.applied_na_efflux_mmol_h`, which is the
   actually applied `plant_efflux` transfer from root symplast to root zone.
   Outward sign is therefore explicitly positive.  Compute
   `mean_rate_mmol_h = math.fsum(rate*duration)/24.0`, then
   `1000.0 * mean_rate_mmol_h / root_dry_mass_g(final_state)` to obtain
   `umol Na g_root_dry_mass^-1 h^-1`.  Do not use requested efflux, a stock
   difference, an absolute flux, or the opposite sign.
2. `root_h2o2_concentration_time_auc`: at every state node set
   `y_i = h2o2_scale * s_i.ros_dimensionless` in
   `umol H2O2 g_root_fresh_mass^-1`; apply the exact trapezoid above to obtain
   `umol H2O2 g_root_fresh_mass^-1 h`.
3. `root_mannitol_concentration_above_empty_vector`: at the exact final state
   set `Y = 1_000_000.0 * s.mannitol_mmol / root_fresh_mass_g(s)` in
   `nmol g_root_fresh_mass^-1`.  Return the candidate `Y` minus the exact
   matched-EV arithmetic mean defined in Section 20.6.2; this endpoint is a
   terminal difference and is not integrated.
4. `xylem_sap_na_concentration_time_auc`: at every state node locate the
   unique `NetworkState` compartment whose kind is exactly `xylem`, require
   positive `volume_l`, and set
   `y_i = stocks[ConservedEntity.NA] / volume_l` in `mmol Na L^-1`; apply the
   exact trapezoid to obtain `mmol Na L^-1 h`.  No shoot stock, root stock,
   flow-weighting, or EC-to-Na conversion is permitted.

All source states, diagnostics, compartments, stocks, rates, times, masses,
node values, products, and final values must be finite.  Every log-scale H3
value must be strictly positive before drift/error or any logarithm; failure,
a missing/duplicate xylem compartment, incomplete terminal window, or an
invalid grid raises `H3_ENDPOINT_UNDEFINED`.  No epsilon or empirical-looking
fallback is allowed.  The two cumulative endpoints are emitted only at day
84; they are not emitted as zero at day 0.  If the plant is dead before day
84, every terminal ion/H3 value is structurally undefined and
survivor-conditional; no partial AUC or post-death mass substitution is used.

Root harvest, destructive tissue chemistry, and repeated root assays can
alter the whole-plant unit.  This synthetic terminal schedule assumes one
endpoint harvest after the day-84 canopy image and reservoir sample.  It does
not authorize repeated destructive sampling.  A physical protocol must prove
whether each assay is non-destructive or allocate a separately randomized,
powered destructive-harvest cohort outside the 720 primary plants.  Until
that choice is registered, physical H3 sampling fails
`DESTRUCTIVE_SAMPLING_PROTOCOL_REQUIRED`.

#### 20.6.2 Exact MNAR selection model

The Section 12 construction is a **selection model**, not a pattern-mixture
model.  For a candidate observation, its matched empty-vector reference set
contains exactly the defined EV latent rows with identical

```text
(cohort_id, run_id, water_id, reservoir_id, scheduled_time_days, endpoint_id)
```

after hierarchy/mechanistic simulation and before drift, error, censoring, or
missingness.  The matched EV reference is the `math.fsum` arithmetic mean on
the native endpoint scale, divided by the exact count.  Transformation batch,
position, and plant ID are not matching keys.  There must be at least one
defined matched EV row.  For log-scale scores, every candidate and matched-EV
value must be strictly positive before taking a log.  Missing match,
nonpositive log input, or undefined EV terminal endpoint fails
`MNAR_MATCH_INVALID`; it is not imputed or replaced by an epsilon.

The hidden score formulas in Section 12 then use that exact matched mean.  C3
uses the native candidate-minus-matched-EV difference.  Empty-vector rows use
hidden score zero.  The public row reveals only
`scheduled_measurement_missing`; hidden score, probability, and uniform remain
private.  This exact matching occurs separately in discovery and confirmation
and never crosses reservoirs, waters, runs, times, or endpoints.

#### 20.6.3 Day-42 and same-time event ordering

At any time shared by state integration, calibration, observation, scenario
onset, and operator events, the order is:

1. integrate the open interval ending at `t` under the pre-event parameters;
2. apply any sensor calibration whose boundary is exactly `t`;
3. take scheduled plant/reservoir observations at `t`;
4. apply a scenario mechanism onset at `t` for subsequent intervals;
5. execute an operator event only if its registered time is exactly `t`.

Thus the delayed-toxicity day-42 observation is a left-limit/pre-onset
observation.  The `senescence_h_inv = 0.06 h^-1` override governs intervals
with `t > 42.0`; it does not retroactively change the day-42 sample.  This
replaces the ambiguous `t >= 42` wording in Section 14.

### 20.7 B11/B18 sensor, epoch, and nonzero-drift contract

Each row has a prospectively determined `sensor_id` before drift RNG:

```text
canopy:  CANOPY::<cohort_id>::<run_id>
assay:   ASSAY::<assay_batch_id>::<endpoint_id>
```

A physical protocol must replace these logical synthetic IDs with an actual
instrument assignment map before use.  The drift/reset draw key is exactly
`(sensor_id, endpoint_id, calibration_epoch_index)`.  It is never keyed only
to endpoint, day, plant, or observation ordinal.

For calibration interval `I`, phase offset `o`, and scheduled time `t`, define

```text
k = floor((t - o) / I)
epoch_start = o + k*I
elapsed = t - epoch_start
b(sensor,e,t) = eta(sensor,e,k) + drift_rate[e] * elapsed
calibration_epoch_id = CAL::<sensor_id>::<endpoint_id>::<k>
```

An exact boundary uses the new epoch (`elapsed = 0`) because calibration is
step 2 in Section 20.6.3.  `eta` is one post-calibration residual draw per
sensor × endpoint × epoch.  Every observation mapped to the same triple uses
the same `eta` plus its deterministic elapsed drift.

The zero-rate anchor has `I = 7.0 days` and `o = 0.0 days`.  The B18
`sensor_drift_missingness` scenario has `I = 14.0 days` and
`o = -7.0 days`, so calibration boundaries are `-7, 7, 21, 35, 49, 63, 77,…`
and observations at days `0, 14, 28, 42, 56, 70, 84` have exactly 7.0 days
of accumulated drift.  The nonzero rates in Section 15 therefore cannot be
reset to zero at every observation.  The B18 literal changed paths are:

```text
generator.observation.canopy_observation_error_sd
generator.missingness.missingness_stress_slope
generator.drift.calibration_interval_days
generator.drift.calibration_phase_offset_days
generator.drift.canopy_drift_per_day
generator.drift.ion_drift_per_day_by_endpoint.*
generator.drift.h3_drift_per_day_by_endpoint.*
generator.drift.post_calibration_residual_sd_by_endpoint.*
```

No other observation, missingness, biology, forcing, chemistry, or outcome
path is allowed.  This literal list reconciles the broader addendum class with
the exact scenario whitelist.

### 20.8 B04 self-contained forcing schema and regenerated hash

The normative nominal forcing payload has exact outer keys and types:

```text
schema_version: string, exactly "1.1.0"
materialization_algorithm: string, exactly "paper1_nominal_forcing_schedule_v2"
water_ids: array[string], exact registered two-water order
records: array[NominalForcingRecord], exactly 336 records
evidence_label: string, exactly "synthetic_only"
```

No additional key is accepted.  `NominalForcingRecord` has exactly:

```text
water_id: string
recipe_id: string
step_index: integer
start_hour: number serialized from an exact Python float
forcing: RootZoneForcingPayload
```

Records are ordered first by the displayed `water_ids`, then by
`step_index = 0,…,167`.  `start_hour = float(12*step_index)`.
`recipe_id` is exactly `paper1_base_nutrient_control_v1@1.0.0` or
`paper1_base_plus_nacl40_challenge_v1@1.0.0`, consistent with `water_id`.

`RootZoneForcingPayload` has exactly these keys/types:

```text
measured_osmolality_osmol_kg: number
temperature_k: number
water_density_kg_l: number
matric_potential_mpa: number
leaf_critical_potential_mpa: number
apar_mol_h: number
temperature_factor: number
potential_transpiration_l_day: number
duration_hours: number
evidence_label: string, exactly "synthetic_only"
hydraulic_domain: HydraulicDomainPayload
```

`HydraulicDomainPayload` has exactly:

```text
model_id="paper1-biology-v1"; version="1.0.0";
purpose="model_applicability"; osmolality_min=0.0;
osmolality_max=0.5; temperature_k_min=290.0;
temperature_k_max=305.0; permitted_evidence_label="physics_constrained";
extrapolation_policy="deny"
```

The first complete record, shown in canonical key order, is:

```json
{"forcing":{"apar_mol_h":0.8,"duration_hours":12.0,"evidence_label":"synthetic_only","hydraulic_domain":{"extrapolation_policy":"deny","model_id":"paper1-biology-v1","osmolality_max":0.5,"osmolality_min":0.0,"permitted_evidence_label":"physics_constrained","purpose":"model_applicability","temperature_k_max":305.0,"temperature_k_min":290.0,"version":"1.0.0"},"leaf_critical_potential_mpa":-1.8,"matric_potential_mpa":-0.08,"measured_osmolality_osmol_kg":0.02,"potential_transpiration_l_day":0.8,"temperature_factor":0.85,"temperature_k":297.15,"water_density_kg_l":0.9973},"recipe_id":"paper1_base_nutrient_control_v1@1.0.0","start_hour":0.0,"step_index":0,"water_id":"nonsaline_nutrient_matched_control"}
```

The complete payload is encoded by repository `canonical_json_bytes` and has
SHA-256
`329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96`.
The exact materializer logic is preserved in Section 20.11.  Missing/extra
keys, integers substituted for registered floats, different record ordering,
or another recipe/domain version changes the hash and fails.

### 20.9 B14–B15/B20 calibration dimensions, objective, and solver

#### 20.9.1 Explicit panel API

The corrected calibration interface is:

```python
def calibrate_mechanism_to_estimand(
    candidate: CandidateSpec,
    target_delta_log_ratio: float,
    baseline: BiologyParameters,
    initial_state: PlantState,
    effects_template: CandidateEffects,
    fit_panels: CalibrationForcingPanelBundle,
    holdout_panels: CalibrationForcingPanelBundle,
    lower: float,
    upper: float,
    *,
    parameter_xtol: float,
    parameter_rtol: float,
    objective_residual_tolerance_log_ratio: float,
    holdout_tolerance_log_ratio: float,
    max_iterations: int,
) -> MechanismCalibration: ...
```

`CalibrationForcingPanelBundle` requires exact fields
`schema_version`, `panel_kind`, `panel_size`, `water_ids`, `panels`,
`canonical_sha256`, and `evidence_label`.  `panels` is an exact tuple of `K`
`CalibrationForcingPanel` objects: 64 for the primary run and 32 or 128 only
for registered S031 runs.  Each panel has `panel_index` and
`forcings_by_water_id`; the latter has exactly the two registered water keys,
each mapped to exactly 168 ordered forcings.  For declared size `K`, panel
indices are exactly `0..K-1`, with no duplicates or gaps.  `K` must be exactly
32, 64, or 128.  The fit bundle must say `fit`, the holdout
bundle `holdout`, and their hashes must differ.  This explicit panel dimension
replaces the mapping-of-one-sequence API in the addendum/repair plan.

The runtime bundle and hashed artifact have an intentional, exact partition
that avoids a self-referential hash.  Section 20.9.3 defines the canonical
artifact payload and explicitly omits `canonical_sha256`.  Its canonical JSON
bytes are SHA-256 hashed; the resulting lowercase digest is then stored as the
runtime bundle's `canonical_sha256`.  Runtime `panels` are the exact typed
reconstruction of the artifact's ordered `records`.  Revalidation constructs
the Section 20.9.3 artifact payload from every runtime scientific/metadata
field except `canonical_sha256`, recomputes the digest, and uses constant-time
comparison with the stored digest.  The digest is never included in the bytes
it authenticates, and no document claims a self-containing bundle hashes to
itself.  Missing/extra artifact keys, a caller-authored digest, or any record
change fails `CALIBRATION_FORCING_INVALID`.

Primary calibration rejects any `K != 64`.  An S031 run must declare the
single sensitivity ID/value, use the same `K` for fit and holdout, and match
the exact registered prefix hashes in Section 20.9.3.  A 32/128 bundle without
S031 identity, a primary run with a sensitivity hash, independently redrawn
smaller panels, unequal fit/holdout sizes, or a caller-supplied hash fails
`CALIBRATION_FORCING_INVALID` before objective evaluation.

The registration fields are renamed and frozen as:

| Field | Value | Unit |
|---|---:|---|
| `parameter_xtol` | 1.0e-6 | dimensionless primary-parameter units |
| `parameter_rtol` | 1.0e-6 | dimensionless |
| `objective_residual_tolerance_log_ratio` | 1.0e-6 | log-ratio |
| `holdout_tolerance_log_ratio` | 0.020 | log-ratio |
| `max_iterations` | 100 | count |
| fit/holdout panel size | 64 / 64 | panels |
| SciPy runtime | 1.18.0 | exact locked version |

SciPy `brentq` receives `xtol=parameter_xtol`,
`rtol=parameter_rtol`, and `maxiter=max_iterations`.  Its parameter-space
stopping rule is the documented combined rule
`abs(x-x0) <= xtol + rtol*abs(x0)`; a log-ratio unit is not attached to
`xtol`.  After return, the objective is evaluated again and must satisfy the
separate objective-residual tolerance.  The holdout residual is evaluated
only after the fit gate passes.

#### 20.9.2 Exact AUC/estimand objective

For selected registered panel size `K`, each panel `p`, mechanism multiplier `m`, group `g in {C2, EV}`, and water
`w`, simulate from the same canonical initial state with all hierarchy effects
zero, batch chemistry multipliers one, no observation error, no drift, no
censoring, and no missingness.  Apply the C2 template with
`ros_clearance_multiplier=m` and fixed
`redox_growth_penalty=0.015 h^-1`; EV uses the canonical baseline.

At canopy days `[0,3,7,14,21,28,35,42,49,56,63,70,77,84]`, calculate

```text
AUC[g,w,p,m] = canopy_auc(days, canopy, pretreatment_canopy=canopy[0])
mu[g,w,p,m] = log(AUC[g,w,p,m])
delta[p,m] = (mu[C2,challenge]-mu[C2,control])
             - (mu[EV,challenge]-mu[EV,control])
f_K(m) = math.fsum(delta[p,m] for p in 0..K-1)/K - log(1.30)
```

Every pretreatment canopy and AUC must be strictly positive and finite before
the logarithm.  Primary B20 uses `K=64`; only S031 may use `K=32` or `K=128`.
This is guaranteed by eligibility, not by an epsilon.  Failure
raises the original biology/AUC error.  `math.fsum` and panel-index order are
mandatory; no group, water, or panel aggregation may be substituted.

Evaluate `f_K(lower)` and `f_K(upper)` once.  If either is exactly zero in binary64,
return that endpoint with zero solver iterations and boundary status `lower`
or `upper`; an exact endpoint root is accepted.  Otherwise require opposite
signs and run Brent.  Same-sign endpoints fail without widening, scanning,
redrawing, or candidate substitution.  An interior result is accepted only if
the solver converges and the recomputed fit residual is at most 1e-6 in
absolute log-ratio.  The independently computed holdout objective at that same
`m` must be within 0.020 log-ratio.  No solver result, fitted multiplier,
estimand, residual, rank, or pass flag appears in the registration fixture.

#### 20.9.3 Self-contained panel payload and hashes

The canonical panel artifact—the sole byte payload hashed for
`canonical_sha256`—has exact outer keys:

```text
schema_version: string, "1.1.0"
panel_kind: string, "fit" or "holdout"
materialization_algorithm: string, "paper1_calibration_forcing_panel_v2"
root_seed: integer, 420260813
spawn_key: array[integer], [11,0] or [11,1]
bit_generator: string, "PCG64"
numpy_version: string, "2.5.2"
panel_size: integer, exactly K in {32,64,128}
water_ids: array[string], exact two-water order
forcing_schema_version: string, "paper1_root_zone_forcing@1.0.0"
records: array[CalibrationForcingRecord], exactly K*2*168
evidence_label: string, "synthetic_only"
```

`canonical_sha256` is deliberately not an artifact-payload key.  After this
payload is canonicalized and hashed, its digest is attached only to the typed
runtime `CalibrationForcingPanelBundle` as specified in Section 20.9.1.

`CalibrationForcingRecord` has exactly `panel_index` (integer), `water_id`
(string), `recipe_id` (string), `step_index` (integer), `start_hour` (float),
and `forcing` (the exact `RootZoneForcingPayload` in Section 20.8).  Order is
panel index, then registered water order, then step index.  The complete first
fit record is:

```json
{"forcing":{"apar_mol_h":0.8594496676967562,"duration_hours":12.0,"evidence_label":"synthetic_only","hydraulic_domain":{"extrapolation_policy":"deny","model_id":"paper1-biology-v1","osmolality_max":0.5,"osmolality_min":0.0,"permitted_evidence_label":"physics_constrained","purpose":"model_applicability","temperature_k_max":305.0,"temperature_k_min":290.0,"version":"1.0.0"},"leaf_critical_potential_mpa":-1.8,"matric_potential_mpa":-0.08435442859207379,"measured_osmolality_osmol_kg":0.02,"potential_transpiration_l_day":0.8393314487790248,"temperature_factor":0.85,"temperature_k":296.58346643377195,"water_density_kg_l":0.9973},"panel_index":0,"recipe_id":"paper1_base_nutrient_control_v1@1.0.0","start_hour":0.0,"step_index":0,"water_id":"nonsaline_nutrient_matched_control"}
```

The first holdout record differs only in its perturbed values and is exactly:

```json
{"forcing":{"apar_mol_h":0.8439782983917882,"duration_hours":12.0,"evidence_label":"synthetic_only","hydraulic_domain":{"extrapolation_policy":"deny","model_id":"paper1-biology-v1","osmolality_max":0.5,"osmolality_min":0.0,"permitted_evidence_label":"physics_constrained","purpose":"model_applicability","temperature_k_max":305.0,"temperature_k_min":290.0,"version":"1.0.0"},"leaf_critical_potential_mpa":-1.8,"matric_potential_mpa":-0.08575495972206543,"measured_osmolality_osmol_kg":0.02,"potential_transpiration_l_day":0.7681048288999819,"temperature_factor":0.85,"temperature_k":297.5365515623163,"water_density_kg_l":0.9973},"panel_index":0,"recipe_id":"paper1_base_nutrient_control_v1@1.0.0","start_hour":0.0,"step_index":0,"water_id":"nonsaline_nutrient_matched_control"}
```

The materializer makes one 128-panel innovation draw per kind, then hashes
literal prefixes without redrawing.  The regenerated artifacts are:

| Panel artifact | Records | SHA-256 | Range audit `(min,max)` |
|---|---:|---|---|
| fit-32 | 10,752 | `8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3` | T `(291.3926391411616,298.7281070996637)`; APAR `(0.0,1.25972567775521)`; matric `(-0.1164879822580775,-0.004705176034776416)`; transpiration `(0.10869459560526429,1.0345452226753669)` |
| holdout-32 | 10,752 | `80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a` | T `(291.5408547116821,298.88344664294243)`; APAR `(0.0,1.299704845541121)`; matric `(-0.11182186298881373,-0.0004547261506736011)`; transpiration `(0.11407399066395506,1.0588583972041723)` |
| fit-64 (**primary**) | 21,504 | `4e32c2831ea039c5a1939aed19091160f9c8c112d99a9e2bc937f05539b51eaf` | T `(290.89421868483754,298.7281070996637)`; APAR `(0.0,1.25972567775521)`; matric `(-0.1164879822580775,-0.004594178437707541)`; transpiration `(0.10869459560526429,1.086546918085342)` |
| holdout-64 (**primary**) | 21,504 | `d1f5b6b185458f50f6453391065e6af970ce5069921507431ce46fede0f9ca5a` | T `(291.387644840006,298.88344664294243)`; APAR `(0.0,1.299704845541121)`; matric `(-0.12064296468066651,-0.0004547261506736011)`; transpiration `(0.10420996700536547,1.0588583972041723)` |
| fit-128 | 43,008 | `91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9` | T `(290.89421868483754,298.900281776376)`; APAR `(0.0,1.25972567775521)`; matric `(-0.12056731475474103,-0.0034183698000421273)`; transpiration `(0.10869459560526429,1.086546918085342)` |
| holdout-128 | 43,008 | `3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11` | T `(291.1388193975223,299.31926514526134)`; APAR `(0.0,1.299704845541121)`; matric `(-0.12064296468066651,-0.0004547261506736011)`; transpiration `(0.10420996700536547,1.0960330562326226)` |

For each kind, the canonical records and forcing values of the 32 payload
must equal exactly the first 10,752 corresponding records/values selected by
panel index from the 64 payload, and the 64 payload must equal exactly the
first 21,504 records/values selected by panel index from the 128 payload; only
the outer `panel_size` and resulting canonical hash differ.  Implementation
must audit that prefix relation before accepting any artifact.

These hashes were regenerated in multiple fresh processes from
`SeedSequence(420260813).spawn(12)[11].spawn(2)` under NumPy 2.5.2.  They
contain exogenous forcing only, no plant outcome or calibration result.

### 20.10 Exact scenario and sensitivity registries

#### 20.10.1 Scenario whitelist

The ten-scenario registry is exact.  The only changed paths relative to the
anchor are:

| Scenario | Literal changed paths |
|---|---|
| `perfect_control` | none |
| `true_ion_exclusion` | `mechanism.biology_parameter_overrides.root_na_permeability_l_cm2_h` |
| `root_na_accumulation` | `mechanism.biology_parameter_overrides.na_efflux_vmax_mmol_h` |
| `marker_only` | `mechanism.biology_parameter_overrides.ros_clearance_h_inv` |
| `nonsaline_penalty` | `mechanism.biology_parameter_overrides.mannitol_carbon_cost_mmol_c_mmol_inv` |
| `chassis_interaction` | `mechanism.chassis_id`; `mechanism.candidate_chassis_mechanism_modifiers.C5.xylem_na_retrieval_multiplier.operation`; `.factor` |
| `delayed_toxicity` | `mechanism.onset_time_days`; `mechanism.post_onset_biology_parameter_overrides.senescence_h_inv` |
| `sensor_drift_missingness` | exact Section 20.7 list only |
| `insufficient_purge` | `generator.water_loop.purge_volume_l_day` |
| `selection_bias_false_leader` | `generator.hierarchy.plant_variance` |

The B18 wildcard stars are expanded at load time to the exact ten endpoint
IDs in Section 8; runtime wildcards are forbidden.  The literal expanded list
is part of the normalized config hash.  Scenario onset boundaries use Section
20.6.3.  No scenario may change a water recipe, forcing osmolality, initial
state, candidate effect truth, direct outcome, calibration target, selection,
or decision.

#### 20.10.2 Machine-addressable sensitivity registry

Each sensitivity record has exact fields
`sensitivity_id`, `mode`, `paths`, `values`, `unit`, `anchor_value`, and
`evidence_label`.  IDs and paths are unique except where one explicitly named
bundle changes its listed paths together.  `mode` is always
`one_at_a_time`; there is no Cartesian/factorial expansion.  One run selects
exactly one sensitivity ID and one non-anchor value.  The run ID is derived
from the sensitivity ID plus value index, so no two registered runs collide.

Every path below is an absolute document-qualified canonical pointer.  The
literal selector `[water_id=...]` or `[scenario_id=...]` names exactly one
record in its ordered registry; it is not a wildcard or query language.  A
loader expands the table into primitive strings exactly as printed and accepts
no suffix path, `*`, ellipsis, map-wide alias, or runtime expansion.

For serialization, `sensitivity_id`, `mode`, `unit`, and `evidence_label` are
primitive strings; `paths` is a nonempty ordered array of primitive strings;
`anchor_value` is an ordered array of finite primitive numbers with exactly
one value per path; and `values` is a nonempty ordered array of finite
primitive numbers.  Single-path records still use one-element `paths` and
`anchor_value` arrays.  For rows whose unit says `multiplier`, each selected
value multiplies every aligned anchor value; every other row replaces every
aligned path with the selected absolute value.  Bundle application is atomic.
The loader reads the current aligned anchors, requires bit-exact equality to
the registered `anchor_value` array, applies the one selected value to a
detached registry, then canonically revalidates the entire registry before
RNG.  A partial bundle or changed anchor fails `SENSITIVITY_REGISTRY_INVALID`.

| Sensitivity ID | Literal path(s) | Non-anchor values | Unit |
|---|---|---|---|
| `S001_charge_tolerance` | `configs/synthetic_scenarios.yaml::anchor.generator.chemistry.charge_balance_tolerance_percent`<br>`configs/paper1_water_recipes.yaml::active_recipes[water_id=nonsaline_nutrient_matched_control].charge_balance_tolerance_percent`<br>`configs/paper1_water_recipes.yaml::active_recipes[water_id=pilot_selected_full_ion_marine_challenge].charge_balance_tolerance_percent` | 0.10, 0.50, 2.00 | percent |
| `S002_temperature_phi` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.temperature_ar1_phi` | 0.40, 0.90 | dimensionless |
| `S003_apar_phi` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.apar_ar1_phi` | 0.40, 0.90 | dimensionless |
| `S004_matric_phi` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.matric_potential_ar1_phi` | 0.40, 0.90 | dimensionless |
| `S005_temperature_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.temperature_innovation_sd_k` | 0.175, 0.70 | K |
| `S006_apar_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.apar_log_innovation_sd` | 0.05, 0.20 | log-ratio |
| `S007_matric_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.matric_potential_innovation_sd_mpa` | 0.003, 0.012 | MPa |
| `S008_transpiration_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.potential_transpiration_log_innovation_sd` | 0.04, 0.16 | log-ratio |
| `S009_burnin` | `configs/synthetic_scenarios.yaml::anchor.generator.climate.climate_initialization_burnin_steps` | 32, 128 | count |
| `S010_common_ion_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.chemistry.common_ion_log_sd` | 0.015, 0.060 | log-ratio |
| `S011_boron_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.chemistry.boron_log_sd` | 0.040, 0.160 | log-ratio |
| `S012_chemistry_measurement_sd` | `configs/synthetic_scenarios.yaml::anchor.generator.chemistry.ec_measurement_sd_ds_m`<br>`configs/synthetic_scenarios.yaml::anchor.generator.chemistry.osmolality_measurement_sd_osmol_kg`<br>`configs/synthetic_scenarios.yaml::anchor.generator.chemistry.ph_measurement_sd`<br>`configs/synthetic_scenarios.yaml::anchor.generator.chemistry.temperature_measurement_sd_k` | 0.5, 2.0 | multiplier applied to each listed anchor |
| `S013_initial_volume` | `configs/synthetic_scenarios.yaml::anchor.generator.water_loop.reservoir_initial_volume_l` | 100.0, 140.0 | L |
| `S014_return_fraction` | `configs/synthetic_scenarios.yaml::anchor.generator.water_loop.drainage_return_fraction` | 0.50, 0.90 | dimensionless |
| `S015_irrigation` | `configs/synthetic_scenarios.yaml::anchor.generator.water_loop.irrigation_volume_l_per_plant_day` | 0.40, 0.80 | L plant^-1 day^-1 |
| `S016_anchor_purge` | `configs/synthetic_scenarios.yaml::anchor.generator.water_loop.purge_volume_l_day` | 0.60, 2.40 | L day^-1 |
| `S017_sample_volume` | `configs/synthetic_scenarios.yaml::anchor.generator.water_loop.sampling_volume_l_per_sample` | 0.025, 0.100 | L sample^-1 |
| `S018_canopy_error` | `configs/synthetic_scenarios.yaml::anchor.generator.observation.canopy_observation_error_sd` | 0.025, 0.100 | log-ratio |
| `S019_ion_error` | `configs/synthetic_scenarios.yaml::anchor.generator.observation.ion_observation_error_sd` | 0.020, 0.080 | log-ratio |
| `S020_heteroscedasticity` | `configs/synthetic_scenarios.yaml::anchor.generator.observation.canopy_heteroscedastic_log_slope`<br>`configs/synthetic_scenarios.yaml::anchor.generator.observation.ion_heteroscedastic_log_slope` | 0.5, 2.0 | multiplier applied to each listed anchor |
| `S021_limits` | `configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.root_zone_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.root_zone_cl_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.root_zone_k_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.xylem_sap_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.drainage_total_b_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.root_surface_outward_na_flux_per_root_dry_mass`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.root_h2o2_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_by_endpoint.xylem_sap_na_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.root_zone_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.root_zone_cl_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.root_zone_k_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.xylem_sap_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.drainage_total_b_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.root_surface_outward_na_flux_per_root_dry_mass`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.root_h2o2_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_by_endpoint.xylem_sap_na_concentration_time_auc` | 0.5, 2.0 | multiplier applied to each listed anchor |
| `S022_limit_variation` | `configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.root_zone_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.root_zone_cl_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.root_zone_k_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.xylem_sap_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.drainage_total_b_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.root_surface_outward_na_flux_per_root_dry_mass`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.root_h2o2_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.lod_log_sd_by_endpoint.xylem_sap_na_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.root_zone_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.root_zone_cl_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.root_zone_k_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.xylem_sap_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.drainage_total_b_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.root_surface_outward_na_flux_per_root_dry_mass`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.root_h2o2_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.censoring.loq_log_sd_by_endpoint.xylem_sap_na_concentration_time_auc` | 0.00, 0.025, 0.10 | log-ratio |
| `S023_calibration_interval` | `configs/synthetic_scenarios.yaml::anchor.generator.drift.calibration_interval_days` | 3.5, 14.0 | day |
| `S024_drift_residuals` | `configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.green_canopy_area`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.root_zone_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.root_zone_cl_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.root_zone_k_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.xylem_sap_na_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.drainage_total_b_concentration`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.root_surface_outward_na_flux_per_root_dry_mass`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.root_h2o2_concentration_time_auc`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.root_mannitol_concentration_above_empty_vector`<br>`configs/synthetic_scenarios.yaml::anchor.generator.drift.post_calibration_residual_sd_by_endpoint.xylem_sap_na_concentration_time_auc` | 0.5, 2.0 | multiplier applied to each listed anchor |
| `S025_death_heterogeneity` | `configs/synthetic_scenarios.yaml::anchor.generator.death.biomass_death_threshold_log_sd`<br>`configs/synthetic_scenarios.yaml::anchor.generator.death.injury_death_threshold_log_sd`<br>`configs/synthetic_scenarios.yaml::anchor.generator.death.sustained_injury_duration_log_sd` | 0.00, 0.05, 0.20, 0.30 | log-ratio |
| `S026_missingness_intercept` | `configs/synthetic_scenarios.yaml::anchor.generator.missingness.missingness_intercept` | -4.0, -2.0 | logit |
| `S027_mar_slope` | `configs/synthetic_scenarios.yaml::anchor.generator.missingness.missingness_stress_slope` | 0.00, 0.40, 0.80 | logit/SD |
| `S028_mnar_delta` | `configs/synthetic_scenarios.yaml::anchor.generator.missingness.mnar_tipping_delta` | -0.20, -0.10, 0.00, 0.20 | logit/SD |
| `S029_parameter_xtol` | `configs/synthetic_scenarios.yaml::anchor.generator.calibration.parameter_xtol` | 1e-8, 1e-4 | dimensionless |
| `S030_parameter_rtol` | `configs/synthetic_scenarios.yaml::anchor.generator.calibration.parameter_rtol` | 1e-8, 1e-4 | dimensionless |
| `S031_panel_size` | `configs/synthetic_scenarios.yaml::anchor.generator.calibration.fit_panel_size`<br>`configs/synthetic_scenarios.yaml::anchor.generator.calibration.holdout_panel_size` | 32, 128 | count; exact paired value and fixed-prefix hashes required |
| `S032_holdout_tolerance` | `configs/synthetic_scenarios.yaml::anchor.generator.calibration.holdout_tolerance_log_ratio` | 0.010, 0.050 | log-ratio |
| `S033_confirmation_cell` | `configs/synthetic_scenarios.yaml::anchor.generator.design.confirmation_plants_per_group_reservoir` | 5 | count |
| `S034_chassis_modifier` | `configs/synthetic_scenarios.yaml::scenarios[scenario_id=chassis_interaction].mechanism.candidate_chassis_mechanism_modifiers.C5.xylem_na_retrieval_multiplier.factor` | 0.60, 1.00 | dimensionless |
| `S035_delayed_onset` | `configs/synthetic_scenarios.yaml::scenarios[scenario_id=delayed_toxicity].mechanism.onset_time_days` | 28.0, 56.0 | day |
| `S036_insufficient_purge` | `configs/synthetic_scenarios.yaml::scenarios[scenario_id=insufficient_purge].generator.water_loop.purge_volume_l_day` | 0.00, 0.30 | L day^-1 |

S031 value 32 requires fit hash
`8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3`
and holdout hash
`80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a`;
value 128 requires fit hash
`91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9`
and holdout hash
`3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11`.
The primary 64/64 hashes remain unchanged and can never be inferred from the
sensitivity value or overwritten in the primary registration.

All water-loop sensitivity preflights substitute their selected value into
the Section 20.3 equations before RNG.  For S013 specifically, discovery
shared-batch debits are 3,526.00 L at `V0=100` and 3,686.00 L at `V0=140`;
maximum-confirmation 30-plant debits are 3,928.20/4,168.20 L; and 25-plant
debits are 3,474.60/3,714.60 L.  The corresponding 5,000-L remainders are
1,474.00/1,314.00, 1,071.80/831.80, and 1,525.40/1,285.40 L.  No literal
120-L closure target survives inside an S013 run.

The 5,000-L capacity itself is not a sensitivity knob.  S014 return fraction
0.50 is deliberately a capacity-stress value: it preflights to 5,420.40 L for
the four-loop discovery batch, 5,862.60 L for the six-loop 30-plant
confirmation batch, and 5,106.60 L for the six-loop 25-plant confirmation
batch, and therefore must fail `WATER_BATCH_CAPACITY_EXCEEDED` without RNG or
output.  This registered structural failure is reported as such; an
implementation may not silently increase capacity, split IDs, omit a cohort,
or relabel it as a completed outcome sensitivity.

Anchor values remain those in Sections 3–17/20.9.  A sensitivity value that
equals its anchor is the reference run, not a second sensitivity run.  Bundle
records list every expanded path and scaled value in the run manifest.  A
request containing two sensitivity IDs, two value indices, an unregistered
path, a duplicate ID/path, or a generated ID collision fails before RNG.

### 20.11 Reproducibility and complete provenance

The independent materializer is a durable tracked implementation artifact at
`scripts/registration/task4_registration_hash_materializer.py`; SHA-256 at
registration time is
`0397fb262931c08f197ea841c24e055bbb751cbdec06dbc7473a87c9981497d5`.
It imports repository `canonical_json_bytes`, pins NumPy 2.5.2/PCG64, calls
`SeedSequence.spawn` in the registered order, constructs Python floats
explicitly, emits no plant outcomes, and performs no solver call.  Running it
twice in the locked environment produced byte-identical hash lines for the
nominal, operator, sample, fit, and holdout artifacts.  Independent re-review
must run it again; a mismatch blocks adoption.

Its sufficient reproduction algorithm is:

```text
1. Build 168 nominal 12-hour records per water from Section 4/20.8.
2. Hash the exact 1.1.0 nominal payload with canonical_json_bytes.
3. Spawn root 420260813 into 12 children; take child 11; spawn fit/holdout.
4. For each child call PCG64 Generator.standard_normal((128,4,232)) exactly
   once; 32 and 64 are literal leading panel-index prefixes of that array.
5. Update variables in fixed order temperature, APAR, matric potential,
   potential transpiration; discard 64 burn-in values; retain 168.
6. Apply additive/lognormal equations in Section 5 with Python binary64.
7. Emit panel, water, step order using the exact nested schema in 20.9.3 for
   K=32,64,128; independently assert 32-records prefix 64-records prefix 128.
8. Hash canonical bytes; never serialize NumPy scalar subclasses; mark only
   K=64 primary and require S031 identity for K=32/128.
```

The local-input ledger in Section 18 is extended with these exact authorities:

| Local source | SHA-256 |
|---|---|
| `docs/superpowers/plans/2026-08-12-almondlab-paper1-statistics.md` | `76c26b22ec3a0ba87d5c3e71f100d8684c35143b6c8cb2f76ba58cfd5c659638` |
| `task-4-plan-extract.md` | `ba9957df8625f6914f1a482a92130224bc2372736aab401f328cd01f3cd9a47b` |
| `uv.lock` | `07cf8f7c5b8962ef2c3c89f8336fd62c87b27a2d61b2ac13ddf4403fe571dff0` |
| `pyproject.toml` | `4c7fdac6014cc49395d60740549d91cd9fa29612844fa09202e40d4da462159b` |
| final approved Task 3 commit | `d242473269803fa16461f78e8784813272912fbb` |
| `src/almondlab/design.py` at that commit | `9ae36381d59c641728c01e1e04ef4a9f1106fc02332c9b352e3e71bc3ebf15b9` |
| `tests/test_design.py` at that commit | `05565f4ac926809df35a1b9a8fac10404e27e0b0fdc8f01e1afbdd627bf5ffb3` |
| `tests/fixtures/paper1_small.yaml` at that commit | `beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6` |

The final Task 3 API dependency is exactly
`ConfirmationDesignConfig`, `randomize`, `revalidate_confirmation_design`,
`revalidate_baseline_roster`, `revalidate_position_map`,
`revalidate_randomization_manifest`, `revalidate_cohort_identity_set`,
`revalidate_experimental_unit_audit`, `cohort_identity_set`,
`validate_cohort_separation`, and `validate_experimental_units`, with
`run_sequence_ordinal` carried by physical slots and allocation records.
Task 4 may call but not shadow, loosen, rename, or reconstruct these
authorities.  Any source hash or signature mismatch fails before configuration
assembly.

The exact scientific runtime for regenerated artifacts is Python 3.12 under
the repository environment, NumPy 2.5.2, SciPy 1.18.0, PCG64, and repository
canonical JSON.  Official SciPy 1.18.0 documentation supplies the registered
Brent combined parameter-space stopping rule; official NumPy 2.5 documentation
supplies the SeedSequence/PCG64 spawning mechanics.  These software references
support reproducibility mechanics only, not biological validity.

### 20.12 Re-review gates

This repair does not claim approval.  Independent re-review must verify all of
the following before configuration work starts:

1. preserved Task 3 shared-batch identities, aggregate debit by unique
   `(cohort_id, water_batch_id)`, 5,000-L capacity, exact 4/6-loop totals and
   remainders, no rollover, exact sample/operator order, parameterized `V0`,
   and anchor 119.95-L terminal volume;
2. water-batch chemistry keys and complete initial/makeup solute accounting;
3. the explicit synthetic-root-zone abstraction and physical-use block;
4. acid/base/titrant/final-volume accounting and mandatory physicalization
   failure until a batch-specific revision exists;
5. analyte × compartment × phase stops without weakening root/tissue rules;
6. exact assay applicability, censor bounds/vocabulary, sample/assay keys, and
   missingness nulling;
7. exact matched-EV selection-model aggregation and positivity failures;
8. sensor × endpoint × epoch keys, B18 phase offset, and same-time ordering;
9. hierarchy StandardNormal-to-variance transform, target/formula/order, and
   pre-integration application;
10. executable four-endpoint H3 mappings, exact 0.25-hour grid and `math.fsum`
    trapezoids, terminal flux window/sign/mass conventions, synthetic mapping
    labels, physical-use block, and post-death undefined behavior;
11. explicit primary-64 plus fixed-prefix 32/64/128 panel API,
    AUC/`mu`/objective aggregation, endpoint roots,
    correct Brent units/rule, SciPy version, and separate residual gates;
12. the exact nominal/operator/sample and six fit/holdout panel schemas,
    hashes, range audits, prefix relations, and primary/sensitivity separation;
13. fully expanded absolute scenario/sensitivity paths and non-colliding
    one-at-a-time sensitivity registry;
14. complete local provenance and absence of plant outcomes, solver results,
    physical claims, or Acceptance 7/8/9/16 self-certification.

Until an independent reviewer returns approval, the status remains
**repaired prospective synthetic-only proposal awaiting re-review**.  It is not
an accepted protocol, physical recipe, assay, calibration result, or evidence
that any construct improves almond salinity performance.
