"""Prospective Task 4 water-recipe, domain, and physical-stop contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from almondlab.chemistry import charge_balance_error
from almondlab.contracts import EvidenceLabel
from almondlab.domains import load_model_domains
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    Paper1DesignConfig,
    SharedSourceLoopDemand,
    load_paper1_design,
    load_paper1_water_recipes,
    load_task4_stop_policy,
    migrate_paper1_design_water_recipes,
    preflight_shared_source_batch_capacity,
    validate_active_paper1_water_recipes,
)


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "configs" / "experiment_paper1.yaml"
DOMAIN_PATH = ROOT / "configs" / "model_domains.yaml"
RECIPE_PATH = ROOT / "configs" / "paper1_water_recipes.yaml"
STOP_POLICY_PATH = ROOT / "configs" / "paper1_task4_stop_policy.yaml"

CONTROL_ID = "nonsaline_nutrient_matched_control"
CHALLENGE_ID = "pilot_selected_full_ion_marine_challenge"
LEGACY_RAW_SHA256 = "d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0"
LEGACY_ANCHOR_SHA256S = {
    CONTROL_ID: "a804553ff5d1e0c9938a10d14430d593cde2c5cbddd0a00c3e5460f884c61e1f",
    CHALLENGE_ID: "bef482128d45eff8a42593b9a19534f847858a265814edf627b8421d3e3b08a4",
}

EXPECTED_CHEMISTRY = {
    CONTROL_ID: {
        "ec_kind": "ECw",
        "ec_ds_m": 1.5,
        "temperature_k": 298.15,
        "measured_osmolality_osmol_kg": 0.02,
        "ph": 6.5,
        "alkalinity_mmol_c_l": 1.0,
        "na_mmol_l": 4.0,
        "cl_mmol_l": 4.0,
        "ca_mmol_l": 2.0,
        "mg_mmol_l": 1.0,
        "k_mmol_l": 2.0,
        "total_b_mmol_l": 0.05,
        "sulfate_mmol_l": 1.0,
        "bicarbonate_mmol_l": 0.75,
        "nitrate_mmol_l": 5.0,
        "phosphate_mmol_l": 0.25,
    },
    CHALLENGE_ID: {
        "ec_kind": "ECw",
        "ec_ds_m": 6.0,
        "temperature_k": 298.15,
        "measured_osmolality_osmol_kg": 0.1,
        "ph": 6.5,
        "alkalinity_mmol_c_l": 1.0,
        "na_mmol_l": 44.0,
        "cl_mmol_l": 44.0,
        "ca_mmol_l": 2.0,
        "mg_mmol_l": 1.0,
        "k_mmol_l": 2.0,
        "total_b_mmol_l": 0.05,
        "sulfate_mmol_l": 1.0,
        "bicarbonate_mmol_l": 0.75,
        "nitrate_mmol_l": 5.0,
        "phosphate_mmol_l": 0.25,
    },
}

EXPECTED_CONTROL_AMENDMENTS = (
    ("sodium_chloride", "NaCl", "anhydrous", 4.0, 58.44, 233.76, {"na": 4.0, "cl": 4.0}, 0.0),
    (
        "calcium_nitrate_tetrahydrate",
        "Ca(NO3)2·4H2O",
        "tetrahydrate",
        2.0,
        236.15,
        472.3,
        {"ca": 2.0, "nitrate": 4.0},
        0.0,
    ),
    (
        "magnesium_sulfate_heptahydrate",
        "MgSO4·7H2O",
        "heptahydrate",
        1.0,
        246.48,
        246.48,
        {"mg": 1.0, "sulfate": 1.0},
        0.0,
    ),
    (
        "potassium_nitrate",
        "KNO3",
        "anhydrous",
        1.0,
        101.103,
        101.103,
        {"k": 1.0, "nitrate": 1.0},
        0.0,
    ),
    (
        "potassium_bicarbonate",
        "KHCO3",
        "anhydrous",
        0.75,
        100.115,
        75.08625,
        {"k": 0.75, "bicarbonate": 0.75},
        0.75,
    ),
    (
        "monobasic_potassium_phosphate",
        "KH2PO4",
        "anhydrous",
        0.25,
        136.086,
        34.0215,
        {"k": 0.25, "phosphate": 0.25},
        0.25,
    ),
    ("boric_acid", "H3BO3", "anhydrous", 0.05, 61.84, 3.092, {"total_b": 0.05}, 0.0),
)


def _recipe_by_water(registry):
    return {recipe.water_id: recipe for recipe in registry.active_recipes}


def _quantity_values(values):
    return {name: quantity.value for name, quantity in values.items()}


def _write_yaml(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_recipe_registry_freezes_history_lineage_and_active_identity() -> None:
    """Catches mutating a legacy hypothesis in place or detaching active lineage."""

    registry = load_paper1_water_recipes(RECIPE_PATH)
    assert registry.schema_version == "1.0.0"
    assert tuple(anchor.water_id for anchor in registry.historical_anchors) == (
        CONTROL_ID,
        CHALLENGE_ID,
    )
    assert tuple(recipe.water_id for recipe in registry.active_recipes) == (
        CONTROL_ID,
        CHALLENGE_ID,
    )
    assert tuple(recipe.recipe_id for recipe in registry.active_recipes) == (
        "paper1_base_nutrient_control_v1",
        "paper1_base_plus_nacl40_challenge_v1",
    )
    for anchor in registry.historical_anchors:
        assert anchor.source_design_raw_sha256 == LEGACY_RAW_SHA256
        assert anchor.anchor_canonical_sha256 == LEGACY_ANCHOR_SHA256S[anchor.water_id]
        assert anchor.status == "superseded_unbalanced_hypothesis_anchor"
        assert anchor.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    for recipe in registry.active_recipes:
        assert recipe.revision == "1.0.0"
        assert recipe.status == "active"
        assert recipe.supersedes_anchor_sha256 == LEGACY_ANCHOR_SHA256S[recipe.water_id]
        assert recipe.charge_convention_id == "almondlab.chemistry.charge_balance_error@1"
        assert recipe.model_domain_id == "core_v1"
        assert recipe.model_domain_version == "1.1.0"
        assert recipe.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
        assert recipe.generated_batch_evidence_label is EvidenceLabel.SYNTHETIC_ONLY


def test_formula_molecular_weight_mass_and_stoichiometry_are_independent_literals() -> None:
    """Catches wrong hydrate, mass, or contributions for the approved formula."""

    registry = load_paper1_water_recipes(RECIPE_PATH)
    recipes = _recipe_by_water(registry)
    control = recipes[CONTROL_ID]
    observed = tuple(
        (
            row.reagent_id,
            row.formula,
            row.hydrate_state,
            row.amount.value,
            row.molecular_weight.value,
            row.mass_per_final_litre.value,
            _quantity_values(row.stoichiometric_contributions_mmol_l),
            row.alkalinity_contribution_mmol_c_l.value,
        )
        for row in control.preparation.amendments
    )
    assert observed == EXPECTED_CONTROL_AMENDMENTS
    challenge_rows = recipes[CHALLENGE_ID].preparation.amendments
    assert len(challenge_rows) == 1
    increment = challenge_rows[0]
    assert (
        increment.reagent_id,
        increment.formula,
        increment.hydrate_state,
        increment.amount.value,
        increment.molecular_weight.value,
        increment.mass_per_final_litre.value,
        _quantity_values(increment.stoichiometric_contributions_mmol_l),
        increment.alkalinity_contribution_mmol_c_l.value,
    ) == (
        "sodium_chloride_challenge_increment",
        "NaCl",
        "anhydrous",
        40.0,
        58.44,
        2337.6,
        {"na": 40.0, "cl": 40.0},
        0.0,
    )
    for recipe in registry.active_recipes:
        for row in recipe.preparation.amendments:
            assert row.amount.unit == "mmol L^-1"
            assert row.molecular_weight.unit == "g mol^-1"
            assert row.mass_per_final_litre.unit == "mg L^-1"
            assert row.mass_per_final_litre.value == pytest.approx(
                row.amount.value * row.molecular_weight.value,
                rel=0.0,
                abs=1e-12,
            )
            assert all(
                quantity.unit == "mmol L^-1"
                for quantity in row.stoichiometric_contributions_mmol_l.values()
            )
            assert row.alkalinity_contribution_mmol_c_l.unit == "mmol_c L^-1"


def test_active_targets_reconcile_and_charge_uses_alkalinity_once() -> None:
    """Catches target drift or double-counting bicarbonate/phosphate in charge balance."""

    registry = load_paper1_water_recipes(RECIPE_PATH)
    design = load_paper1_design(DESIGN_PATH)
    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    recipes = validate_active_paper1_water_recipes(
        registry,
        design=design,
        domain=domain,
        physical_use=False,
    )
    assert tuple(recipe.water_id for recipe in recipes) == (CONTROL_ID, CHALLENGE_ID)
    for recipe in recipes:
        assert recipe.preparation.preparation_basis == "formula_resolved_synthetic_target"
        assert (
            recipe.preparation.physicalization_status
            == "blocked_pending_batch_specific_titration_revision"
        )
        chemistry = recipe.chemistry.model_dump(mode="json")
        assert chemistry == EXPECTED_CHEMISTRY[recipe.water_id]
        assert recipe.preparation.computed_target_chemistry.model_dump(
            mode="json"
        ) == chemistry
        source = recipe.preparation.source_water_chemistry
        for analyte_id in (
            "na",
            "cl",
            "ca",
            "mg",
            "k",
            "total_b",
            "sulfate",
            "bicarbonate",
            "nitrate",
            "phosphate",
        ):
            formula_total = getattr(source, f"{analyte_id}_mmol_l") + sum(
                row.stoichiometric_contributions_mmol_l.get(
                    analyte_id,
                    None,
                ).value
                if analyte_id in row.stoichiometric_contributions_mmol_l
                else 0.0
                for row in recipe.preparation.amendments
            )
            assert formula_total == getattr(recipe.chemistry, f"{analyte_id}_mmol_l")
        alkalinity_total = source.alkalinity_mmol_c_l + sum(
            row.alkalinity_contribution_mmol_c_l.value
            for row in recipe.preparation.amendments
        )
        assert alkalinity_total == recipe.chemistry.alkalinity_mmol_c_l
        nonstoichiometric = recipe.preparation.registered_nonstoichiometric_targets
        assert tuple(nonstoichiometric) == (
            "ec_ds_m",
            "measured_osmolality_osmol_kg",
            "ph",
            "temperature_k",
            "alkalinity_mmol_c_l",
        )
        for field_name, quantity in nonstoichiometric.items():
            assert quantity.value == chemistry[field_name]
            assert quantity.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
        water = recipe.chemistry
        cations = water.na_mmol_l + water.k_mmol_l + 2 * water.ca_mmol_l + 2 * water.mg_mmol_l
        anions = (
            water.cl_mmol_l
            + water.nitrate_mmol_l
            + 2 * water.sulfate_mmol_l
            + water.alkalinity_mmol_c_l
        )
        independent_error = 100 * (cations - anions) / (cations + anions)
        assert independent_error == 0.0
        assert charge_balance_error(water) == pytest.approx(independent_error, abs=1e-15)
        assert recipe.charge_balance_tolerance_percent.value == 1.0
        assert recipe.charge_balance_tolerance_percent.unit == "percent"


def test_recipe_migration_changes_only_the_two_chemistry_records() -> None:
    """Catches migration changing discovery identities, counts, units, or order."""

    registry = load_paper1_water_recipes(RECIPE_PATH)
    active_design = load_paper1_design(DESIGN_PATH)
    legacy_payload = active_design.model_dump(mode="json")
    anchors = {anchor.water_id: anchor for anchor in registry.historical_anchors}
    for row in legacy_payload["water_conditions"]:
        row["chemistry"] = anchors[row["water_id"]].chemistry.model_dump(mode="json")
    legacy_design = Paper1DesignConfig.model_validate(legacy_payload)

    migrated = migrate_paper1_design_water_recipes(legacy_design, registry)
    before = legacy_design.model_dump(mode="json")
    after = migrated.model_dump(mode="json")
    before_waters = before.pop("water_conditions")
    after_waters = after.pop("water_conditions")
    assert after == before
    assert [row["water_id"] for row in after_waters] == [
        row["water_id"] for row in before_waters
    ]
    assert [row["chemistry"] for row in after_waters] == [
        EXPECTED_CHEMISTRY[CONTROL_ID],
        EXPECTED_CHEMISTRY[CHALLENGE_ID],
    ]


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("active_recipes", 0, "preparation", "amendments", 0, "amount", "value"), True),
        (("active_recipes", 0, "preparation", "amendments", 0, "amount", "value"), 4.1),
        (
            ("active_recipes", 0, "preparation", "amendments", 0, "molecular_weight", "value"),
            "58.440",
        ),
        (("active_recipes", 0, "preparation", "amendments", 0, "formula"), "Na2Cl"),
        (("active_recipes", 0, "preparation", "amendments", 0, "hydrate_state"), "monohydrate"),
        (
            ("active_recipes", 0, "preparation", "amendments", 0, "mass_per_final_litre", "value"),
            233.761,
        ),
        (
            (
                "active_recipes",
                0,
                "preparation",
                "amendments",
                0,
                "stoichiometric_contributions_mmol_l",
                "cl",
                "value",
            ),
            4.1,
        ),
        (("active_recipes", 0, "supersedes_anchor_sha256"), "0" * 64),
        (("active_recipes", 0, "evidence_label"), "physics_constrained"),
        (("active_recipes", 0, "generated_batch_evidence_label"), "hypothesis_prior"),
        (("active_recipes", 0, "preparation", "preparation_basis"), "formula_resolved_amendment"),
        (("active_recipes", 0, "preparation", "physicalization_status"), "ready"),
        (
            (
                "active_recipes",
                0,
                "preparation",
                "registered_nonstoichiometric_targets",
                "ec_ds_m",
                "value",
            ),
            1.6,
        ),
    ],
)
def test_recipe_loader_rejects_coercion_arithmetic_lineage_and_claim_mutations(
    tmp_path: Path,
    path: tuple[object, ...],
    replacement: object,
) -> None:
    """Catches coercion or partial edits being accepted as the registered recipe."""

    payload = yaml.safe_load(RECIPE_PATH.read_text(encoding="utf-8"))
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    mutated = _write_yaml(tmp_path, "mutated-recipes.yaml", payload)
    with pytest.raises(AlmondLabError):
        load_paper1_water_recipes(mutated)


def test_physical_preparation_is_blocked_without_batch_titration_revision() -> None:
    """Catches synthetic pH/alkalinity targets being promoted to a preparable batch."""

    registry = load_paper1_water_recipes(RECIPE_PATH)
    design = load_paper1_design(DESIGN_PATH)
    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    with pytest.raises(AlmondLabError) as exc_info:
        validate_active_paper1_water_recipes(
            registry,
            design=design,
            domain=domain,
            physical_use=True,
        )
    assert exc_info.value.code == "PHYSICAL_RECIPE_NOT_REGISTERED"


def test_core_domain_is_versioned_for_only_the_registered_synthetic_chassis() -> None:
    """Catches using the secondary simulation chassis under the old domain version."""

    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    assert domain.version == "1.1.0"
    assert domain.allowed_chassis == ("Vairo", "SYNTHETIC_VAIRO_B")
    assert domain.allowed_life_stages == ("juvenile",)
    assert domain.required_analytes == (
        "na",
        "cl",
        "ca",
        "mg",
        "k",
        "total_b",
        "sulfate",
        "bicarbonate",
        "nitrate",
        "phosphate",
    )


def test_stop_policy_has_exact_root_tissue_applicability_and_explicit_absence() -> None:
    """Catches applying the 4 mmol/L tissue stop to 44 mmol/L challenge feed."""

    policy = load_task4_stop_policy(STOP_POLICY_PATH)
    assert policy.schema_version == "1.0.0"
    assert policy.policy_id == "paper1_task4_stop_policy@1.0.0"
    assert policy.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert policy.absent_applicability == "explicit_not_applicable"
    rule = policy.concentration_rule
    assert rule.analyte_ids == ("na", "cl", "k")
    assert rule.compartment_kinds == (
        "root_apoplast",
        "root_symplast",
        "root_vacuole",
        "xylem",
        "shoot_tissue",
    )
    assert rule.phase_ids == ("initialization", "state_transition", "terminal")
    assert rule.maximum.value == 4.0
    assert rule.maximum.unit == "mmol L^-1"
    assert rule.maximum.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR
    assert rule.boundary == "stop_above_equality_accepted"
    assert policy.resolve_concentration_rule(
        analyte_id="na",
        compartment_kind="root_apoplast",
        phase_id="initialization",
    ) == rule
    assert policy.resolve_concentration_rule(
        analyte_id="na",
        compartment_kind="source_water",
        phase_id="initialization",
    ) is None


def test_stop_policy_preserves_other_literal_physical_boundaries() -> None:
    """Catches loss of source capacity, ECw, osmolality, volume, injury, or containment gates."""

    policy = load_task4_stop_policy(STOP_POLICY_PATH)
    rules = {rule.rule_id: rule for rule in policy.other_rules}
    assert tuple(rules) == (
        "ecw",
        "osmolality",
        "loop_compartment_volume",
        "shared_source_batch_volume",
        "injury",
        "containment_discharge",
    )
    assert rules["ecw"].maximum.value == 10.0
    assert rules["ecw"].maximum.unit == "dS m^-1"
    assert rules["osmolality"].maximum.value == 0.4
    assert rules["osmolality"].maximum.unit == "osmol kg^-1"
    assert rules["loop_compartment_volume"].minimum.value == 0.1
    assert rules["loop_compartment_volume"].maximum.value == 1000.0
    assert rules["shared_source_batch_volume"].minimum.value == 0.0
    assert rules["shared_source_batch_volume"].maximum.value == 5000.0
    assert rules["injury"].maximum.value == 1.0
    assert rules["containment_discharge"].maximum.value == 0.0
    assert rules["shared_source_batch_volume"].applicability_key_fields == (
        "cohort_id",
        "water_batch_id",
    )
    assert rules["shared_source_batch_volume"].aggregate_debit_preflight is True
    assert rules["ecw"].compartment_kinds == ("source_water", "irrigation_tank")
    assert rules["ecw"].phase_ids == ("operational_sample",)
    assert rules["osmolality"].compartment_kinds == ("mechanistic_water_forcing",)
    assert rules["osmolality"].phase_ids == ("integration",)
    assert rules["loop_compartment_volume"].compartment_kinds == (
        "treatment_feed",
        "treatment_product",
        "treatment_concentrate",
        "blend_tank",
        "irrigation_tank",
        "root_zone",
        "drainage",
        "condensate",
        "purge_holding",
    )
    assert rules["shared_source_batch_volume"].compartment_kinds == (
        "shared_source_batch_inventory",
    )
    assert rules["injury"].compartment_kinds == ("plant_state",)
    assert rules["injury"].phase_ids == ("state_transition", "terminal")
    assert rules["containment_discharge"].compartment_kinds == (
        "external_unauthorized_discharge_ledger",
    )
    assert all(
        rule.boundary
        in {"stop_above_equality_accepted", "stop_outside_boundaries_accepted"}
        for rule in rules.values()
    )
    assert all(rule.evidence_label is EvidenceLabel.HYPOTHESIS_PRIOR for rule in rules.values())


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("evidence_label",), "synthetic_only"),
        (("absent_applicability",), "implicit_infinity"),
        (("concentration_rule", "analyte_ids"), ["na", "cl"]),
        (("concentration_rule", "compartment_kinds"), ["source_water"]),
        (("concentration_rule", "phase_ids"), ["initialization"]),
        (("concentration_rule", "maximum", "value"), 4),
        (("concentration_rule", "maximum", "value"), 44.0),
        (("concentration_rule", "boundary"), "stop_at_or_above"),
        (("other_rules", 3, "maximum", "value"), 1000.0),
        (("other_rules", 3, "aggregate_debit_preflight"), False),
    ],
)
def test_stop_policy_loader_rejects_scope_or_boundary_mutation(
    tmp_path: Path,
    path: tuple[object, ...],
    replacement: object,
) -> None:
    """Catches broadening, weakening, or silently disabling an applicability gate."""

    payload = yaml.safe_load(STOP_POLICY_PATH.read_text(encoding="utf-8"))
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    mutated = _write_yaml(tmp_path, "mutated-stop-policy.yaml", payload)
    with pytest.raises(AlmondLabError):
        load_task4_stop_policy(mutated)


def test_recipe_registry_is_deeply_immutable_and_copy_forgery_is_revalidated() -> None:
    """Catches mutable contribution maps and Pydantic model-copy validation bypasses."""

    registry = load_paper1_water_recipes(RECIPE_PATH)
    contribution_map = (
        registry.active_recipes[0]
        .preparation.amendments[0]
        .stoichiometric_contributions_mmol_l
    )
    with pytest.raises(TypeError):
        contribution_map["na"] = contribution_map["na"]  # type: ignore[index]

    forged_recipe = registry.active_recipes[0].model_copy(
        update={"generated_batch_evidence_label": EvidenceLabel.HYPOTHESIS_PRIOR}
    )
    forged_registry = registry.model_copy(
        update={"active_recipes": (forged_recipe, registry.active_recipes[1])}
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_active_paper1_water_recipes(
            forged_registry,
            design=load_paper1_design(DESIGN_PATH),
            domain=load_model_domains(DOMAIN_PATH).get("core_v1"),
            physical_use=False,
        )
    assert exc_info.value.code == "PAPER1_WATER_RECIPE_INVALID"


@pytest.mark.parametrize("replacement", [float("nan"), float("inf"), 1e308])
def test_recipe_loader_rejects_nonfinite_or_unbounded_registered_amounts(
    tmp_path: Path, replacement: float
) -> None:
    """Catches NaN, infinity, and arithmetic-overflow scale recipe quantities."""

    payload = yaml.safe_load(RECIPE_PATH.read_text(encoding="utf-8"))
    payload["active_recipes"][0]["preparation"]["amendments"][0]["amount"][
        "value"
    ] = replacement
    mutated = _write_yaml(tmp_path, "unbounded-recipes.yaml", payload)
    with pytest.raises(AlmondLabError):
        load_paper1_water_recipes(mutated)


def test_stop_policy_copy_forgery_is_revalidated_at_lookup() -> None:
    """Catches model_copy bypass weakening explicit non-applicability semantics."""

    policy = load_task4_stop_policy(STOP_POLICY_PATH)
    forged = policy.model_copy(update={"absent_applicability": "implicit_infinity"})
    with pytest.raises(AlmondLabError) as exc_info:
        forged.resolve_concentration_rule(
            analyte_id="na",
            compartment_kind="root_apoplast",
            phase_id="initialization",
        )
    assert exc_info.value.code == "TASK4_STOP_POLICY_INVALID"


def _shared_demand(
    *,
    cohort_id: str,
    run_id: str,
    reservoir_id: str,
    water_batch_id: str,
    expected_debit_l: float,
    water_id: str = CONTROL_ID,
) -> SharedSourceLoopDemand:
    return SharedSourceLoopDemand(
        cohort_id=cohort_id,
        run_id=run_id,
        water_id=water_id,
        reservoir_id=reservoir_id,
        water_batch_id=water_batch_id,
        recipe_id=(
            "paper1_base_nutrient_control_v1"
            if water_id == CONTROL_ID
            else "paper1_base_plus_nacl40_challenge_v1"
        ),
        recipe_revision="1.0.0",
        chemistry_sha256="1" * 64,
        expected_debit_l=expected_debit_l,
    )


@pytest.mark.parametrize(
    ("loop_count", "debit_per_loop", "expected_total", "expected_remaining"),
    [
        (4, 901.5, 3606.0, 1394.0),
        (6, 674.7, 4048.2, 951.8),
        (6, 599.1, 3594.6, 1405.4),
    ],
)
def test_shared_source_capacity_preflight_aggregates_before_execution(
    loop_count: int,
    debit_per_loop: float,
    expected_total: float,
    expected_remaining: float,
) -> None:
    """Catches the prohibited per-loop-only 5,000-L capacity check."""

    policy = load_task4_stop_policy(STOP_POLICY_PATH)
    demands = tuple(
        _shared_demand(
            cohort_id="discovery",
            run_id="discovery_run_1",
            reservoir_id=f"reservoir-{index}",
            water_batch_id="shared-control-batch",
            expected_debit_l=debit_per_loop,
        )
        for index in range(loop_count)
    )
    audits = preflight_shared_source_batch_capacity(policy, demands)
    assert len(audits) == 1
    assert audits[0].aggregate_expected_debit_l == pytest.approx(
        expected_total, rel=0.0, abs=1e-12
    )
    assert audits[0].remaining_capacity_l == pytest.approx(
        expected_remaining, rel=0.0, abs=1e-12
    )
    assert audits[0].loop_count == loop_count


def test_shared_source_capacity_preflight_rejects_aggregate_excess_and_aliasing() -> None:
    """Catches rollover-by-alias and aggregate overflow hidden by valid individual loops."""

    policy = load_task4_stop_policy(STOP_POLICY_PATH)
    excessive = tuple(
        _shared_demand(
            cohort_id="confirmation",
            run_id=f"confirmation_run_{index + 1}",
            reservoir_id=f"reservoir-{index}",
            water_batch_id="shared-control-batch",
            expected_debit_l=901.5,
        )
        for index in range(6)
    )
    with pytest.raises(AlmondLabError) as exc_info:
        preflight_shared_source_batch_capacity(policy, excessive)
    assert exc_info.value.code == "WATER_BATCH_CAPACITY_EXCEEDED"

    aliased = (
        _shared_demand(
            cohort_id="discovery",
            run_id="discovery_run_1",
            reservoir_id="reservoir-1",
            water_batch_id="shared-batch",
            expected_debit_l=901.5,
        ),
        _shared_demand(
            cohort_id="discovery",
            run_id="discovery_run_1",
            reservoir_id="reservoir-2",
            water_batch_id="shared-batch",
            expected_debit_l=901.5,
            water_id=CHALLENGE_ID,
        ),
    )
    with pytest.raises(AlmondLabError) as exc_info:
        preflight_shared_source_batch_capacity(policy, aliased)
    assert exc_info.value.code == "WATER_BATCH_IDENTITY_MISMATCH"


def test_shared_source_capacity_accepts_equality_and_revalidates_extreme_debits() -> None:
    """Catches an exclusive 5,000-L boundary and nonfinite model-copy bypass."""

    policy = load_task4_stop_policy(STOP_POLICY_PATH)
    exact = _shared_demand(
        cohort_id="discovery",
        run_id="discovery_run_1",
        reservoir_id="reservoir-1",
        water_batch_id="shared-control-batch",
        expected_debit_l=5000.0,
    )
    audit = preflight_shared_source_batch_capacity(policy, (exact,))[0]
    assert audit.aggregate_expected_debit_l == 5000.0
    assert audit.remaining_capacity_l == 0.0

    huge = exact.model_copy(update={"expected_debit_l": 1e308})
    with pytest.raises(AlmondLabError) as exc_info:
        preflight_shared_source_batch_capacity(policy, (huge,))
    assert exc_info.value.code == "WATER_BATCH_CAPACITY_EXCEEDED"

    forged_nonfinite = exact.model_copy(update={"expected_debit_l": float("nan")})
    with pytest.raises(AlmondLabError) as exc_info:
        preflight_shared_source_batch_capacity(policy, (forged_nonfinite,))
    assert exc_info.value.code == "WATER_BATCH_DEBIT_INVALID"
