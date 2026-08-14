"""Discovery-only Task 4 runtime authority assembly.

This module authenticates already registered inputs.  It intentionally contains
no Task 4 outcome RNG, calibration, candidate ranking, confirmation-family
construction, run-directory creation, or artifact output.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from math import isclose, isfinite
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel

from almondlab.biology_surrogate import CandidateEffects, apply_candidate_effects
from almondlab.contracts import EvidenceLabel
from almondlab.design import (
    BaselineRoster,
    ConfirmationDesignConfig,
    ExperimentalUnitAudit,
    ExperimentalUnitSpec,
    PositionMap,
    RandomizationManifest,
    cohort_identity_set,
    randomize,
    revalidate_baseline_roster,
    revalidate_experimental_unit_audit,
    revalidate_position_map,
    revalidate_randomization_manifest,
)
from almondlab.errors import AlmondLabError, fail
from almondlab.paper1_contracts import (
    CandidateRegistry,
    CandidateSpec,
    Paper1DesignConfig,
    Paper1WaterRecipeRegistry,
    SensitivityRegistry,
    SharedSourceBatchCapacityAudit,
    SyntheticGeneratorConfig,
    SyntheticScenarioRegistry,
    Task4StopPolicy,
    apply_registered_sensitivity,
    preflight_shared_source_batch_capacity,
    validate_active_paper1_water_recipes,
)
from almondlab.provenance import canonical_json_bytes
from almondlab.schemas import ModelDomain
from almondlab.task4_forcing import (
    NominalForcingArtifact,
    revalidate_nominal_forcing_artifact,
)


_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_CANDIDATE_IDS = ("C1", "C2", "C3", "C4", "C5", "C6")
_PRIMARY_PARAMETER_IDS = MappingProxyType(
    {
        "C1": "na_efflux_vmax_multiplier",
        "C2": "ros_clearance_multiplier",
        "C3": "mannitol_vmax_multiplier",
        "C4": "na_efflux_vmax_multiplier",
        "C5": "xylem_na_retrieval_multiplier",
        "C6": "sos_efflux_activation_multiplier",
    }
)
_RAW_AUTHORITY_NAMES = (
    "configs/candidates.yaml",
    "configs/experiment_paper1.yaml",
    "configs/model_domains.yaml",
    "configs/paper1_task4_stop_policy.yaml",
    "configs/paper1_water_recipes.yaml",
    "configs/synthetic_scenarios.yaml",
    "fixtures/candidate_effects.yaml",
    "fixtures/paper1_small.yaml",
)
_RAW_SHA256S = MappingProxyType(
    {
        "configs/candidates.yaml": (
            "f4eb6c496ddfce2fb7077db34a03e6836da2cd4c62ad21d504b0227a277c5a05"
        ),
        "configs/experiment_paper1.yaml": (
            "a40c28829c4ca3dadb3a87a3f6e8731b73ab9d38a53f2dae9b4c26657ac8ab18"
        ),
        "configs/model_domains.yaml": (
            "0cac0e90c7746e4897f760d2ff87a57d2ddceb175690d51be1beb31f41719411"
        ),
        "configs/paper1_task4_stop_policy.yaml": (
            "03e07ee719e5e376e9c03202be945c6b02d77a7373a3bdb164d5c08f7427ee34"
        ),
        "configs/paper1_water_recipes.yaml": (
            "d46a0e4dc02cd74cfa5b4f437f367009301d4aab8cad9a1115ec6be37afa24d3"
        ),
        "configs/synthetic_scenarios.yaml": (
            "fdc7b4068d80a9d5e42f7c2c5322d7a79b076951b1cccc3ba674af91a53d56d6"
        ),
        "fixtures/candidate_effects.yaml": (
            "4e92c1567227b9e1f6e0713b79890bfc652a5b21a8de013769eaaa01ac939c21"
        ),
        "fixtures/paper1_small.yaml": (
            "beecb5f2a3637aee52bcd74b5b717ff59f4d9bfe9a57a11429cf00950ee6a4b6"
        ),
    }
)
_NORMALIZED_SHA256S = MappingProxyType(
    {
        "configs/candidates.yaml:normalized_sha256": (
            "4e401c13ebfd97544a7f5bf7e7c967637dbf8329f0650dae7676c4656968f0ca"
        ),
        "configs/experiment_paper1.yaml:normalized_sha256": (
            "f5911a6a63d7444575c2013d9737b9219ef21fb1f5c58dcc5fd633bcde38f5c9"
        ),
        "configs/model_domains.yaml::core_v1:normalized_sha256": (
            "f6e80805ac05a2059baae3e9a05dab1c89b988911b34a366a46249bb9fac8ee0"
        ),
        "configs/paper1_task4_stop_policy.yaml:normalized_sha256": (
            "94c1aee1bc6b5547973e29d201373dfbe2f545ec694ac5dc9b836b40fa0127a9"
        ),
        "configs/paper1_water_recipes.yaml:normalized_sha256": (
            "8a902441d143017fddfddf5b174302187dd8da1d9a46f98af9a94d18e317b1bd"
        ),
        "configs/synthetic_scenarios.yaml:normalized_sha256": (
            "4229e855bcf783d994ce24f6dc98d1dc8eded92f5134f854880cb44204f6150a"
        ),
        "fixtures/candidate_effects.yaml:normalized_sha256": (
            "0d5b62381409a3ed814b4687291e7f4c4c987c8d84db63353b85c11789fe25e8"
        ),
        "paper1_nominal_forcing_schedule_v2:canonical_sha256": (
            "329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96"
        ),
    }
)
_CONFIG_SHA256_NAMES = (
    "configs/candidates.yaml:raw_sha256",
    "configs/candidates.yaml:normalized_sha256",
    "configs/experiment_paper1.yaml:raw_sha256",
    "configs/experiment_paper1.yaml:normalized_sha256",
    "configs/model_domains.yaml:raw_sha256",
    "configs/model_domains.yaml::core_v1:normalized_sha256",
    "configs/paper1_task4_stop_policy.yaml:raw_sha256",
    "configs/paper1_task4_stop_policy.yaml:normalized_sha256",
    "configs/paper1_water_recipes.yaml:raw_sha256",
    "configs/paper1_water_recipes.yaml:normalized_sha256",
    "configs/synthetic_scenarios.yaml:raw_sha256",
    "configs/synthetic_scenarios.yaml:normalized_sha256",
    "fixtures/candidate_effects.yaml:raw_sha256",
    "fixtures/candidate_effects.yaml:normalized_sha256",
    "fixtures/paper1_small.yaml:raw_sha256",
    "paper1_nominal_forcing_schedule_v2:canonical_sha256",
)
_DISCOVERY_ROOT_SEED = 20260812
_DISCOVERY_CONFIG_SHA256 = (
    "f5911a6a63d7444575c2013d9737b9219ef21fb1f5c58dcc5fd633bcde38f5c9"
)
_DISCOVERY_ROSTER_SHA256 = (
    "f34dc944bf951fc8c2f752d981433482d475a4c4f3091e6d8d8f2e7d0df719d8"
)
_DISCOVERY_POSITION_SHA256 = (
    "fed49c40785388661b46a0ee5c174617e39230fac80171677cfdcca9b9d9cbea"
)
_DISCOVERY_ALLOCATION_SHA256 = (
    "bd4cb366ac9c3144ab881af29615311839f1fc0a9a881645ba4995dcab7b7c3f"
)
_DISCOVERY_MANIFEST_SHA256 = (
    "dea12ab75748223c01e24accbe92eca153a7da90aa3b1235294e75699ad7516f"
)
_CAPACITY_EXPECTED = MappingProxyType(
    {
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
)
_CAPACITY_SENSITIVITY_IDS = (
    "S013_initial_volume",
    "S014_return_fraction",
    "S015_irrigation",
    "S016_anchor_purge",
    "S017_sample_volume",
    "S036_insufficient_purge",
)
_CAPACITY_BATCH_AUTHORITIES = MappingProxyType(
    {
        "disc-r1-w1-water-batch": (
            "nonsaline_nutrient_matched_control",
            "paper1_base_nutrient_control_v1",
            "1eb4a39c6c1f0c1180d13352764a1536ba3c3399ac906cba00a9594d1530df71",
        ),
        "disc-r1-w2-water-batch": (
            "pilot_selected_full_ion_marine_challenge",
            "paper1_base_plus_nacl40_challenge_v1",
            "9ad6c980516b54fe774e860d211d0677eb71946baa43232b9eb70685fbf543be",
        ),
        "disc-r2-w1-water-batch": (
            "nonsaline_nutrient_matched_control",
            "paper1_base_nutrient_control_v1",
            "1eb4a39c6c1f0c1180d13352764a1536ba3c3399ac906cba00a9594d1530df71",
        ),
        "disc-r2-w2-water-batch": (
            "pilot_selected_full_ion_marine_challenge",
            "paper1_base_plus_nacl40_challenge_v1",
            "9ad6c980516b54fe774e860d211d0677eb71946baa43232b9eb70685fbf543be",
        ),
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CohortDesignBundle:
    cohort_id: Literal["discovery", "confirmation"]
    baseline_roster: BaselineRoster
    position_map: PositionMap
    manifest: RandomizationManifest
    audit: ExperimentalUnitAudit


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


def _simulation_invalid(message: str, field_path: str) -> None:
    fail("PAPER1_SIMULATION_CONFIG_INVALID", message, field_path)


def _authority_mismatch(message: str, field_path: str) -> None:
    fail("PAPER1_CONFIG_AUTHORITY_MISMATCH", message, field_path)


def _cohort_invalid(message: str, field_path: str) -> None:
    fail("COHORT_DESIGN_INVALID", message, field_path)


def _confirmation_required(field_path: str) -> None:
    fail(
        "CONFIRMATION_DESIGN_REGISTRATION_REQUIRED",
        "confirmation design requires separately approved registration",
        field_path,
        {"required_authority": "task4_registered_confirmation_cohort_bundle"},
    )


def _candidate_invalid(
    message: str,
    field_path: str,
    *,
    cause: Exception | None = None,
) -> None:
    details = None if cause is None else {"cause_type": type(cause).__name__}
    fail("CANDIDATE_PARAMETER_VIOLATION", message, field_path, details)


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _model_payload(value: BaseModel) -> dict[str, object]:
    payload = value.model_dump(mode="json", warnings="error")
    if type(payload) is not dict:
        raise TypeError("registered model did not serialize to a mapping")
    return payload


def _canonical_authority_model(
    value: object,
    expected_type: type[BaseModel],
    *,
    input_field: str,
    digest_field: str,
) -> BaseModel:
    if type(value) is not expected_type:
        _simulation_invalid(
            f"{input_field} must be an exact {expected_type.__name__}",
            input_field,
        )
    try:
        payload = _model_payload(value)
        return expected_type.model_validate(payload)
    except Exception as error:
        _authority_mismatch(
            f"{input_field} failed complete canonical reconstruction",
            digest_field,
        )


def _canonical_discovery_design(config: object) -> Paper1DesignConfig:
    if type(config) is not Paper1DesignConfig:
        _cohort_invalid(
            "discovery requires an exact Paper1DesignConfig",
            "config",
        )
    try:
        return Paper1DesignConfig.model_validate(_model_payload(config))
    except Exception:
        _cohort_invalid("discovery config failed canonical reconstruction", "config")


def assemble_cohort_design_bundle(
    *,
    cohort_id: Literal["discovery", "confirmation"],
    config: Paper1DesignConfig | ConfirmationDesignConfig,
    baseline_roster: BaselineRoster,
    position_map: PositionMap,
    manifest: RandomizationManifest,
    audit: ExperimentalUnitAudit,
) -> CohortDesignBundle:
    """Canonically assemble one mechanical discovery design bundle."""

    if type(cohort_id) is not str:
        _cohort_invalid("cohort_id must be a primitive role string", "cohort_id")
    if cohort_id == "confirmation":
        _confirmation_required("cohort_id")
    if cohort_id != "discovery":
        _cohort_invalid("cohort_id is not a registered role", "cohort_id")

    checked_config = _canonical_discovery_design(config)
    checked_roster = revalidate_baseline_roster(baseline_roster)
    checked_map = revalidate_position_map(position_map)
    checked_manifest = revalidate_randomization_manifest(manifest)
    identity = cohort_identity_set(
        checked_manifest,
        baseline_roster=checked_roster,
        position_map=checked_map,
    )
    if identity.cohort_id != "discovery":
        _cohort_invalid("physical inputs are not a discovery cohort", "cohort_id")
    spec = ExperimentalUnitSpec.from_design(
        checked_config,
        position_map=checked_map,
    )
    checked_audit = revalidate_experimental_unit_audit(
        audit,
        records=checked_manifest.records,
        spec=spec,
    )
    replayed = randomize(
        checked_config,
        checked_manifest.root_seed,
        position_map=checked_map,
        baseline_roster=checked_roster,
    )
    if not hmac.compare_digest(
        replayed.canonical_json_bytes(),
        checked_manifest.canonical_json_bytes(),
    ):
        _cohort_invalid(
            "manifest differs from deterministic Task 3 replay",
            "manifest",
        )
    return CohortDesignBundle(
        cohort_id="discovery",
        baseline_roster=checked_roster,
        position_map=checked_map,
        manifest=checked_manifest,
        audit=checked_audit,
    )


def revalidate_cohort_design_bundle(
    value: object,
    *,
    config: Paper1DesignConfig | ConfirmationDesignConfig,
) -> CohortDesignBundle:
    """Reconstruct an exact bundle; frozen appearance is never trusted."""

    if type(value) is not CohortDesignBundle:
        _cohort_invalid("value must be an exact CohortDesignBundle", "cohort_id")
    try:
        cohort_id = value.cohort_id
    except Exception:
        _cohort_invalid("cohort_id could not be read", "cohort_id")
    if type(cohort_id) is not str:
        _cohort_invalid("cohort_id must be a primitive role string", "cohort_id")
    if cohort_id == "confirmation":
        _confirmation_required("cohort_id")
    if cohort_id != "discovery":
        _cohort_invalid("cohort_id is not a registered role", "cohort_id")
    return assemble_cohort_design_bundle(
        cohort_id="discovery",
        config=config,
        baseline_roster=value.baseline_roster,
        position_map=value.position_map,
        manifest=value.manifest,
        audit=value.audit,
    )


def _check_confirmation_pair(
    confirmation_config: object,
    confirmation_design: object,
) -> None:
    config_present = confirmation_config is not None
    design_present = confirmation_design is not None
    if config_present != design_present:
        fail(
            "PAPER1_SIMULATION_CONFIG_INVALID",
            "confirmation config and design must be absent or present together",
            "confirmation_design",
        )
    if config_present:
        _confirmation_required("confirmation_design")


def _canonical_raw_authority_bytes(
    value: object,
) -> dict[str, str]:
    if type(value) not in (dict, _MAPPING_PROXY_TYPE):
        _simulation_invalid(
            "raw authority bytes must be an exact dictionary or mapping proxy",
            "raw_authority_bytes_by_name",
        )
    try:
        keys = tuple(value)
        if (
            len(keys) != len(_RAW_AUTHORITY_NAMES)
            or set(keys) != set(_RAW_AUTHORITY_NAMES)
            or any(type(key) is not str for key in keys)
        ):
            _simulation_invalid(
                "raw authority names must equal the exact eight-key inventory",
                "raw_authority_bytes_by_name",
            )
        supplied = {name: value[name] for name in _RAW_AUTHORITY_NAMES}
    except AlmondLabError:
        raise
    except Exception:
        _simulation_invalid(
            "raw authority mapping could not be copied",
            "raw_authority_bytes_by_name",
        )
    if any(type(item) is not bytes for item in supplied.values()):
        _simulation_invalid(
            "raw authority values must be exact bytes",
            "raw_authority_bytes_by_name",
        )
    observed: dict[str, str] = {}
    for name in _RAW_AUTHORITY_NAMES:
        digest = hashlib.sha256(supplied[name]).hexdigest()
        if not hmac.compare_digest(digest, _RAW_SHA256S[name]):
            _authority_mismatch(
                "raw authority bytes differ from the registration",
                f"{name}:raw_sha256",
            )
        observed[f"{name}:raw_sha256"] = digest
    return observed


def _canonical_retained_hashes(value: object) -> dict[str, str]:
    if type(value) not in (dict, _MAPPING_PROXY_TYPE):
        _simulation_invalid(
            "config_sha256s must be an exact dictionary or mapping proxy",
            "config_sha256s",
        )
    try:
        keys = tuple(value)
        if keys != _CONFIG_SHA256_NAMES:
            _simulation_invalid(
                "config_sha256s must equal the exact 16-key inventory",
                "config_sha256s",
            )
        copied = {name: value[name] for name in _CONFIG_SHA256_NAMES}
    except AlmondLabError:
        raise
    except Exception:
        _simulation_invalid("config_sha256s could not be copied", "config_sha256s")
    for name, digest in copied.items():
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _simulation_invalid("config digest is not lowercase SHA-256", name)
        expected = (
            _RAW_SHA256S[name.removesuffix(":raw_sha256")]
            if name.endswith(":raw_sha256")
            else _NORMALIZED_SHA256S[name]
        )
        if not hmac.compare_digest(digest, expected):
            _authority_mismatch(
                "retained config digest differs from the registration",
                name,
            )
    return copied


def _candidate_effect_payload(
    value: Mapping[str, CandidateEffects],
) -> dict[str, object]:
    return {
        candidate_id: {
            "candidate_id": effect.candidate_id,
            "schema_version": effect.schema_version,
            "parameters": dict(effect.parameters),
            "evidence_label": effect.evidence_label.value,
        }
        for candidate_id, effect in value.items()
    }


def _canonical_candidate_effects(
    value: object,
) -> Mapping[str, CandidateEffects]:
    if type(value) not in (dict, _MAPPING_PROXY_TYPE):
        _candidate_invalid(
            "candidate effects must be an exact dictionary or mapping proxy",
            "candidate_effects",
        )
    try:
        keys = tuple(value)
    except Exception as error:
        _candidate_invalid(
            "candidate effect mapping could not be iterated",
            "candidate_effects",
            cause=error,
        )
    if keys != _CANDIDATE_IDS or any(type(key) is not str for key in keys):
        _candidate_invalid(
            "candidate effects must contain ordered C1 through C6",
            "candidate_effects",
        )
    rebuilt: dict[str, CandidateEffects] = {}
    for candidate_id in _CANDIDATE_IDS:
        base_path = f"candidate_effects.{candidate_id}"
        try:
            effect = value[candidate_id]
            if type(effect) is not CandidateEffects:
                _candidate_invalid(
                    "candidate effect must be an exact CandidateEffects",
                    "candidate_effects",
                )
            if type(effect.candidate_id) is not str or effect.candidate_id != candidate_id:
                _candidate_invalid(
                    "candidate effect key and identifier differ",
                    "candidate_effects",
                )
            if type(effect.schema_version) is not str:
                _candidate_invalid(
                    "candidate schema version must be a primitive string",
                    f"{base_path}.schema_version",
                )
            if type(effect.evidence_label) is not EvidenceLabel:
                _candidate_invalid(
                    "candidate evidence must be an exact EvidenceLabel",
                    f"{base_path}.evidence_label",
                )
            if type(effect.parameters) is not _MAPPING_PROXY_TYPE:
                _candidate_invalid(
                    "candidate parameter mapping must be an exact mapping proxy",
                    f"{base_path}.parameters",
                )
            parameter_items = tuple(effect.parameters.items())
            for key, parameter in parameter_items:
                if type(key) is not str:
                    _candidate_invalid(
                        "candidate parameter keys must be primitive strings",
                        f"{base_path}.parameters",
                    )
                if type(parameter) is not float or not isfinite(parameter):
                    _candidate_invalid(
                        "candidate parameter values must be finite primitive floats",
                        f"{base_path}.parameters.{key}",
                    )
            copied_parameters = dict(parameter_items)
            reconstructed = CandidateEffects(
                candidate_id=effect.candidate_id,
                schema_version=effect.schema_version,
                parameters=copied_parameters,
                evidence_label=effect.evidence_label,
            )
        except AlmondLabError:
            raise
        except Exception as error:
            _candidate_invalid(
                "candidate effect failed complete reconstruction",
                base_path,
                cause=error,
            )
        rebuilt[candidate_id] = reconstructed
    immutable = MappingProxyType(rebuilt)
    digest = _sha256(_candidate_effect_payload(immutable))
    field_path = "fixtures/candidate_effects.yaml:normalized_sha256"
    if not hmac.compare_digest(digest, _NORMALIZED_SHA256S[field_path]):
        _authority_mismatch(
            "candidate effects differ from the registered normalized authority",
            field_path,
        )
    return immutable


def _candidate_rows(value: object) -> tuple[CandidateSpec, ...]:
    if type(value) is not CandidateRegistry:
        _simulation_invalid(
            "candidates must be an exact CandidateRegistry",
            "candidates",
        )
    try:
        rows = value.candidates
    except Exception as error:
        _candidate_invalid(
            "candidate registry could not be read",
            "candidates",
            cause=error,
        )
    if (
        type(rows) is not tuple
        or len(rows) != 6
        or any(type(row) is not CandidateSpec for row in rows)
        or tuple(row.candidate_id for row in rows) != _CANDIDATE_IDS
    ):
        _candidate_invalid(
            "candidate registry must contain exact ordered base records",
            "candidates",
        )
    return rows


def _canonical_candidate_registry(
    value: CandidateRegistry,
    *,
    effects: Mapping[str, CandidateEffects],
    anchor_parameters: object,
) -> CandidateRegistry:
    rows = _candidate_rows(value)
    for candidate, candidate_id in zip(rows, _CANDIDATE_IDS, strict=True):
        try:
            primary = candidate.primary_parameter_id
        except Exception as error:
            _candidate_invalid(
                "candidate primary mechanism could not be read",
                "candidate.primary_parameter_id",
                cause=error,
            )
        if type(primary) is not str or primary != _PRIMARY_PARAMETER_IDS[candidate_id]:
            _candidate_invalid(
                "candidate primary parameter disagrees with the isolation registry",
                "candidate.primary_parameter_id",
            )
        apply_candidate_effects(
            anchor_parameters,  # type: ignore[arg-type]
            effects[candidate_id],
            candidate,
        )
    try:
        checked = CandidateRegistry.model_validate(_model_payload(value))
    except AlmondLabError:
        raise
    except Exception:
        _authority_mismatch(
            "candidate registry failed complete canonical reconstruction",
            "configs/candidates.yaml:normalized_sha256",
        )
    digest = _sha256(_model_payload(checked))
    field_path = "configs/candidates.yaml:normalized_sha256"
    if not hmac.compare_digest(digest, _NORMALIZED_SHA256S[field_path]):
        _authority_mismatch(
            "candidate registry differs from normalized authority",
            field_path,
        )
    return checked


def _roster_payload(roster: BaselineRoster) -> list[dict[str, object]]:
    return [
        {
            "plant_id": plant.plant_id,
            "group_id": plant.group_id,
            "pretreatment_canopy": plant.pretreatment_canopy,
            "baseline_canopy_stratum": plant.baseline_canopy_stratum,
            "transformation_batch_block": plant.transformation_batch_block,
            "transformation_batch_id": plant.transformation_batch_id,
            "transformation_event_id": plant.transformation_event_id,
            "cohort_id": plant.cohort_id,
        }
        for plant in sorted(roster.plants, key=lambda item: item.plant_id)
    ]


def _position_payload(position_map: PositionMap) -> list[dict[str, object]]:
    return [
        {
            "position_id": slot.position_id,
            "run_id": slot.run_id,
            "run_sequence_ordinal": slot.run_sequence_ordinal,
            "water_id": slot.water_id,
            "reservoir_id": slot.reservoir_id,
            "water_batch_id": slot.water_batch_id,
            "greenhouse_compartment_id": slot.greenhouse_compartment_id,
            "bench_id": slot.bench_id,
            "row": slot.row,
            "column": slot.column,
            "spatial_gradient_profile_id": slot.spatial_gradient_profile_id,
            "permitted_movement_schedule_ids": list(
                slot.permitted_movement_schedule_ids
            ),
            "cohort_id": slot.cohort_id,
        }
        for slot in sorted(position_map.slots, key=lambda item: item.position_id)
    ]


def _require_registered_discovery(bundle: CohortDesignBundle) -> None:
    manifest = bundle.manifest
    literal_checks = (
        (
            manifest.root_seed == _DISCOVERY_ROOT_SEED,
            "discovery_design.manifest.root_seed",
        ),
        (
            manifest.config_sha256 == _DISCOVERY_CONFIG_SHA256,
            "discovery_design.manifest.config_sha256",
        ),
        (
            manifest.allocation_sha256 == _DISCOVERY_ALLOCATION_SHA256,
            "discovery_design.manifest.allocation_sha256",
        ),
        (
            dict(manifest.input_sha256s)
            == {
                "baseline_roster_canonical": _DISCOVERY_ROSTER_SHA256,
                "position_map_canonical": _DISCOVERY_POSITION_SHA256,
            },
            "discovery_design.manifest.input_sha256s",
        ),
        (
            len(manifest.records) == 720,
            "discovery_design.manifest.records",
        ),
        (
            bundle.audit.biological_n == 720
            and bundle.audit.water_treatment_n == 16,
            "discovery_design.audit",
        ),
        (
            _sha256(_roster_payload(bundle.baseline_roster))
            == _DISCOVERY_ROSTER_SHA256,
            "discovery_design.baseline_roster",
        ),
        (
            _sha256(_position_payload(bundle.position_map))
            == _DISCOVERY_POSITION_SHA256,
            "discovery_design.position_map",
        ),
        (
            hashlib.sha256(manifest.canonical_json_bytes()).hexdigest()
            == _DISCOVERY_MANIFEST_SHA256,
            "discovery_design.manifest",
        ),
    )
    for passed, field_path in literal_checks:
        if not passed:
            _authority_mismatch(
                "discovery design differs from the registered Task 3 authority",
                field_path,
            )


def _derive_nominal_forcing(
    scenario_registry: SyntheticScenarioRegistry,
    water_recipes: Paper1WaterRecipeRegistry,
) -> tuple[NominalForcingArtifact, str]:
    recipes = {
        recipe.water_id: f"{recipe.recipe_id}@{recipe.revision}"
        for recipe in water_recipes.active_recipes
    }
    records: list[dict[str, object]] = []
    for water_id, schedule in scenario_registry.anchor.forcings_by_water_id.items():
        for step_index, forcing in enumerate(schedule):
            records.append(
                {
                    "water_id": water_id,
                    "recipe_id": recipes[water_id],
                    "step_index": step_index,
                    "start_hour": float(12 * step_index),
                    "forcing": forcing,
                }
            )
    try:
        artifact = NominalForcingArtifact.model_validate(
            {
                "schema_version": "1.1.0",
                "materialization_algorithm": (
                    "paper1_nominal_forcing_schedule_v2"
                ),
                "water_ids": tuple(scenario_registry.anchor.forcings_by_water_id),
                "records": records,
                "evidence_label": EvidenceLabel.SYNTHETIC_ONLY,
            }
        )
        checked = revalidate_nominal_forcing_artifact(artifact)
        digest = _sha256(_model_payload(checked))
    except AlmondLabError:
        raise
    except Exception:
        _authority_mismatch(
            "nominal forcing could not be derived from retained authorities",
            "paper1_nominal_forcing_schedule_v2:canonical_sha256",
        )
    expected = _NORMALIZED_SHA256S[
        "paper1_nominal_forcing_schedule_v2:canonical_sha256"
    ]
    if not hmac.compare_digest(digest, expected):
        _authority_mismatch(
            "derived nominal forcing differs from registered authority",
            "paper1_nominal_forcing_schedule_v2:canonical_sha256",
        )
    return checked, digest


def _validate_capacity_audits(
    audits: object,
    *,
    expected_debit: float,
    field_path: str,
) -> None:
    if type(audits) is not tuple or len(audits) != 4:
        _authority_mismatch(
            "capacity preflight result differs from registration",
            field_path,
        )
    expected_batch_ids = tuple(_CAPACITY_BATCH_AUTHORITIES)
    for index, audit in enumerate(audits):
        if type(audit) is not SharedSourceBatchCapacityAudit:
            _authority_mismatch(
                "capacity preflight result differs from registration",
                field_path,
            )
        try:
            checked = SharedSourceBatchCapacityAudit.model_validate(
                _model_payload(audit)
            )
        except Exception:
            _authority_mismatch(
                "capacity preflight result differs from registration",
                field_path,
            )
        batch_id = expected_batch_ids[index]
        water_id, recipe_id, chemistry_sha256 = _CAPACITY_BATCH_AUTHORITIES[
            batch_id
        ]
        primitive_types_match = (
            type(checked.cohort_id) is str
            and type(checked.water_batch_id) is str
            and type(checked.water_id) is str
            and type(checked.recipe_id) is str
            and type(checked.recipe_revision) is str
            and type(checked.chemistry_sha256) is str
            and type(checked.loop_count) is int
            and type(checked.aggregate_expected_debit_l) is float
            and type(checked.capacity_l) is float
            and type(checked.remaining_capacity_l) is float
        )
        authority_matches = (
            primitive_types_match
            and checked == audit
            and checked.cohort_id == "discovery"
            and checked.water_batch_id == batch_id
            and checked.water_id == water_id
            and checked.recipe_id == recipe_id
            and checked.recipe_revision == "1.0.0"
            and checked.chemistry_sha256 == chemistry_sha256
            and checked.loop_count == 4
            and isclose(
                checked.aggregate_expected_debit_l,
                expected_debit,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            and checked.capacity_l == 5000.0
            and isclose(
                checked.remaining_capacity_l,
                5000.0 - expected_debit,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )
        if not authority_matches:
            _authority_mismatch(
                "capacity preflight result differs from registration",
                field_path,
            )


def _is_registered_s014_rejection(error: AlmondLabError) -> bool:
    expected_details = {
        "cohort_id": "discovery",
        "water_batch_id": "disc-r1-w1-water-batch",
        "aggregate_expected_debit_l": 5420.4,
        "capacity_l": 5000.0,
    }
    return (
        error.code == "WATER_BATCH_CAPACITY_EXCEEDED"
        and error.field_path == "manifest.records"
        and type(error.details) is dict
        and error.details == expected_details
        and tuple(error.details) == tuple(expected_details)
        and type(error.details["cohort_id"]) is str
        and type(error.details["water_batch_id"]) is str
        and type(error.details["aggregate_expected_debit_l"]) is float
        and type(error.details["capacity_l"]) is float
    )


def _preflight_registered_capacity(
    *,
    design: Paper1DesignConfig,
    discovery_design: CohortDesignBundle,
    water_recipes: Paper1WaterRecipeRegistry,
    scenario_registry: SyntheticScenarioRegistry,
    stop_policy: Task4StopPolicy,
) -> None:
    authority_tuple = (
        (
            design,
            discovery_design.baseline_roster,
            discovery_design.position_map,
            discovery_design.manifest,
        ),
    )
    nominal = preflight_shared_source_batch_capacity(
        stop_policy,
        config=design,
        baseline_roster=discovery_design.baseline_roster,
        position_map=discovery_design.position_map,
        manifest=discovery_design.manifest,
        recipe_registry=water_recipes,
        water_loop=scenario_registry.anchor.generator.water_loop,
    )
    _validate_capacity_audits(
        nominal,
        expected_debit=_CAPACITY_EXPECTED[None],
        field_path="scenario_registry.anchor.generator.water_loop",
    )
    try:
        sensitivities = SensitivityRegistry(
            schema_version="1.0.0",
            records=scenario_registry.sensitivities,
        )
    except Exception:
        _authority_mismatch(
            "scenario sensitivity inventory is incomplete",
            "scenario_registry.sensitivities",
        )
    by_id = {record.sensitivity_id: record for record in sensitivities.records}
    for sensitivity_id in _CAPACITY_SENSITIVITY_IDS:
        record = by_id[sensitivity_id]
        for value_index, selected_value in enumerate(record.values):
            field_path = f"scenario_registry.sensitivities.{sensitivity_id}"
            try:
                applied = apply_registered_sensitivity(
                    sensitivities,
                    scenario_registry=scenario_registry,
                    recipe_registry=water_recipes,
                    selections=((sensitivity_id, value_index),),
                    capacity_authorities=authority_tuple,
                    stop_policy=stop_policy,
                )
            except AlmondLabError as error:
                if sensitivity_id == "S014_return_fraction" and selected_value == 0.50:
                    if _is_registered_s014_rejection(error):
                        continue
                    _authority_mismatch(
                        "S014 structural rejection differs from registration",
                        "scenario_registry.sensitivities.S014_return_fraction",
                    )
                raise
            if sensitivity_id == "S014_return_fraction" and selected_value == 0.50:
                _authority_mismatch(
                    "S014 structural rejection unexpectedly passed",
                    "scenario_registry.sensitivities.S014_return_fraction",
                )
            expected = _CAPACITY_EXPECTED[(sensitivity_id, float(selected_value))]
            _validate_capacity_audits(
                applied.capacity_audits,
                expected_debit=expected,
                field_path=field_path,
            )


def _normalized_digest(
    value: BaseModel,
    *,
    field_path: str,
) -> str:
    try:
        digest = _sha256(_model_payload(value))
    except Exception:
        _authority_mismatch("authority could not be normalized", field_path)
    expected = _NORMALIZED_SHA256S[field_path]
    if not hmac.compare_digest(digest, expected):
        _authority_mismatch("normalized authority differs from registration", field_path)
    return digest


def _assemble_validated_simulation_config(
    *,
    design: object,
    candidates: object,
    candidate_effects: object,
    model_domain: object,
    water_recipes: object,
    scenario_registry: object,
    stop_policy: object,
    discovery_design: object,
    generator: object | None,
    raw_hashes: Mapping[str, str],
) -> Paper1SimulationConfig:
    checked_design = _canonical_authority_model(
        design,
        Paper1DesignConfig,
        input_field="design",
        digest_field="configs/experiment_paper1.yaml:normalized_sha256",
    )
    checked_domain = _canonical_authority_model(
        model_domain,
        ModelDomain,
        input_field="model_domain",
        digest_field="configs/model_domains.yaml::core_v1:normalized_sha256",
    )
    if type(water_recipes) is not Paper1WaterRecipeRegistry:
        _simulation_invalid(
            "water_recipes must be an exact Paper1WaterRecipeRegistry",
            "water_recipes",
        )
    validate_active_paper1_water_recipes(
        water_recipes,
        design=checked_design,  # type: ignore[arg-type]
        domain=checked_domain,  # type: ignore[arg-type]
        physical_use=False,
    )
    checked_recipes = _canonical_authority_model(
        water_recipes,
        Paper1WaterRecipeRegistry,
        input_field="water_recipes",
        digest_field="configs/paper1_water_recipes.yaml:normalized_sha256",
    )
    checked_scenarios = _canonical_authority_model(
        scenario_registry,
        SyntheticScenarioRegistry,
        input_field="scenario_registry",
        digest_field="configs/synthetic_scenarios.yaml:normalized_sha256",
    )
    checked_policy = _canonical_authority_model(
        stop_policy,
        Task4StopPolicy,
        input_field="stop_policy",
        digest_field="configs/paper1_task4_stop_policy.yaml:normalized_sha256",
    )

    effects = _canonical_candidate_effects(candidate_effects)
    checked_candidates = _canonical_candidate_registry(
        candidates,  # type: ignore[arg-type]
        effects=effects,
        anchor_parameters=checked_scenarios.anchor.parameters,  # type: ignore[attr-defined]
    )
    if type(discovery_design) is not CohortDesignBundle:
        _simulation_invalid(
            "discovery_design must be an exact CohortDesignBundle",
            "discovery_design",
        )
    checked_bundle = revalidate_cohort_design_bundle(
        discovery_design,
        config=checked_design,  # type: ignore[arg-type]
    )
    _require_registered_discovery(checked_bundle)

    derived_generator = SyntheticGeneratorConfig.model_validate(
        _model_payload(checked_scenarios.anchor.generator)  # type: ignore[attr-defined]
    )
    if generator is not None:
        if type(generator) is not SyntheticGeneratorConfig:
            _simulation_invalid(
                "generator must be an exact SyntheticGeneratorConfig",
                "generator",
            )
        try:
            retained_generator = SyntheticGeneratorConfig.model_validate(
                _model_payload(generator)
            )
        except Exception:
            _authority_mismatch(
                "retained generator failed canonical reconstruction",
                "generator",
            )
        if _model_payload(retained_generator) != _model_payload(derived_generator):
            _authority_mismatch(
                "retained generator differs from the scenario anchor",
                "generator",
            )

    normalized_recipe_digest = _normalized_digest(
        checked_recipes,  # type: ignore[arg-type]
        field_path="configs/paper1_water_recipes.yaml:normalized_sha256",
    )
    if checked_scenarios.water_recipe_registry_sha256 != normalized_recipe_digest:  # type: ignore[attr-defined]
        _authority_mismatch(
            "scenario registry names a different recipe authority",
            "scenario_registry.water_recipe_registry_sha256",
        )

    normalized = {
        "configs/candidates.yaml:normalized_sha256": _normalized_digest(
            checked_candidates,
            field_path="configs/candidates.yaml:normalized_sha256",
        ),
        "configs/experiment_paper1.yaml:normalized_sha256": _normalized_digest(
            checked_design,  # type: ignore[arg-type]
            field_path="configs/experiment_paper1.yaml:normalized_sha256",
        ),
        "configs/model_domains.yaml::core_v1:normalized_sha256": _normalized_digest(
            checked_domain,  # type: ignore[arg-type]
            field_path="configs/model_domains.yaml::core_v1:normalized_sha256",
        ),
        "configs/paper1_task4_stop_policy.yaml:normalized_sha256": _normalized_digest(
            checked_policy,  # type: ignore[arg-type]
            field_path="configs/paper1_task4_stop_policy.yaml:normalized_sha256",
        ),
        "configs/paper1_water_recipes.yaml:normalized_sha256": normalized_recipe_digest,
        "configs/synthetic_scenarios.yaml:normalized_sha256": _normalized_digest(
            checked_scenarios,  # type: ignore[arg-type]
            field_path="configs/synthetic_scenarios.yaml:normalized_sha256",
        ),
        "fixtures/candidate_effects.yaml:normalized_sha256": _sha256(
            _candidate_effect_payload(effects)
        ),
    }
    _, nominal_digest = _derive_nominal_forcing(
        checked_scenarios,  # type: ignore[arg-type]
        checked_recipes,  # type: ignore[arg-type]
    )
    normalized[
        "paper1_nominal_forcing_schedule_v2:canonical_sha256"
    ] = nominal_digest

    hashes: dict[str, str] = {}
    for name in _CONFIG_SHA256_NAMES:
        if name.endswith(":raw_sha256"):
            if name not in raw_hashes:
                _simulation_invalid("retained raw digest is missing", name)
            hashes[name] = raw_hashes[name]
        else:
            hashes[name] = normalized[name]
    for name in _CONFIG_SHA256_NAMES:
        expected = (
            _RAW_SHA256S[name.removesuffix(":raw_sha256")]
            if name.endswith(":raw_sha256")
            else _NORMALIZED_SHA256S[name]
        )
        if not hmac.compare_digest(hashes[name], expected):
            _authority_mismatch("aggregate digest differs from registration", name)

    _preflight_registered_capacity(
        design=checked_design,  # type: ignore[arg-type]
        discovery_design=checked_bundle,
        water_recipes=checked_recipes,  # type: ignore[arg-type]
        scenario_registry=checked_scenarios,  # type: ignore[arg-type]
        stop_policy=checked_policy,  # type: ignore[arg-type]
    )
    return Paper1SimulationConfig(
        design=checked_design,  # type: ignore[arg-type]
        candidates=checked_candidates,
        candidate_effects=effects,
        model_domain=checked_domain,  # type: ignore[arg-type]
        water_recipes=checked_recipes,  # type: ignore[arg-type]
        scenario_registry=checked_scenarios,  # type: ignore[arg-type]
        stop_policy=checked_policy,  # type: ignore[arg-type]
        discovery_design=checked_bundle,
        confirmation_config=None,
        confirmation_design=None,
        generator=derived_generator,
        config_sha256s=MappingProxyType(hashes),
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )


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
) -> Paper1SimulationConfig:
    """Authenticate and detach the registered discovery runtime inputs."""

    _check_confirmation_pair(confirmation_config, confirmation_design)
    raw_hashes = _canonical_raw_authority_bytes(raw_authority_bytes_by_name)
    return _assemble_validated_simulation_config(
        design=design,
        candidates=candidates,
        candidate_effects=candidate_effects,
        model_domain=model_domain,
        water_recipes=water_recipes,
        scenario_registry=scenario_registry,
        stop_policy=stop_policy,
        discovery_design=discovery_design,
        generator=None,
        raw_hashes=raw_hashes,
    )


def revalidate_paper1_simulation_config(
    value: object,
) -> Paper1SimulationConfig:
    """Reconstruct every retained authority without reopening any source."""

    if type(value) is not Paper1SimulationConfig:
        _simulation_invalid(
            "value must be an exact Paper1SimulationConfig",
            "value",
        )
    if (
        type(value.evidence_label) is not EvidenceLabel
        or value.evidence_label is not EvidenceLabel.SYNTHETIC_ONLY
    ):
        _simulation_invalid(
            "evidence_label must be the synthesized synthetic-only label",
            "evidence_label",
        )
    _check_confirmation_pair(value.confirmation_config, value.confirmation_design)
    retained = _canonical_retained_hashes(value.config_sha256s)
    raw_hashes = {
        name: retained[name]
        for name in _CONFIG_SHA256_NAMES
        if name.endswith(":raw_sha256")
    }
    return _assemble_validated_simulation_config(
        design=value.design,
        candidates=value.candidates,
        candidate_effects=value.candidate_effects,
        model_domain=value.model_domain,
        water_recipes=value.water_recipes,
        scenario_registry=value.scenario_registry,
        stop_policy=value.stop_policy,
        discovery_design=value.discovery_design,
        generator=value.generator,
        raw_hashes=raw_hashes,
    )
