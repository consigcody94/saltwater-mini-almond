"""Prospective Task 4 water-recipe, domain, and physical-stop contracts."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

import almondlab.paper1_contracts as paper1_contracts
from almondlab.chemistry import charge_balance_error, sodium_adsorption_ratio_for_water
from almondlab.contracts import DataOrigin, EvidenceLabel
from almondlab.design import (
    BaselinePlant,
    BaselineRoster,
    ConfirmationDesignConfig,
    PositionMap,
    PositionSlot,
    RandomizationManifest,
    load_randomization_fixture,
    randomize,
)
from almondlab.domains import DomainRequest, load_model_domains
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    AnalysisPopulation,
    Paper1DesignConfig,
    RegisteredQuantity,
    WaterLoopGeneratorConfig,
    load_paper1_design,
    load_paper1_water_recipes,
    load_task4_stop_policy,
    migrate_paper1_design_water_recipes,
    validate_active_paper1_water_recipes,
)
from almondlab.provenance import canonical_json_bytes, sha256_bytes
from almondlab.schemas import ModelDomain


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "configs" / "experiment_paper1.yaml"
DOMAIN_PATH = ROOT / "configs" / "model_domains.yaml"
RECIPE_PATH = ROOT / "configs" / "paper1_water_recipes.yaml"
STOP_POLICY_PATH = ROOT / "configs" / "paper1_task4_stop_policy.yaml"
TASK3_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "paper1_small.yaml"
TASK3_ROOT_SEED = 20260812

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


def _task4_domain_request(
    *,
    chassis: str,
    requested_label: EvidenceLabel,
) -> DomainRequest:
    """Build a complete real request; literals do not depend on the gate under test."""

    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    water = _recipe_by_water(load_paper1_water_recipes(RECIPE_PATH))[CONTROL_ID].chemistry
    provenance_sha256 = "c" * 64
    observations: list[dict[str, object]] = []
    for requirement in domain.required_chemistry_fields:
        value = (
            sodium_adsorption_ratio_for_water(water)
            if requirement.field_name == "sar"
            else getattr(water, requirement.field_name)
        )
        row: dict[str, object] = {
            "field_name": requirement.field_name,
            "value": value,
            "observation_kind": requirement.observation_kind,
            "data_origin": DataOrigin.SYNTHETIC,
            "evidence_label": requested_label,
            "provenance_id": "task4-registered-control-chemistry",
            "provenance_sha256": provenance_sha256,
        }
        if requirement.field_name == "ec_ds_m":
            row["ec_kind"] = water.ec_kind
        observations.append(row)
    observations.extend(
        {
            "field_name": f"{analyte_id}_mmol_l",
            "value": getattr(water, f"{analyte_id}_mmol_l"),
            "observation_kind": "measured",
            "data_origin": DataOrigin.SYNTHETIC,
            "evidence_label": requested_label,
            "provenance_id": "task4-registered-control-chemistry",
            "provenance_sha256": provenance_sha256,
        }
        for analyte_id in domain.required_analytes
    )
    return DomainRequest(
        water=water,
        chemistry_observations=tuple(observations),
        provenance_sources=(
            {
                "provenance_id": "task4-registered-control-chemistry",
                "sha256": provenance_sha256,
            },
        ),
        chassis=chassis,
        life_stage="juvenile",
        calibration_datasets=(),
        requested_label=requested_label,
    )


@pytest.mark.parametrize(
    "requested_label",
    (
        EvidenceLabel.PHYSICS_CONSTRAINED,
        EvidenceLabel.EMPIRICALLY_CALIBRATED,
        EvidenceLabel.HYPOTHESIS_PRIOR,
    ),
)
def test_task4_chassis_gate_refuses_secondary_chassis_above_synthetic_only(
    requested_label: EvidenceLabel,
) -> None:
    """Catches global core_v1 permission minting a strong secondary-chassis claim."""

    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    request = _task4_domain_request(
        chassis="SYNTHETIC_VAIRO_B",
        requested_label=requested_label,
    )
    with pytest.raises(AlmondLabError):
        paper1_contracts.validate_task4_domain_request(domain, request)


def test_task4_chassis_gate_retains_vairo_and_synthetic_only_controls() -> None:
    """Catches an overbroad fix that weakens Vairo or rejects the synthetic design tier."""

    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    vairo = paper1_contracts.validate_task4_domain_request(
        domain,
        _task4_domain_request(
            chassis="Vairo",
            requested_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        ),
    )
    secondary = paper1_contracts.validate_task4_domain_request(
        domain,
        _task4_domain_request(
            chassis="SYNTHETIC_VAIRO_B",
            requested_label=EvidenceLabel.SYNTHETIC_ONLY,
        ),
    )
    assert vairo.evidence_label is EvidenceLabel.PHYSICS_CONSTRAINED
    assert vairo.violations == ()
    assert secondary.evidence_label is EvidenceLabel.SYNTHETIC_ONLY
    assert secondary.violations == ()


def test_task4_chassis_gate_revalidates_copy_and_subclass_attacks() -> None:
    """Catches model_copy and Pydantic-subclass paths bypassing the chassis ceiling."""

    domain = load_model_domains(DOMAIN_PATH).get("core_v1")
    vairo = _task4_domain_request(
        chassis="Vairo",
        requested_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    copied = vairo.model_copy(update={"chassis": "SYNTHETIC_VAIRO_B"})
    with pytest.raises(AlmondLabError):
        paper1_contracts.validate_task4_domain_request(domain, copied)

    copied_domain = domain.model_copy(update={"version": "9.9.9"})
    with pytest.raises(AlmondLabError):
        paper1_contracts.validate_task4_domain_request(copied_domain, vairo)

    class HostileDomainRequest(DomainRequest):
        hidden_requested_label: EvidenceLabel = EvidenceLabel.PHYSICS_CONSTRAINED

    hostile_request = HostileDomainRequest.model_validate(vairo.model_dump(mode="json"))
    with pytest.raises(AlmondLabError):
        paper1_contracts.validate_task4_domain_request(domain, hostile_request)

    class HostileModelDomain(ModelDomain):
        hidden_allowed_chassis: str = "unregistered"

    hostile_domain = HostileModelDomain.model_validate(domain.model_dump(mode="json"))
    with pytest.raises(AlmondLabError):
        paper1_contracts.validate_task4_domain_request(hostile_domain, vairo)


def _registered_quantity(value: float, unit: str) -> RegisteredQuantity:
    return RegisteredQuantity(
        value=value,
        unit=unit,
        evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
    )


@lru_cache(maxsize=1)
def _registered_water_loop() -> WaterLoopGeneratorConfig:
    return WaterLoopGeneratorConfig(
        reservoir_initial_volume_l=_registered_quantity(120.0, "L"),
        water_batch_volume_l=_registered_quantity(5000.0, "L"),
        irrigation_volume_l_per_plant_day=_registered_quantity(
            0.60, "L plant^-1 day^-1"
        ),
        drainage_return_fraction=_registered_quantity(0.70, "dimensionless"),
        purge_volume_l_day=_registered_quantity(1.20, "L day^-1"),
        sampling_volume_l_per_sample=_registered_quantity(0.05, "L sample^-1"),
        reservoir_min_volume_l=_registered_quantity(80.0, "L"),
        reservoir_max_volume_l=_registered_quantity(160.0, "L"),
        operator_event_times_days=tuple(
            _registered_quantity(float(index) + 0.25, "day") for index in range(84)
        ),
    )


@lru_cache(maxsize=1)
def _discovery_authorities() -> tuple[PositionMap, RandomizationManifest]:
    inputs = load_randomization_fixture(TASK3_FIXTURE_PATH)
    manifest = randomize(
        load_paper1_design(DESIGN_PATH),
        TASK3_ROOT_SEED,
        position_map=inputs.position_map,
        baseline_roster=inputs.baseline_roster,
    )
    return inputs.position_map, manifest


@lru_cache(maxsize=8)
def _confirmation_authorities(
    plants_per_group_reservoir: int,
    selected_candidate_count: int = 4,
) -> tuple[PositionMap, RandomizationManifest]:
    """Construct a registered 1--4 candidate + EV confirmation authority."""

    selected_candidates = ("C1", "C2", "C3", "C4")[:selected_candidate_count]
    groups = (*selected_candidates, "empty_vector")
    runs = ("confirmation_run_a", "confirmation_run_b")
    waters = (CONTROL_ID, CHALLENGE_ID)
    config = ConfirmationDesignConfig(
        schema_version="1.0",
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
        population=AnalysisPopulation.COMPOSITE_ROOT,
        selected_candidate_ids=selected_candidates,
        water_ids=waters,
        runs=runs,
        reservoirs_per_water=6,
        independent_plants_per_group_reservoir=plants_per_group_reservoir,
        balanced_transformation_batches=("batch_a", "batch_b"),
        construct_level_unit="independently_transformed_plant",
        water_treatment_unit="reservoir",
        discovery_max_run_sequence_ordinal=2,
    )
    plants: list[BaselinePlant] = []
    plants_per_group = 12 * plants_per_group_reservoir
    for group_id in groups:
        for index in range(plants_per_group):
            batch_block = "batch_a" if index < plants_per_group // 2 else "batch_b"
            stratum_index = index % (plants_per_group // 2)
            stratum = (
                "lower_canopy"
                if stratum_index < plants_per_group // 4
                else "upper_canopy"
            )
            plants.append(
                BaselinePlant(
                    plant_id=f"confirm-{group_id}-{index + 1:03d}",
                    group_id=group_id,
                    pretreatment_canopy=20.0 + index / 1000,
                    baseline_canopy_stratum=stratum,
                    transformation_batch_block=batch_block,
                    transformation_batch_id=(
                        f"confirm-{group_id}-physical-{batch_block}"
                    ),
                    transformation_event_id=(
                        f"confirm-{group_id}-event-{index + 1:03d}"
                    ),
                    cohort_id="confirmation",
                )
            )
    slots: list[PositionSlot] = []
    plants_per_loop = len(groups) * plants_per_group_reservoir
    bench_width = 20 if plants_per_loop == 20 else 9
    for water_index, water_id in enumerate(waters, start=1):
        for reservoir_number in range(1, 7):
            run_index = 0 if reservoir_number <= 3 else 1
            for slot_number in range(1, plants_per_loop + 1):
                slots.append(
                    PositionSlot(
                        position_id=(
                            f"confirm-w{water_index}-res{reservoir_number:02d}"
                            f"-slot{slot_number:02d}"
                        ),
                        run_id=runs[run_index],
                        run_sequence_ordinal=3 + run_index,
                        water_id=water_id,
                        reservoir_id=(
                            f"confirm-w{water_index}-reservoir-{reservoir_number:02d}"
                        ),
                        water_batch_id=f"confirm-w{water_index}-water-batch",
                        greenhouse_compartment_id=(
                            f"confirm-compartment-{run_index + 1}"
                        ),
                        bench_id=f"confirm-w{water_index}-res{reservoir_number:02d}",
                        row=(slot_number - 1) // bench_width + 1,
                        column=(slot_number - 1) % bench_width + 1,
                        spatial_gradient_profile_id=(
                            f"confirm-gradient-w{water_index}"
                            f"-res{reservoir_number:02d}"
                        ),
                        permitted_movement_schedule_ids=("confirm-rotation",),
                        cohort_id="confirmation",
                    )
                )
    position_map = PositionMap(tuple(slots))
    manifest = randomize(
        config,
        TASK3_ROOT_SEED,
        position_map=position_map,
        baseline_roster=BaselineRoster(tuple(plants)),
    )
    return position_map, manifest


def _capacity_preflight(
    position_map: PositionMap,
    manifest: RandomizationManifest,
    *,
    registry=None,
    water_loop: WaterLoopGeneratorConfig | None = None,
):
    return paper1_contracts.preflight_shared_source_batch_capacity(
        load_task4_stop_policy(STOP_POLICY_PATH),
        position_map=position_map,
        manifest=manifest,
        recipe_registry=(
            load_paper1_water_recipes(RECIPE_PATH) if registry is None else registry
        ),
        water_loop=_registered_water_loop() if water_loop is None else water_loop,
    )


@pytest.mark.parametrize(
    (
        "cohort",
        "plants_per_group_reservoir",
        "expected_batch_count",
        "expected_loop_count",
        "expected_per_loop",
        "expected_total",
        "expected_remaining",
    ),
    (
        ("discovery", 5, 4, 4, 901.5, 3606.0, 1394.0),
        ("confirmation", 6, 2, 6, 674.7, 4048.2, 951.8),
        ("confirmation", 5, 2, 6, 599.1, 3594.6, 1405.4),
    ),
)
def test_shared_source_capacity_is_derived_from_task3_and_registered_generator(
    cohort: str,
    plants_per_group_reservoir: int,
    expected_batch_count: int,
    expected_loop_count: int,
    expected_per_loop: float,
    expected_total: float,
    expected_remaining: float,
) -> None:
    """Catches caller-authored debit, chemistry, or batch identity entering the audit."""

    position_map, manifest = (
        _discovery_authorities()
        if cohort == "discovery"
        else _confirmation_authorities(plants_per_group_reservoir)
    )
    registry = load_paper1_water_recipes(RECIPE_PATH)
    recipes = _recipe_by_water(registry)
    audits = _capacity_preflight(position_map, manifest, registry=registry)
    assert len(audits) == expected_batch_count
    assert {audit.cohort_id for audit in audits} == {cohort}
    assert {audit.loop_count for audit in audits} == {expected_loop_count}
    for audit in audits:
        assert audit.aggregate_expected_debit_l == pytest.approx(
            expected_total, rel=0.0, abs=1e-12
        )
        assert audit.aggregate_expected_debit_l / audit.loop_count == pytest.approx(
            expected_per_loop, rel=0.0, abs=1e-12
        )
        assert audit.remaining_capacity_l == pytest.approx(
            expected_remaining, rel=0.0, abs=1e-12
        )
        recipe = recipes[audit.water_id]
        assert audit.recipe_id == recipe.recipe_id
        assert audit.recipe_revision == recipe.revision
        assert audit.chemistry_sha256 == sha256_bytes(
            canonical_json_bytes(recipe.chemistry.model_dump(mode="json"))
        )


@pytest.mark.parametrize(
    (
        "selected_candidate_count",
        "plants_per_group_reservoir",
        "expected_per_loop",
        "expected_total",
    ),
    (
        (1, 5, 372.3, 2233.8),
        (1, 6, 402.54, 2415.24),
        (2, 5, 447.9, 2687.4),
        (2, 6, 493.26, 2959.56),
        (3, 5, 523.5, 3141.0),
        (3, 6, 583.98, 3503.88),
        (4, 5, 599.1, 3594.6),
        (4, 6, 674.7, 4048.2),
    ),
)
def test_shared_source_capacity_derives_every_task3_confirmation_size(
    selected_candidate_count: int,
    plants_per_group_reservoir: int,
    expected_per_loop: float,
    expected_total: float,
) -> None:
    """Catches hard-coding Task 4 to the maximum four selected candidates."""

    position_map, manifest = _confirmation_authorities(
        plants_per_group_reservoir,
        selected_candidate_count,
    )
    audits = _capacity_preflight(position_map, manifest)
    assert len(audits) == 2
    assert {audit.loop_count for audit in audits} == {6}
    for audit in audits:
        assert audit.aggregate_expected_debit_l / 6 == pytest.approx(
            expected_per_loop,
            rel=0.0,
            abs=1e-12,
        )
        assert audit.aggregate_expected_debit_l == pytest.approx(
            expected_total,
            rel=0.0,
            abs=1e-12,
        )


def test_shared_source_capacity_rejects_different_groups_between_loops() -> None:
    """Catches separately valid candidate sets being mixed within one cohort."""

    position_map, manifest = _confirmation_authorities(5)
    target = manifest.records[0]
    changed = tuple(
        replace(record, group_id="C5")
        if (
            record.run_id,
            record.water_id,
            record.reservoir_id,
            record.group_id,
        )
        == (target.run_id, target.water_id, target.reservoir_id, "C1")
        else record
        for record in manifest.records
    )
    forged = replace(
        manifest,
        records=changed,
        allocation_sha256=sha256_bytes(
            canonical_json_bytes([record.to_dict() for record in changed])
        ),
    )
    with pytest.raises(AlmondLabError):
        _capacity_preflight(position_map, forged)


def test_shared_source_capacity_rejects_position_manifest_omission_and_addition() -> None:
    """Catches a partial caller projection being mistaken for the complete Task 3 loop set."""

    position_map, manifest = _discovery_authorities()
    omitted = PositionMap(position_map.slots[:-1])
    last = position_map.slots[-1]
    added = PositionMap(
        (
            *position_map.slots,
            replace(
                last,
                position_id="unregistered-extra-position",
                bench_id="unregistered-extra-bench",
                reservoir_id="unregistered-extra-reservoir",
            ),
        )
    )
    for mismatched in (omitted, added):
        with pytest.raises(AlmondLabError):
            _capacity_preflight(mismatched, manifest)


def test_shared_source_capacity_rejects_split_or_invented_batch_identity() -> None:
    """Catches matching forged authorities splitting the registered four-loop source."""

    inputs = load_randomization_fixture(TASK3_FIXTURE_PATH)
    position_map, original_manifest = _discovery_authorities()
    first = position_map.slots[0]
    split_slots = tuple(
        replace(slot, water_batch_id=f"{first.water_batch_id}-invented-split")
        if (
            slot.run_id,
            slot.water_id,
            slot.reservoir_id,
        )
        == (first.run_id, first.water_id, first.reservoir_id)
        else slot
        for slot in position_map.slots
    )
    split_map = PositionMap(split_slots)
    split_manifest = randomize(
        load_paper1_design(DESIGN_PATH),
        TASK3_ROOT_SEED,
        position_map=split_map,
        baseline_roster=inputs.baseline_roster,
    )
    with pytest.raises(AlmondLabError):
        _capacity_preflight(split_map, split_manifest)

    invented_slots = tuple(
        replace(slot, water_batch_id="runtime-invented-batch")
        if slot.water_batch_id == first.water_batch_id
        else slot
        for slot in position_map.slots
    )
    with pytest.raises(AlmondLabError):
        _capacity_preflight(PositionMap(invented_slots), original_manifest)


def test_shared_source_capacity_has_no_caller_override_ingress() -> None:
    """Catches reintroducing the zero-debit, split-ID, or fake-hash API surface."""

    position_map, manifest = _discovery_authorities()
    assert _capacity_preflight(position_map, manifest)
    for injected in (
        {"expected_debit_l": 0.0},
        {"water_batch_id": "runtime-invented-batch"},
        {"chemistry_sha256": "0" * 64},
        {"loop_demands": ()},
    ):
        with pytest.raises(TypeError):
            paper1_contracts.preflight_shared_source_batch_capacity(
                load_task4_stop_policy(STOP_POLICY_PATH),
                position_map=position_map,
                manifest=manifest,
                recipe_registry=load_paper1_water_recipes(RECIPE_PATH),
                water_loop=_registered_water_loop(),
                **injected,
            )


@pytest.mark.parametrize("replacement", (0.0, 0.70, float("nan"), 1e308))
def test_shared_source_capacity_revalidates_copied_water_loop_arithmetic(
    replacement: float,
) -> None:
    """Catches model_copy supplying zero, altered, nonfinite, or overflowing debit inputs."""

    position_map, manifest = _discovery_authorities()
    water_loop = _registered_water_loop()
    forged_irrigation = water_loop.irrigation_volume_l_per_plant_day.model_copy(
        update={"value": replacement}
    )
    forged = water_loop.model_copy(
        update={"irrigation_volume_l_per_plant_day": forged_irrigation}
    )
    with pytest.raises(AlmondLabError):
        _capacity_preflight(position_map, manifest, water_loop=forged)


def test_shared_source_capacity_revalidates_copied_recipe_authority() -> None:
    """Catches model_copy changing the chemistry identity used by the audit."""

    position_map, manifest = _discovery_authorities()
    registry = load_paper1_water_recipes(RECIPE_PATH)
    forged_recipe = registry.active_recipes[0].model_copy(
        update={"recipe_id": "runtime-forged-recipe"}
    )
    forged_registry = registry.model_copy(
        update={"active_recipes": (forged_recipe, registry.active_recipes[1])}
    )
    with pytest.raises(AlmondLabError):
        _capacity_preflight(position_map, manifest, registry=forged_registry)


def test_shared_source_capacity_rejects_authority_subclasses() -> None:
    """Catches subclass-only hidden state bypassing detached authority reconstruction."""

    position_map, manifest = _discovery_authorities()
    registry = load_paper1_water_recipes(RECIPE_PATH)

    class HostilePositionMap(PositionMap):
        pass

    class HostileManifest(RandomizationManifest):
        pass

    hostile_map = HostilePositionMap(position_map.slots)
    hostile_manifest = HostileManifest(
        schema_version=manifest.schema_version,
        model_version=manifest.model_version,
        root_seed=manifest.root_seed,
        seed_tree=manifest.seed_tree,
        records=manifest.records,
        config_sha256=manifest.config_sha256,
        allocation_sha256=manifest.allocation_sha256,
        input_sha256s=dict(manifest.input_sha256s),
        evidence_label=manifest.evidence_label,
    )
    for candidate_map, candidate_manifest in (
        (hostile_map, manifest),
        (position_map, hostile_manifest),
    ):
        with pytest.raises(AlmondLabError):
            _capacity_preflight(candidate_map, candidate_manifest)

    class HostileRegistry(paper1_contracts.Paper1WaterRecipeRegistry):
        hidden_chemistry_sha256: str = "0" * 64

    hostile_registry = HostileRegistry.model_validate(registry.model_dump(mode="json"))
    with pytest.raises(AlmondLabError):
        _capacity_preflight(position_map, manifest, registry=hostile_registry)

    class HostileWaterLoop(WaterLoopGeneratorConfig):
        hidden_expected_debit_l: float = 0.0

    hostile_loop = HostileWaterLoop.model_validate(
        _registered_water_loop().model_dump(mode="json")
    )
    with pytest.raises(AlmondLabError):
        _capacity_preflight(position_map, manifest, water_loop=hostile_loop)
