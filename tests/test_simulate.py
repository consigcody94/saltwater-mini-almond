"""Task 4 discovery-only runtime assembly authority tests.

These tests deliberately stop at input assembly and deterministic Task 3 replay.
They do not generate a synthetic outcome or authorize a confirmation family.
"""

from __future__ import annotations

import dataclasses
import importlib.resources
import inspect
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType
from typing import Literal, Mapping, get_type_hints

import pytest

import almondlab.paper1_contracts as paper1_contracts
from almondlab.biology_surrogate import CandidateEffects, load_candidate_effects
from almondlab.contracts import EvidenceLabel
from almondlab.design import (
    BaselineRoster,
    CohortIdentitySet,
    ConfirmationDesignConfig,
    ExperimentalUnitAudit,
    ExperimentalUnitSpec,
    PositionMap,
    RandomizationManifest,
    cohort_identity_set,
    load_randomization_fixture,
    randomize,
    validate_experimental_units,
)
from almondlab.domains import load_model_domains
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    CandidateRegistry,
    Paper1DesignConfig,
    Paper1WaterRecipeRegistry,
    SharedSourceBatchCapacityAudit,
    SyntheticGeneratorConfig,
    SyntheticScenarioRegistry,
    Task4StopPolicy,
    load_candidate_specs,
    load_paper1_design,
    load_paper1_water_recipes,
    load_synthetic_scenarios,
    load_task4_stop_policy,
)
from almondlab.schemas import ModelDomain
from almondlab.simulate import (
    CohortDesignBundle,
    Paper1SimulationConfig,
    assemble_cohort_design_bundle,
    assemble_paper1_simulation_config,
    revalidate_cohort_design_bundle,
    revalidate_paper1_simulation_config,
)


ROOT = Path(__file__).resolve().parents[1]
TASK3_ROOT_SEED = 20260812
RAW_PATHS = MappingProxyType(
    {
        "configs/candidates.yaml": ROOT / "configs" / "candidates.yaml",
        "configs/experiment_paper1.yaml": (
            ROOT / "configs" / "experiment_paper1.yaml"
        ),
        "configs/model_domains.yaml": ROOT / "configs" / "model_domains.yaml",
        "configs/paper1_task4_stop_policy.yaml": (
            ROOT / "configs" / "paper1_task4_stop_policy.yaml"
        ),
        "configs/paper1_water_recipes.yaml": (
            ROOT / "configs" / "paper1_water_recipes.yaml"
        ),
        "configs/synthetic_scenarios.yaml": (
            ROOT / "configs" / "synthetic_scenarios.yaml"
        ),
        "fixtures/candidate_effects.yaml": (
            ROOT / "tests" / "fixtures" / "candidate_effects.yaml"
        ),
        "fixtures/paper1_small.yaml": (
            ROOT / "tests" / "fixtures" / "paper1_small.yaml"
        ),
    }
)
EXPECTED_HASHES = MappingProxyType(
    {
        "configs/candidates.yaml:raw_sha256": (
            "f4eb6c496ddfce2fb7077db34a03e6836da2cd4c62ad21d504b0227a277c5a05"
        ),
        "configs/candidates.yaml:normalized_sha256": (
            "4e401c13ebfd97544a7f5bf7e7c967637dbf8329f0650dae7676c4656968f0ca"
        ),
        "configs/experiment_paper1.yaml:raw_sha256": (
            "a40c28829c4ca3dadb3a87a3f6e8731b73ab9d38a53f2dae9b4c26657ac8ab18"
        ),
        "configs/experiment_paper1.yaml:normalized_sha256": (
            "f5911a6a63d7444575c2013d9737b9219ef21fb1f5c58dcc5fd633bcde38f5c9"
        ),
        "configs/model_domains.yaml:raw_sha256": (
            "0cac0e90c7746e4897f760d2ff87a57d2ddceb175690d51be1beb31f41719411"
        ),
        "configs/model_domains.yaml::core_v1:normalized_sha256": (
            "f6e80805ac05a2059baae3e9a05dab1c89b988911b34a366a46249bb9fac8ee0"
        ),
        "configs/paper1_task4_stop_policy.yaml:raw_sha256": (
            "03e07ee719e5e376e9c03202be945c6b02d77a7373a3bdb164d5c08f7427ee34"
        ),
        "configs/paper1_task4_stop_policy.yaml:normalized_sha256": (
            "94c1aee1bc6b5547973e29d201373dfbe2f545ec694ac5dc9b836b40fa0127a9"
        ),
        "configs/paper1_water_recipes.yaml:raw_sha256": (
            "d46a0e4dc02cd74cfa5b4f437f367009301d4aab8cad9a1115ec6be37afa24d3"
        ),
        "configs/paper1_water_recipes.yaml:normalized_sha256": (
            "8a902441d143017fddfddf5b174302187dd8da1d9a46f98af9a94d18e317b1bd"
        ),
        "configs/synthetic_scenarios.yaml:raw_sha256": (
            "fdc7b4068d80a9d5e42f7c2c5322d7a79b076951b1cccc3ba674af91a53d56d6"
        ),
        "configs/synthetic_scenarios.yaml:normalized_sha256": (
            "4229e855bcf783d994ce24f6dc98d1dc8eded92f5134f854880cb44204f6150a"
        ),
        "fixtures/candidate_effects.yaml:raw_sha256": (
            "4e92c1567227b9e1f6e0713b79890bfc652a5b21a8de013769eaaa01ac939c21"
        ),
        "fixtures/candidate_effects.yaml:normalized_sha256": (
            "0d5b62381409a3ed814b4687291e7f4c4c987c8d84db63353b85c11789fe25e8"
        ),
        "fixtures/paper1_small.yaml:raw_sha256": (
            "beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6"
        ),
        "paper1_nominal_forcing_schedule_v2:canonical_sha256": (
            "329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96"
        ),
    }
)


@dataclass(frozen=True, slots=True)
class _RegisteredAuthorities:
    design: Paper1DesignConfig
    candidates: CandidateRegistry
    candidate_effects: Mapping[str, CandidateEffects]
    model_domain: ModelDomain
    water_recipes: Paper1WaterRecipeRegistry
    scenario_registry: SyntheticScenarioRegistry
    stop_policy: Task4StopPolicy
    baseline_roster: BaselineRoster
    position_map: PositionMap
    manifest: RandomizationManifest
    audit: ExperimentalUnitAudit


@lru_cache(maxsize=1)
def _registered_authorities() -> _RegisteredAuthorities:
    design = load_paper1_design(RAW_PATHS["configs/experiment_paper1.yaml"])
    physical = load_randomization_fixture(
        RAW_PATHS["fixtures/paper1_small.yaml"]
    )
    manifest = randomize(
        design,
        TASK3_ROOT_SEED,
        position_map=physical.position_map,
        baseline_roster=physical.baseline_roster,
    )
    identity = cohort_identity_set(
        manifest,
        baseline_roster=physical.baseline_roster,
        position_map=physical.position_map,
    )
    audit = validate_experimental_units(
        manifest.records,
        ExperimentalUnitSpec.from_design(
            design, position_map=physical.position_map
        ),
        cohorts=(identity,),
    )
    return _RegisteredAuthorities(
        design=design,
        candidates=load_candidate_specs(RAW_PATHS["configs/candidates.yaml"]),
        candidate_effects=load_candidate_effects(
            RAW_PATHS["fixtures/candidate_effects.yaml"]
        ),
        model_domain=load_model_domains(
            RAW_PATHS["configs/model_domains.yaml"]
        ).get("core_v1"),
        water_recipes=load_paper1_water_recipes(
            RAW_PATHS["configs/paper1_water_recipes.yaml"]
        ),
        scenario_registry=load_synthetic_scenarios(
            RAW_PATHS["configs/synthetic_scenarios.yaml"]
        ),
        stop_policy=load_task4_stop_policy(
            RAW_PATHS["configs/paper1_task4_stop_policy.yaml"]
        ),
        baseline_roster=physical.baseline_roster,
        position_map=physical.position_map,
        manifest=manifest,
        audit=audit,
    )


def _raw_authority_bytes() -> dict[str, bytes]:
    return {name: path.read_bytes() for name, path in RAW_PATHS.items()}


def _bundle(
    authorities: _RegisteredAuthorities | None = None,
) -> CohortDesignBundle:
    registered = authorities or _registered_authorities()
    return assemble_cohort_design_bundle(
        cohort_id="discovery",
        config=registered.design,
        baseline_roster=registered.baseline_roster,
        position_map=registered.position_map,
        manifest=registered.manifest,
        audit=registered.audit,
    )


def _mechanical_bundle(
    *,
    seed: int,
    design: Paper1DesignConfig | None = None,
    baseline_roster: BaselineRoster | None = None,
    position_map: PositionMap | None = None,
) -> CohortDesignBundle:
    """Build a reject-only mechanically valid Task 3 discovery adversary."""

    registered = _registered_authorities()
    selected_design = design or registered.design
    selected_roster = baseline_roster or registered.baseline_roster
    selected_map = position_map or registered.position_map
    manifest = randomize(
        selected_design,
        seed,
        position_map=selected_map,
        baseline_roster=selected_roster,
    )
    identity = cohort_identity_set(
        manifest,
        baseline_roster=selected_roster,
        position_map=selected_map,
    )
    audit = validate_experimental_units(
        manifest.records,
        ExperimentalUnitSpec.from_design(
            selected_design,
            position_map=selected_map,
        ),
        cohorts=(identity,),
    )
    return assemble_cohort_design_bundle(
        cohort_id="discovery",
        config=selected_design,
        baseline_roster=selected_roster,
        position_map=selected_map,
        manifest=manifest,
        audit=audit,
    )


def _aggregate_kwargs(
    *,
    discovery_design: CohortDesignBundle | None = None,
    candidate_effects: Mapping[str, CandidateEffects] | None = None,
    raw_authority_bytes_by_name: Mapping[str, bytes] | None = None,
    confirmation_config: object = None,
    confirmation_design: object = None,
) -> dict[str, object]:
    registered = _registered_authorities()
    return {
        "design": registered.design,
        "candidates": registered.candidates,
        "candidate_effects": (
            registered.candidate_effects
            if candidate_effects is None
            else candidate_effects
        ),
        "model_domain": registered.model_domain,
        "water_recipes": registered.water_recipes,
        "scenario_registry": registered.scenario_registry,
        "stop_policy": registered.stop_policy,
        "discovery_design": discovery_design or _bundle(registered),
        "confirmation_config": confirmation_config,
        "confirmation_design": confirmation_design,
        "raw_authority_bytes_by_name": (
            _raw_authority_bytes()
            if raw_authority_bytes_by_name is None
            else raw_authority_bytes_by_name
        ),
    }


@lru_cache(maxsize=1)
def _simulation_config() -> Paper1SimulationConfig:
    return assemble_paper1_simulation_config(**_aggregate_kwargs())  # type: ignore[arg-type]


def _assert_error(
    expected_code: str,
    expected_field_path: str,
    function: object,
) -> AlmondLabError:
    with pytest.raises(AlmondLabError) as caught:
        function()  # type: ignore[operator]
    assert caught.value.code == expected_code
    assert caught.value.field_path == expected_field_path
    return caught.value


def test_task4_simulation_public_surface_and_exact_shapes() -> None:
    """Catches a widened, positional, mutable, or incomplete runtime API."""

    assert tuple(field.name for field in fields(CohortDesignBundle)) == (
        "cohort_id",
        "baseline_roster",
        "position_map",
        "manifest",
        "audit",
    )
    assert tuple(field.name for field in fields(Paper1SimulationConfig)) == (
        "design",
        "candidates",
        "candidate_effects",
        "model_domain",
        "water_recipes",
        "scenario_registry",
        "stop_policy",
        "discovery_design",
        "confirmation_config",
        "confirmation_design",
        "generator",
        "config_sha256s",
        "evidence_label",
    )
    bundle_hints = get_type_hints(CohortDesignBundle)
    assert bundle_hints == {
        "cohort_id": Literal["discovery", "confirmation"],
        "baseline_roster": BaselineRoster,
        "position_map": PositionMap,
        "manifest": RandomizationManifest,
        "audit": ExperimentalUnitAudit,
    }
    aggregate_hints = get_type_hints(Paper1SimulationConfig)
    assert aggregate_hints["candidate_effects"] == Mapping[str, CandidateEffects]
    assert aggregate_hints["confirmation_config"] == ConfirmationDesignConfig | None
    assert aggregate_hints["confirmation_design"] == CohortDesignBundle | None
    assert aggregate_hints["generator"] is SyntheticGeneratorConfig
    assert aggregate_hints["config_sha256s"] == Mapping[str, str]
    assert aggregate_hints["evidence_label"] == Literal[
        EvidenceLabel.SYNTHETIC_ONLY
    ]

    signatures = {
        assemble_cohort_design_bundle: (
            (
                "cohort_id",
                "config",
                "baseline_roster",
                "position_map",
                "manifest",
                "audit",
            ),
            (inspect.Parameter.KEYWORD_ONLY,) * 6,
        ),
        revalidate_cohort_design_bundle: (
            ("value", "config"),
            (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ),
        ),
        assemble_paper1_simulation_config: (
            (
                "design",
                "candidates",
                "candidate_effects",
                "model_domain",
                "water_recipes",
                "scenario_registry",
                "stop_policy",
                "discovery_design",
                "confirmation_config",
                "confirmation_design",
                "raw_authority_bytes_by_name",
            ),
            (inspect.Parameter.KEYWORD_ONLY,) * 11,
        ),
        revalidate_paper1_simulation_config: (
            ("value",),
            (inspect.Parameter.POSITIONAL_OR_KEYWORD,),
        ),
    }
    for function, (expected_names, expected_kinds) in signatures.items():
        signature = inspect.signature(function)
        assert tuple(signature.parameters) == expected_names
        assert tuple(
            parameter.kind for parameter in signature.parameters.values()
        ) == expected_kinds

    registered = _registered_authorities()
    with pytest.raises(TypeError):
        CohortDesignBundle(  # type: ignore[misc]
            "discovery",
            registered.baseline_roster,
            registered.position_map,
            registered.manifest,
            registered.audit,
        )


def test_registered_discovery_bundle_round_trips_and_recomputes_the_audit() -> None:
    """Catches trusted caller summaries, alias retention, or a lost Task 3 replay."""

    registered = _registered_authorities()
    bundle = _bundle(registered)
    checked = revalidate_cohort_design_bundle(bundle, config=registered.design)
    assert checked is not bundle
    assert checked.baseline_roster is not registered.baseline_roster
    assert checked.position_map is not registered.position_map
    assert checked.manifest is not registered.manifest
    assert checked.audit is not registered.audit
    assert checked.audit.biological_n == 720
    assert checked.audit.water_treatment_n == 16
    assert len(checked.manifest.records) == 720
    assert checked.manifest.canonical_json_bytes() == (
        registered.manifest.canonical_json_bytes()
    )
    assert not hasattr(checked, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        checked.cohort_id = "confirmation"  # type: ignore[misc]

    forged_audit = replace(registered.audit, biological_n=719)
    _assert_error(
        "EXPERIMENTAL_UNIT_INVALID",
        "audit",
        lambda: assemble_cohort_design_bundle(
            cohort_id="discovery",
            config=registered.design,
            baseline_roster=registered.baseline_roster,
            position_map=registered.position_map,
            manifest=registered.manifest,
            audit=forged_audit,
        ),
    )


def test_bundle_revalidation_rejects_outer_subclasses_and_nested_forgery() -> None:
    """Catches frozen appearance or isinstance-only acceptance at the bundle edge."""

    registered = _registered_authorities()
    bundle = _bundle(registered)

    class BundleSubclass(CohortDesignBundle):
        pass

    subclassed = BundleSubclass(
        cohort_id=bundle.cohort_id,
        baseline_roster=bundle.baseline_roster,
        position_map=bundle.position_map,
        manifest=bundle.manifest,
        audit=bundle.audit,
    )
    _assert_error(
        "COHORT_DESIGN_INVALID",
        "cohort_id",
        lambda: revalidate_cohort_design_bundle(
            subclassed,
            config=registered.design,
        ),
    )

    forged_roster = BaselineRoster(tuple(registered.baseline_roster.plants))
    object.__setattr__(forged_roster, "plants", (object(),))
    forged_map = PositionMap(tuple(registered.position_map.slots))
    object.__setattr__(forged_map, "slots", (object(),))
    forged_manifest = revalidate_cohort_design_bundle(
        bundle,
        config=registered.design,
    ).manifest
    object.__setattr__(forged_manifest, "allocation_sha256", "0" * 64)
    forged_audit = replace(registered.audit, biological_n=719)
    attacks = (
        ("baseline_roster", forged_roster, "ROSTER_INVALID"),
        ("position_map", forged_map, "POSITION_MAP_INVALID"),
        ("manifest", forged_manifest, "RANDOMIZATION_INVALID"),
        ("audit", forged_audit, "EXPERIMENTAL_UNIT_INVALID"),
    )
    for field_name, forged, expected_code in attacks:
        value = replace(bundle)
        object.__setattr__(value, field_name, forged)
        with pytest.raises(AlmondLabError) as caught:
            revalidate_cohort_design_bundle(value, config=registered.design)
        assert caught.value.code == expected_code


def test_bundle_and_aggregate_reject_omitted_or_added_physical_units() -> None:
    """Catches caller-created 719/721-plant or slot families at both boundaries."""

    registered = _registered_authorities()
    last_plant = registered.baseline_roster.plants[-1]
    last_slot = registered.position_map.slots[-1]
    rosters = (
        BaselineRoster(registered.baseline_roster.plants[:-1]),
        BaselineRoster(
            (
                *registered.baseline_roster.plants,
                replace(last_plant, plant_id="alternate-added-plant"),
            )
        ),
    )
    maps = (
        PositionMap(registered.position_map.slots[:-1]),
        PositionMap(
            (
                *registered.position_map.slots,
                replace(
                    last_slot,
                    position_id="alternate-added-slot",
                    row=999,
                    column=999,
                ),
            )
        ),
    )
    for field_name, alternatives in (
        ("baseline_roster", rosters),
        ("position_map", maps),
    ):
        for alternative in alternatives:
            direct = replace(_bundle(registered))
            object.__setattr__(direct, field_name, alternative)
            with pytest.raises(AlmondLabError):
                revalidate_cohort_design_bundle(direct, config=registered.design)
            with pytest.raises(AlmondLabError):
                assemble_paper1_simulation_config(
                    **_aggregate_kwargs(discovery_design=direct)  # type: ignore[arg-type]
                )


def test_regenerated_298_16_k_design_passes_mechanics_but_not_registration() -> None:
    """Catches a self-consistent one-hundredth-kelvin config regeneration."""

    registered = _registered_authorities()
    first = registered.design.water_conditions[0]
    altered_design = registered.design.model_copy(
        update={
            "water_conditions": (
                first.model_copy(
                    update={
                        "chemistry": first.chemistry.model_copy(
                            update={"temperature_k": 298.16}
                        )
                    }
                ),
                registered.design.water_conditions[1],
            )
        }
    )
    mechanically_valid = _mechanical_bundle(
        seed=TASK3_ROOT_SEED,
        design=altered_design,
    )
    kwargs = _aggregate_kwargs(discovery_design=mechanically_valid)
    kwargs["design"] = altered_design
    with pytest.raises(AlmondLabError) as caught:
        assemble_paper1_simulation_config(**kwargs)  # type: ignore[arg-type]
    assert caught.value.code in {
        "PAPER1_WATER_RECIPE_INVALID",
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
    }


def test_relabelled_water_and_run_ids_do_not_bypass_design_revalidation() -> None:
    """Catches model_copy bypasses that relabel the frozen design namespaces."""

    registered = _registered_authorities()
    relabelled = registered.design.model_copy(
        update={
            "runs": tuple(f"alternate-{run_id}" for run_id in registered.design.runs),
            "water_conditions": tuple(
                water.model_copy(update={"water_id": f"alternate-{water.water_id}"})
                for water in registered.design.water_conditions
            ),
        }
    )
    _assert_error(
        "COHORT_DESIGN_INVALID",
        "config",
        lambda: assemble_cohort_design_bundle(
            cohort_id="discovery",
            config=relabelled,
            baseline_roster=registered.baseline_roster,
            position_map=registered.position_map,
            manifest=registered.manifest,
            audit=registered.audit,
        ),
    )


@pytest.mark.parametrize("alternate_seed", (0, 1, 20260813))
def test_generic_bundle_accepts_mechanical_replay_but_aggregate_rejects_it(
    alternate_seed: int,
) -> None:
    """Catches a valid alternate Task 3 draw being promoted to registration."""

    generic = _mechanical_bundle(seed=alternate_seed)
    assert generic.manifest.root_seed == alternate_seed
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "discovery_design.manifest.root_seed",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(discovery_design=generic)  # type: ignore[arg-type]
        ),
    )


def test_same_count_alternate_physical_ids_pass_mechanics_but_not_registration(
) -> None:
    """Catches relabeled plant, position, reservoir, batch, and event authority."""

    registered = _registered_authorities()

    def alternate_id(value: str | None) -> str | None:
        return None if value is None else f"alternate-{value}"

    roster = BaselineRoster(
        tuple(
            replace(
                plant,
                plant_id=alternate_id(plant.plant_id),
                transformation_batch_id=alternate_id(
                    plant.transformation_batch_id
                ),
                transformation_event_id=alternate_id(
                    plant.transformation_event_id
                ),
            )
            for plant in registered.baseline_roster.plants
        )
    )
    position_map = PositionMap(
        tuple(
            replace(
                slot,
                position_id=alternate_id(slot.position_id),
                reservoir_id=alternate_id(slot.reservoir_id),
                water_batch_id=alternate_id(slot.water_batch_id),
                greenhouse_compartment_id=alternate_id(
                    slot.greenhouse_compartment_id
                ),
                bench_id=alternate_id(slot.bench_id),
            )
            for slot in registered.position_map.slots
        )
    )
    alternate = _mechanical_bundle(
        seed=TASK3_ROOT_SEED,
        baseline_roster=roster,
        position_map=position_map,
    )
    assert len(alternate.baseline_roster.plants) == 720
    assert len(alternate.position_map.slots) == 720
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "discovery_design.manifest.allocation_sha256",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(discovery_design=alternate)  # type: ignore[arg-type]
        ),
    )


class _Bomb:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"hostile confirmation object was inspected: {name}")


def _direct_bundle_with_role(role: object) -> CohortDesignBundle:
    registered = _registered_authorities()
    value = object.__new__(CohortDesignBundle)
    object.__setattr__(value, "cohort_id", role)
    object.__setattr__(value, "baseline_roster", registered.baseline_roster)
    object.__setattr__(value, "position_map", registered.position_map)
    object.__setattr__(value, "manifest", registered.manifest)
    object.__setattr__(value, "audit", registered.audit)
    return value


def test_confirmation_bundle_fails_before_family_inspection() -> None:
    """Catches a future-facing annotation accidentally authorizing confirmation."""

    expected_details = {
        "required_authority": "task4_registered_confirmation_cohort_bundle"
    }
    error = _assert_error(
        "CONFIRMATION_DESIGN_REGISTRATION_REQUIRED",
        "cohort_id",
        lambda: assemble_cohort_design_bundle(
            cohort_id="confirmation",
            config=_Bomb(),  # type: ignore[arg-type]
            baseline_roster=_Bomb(),  # type: ignore[arg-type]
            position_map=_Bomb(),  # type: ignore[arg-type]
            manifest=_Bomb(),  # type: ignore[arg-type]
            audit=_Bomb(),  # type: ignore[arg-type]
        ),
    )
    assert error.details == expected_details
    error = _assert_error(
        "CONFIRMATION_DESIGN_REGISTRATION_REQUIRED",
        "cohort_id",
        lambda: revalidate_cohort_design_bundle(
            _direct_bundle_with_role("confirmation"),
            config=_Bomb(),  # type: ignore[arg-type]
        ),
    )
    assert error.details == expected_details
    _assert_error(
        "COHORT_DESIGN_INVALID",
        "cohort_id",
        lambda: revalidate_cohort_design_bundle(
            _direct_bundle_with_role(1),  # type: ignore[arg-type]
            config=_Bomb(),  # type: ignore[arg-type]
        ),
    )


def test_aggregate_confirmation_pairing_precedence_is_fail_closed() -> None:
    """Catches incomplete or opaque complete confirmation pairs being inspected."""

    for confirmation_config, confirmation_design in (
        (None, _Bomb()),
        (_Bomb(), None),
    ):
        error = _assert_error(
            "PAPER1_SIMULATION_CONFIG_INVALID",
            "confirmation_design",
            lambda config=confirmation_config, design=confirmation_design: (
                assemble_paper1_simulation_config(
                    **_aggregate_kwargs(  # type: ignore[arg-type]
                        confirmation_config=config,
                        confirmation_design=design,
                    )
                )
            ),
        )
        assert error.message == (
            "confirmation config and design must be absent or present together"
        )

    error = _assert_error(
        "CONFIRMATION_DESIGN_REGISTRATION_REQUIRED",
        "confirmation_design",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(  # type: ignore[arg-type]
                confirmation_config=_Bomb(),
                confirmation_design=_Bomb(),
            )
        ),
    )
    assert error.details == {
        "required_authority": "task4_registered_confirmation_cohort_bundle"
    }

    direct = replace(_simulation_config())
    object.__setattr__(direct, "confirmation_config", _Bomb())
    object.__setattr__(direct, "confirmation_design", _Bomb())
    error = _assert_error(
        "CONFIRMATION_DESIGN_REGISTRATION_REQUIRED",
        "confirmation_design",
        lambda: revalidate_paper1_simulation_config(direct),
    )
    assert error.details == {
        "required_authority": "task4_registered_confirmation_cohort_bundle"
    }


def test_registered_aggregate_round_trips_with_exact_hash_inventory() -> None:
    """Catches omitted retained authority, caller hashes, or mutable aggregate maps."""

    value = _simulation_config()
    checked = revalidate_paper1_simulation_config(value)
    assert checked is not value
    assert checked.design is not value.design
    assert checked.discovery_design is not value.discovery_design
    assert checked.generator is not value.generator
    assert checked.generator == checked.scenario_registry.anchor.generator
    assert checked.confirmation_config is None
    assert checked.confirmation_design is None
    assert checked.evidence_label is EvidenceLabel.SYNTHETIC_ONLY
    assert type(checked.candidate_effects) is type(MappingProxyType({}))
    assert type(checked.config_sha256s) is type(MappingProxyType({}))
    assert tuple(checked.config_sha256s) == tuple(EXPECTED_HASHES)
    assert dict(checked.config_sha256s) == dict(EXPECTED_HASHES)
    assert tuple(checked.candidate_effects) == (
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    )
    for candidate_id in checked.candidate_effects:
        assert checked.candidate_effects[candidate_id] is not (
            _registered_authorities().candidate_effects[candidate_id]
        )
        assert type(checked.candidate_effects[candidate_id].parameters) is type(
            MappingProxyType({})
        )


def test_aggregate_rejects_pydantic_subclasses_at_each_retained_authority() -> None:
    """Catches isinstance-only acceptance for every top-level typed authority."""

    kwargs = _aggregate_kwargs()
    expected_paths = {
        "design": "design",
        "candidates": "candidates",
        "model_domain": "model_domain",
        "water_recipes": "water_recipes",
        "scenario_registry": "scenario_registry",
        "stop_policy": "stop_policy",
    }
    for field_name, expected_path in expected_paths.items():
        base = kwargs[field_name]
        base_type = type(base)
        subclass = type(f"Hostile{base_type.__name__}", (base_type,), {})
        subclassed = subclass.model_construct(
            **{
                model_field: getattr(base, model_field)
                for model_field in base_type.model_fields
            }
        )
        attacked = dict(kwargs)
        attacked[field_name] = subclassed
        _assert_error(
            "PAPER1_SIMULATION_CONFIG_INVALID",
            expected_path,
            lambda attacked=attacked: assemble_paper1_simulation_config(
                **attacked  # type: ignore[arg-type]
            ),
        )


def test_registry_and_cross_object_drift_fail_closed() -> None:
    """Catches valid-looking design/domain/recipe/scenario/policy substitutions."""

    registered = _registered_authorities()
    first_water = registered.design.water_conditions[0]
    design = registered.design.model_copy(
        update={
            "water_conditions": (
                first_water.model_copy(
                    update={
                        "chemistry": first_water.chemistry.model_copy(
                            update={"temperature_k": 298.16}
                        )
                    }
                ),
                registered.design.water_conditions[1],
            )
        }
    )
    recipes = registered.water_recipes.model_copy(update={"schema_version": "9.9"})
    scenario_digest = registered.scenario_registry.model_copy(
        update={"water_recipe_registry_sha256": "0" * 64}
    )
    missing_scenario = registered.scenario_registry.model_copy(
        update={"scenarios": registered.scenario_registry.scenarios[:-1]}
    )
    extra_scenario = registered.scenario_registry.model_copy(
        update={
            "scenarios": (
                *registered.scenario_registry.scenarios,
                registered.scenario_registry.scenarios[-1],
            )
        }
    )
    missing_sensitivity = registered.scenario_registry.model_copy(
        update={"sensitivities": registered.scenario_registry.sensitivities[:-1]}
    )
    extra_sensitivity = registered.scenario_registry.model_copy(
        update={
            "sensitivities": (
                *registered.scenario_registry.sensitivities,
                registered.scenario_registry.sensitivities[-1],
            )
        }
    )
    generator = registered.scenario_registry.anchor.generator
    divergent_generator = generator.model_copy(
        update={
            "design": generator.design.model_copy(
                update={
                    "duration_days": generator.design.duration_days.model_copy(
                        update={"value": 85.0}
                    )
                }
            )
        }
    )
    scenario_generator = registered.scenario_registry.model_copy(
        update={
            "anchor": registered.scenario_registry.anchor.model_copy(
                update={"generator": divergent_generator}
            )
        }
    )
    stop_policy = registered.stop_policy.model_copy(
        update={"policy_id": "alternate-stop-policy"}
    )
    model_domain = registered.model_domain.model_copy(update={"version": "alternate"})

    attacks = (
        ("design", design),
        ("water_recipes", recipes),
        ("scenario_registry", scenario_digest),
        ("scenario_registry", missing_scenario),
        ("scenario_registry", extra_scenario),
        ("scenario_registry", missing_sensitivity),
        ("scenario_registry", extra_sensitivity),
        ("scenario_registry", scenario_generator),
        ("stop_policy", stop_policy),
        ("model_domain", model_domain),
    )
    for field_name, replacement_value in attacks:
        kwargs = _aggregate_kwargs()
        kwargs[field_name] = replacement_value
        with pytest.raises(AlmondLabError):
            assemble_paper1_simulation_config(**kwargs)  # type: ignore[arg-type]


def test_nominal_forcing_payload_is_derived_and_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a forcing-boundary result being trusted without canonical hashing."""

    import almondlab.simulate as simulate

    real = simulate.revalidate_nominal_forcing_artifact

    def altered_artifact(value: object) -> object:
        checked = real(value)
        record = checked.records[0].model_copy(
            update={"recipe_id": "unregistered-recipe@9.9"}
        )
        return checked.model_copy(update={"records": (record, *checked.records[1:])})

    monkeypatch.setattr(
        simulate,
        "revalidate_nominal_forcing_artifact",
        altered_artifact,
    )
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "paper1_nominal_forcing_schedule_v2:canonical_sha256",
        lambda: assemble_paper1_simulation_config(**_aggregate_kwargs()),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("missing_name", tuple(RAW_PATHS))
def test_raw_authority_requires_every_exact_byte_source(missing_name: str) -> None:
    """Catches an omitted raw source being recovered from a package or host path."""

    raw = _raw_authority_bytes()
    raw.pop(missing_name)
    _assert_error(
        "PAPER1_SIMULATION_CONFIG_INVALID",
        "raw_authority_bytes_by_name",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(  # type: ignore[arg-type]
                raw_authority_bytes_by_name=raw
            )
        ),
    )


@pytest.mark.parametrize("logical_name", tuple(RAW_PATHS))
def test_raw_authority_rejects_each_one_byte_mutation(logical_name: str) -> None:
    """Catches a raw digest being inferred from a matching typed object."""

    raw = _raw_authority_bytes()
    raw[logical_name] = raw[logical_name][:-1] + bytes(
        [raw[logical_name][-1] ^ 1]
    )
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        f"{logical_name}:raw_sha256",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(  # type: ignore[arg-type]
                raw_authority_bytes_by_name=raw
            )
        ),
    )


def test_raw_authority_rejects_aliases_extras_and_nonexact_types() -> None:
    """Catches path aliases, exotic maps, and bytes-like coercion at ingress."""

    class DictSubclass(dict[str, bytes]):
        pass

    class StringSubclass(str):
        pass

    class BytesSubclass(bytes):
        pass

    invalid_maps: tuple[object, ...] = (
        {**_raw_authority_bytes(), "configs/../candidates.yaml": b"x"},
        {
            **{
                key: value
                for key, value in _raw_authority_bytes().items()
                if key != "configs/candidates.yaml"
            },
            StringSubclass("configs/candidates.yaml"): RAW_PATHS[
                "configs/candidates.yaml"
            ].read_bytes(),
        },
        {
            **_raw_authority_bytes(),
            "configs/candidates.yaml": bytearray(b"x"),
        },
        {
            **_raw_authority_bytes(),
            "configs/candidates.yaml": memoryview(b"x"),
        },
        {
            **_raw_authority_bytes(),
            "configs/candidates.yaml": BytesSubclass(
                RAW_PATHS["configs/candidates.yaml"].read_bytes()
            ),
        },
        DictSubclass(_raw_authority_bytes()),
    )
    for raw in invalid_maps:
        _assert_error(
            "PAPER1_SIMULATION_CONFIG_INVALID",
            "raw_authority_bytes_by_name",
            lambda raw=raw: assemble_paper1_simulation_config(
                **_aggregate_kwargs(  # type: ignore[arg-type]
                    raw_authority_bytes_by_name=raw  # type: ignore[arg-type]
                )
            ),
        )


def test_raw_authority_rejects_path_forms_nonstring_keys_and_source_swaps() -> None:
    """Catches an eight-entry alias map or swapping two authentic raw sources."""

    original = _raw_authority_bytes()
    invalid: list[object] = []
    for alias in (
        "C:/authoring/configs/candidates.yaml",
        "configs\\candidates.yaml",
        "configs/../configs/candidates.yaml",
    ):
        raw = dict(original)
        value = raw.pop("configs/candidates.yaml")
        raw[alias] = value
        invalid.append(raw)
    raw = dict(original)
    value = raw.pop("configs/candidates.yaml")
    raw[Path("configs/candidates.yaml")] = value  # type: ignore[index]
    invalid.append(raw)
    raw = dict(original)
    raw["configs/candidates.yaml"], raw["configs/model_domains.yaml"] = (
        raw["configs/model_domains.yaml"],
        raw["configs/candidates.yaml"],
    )
    invalid.append(raw)

    for raw in invalid:
        with pytest.raises(AlmondLabError) as caught:
            assemble_paper1_simulation_config(
                **_aggregate_kwargs(  # type: ignore[arg-type]
                    raw_authority_bytes_by_name=raw  # type: ignore[arg-type]
                )
            )
        assert caught.value.code in {
            "PAPER1_SIMULATION_CONFIG_INVALID",
            "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        }


def test_candidate_effect_wrapper_rejects_shape_type_and_identifier_attacks() -> None:
    """Catches Task 2's permissive isinstance boundary leaking into Task 4."""

    registered = _registered_authorities()
    base = dict(registered.candidate_effects)
    invalid: list[Mapping[str, CandidateEffects]] = []
    invalid.append({key: base[key] for key in reversed(tuple(base))})
    invalid.append({key: value for key, value in base.items() if key != "C6"})
    invalid.append({**base, "C7": base["C6"]})
    invalid.append({**base, "C1": base["C2"]})

    class HostileEffects(CandidateEffects):
        pass

    invalid.append(
        {
            **base,
            "C1": HostileEffects(
                candidate_id="C1",
                schema_version="1.0.0",
                parameters=dict(base["C1"].parameters),
                evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR,
            ),
        }
    )
    for effects in invalid:
        _assert_error(
            "CANDIDATE_PARAMETER_VIOLATION",
            "candidate_effects",
            lambda effects=effects: assemble_paper1_simulation_config(
                **_aggregate_kwargs(  # type: ignore[arg-type]
                    candidate_effects=effects
                )
            ),
        )


def test_candidate_effect_wrapper_rejects_hostile_and_nonexact_mappings() -> None:
    """Catches lazy outers, mutable parameters, and equality-compatible subclasses."""

    registered = _registered_authorities()
    base = dict(registered.candidate_effects)

    class DictSubclass(dict[str, CandidateEffects]):
        pass

    class HostileMapping(Mapping[str, CandidateEffects]):
        def __getitem__(self, key: str) -> CandidateEffects:
            raise AssertionError("hostile mapping was read")

        def __iter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError("hostile mapping was iterated")

        def __len__(self) -> int:
            raise AssertionError("hostile mapping length was read")

    class StringSubclass(str):
        pass

    class FloatSubclass(float):
        pass

    attacks: list[object] = [DictSubclass(base), HostileMapping()]
    for target, replacement in (
        ("plain_mapping", dict(base["C1"].parameters)),
        (
            "subclass_key",
            MappingProxyType(
                {
                    **{
                        key: value
                        for key, value in base["C1"].parameters.items()
                        if key != "na_efflux_vmax_multiplier"
                    },
                    StringSubclass("na_efflux_vmax_multiplier"): base["C1"].parameters[
                        "na_efflux_vmax_multiplier"
                    ],
                }
            ),
        ),
        (
            "subclass_value",
            MappingProxyType(
                {
                    **dict(base["C1"].parameters),
                    "na_efflux_vmax_multiplier": FloatSubclass(
                        base["C1"].parameters["na_efflux_vmax_multiplier"]
                    ),
                }
            ),
        ),
        (
            "missing_parameter",
            MappingProxyType(
                {
                    key: value
                    for key, value in base["C1"].parameters.items()
                    if key != "na_efflux_vmax_multiplier"
                }
            ),
        ),
        (
            "extra_parameter",
            MappingProxyType({**dict(base["C1"].parameters), "extra": 1.0}),
        ),
    ):
        forged = replace(base["C1"])
        object.__setattr__(forged, "parameters", replacement)
        attacks.append({**base, "C1": forged})

    forged = replace(base["C1"])
    object.__setattr__(forged, "candidate_id", StringSubclass("C1"))
    attacks.append({**base, "C1": forged})
    forged = replace(base["C1"])
    object.__setattr__(forged, "schema_version", StringSubclass("1.0.0"))
    attacks.append({**base, "C1": forged})
    forged = replace(base["C1"])
    object.__setattr__(forged, "evidence_label", "hypothesis_prior")
    attacks.append({**base, "C1": forged})

    for effects in attacks:
        with pytest.raises(AlmondLabError) as caught:
            assemble_paper1_simulation_config(
                **_aggregate_kwargs(  # type: ignore[arg-type]
                    candidate_effects=effects  # type: ignore[arg-type]
                )
            )
        assert caught.value.code == "CANDIDATE_PARAMETER_VIOLATION"


@pytest.mark.parametrize(
    "replacement",
    (True, 1, float("nan"), float("inf"), float("-inf"), object()),
)
def test_candidate_effect_wrapper_rejects_nonprimitive_parameter_values(
    replacement: object,
) -> None:
    """Catches bool, integer, and nonfinite values surviving Task 2 coercion."""

    registered = _registered_authorities()
    effects = dict(registered.candidate_effects)
    hostile = replace(effects["C1"])
    parameters = dict(hostile.parameters)
    parameters["na_efflux_vmax_multiplier"] = replacement
    object.__setattr__(hostile, "parameters", MappingProxyType(parameters))
    effects["C1"] = hostile
    _assert_error(
        "CANDIDATE_PARAMETER_VIOLATION",
        "candidate_effects.C1.parameters.na_efflux_vmax_multiplier",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(candidate_effects=effects)  # type: ignore[arg-type]
        ),
    )


def test_structurally_valid_candidate_effect_drift_fails_before_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a finite replacement being accepted as a registered effect."""

    registered = _registered_authorities()
    effects = dict(registered.candidate_effects)
    parameters = dict(effects["C2"].parameters)
    parameters["ros_clearance_multiplier"] = 1.6
    effects["C2"] = replace(effects["C2"], parameters=parameters)

    def forbidden_application(*args: object, **kwargs: object) -> object:
        raise AssertionError("effect application ran before normalized authority")

    import almondlab.simulate as simulate

    monkeypatch.setattr(simulate, "apply_candidate_effects", forbidden_application)
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "fixtures/candidate_effects.yaml:normalized_sha256",
        lambda: assemble_paper1_simulation_config(
            **_aggregate_kwargs(candidate_effects=effects)  # type: ignore[arg-type]
        ),
    )


def test_candidate_primary_mechanism_mismatch_uses_task2_error() -> None:
    """Catches an altered CandidateSpec bypassing the public Task 2 mechanism gate."""

    registered = _registered_authorities()
    candidates = registered.candidates.model_copy(
        update={
            "candidates": (
                registered.candidates.candidates[0].model_copy(
                    update={"primary_parameter_id": "ros_clearance_multiplier"}
                ),
                *registered.candidates.candidates[1:],
            )
        }
    )
    kwargs = _aggregate_kwargs()
    kwargs["candidates"] = candidates
    _assert_error(
        "CANDIDATE_PARAMETER_VIOLATION",
        "candidate.primary_parameter_id",
        lambda: assemble_paper1_simulation_config(**kwargs),  # type: ignore[arg-type]
    )


def test_caller_owned_mappings_are_detached() -> None:
    """Catches aggregate output aliasing caller raw/effect dictionaries."""

    raw = _raw_authority_bytes()
    effects = dict(_registered_authorities().candidate_effects)
    shared_parameters = dict(effects["C1"].parameters)
    shared_effect = replace(effects["C1"])
    object.__setattr__(
        shared_effect,
        "parameters",
        MappingProxyType(shared_parameters),
    )
    effects["C1"] = shared_effect
    value = assemble_paper1_simulation_config(
        **_aggregate_kwargs(  # type: ignore[arg-type]
            candidate_effects=effects,
            raw_authority_bytes_by_name=raw,
        )
    )
    raw.clear()
    effects.clear()
    shared_parameters["na_efflux_vmax_multiplier"] = 999.0
    assert dict(value.config_sha256s) == dict(EXPECTED_HASHES)
    assert tuple(value.candidate_effects) == (
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    )
    assert (
        value.candidate_effects["C1"].parameters["na_efflux_vmax_multiplier"]
        != 999.0
    )


def test_revalidation_rejects_direct_hash_and_generator_corruption() -> None:
    """Catches frozen appearance being treated as factory provenance."""

    value = replace(_simulation_config())
    hashes = dict(value.config_sha256s)
    hashes["fixtures/paper1_small.yaml:raw_sha256"] = "0" * 64
    object.__setattr__(value, "config_sha256s", MappingProxyType(hashes))
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "fixtures/paper1_small.yaml:raw_sha256",
        lambda: revalidate_paper1_simulation_config(value),
    )

    value = replace(_simulation_config())
    altered_generator = value.generator.model_copy(
        update={
            "design": value.generator.design.model_copy(
                update={
                    "duration_days": value.generator.design.duration_days.model_copy(
                        update={"value": 85.0}
                    )
                }
            )
        }
    )
    object.__setattr__(value, "generator", altered_generator)
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "generator",
        lambda: revalidate_paper1_simulation_config(value),
    )


def test_revalidation_rejects_outer_subclass_and_evidence_forgery() -> None:
    """Catches direct dataclass construction being mistaken for factory evidence."""

    original = _simulation_config()

    class AggregateSubclass(Paper1SimulationConfig):
        pass

    subclassed = AggregateSubclass(
        **{
            field.name: getattr(original, field.name)
            for field in fields(Paper1SimulationConfig)
        }
    )
    _assert_error(
        "PAPER1_SIMULATION_CONFIG_INVALID",
        "value",
        lambda: revalidate_paper1_simulation_config(subclassed),
    )

    forged = replace(original)
    object.__setattr__(forged, "evidence_label", EvidenceLabel.HYPOTHESIS_PRIOR)
    _assert_error(
        "PAPER1_SIMULATION_CONFIG_INVALID",
        "evidence_label",
        lambda: revalidate_paper1_simulation_config(forged),
    )


def test_revalidation_rejects_nonexact_or_swapped_hash_inventory() -> None:
    """Catches mutable-looking, malformed, reordered, or cross-wired digests."""

    class DictSubclass(dict[str, str]):
        pass

    original = _simulation_config()
    registered = dict(EXPECTED_HASHES)
    missing = dict(registered)
    missing.pop("configs/candidates.yaml:raw_sha256")
    extra = {**registered, "extra:raw_sha256": "0" * 64}
    reversed_order = dict(reversed(tuple(registered.items())))
    malformed = dict(registered)
    malformed["configs/candidates.yaml:raw_sha256"] = "A" * 64
    swapped = dict(registered)
    swapped[
        "configs/candidates.yaml:raw_sha256"
    ], swapped["configs/candidates.yaml:normalized_sha256"] = (
        swapped["configs/candidates.yaml:normalized_sha256"],
        swapped["configs/candidates.yaml:raw_sha256"],
    )
    attacks: tuple[object, ...] = (
        missing,
        extra,
        reversed_order,
        malformed,
        swapped,
        DictSubclass(registered),
    )
    for hashes in attacks:
        forged = replace(original)
        object.__setattr__(forged, "config_sha256s", hashes)
        with pytest.raises(AlmondLabError) as caught:
            revalidate_paper1_simulation_config(forged)
        assert caught.value.code in {
            "PAPER1_SIMULATION_CONFIG_INVALID",
            "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        }


def test_revalidation_and_capacity_make_no_hidden_resource_or_path_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches reopening paper1_small.yaml after its digest was retained."""

    value = _simulation_config()

    def forbidden_read(*args: object, **kwargs: object) -> object:
        raise AssertionError("hidden authority read")

    monkeypatch.setattr(importlib.resources, "files", forbidden_read)
    checked = revalidate_paper1_simulation_config(value)
    assert checked.discovery_design.manifest.root_seed == TASK3_ROOT_SEED


def test_capacity_preflight_covers_nominal_and_every_water_loop_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches an omitted sensitivity or silently accepted S014 structural failure."""

    import almondlab.simulate as simulate

    real = paper1_contracts.preflight_shared_source_batch_capacity
    observed: list[tuple[object, object]] = []

    def recording_preflight(*args: object, **kwargs: object) -> object:
        binding = kwargs.get("registered_sensitivity_binding")
        try:
            result = real(*args, **kwargs)
        except AlmondLabError as error:
            observed.append((binding, error))
            raise
        observed.append((binding, result))
        return result

    monkeypatch.setattr(
        paper1_contracts,
        "preflight_shared_source_batch_capacity",
        recording_preflight,
    )
    monkeypatch.setattr(
        simulate,
        "preflight_shared_source_batch_capacity",
        recording_preflight,
    )
    value = assemble_paper1_simulation_config(**_aggregate_kwargs())  # type: ignore[arg-type]
    assert value.evidence_label is EvidenceLabel.SYNTHETIC_ONLY

    expected = {
        None: 3606.0,
        ("S013_initial_volume", 100.0): 3526.0,
        ("S013_initial_volume", 140.0): 3686.0,
        ("S014_return_fraction", 0.90): 1791.6,
        ("S015_irrigation", 0.40): 2698.8,
        ("S015_irrigation", 0.80): 4513.2,
        ("S016_anchor_purge", 0.60): 3404.4,
        ("S016_anchor_purge", 2.40): 4009.2,
        ("S017_sample_volume", 0.025): 3605.4,
        ("S017_sample_volume", 0.100): 3607.2,
        ("S036_insufficient_purge", 0.00): 3202.8,
        ("S036_insufficient_purge", 0.30): 3303.6,
    }
    seen: dict[object, float] = {}
    structural: AlmondLabError | None = None
    for binding, result in observed:
        key = None if binding is None else (binding[0], binding[2])
        if isinstance(result, AlmondLabError):
            assert key == ("S014_return_fraction", 0.50)
            structural = result
        else:
            assert len(result) == 4
            assert {audit.loop_count for audit in result} == {4}
            assert len({audit.aggregate_expected_debit_l for audit in result}) == 1
            seen[key] = result[0].aggregate_expected_debit_l
    assert set(seen) == set(expected)
    for key, expected_debit in expected.items():
        assert seen[key] == pytest.approx(expected_debit, rel=0.0, abs=1e-12)
    assert structural is not None
    assert structural.code == "WATER_BATCH_CAPACITY_EXCEEDED"
    assert structural.field_path == "manifest.records"
    assert structural.details == {
        "cohort_id": "discovery",
        "water_batch_id": "disc-r1-w1-water-batch",
        "aggregate_expected_debit_l": 5420.4,
        "capacity_l": 5000.0,
    }


def test_capacity_preflight_rejects_subclassed_passing_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a duck-typed or subclassed preflight result entering authority."""

    import almondlab.simulate as simulate

    registered = _registered_authorities()
    real_audits = paper1_contracts.preflight_shared_source_batch_capacity(
        registered.stop_policy,
        config=registered.design,
        baseline_roster=registered.baseline_roster,
        position_map=registered.position_map,
        manifest=registered.manifest,
        recipe_registry=registered.water_recipes,
        water_loop=registered.scenario_registry.anchor.generator.water_loop,
    )

    class AuditSubclass(SharedSourceBatchCapacityAudit):
        pass

    subclassed = tuple(
        AuditSubclass.model_validate(audit.model_dump(mode="json"))
        for audit in real_audits
    )
    monkeypatch.setattr(
        simulate,
        "preflight_shared_source_batch_capacity",
        lambda *args, **kwargs: subclassed,
    )
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "scenario_registry.anchor.generator.water_loop",
        lambda: assemble_paper1_simulation_config(**_aggregate_kwargs()),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("code", "field_path", "details"),
    (
        (
            "WRONG_CODE",
            "manifest.records",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
                "capacity_l": 5000.0,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records.water_batch_id",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
                "capacity_l": 5000.0,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
                "capacity_l": 5000.0,
                "extra": True,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records",
            {
                "cohort_id": "confirmation",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
                "capacity_l": 5000.0,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r2-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
                "capacity_l": 5000.0,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.3,
                "capacity_l": 5000.0,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
                "capacity_l": 5000.1,
            },
        ),
        (
            "WATER_BATCH_CAPACITY_EXCEEDED",
            "manifest.records",
            {
                "cohort_id": "discovery",
                "water_batch_id": "disc-r1-w1-water-batch",
                "aggregate_expected_debit_l": 5420.4,
            },
        ),
    ),
)
def test_s014_accepts_only_the_exact_structural_exception(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    field_path: str,
    details: dict[str, object],
) -> None:
    """Catches broad exception swallowing at the registered S014 boundary."""

    real = paper1_contracts.preflight_shared_source_batch_capacity

    def altered_preflight(*args: object, **kwargs: object) -> object:
        binding = kwargs.get("registered_sensitivity_binding")
        if binding is not None and binding[0] == "S014_return_fraction" and binding[2] == 0.50:
            raise AlmondLabError(code, "altered", field_path, details)
        return real(*args, **kwargs)

    monkeypatch.setattr(
        paper1_contracts,
        "preflight_shared_source_batch_capacity",
        altered_preflight,
    )
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "scenario_registry.sensitivities.S014_return_fraction",
        lambda: assemble_paper1_simulation_config(**_aggregate_kwargs()),  # type: ignore[arg-type]
    )


def test_s014_unexpected_pass_is_an_authority_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches the prospectively registered structural failure disappearing."""

    real = paper1_contracts.preflight_shared_source_batch_capacity

    def passing_preflight(*args: object, **kwargs: object) -> object:
        binding = kwargs.get("registered_sensitivity_binding")
        if (
            binding is not None
            and binding[0] == "S014_return_fraction"
            and binding[2] == 0.50
        ):
            return ()
        return real(*args, **kwargs)

    monkeypatch.setattr(
        paper1_contracts,
        "preflight_shared_source_batch_capacity",
        passing_preflight,
    )
    _assert_error(
        "PAPER1_CONFIG_AUTHORITY_MISMATCH",
        "scenario_registry.sensitivities.S014_return_fraction",
        lambda: assemble_paper1_simulation_config(**_aggregate_kwargs()),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "target_binding",
    (None, ("S013_initial_volume", 100.0)),
)
def test_unexpected_capacity_errors_pass_through_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    target_binding: object,
) -> None:
    """Catches broad conversion of nominal or non-S014 capacity failures."""

    import almondlab.simulate as simulate

    real = paper1_contracts.preflight_shared_source_batch_capacity
    sentinel = AlmondLabError(
        "SENTINEL_CAPACITY_FAILURE",
        "unexpected capacity failure",
        "sentinel.capacity",
        {"target": str(target_binding)},
    )

    def failing_preflight(*args: object, **kwargs: object) -> object:
        binding = kwargs.get("registered_sensitivity_binding")
        comparable = None if binding is None else (binding[0], binding[2])
        if comparable == target_binding:
            raise sentinel
        return real(*args, **kwargs)

    monkeypatch.setattr(
        paper1_contracts,
        "preflight_shared_source_batch_capacity",
        failing_preflight,
    )
    monkeypatch.setattr(
        simulate,
        "preflight_shared_source_batch_capacity",
        failing_preflight,
    )
    with pytest.raises(AlmondLabError) as caught:
        assemble_paper1_simulation_config(**_aggregate_kwargs())  # type: ignore[arg-type]
    assert caught.value is sentinel


def test_import_orders_have_no_cycle() -> None:
    """Catches design/contracts importing the downstream simulation aggregate."""

    for order in (
        ("almondlab.design", "almondlab.paper1_contracts", "almondlab.simulate"),
        ("almondlab.simulate", "almondlab.paper1_contracts", "almondlab.design"),
    ):
        completed = subprocess.run(
            [sys.executable, "-c", ";".join(f"import {name}" for name in order)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
