"""Hash-locked Task 4 nominal and calibration forcing contracts.

This module is deliberately limited to exogenous forcing.  It neither imports
the simulator/calibration solver nor contains plant outcomes.  Runtime panel
bundles are defensive typed reconstructions of the prospectively registered
artifacts; their digest authenticates the artifact payload and is never part of
the bytes being hashed.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from dataclasses import fields
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Annotated, Literal, Never

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SkipValidation,
    field_validator,
    model_validator,
)

from almondlab.biology_surrogate import RootZoneForcing
from almondlab.contracts import EvidenceLabel
from almondlab.errors import AlmondLabError, fail
from almondlab.hydraulics import HydraulicDomain
from almondlab.provenance import canonical_json_bytes


_MAPPING_PROXY_TYPE = type(MappingProxyType({}))

TASK4_FORCING_SCHEMA_VERSION = "1.1.0"
TASK4_ROOT_SEED = 420260813
TASK4_WATER_IDS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
TASK4_RECIPE_IDS = MappingProxyType(
    {
        TASK4_WATER_IDS[0]: "paper1_base_nutrient_control_v1@1.0.0",
        TASK4_WATER_IDS[1]: "paper1_base_plus_nacl40_challenge_v1@1.0.0",
    }
)
TASK4_NOMINAL_FORCING_SHA256 = (
    "329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96"
)
TASK4_CALIBRATION_FORCING_SHA256 = MappingProxyType(
    {
        ("fit", 32): "8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3",
        ("holdout", 32): "80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a",
        ("fit", 64): "4e32c2831ea039c5a1939aed19091160f9c8c112d99a9e2bc937f05539b51eaf",
        ("holdout", 64): "d1f5b6b185458f50f6453391065e6af970ce5069921507431ce46fede0f9ca5a",
        ("fit", 128): "91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9",
        ("holdout", 128): "3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11",
    }
)

_NOMINAL_ALGORITHM = "paper1_nominal_forcing_schedule_v2"
_CALIBRATION_ALGORITHM = "paper1_calibration_forcing_panel_v2"
_FORCING_SCHEMA_VERSION = "paper1_root_zone_forcing@1.0.0"
_PANEL_SIZES = frozenset({32, 64, 128})
_SENSITIVITY_ID = "S031_panel_size"
_FORCING_FIELD_NAMES = tuple(field.name for field in fields(RootZoneForcing))
_FORCING_FIELD_SET = frozenset(_FORCING_FIELD_NAMES)
_DOMAIN_FIELD_NAMES = tuple(HydraulicDomain.model_fields)
_DOMAIN_FIELD_SET = frozenset(_DOMAIN_FIELD_NAMES)
_REGISTERED_DOMAIN_PAYLOAD = MappingProxyType(
    {
        "model_id": "paper1-biology-v1",
        "version": "1.0.0",
        "purpose": "model_applicability",
        "osmolality_min": 0.0,
        "osmolality_max": 0.5,
        "temperature_k_min": 290.0,
        "temperature_k_max": 305.0,
        "permitted_evidence_label": "physics_constrained",
        "extrapolation_policy": "deny",
    }
)


class _StrictForcingModel(BaseModel):
    """Frozen boundary model with no coercive instance/subclass shortcut."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        arbitrary_types_allowed=True,
        revalidate_instances="always",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_subclasses_and_exotic_mappings(cls, value: object) -> object:
        if isinstance(value, cls) and type(value) is not cls:
            raise ValueError(f"{cls.__name__} requires an exact model instance")
        if isinstance(value, Mapping):
            if type(value) not in (dict, _MAPPING_PROXY_TYPE):
                raise ValueError(f"{cls.__name__} requires a primitive mapping")
            if any(type(key) is not str for key in value):
                raise ValueError(f"{cls.__name__} requires primitive string keys")
        return value


def _mapping(
    value: object,
    *,
    expected: frozenset[str],
    field_path: str,
) -> Mapping[str, object]:
    if type(value) not in (dict, _MAPPING_PROXY_TYPE):
        raise ValueError(f"{field_path} must be a primitive mapping")
    if any(type(key) is not str for key in value):
        raise ValueError(f"{field_path} keys must be primitive strings")
    observed = frozenset(value)
    if observed != expected:
        raise ValueError(
            f"{field_path} requires exact keys; "
            f"missing={sorted(expected - observed)!r}, "
            f"extra={sorted(observed - expected)!r}"
        )
    return value


def _exact_string(value: object, field_path: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{field_path} must be a nonempty primitive string")
    return value


def _exact_integer(
    value: object,
    field_path: str,
    *,
    minimum: int = 0,
    maximum: int = 2**53 - 1,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(
            f"{field_path} must be an exact integer in [{minimum}, {maximum}]"
        )
    return value


def _exact_float(value: object, field_path: str) -> float:
    if type(value) is not float or not isfinite(value):
        raise ValueError(f"{field_path} must be an exact finite Python float")
    return value


def _sequence(value: object, field_path: str) -> Sequence[object]:
    if type(value) not in (list, tuple):
        raise ValueError(f"{field_path} must be a primitive list or tuple")
    return value


def _evidence_value(value: object, field_path: str) -> EvidenceLabel:
    if type(value) not in (str, EvidenceLabel):
        raise ValueError(f"{field_path} must be an exact evidence label")
    try:
        label = value if type(value) is EvidenceLabel else EvidenceLabel(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_path} is not a recognized evidence label") from error
    if label is not EvidenceLabel.SYNTHETIC_ONLY:
        raise ValueError(f"{field_path} must be synthetic_only")
    return label


def _domain_payload(value: HydraulicDomain) -> dict[str, object]:
    return {
        name: (
            getattr(value, name).value
            if isinstance(getattr(value, name), Enum)
            else getattr(value, name)
        )
        for name in _DOMAIN_FIELD_NAMES
    }


def _require_exact_runtime_domain(value: object, field_path: str) -> HydraulicDomain:
    if type(value) is not HydraulicDomain:
        raise ValueError(f"{field_path} must be an exact HydraulicDomain")
    for name in (
        "model_id",
        "version",
        "purpose",
        "extrapolation_policy",
    ):
        _exact_string(getattr(value, name), f"{field_path}.{name}")
    for name in (
        "osmolality_min",
        "osmolality_max",
        "temperature_k_min",
        "temperature_k_max",
    ):
        _exact_float(getattr(value, name), f"{field_path}.{name}")
    if type(value.permitted_evidence_label) is not EvidenceLabel:
        raise ValueError(
            f"{field_path}.permitted_evidence_label must be an exact EvidenceLabel"
        )
    return value


def _reconstruct_registered_domain(value: object) -> HydraulicDomain:
    if isinstance(value, HydraulicDomain) and type(value) is not HydraulicDomain:
        raise ValueError("forcing.hydraulic_domain must be an exact model")
    if type(value) is HydraulicDomain:
        _require_exact_runtime_domain(value, "forcing.hydraulic_domain")
        raw: object = {
            name: getattr(value, name) for name in _DOMAIN_FIELD_NAMES
        }
    else:
        raw = value
    supplied = _mapping(
        raw,
        expected=_DOMAIN_FIELD_SET,
        field_path="forcing.hydraulic_domain",
    )
    for name in (
        "osmolality_min",
        "osmolality_max",
        "temperature_k_min",
        "temperature_k_max",
    ):
        _exact_float(supplied[name], f"forcing.hydraulic_domain.{name}")
    for name in ("model_id", "version", "purpose", "extrapolation_policy"):
        _exact_string(supplied[name], f"forcing.hydraulic_domain.{name}")
    label = supplied["permitted_evidence_label"]
    if type(label) not in (str, EvidenceLabel):
        raise ValueError(
            "forcing.hydraulic_domain.permitted_evidence_label must be exact"
        )
    plain = {
        name: (item.value if isinstance(item, Enum) else item)
        for name, item in supplied.items()
    }
    if canonical_json_bytes(plain) != canonical_json_bytes(
        dict(_REGISTERED_DOMAIN_PAYLOAD)
    ):
        raise ValueError("forcing.hydraulic_domain is not the registered domain")
    # Rebuild the exact caller-derived payload after byte authentication.  In
    # particular, never replace a signed-zero or forged enum with a registered
    # constant merely because Python equality considers the values equal.
    checked = HydraulicDomain.model_validate(plain)
    if type(checked) is not HydraulicDomain:
        raise ValueError("forcing.hydraulic_domain reconstruction was not exact")
    return checked


def _forcing_payload(value: RootZoneForcing) -> dict[str, object]:
    return {
        name: (
            _domain_payload(value.hydraulic_domain)
            if name == "hydraulic_domain"
            else value.evidence_label.value
            if name == "evidence_label"
            else getattr(value, name)
        )
        for name in _FORCING_FIELD_NAMES
    }


def _require_exact_runtime_forcing(value: object, field_path: str) -> RootZoneForcing:
    if type(value) is not RootZoneForcing:
        raise ValueError(f"{field_path} must be an exact RootZoneForcing")
    for name in _FORCING_FIELD_NAMES:
        if name in {"evidence_label", "hydraulic_domain"}:
            continue
        _exact_float(getattr(value, name), f"{field_path}.{name}")
    if type(value.evidence_label) is not EvidenceLabel:
        raise ValueError(f"{field_path}.evidence_label must be an exact EvidenceLabel")
    _require_exact_runtime_domain(
        value.hydraulic_domain,
        f"{field_path}.hydraulic_domain",
    )
    return value


def _reconstruct_forcing(value: object) -> RootZoneForcing:
    if isinstance(value, RootZoneForcing) and type(value) is not RootZoneForcing:
        raise ValueError("forcing must be an exact RootZoneForcing")
    if type(value) is RootZoneForcing:
        _require_exact_runtime_forcing(value, "forcing")
        raw: object = {
            name: getattr(value, name) for name in _FORCING_FIELD_NAMES
        }
    else:
        raw = value
    supplied = _mapping(raw, expected=_FORCING_FIELD_SET, field_path="forcing")
    numeric: dict[str, float] = {}
    for name in _FORCING_FIELD_NAMES:
        if name in {"evidence_label", "hydraulic_domain"}:
            continue
        numeric[name] = _exact_float(supplied[name], f"forcing.{name}")

    # This is the registered Task 4 forcing boundary, not a general biology
    # constructor.  It rejects otherwise-finite but out-of-domain caller data
    # before hashing.
    if not 0.0 <= numeric["measured_osmolality_osmol_kg"] <= 0.5:
        raise ValueError("forcing.measured_osmolality_osmol_kg is out of domain")
    if not 290.0 <= numeric["temperature_k"] <= 305.0:
        raise ValueError("forcing.temperature_k is out of domain")
    if not 0.0 < numeric["water_density_kg_l"] <= 2.0:
        raise ValueError("forcing.water_density_kg_l is out of domain")
    if not -2.0 <= numeric["matric_potential_mpa"] <= 0.0:
        raise ValueError("forcing.matric_potential_mpa is out of domain")
    if numeric["leaf_critical_potential_mpa"] != -1.8:
        raise ValueError("forcing.leaf_critical_potential_mpa is unregistered")
    if not 0.0 <= numeric["apar_mol_h"] <= 2.0:
        raise ValueError("forcing.apar_mol_h is out of domain")
    if not 0.0 <= numeric["temperature_factor"] <= 1.0:
        raise ValueError("forcing.temperature_factor is out of domain")
    if not 0.0 < numeric["potential_transpiration_l_day"] <= 2.0:
        raise ValueError("forcing.potential_transpiration_l_day is out of domain")
    if numeric["duration_hours"] != 12.0:
        raise ValueError("forcing.duration_hours must equal 12.0")

    label = _evidence_value(supplied["evidence_label"], "forcing.evidence_label")
    domain = _reconstruct_registered_domain(supplied["hydraulic_domain"])
    return RootZoneForcing(
        **numeric,
        evidence_label=label,
        hydraulic_domain=domain,
    )


def _water_id(value: object) -> str:
    checked = _exact_string(value, "water_id")
    if checked not in TASK4_WATER_IDS:
        raise ValueError("water_id is not registered")
    return checked


def _recipe_id(value: object) -> str:
    return _exact_string(value, "recipe_id")


class NominalForcingRecord(_StrictForcingModel):
    water_id: str
    recipe_id: str
    step_index: int = Field(ge=0, le=167)
    start_hour: float
    forcing: Annotated[RootZoneForcing, SkipValidation]

    _water = field_validator("water_id", mode="before")(_water_id)
    _recipe = field_validator("recipe_id", mode="before")(_recipe_id)

    @field_validator("step_index", mode="before")
    @classmethod
    def validate_step_index(cls, value: object) -> int:
        return _exact_integer(value, "step_index", maximum=167)

    @field_validator("start_hour", mode="before")
    @classmethod
    def validate_start_hour(cls, value: object) -> float:
        return _exact_float(value, "start_hour")

    @field_validator("forcing", mode="before")
    @classmethod
    def validate_forcing(cls, value: object) -> RootZoneForcing:
        return _reconstruct_forcing(value)

    @model_validator(mode="after")
    def validate_coordinate(self) -> "NominalForcingRecord":
        if self.recipe_id != TASK4_RECIPE_IDS[self.water_id]:
            raise ValueError("recipe_id does not match water_id")
        if self.start_hour != float(12 * self.step_index):
            raise ValueError("start_hour does not match step_index")
        return self


class NominalForcingArtifact(_StrictForcingModel):
    schema_version: Literal["1.1.0"]
    materialization_algorithm: Literal["paper1_nominal_forcing_schedule_v2"]
    water_ids: tuple[str, str]
    records: tuple[NominalForcingRecord, ...]
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

    @field_validator("water_ids", mode="before")
    @classmethod
    def validate_water_ids(cls, value: object) -> tuple[str, str]:
        supplied = _sequence(value, "water_ids")
        if tuple(supplied) != TASK4_WATER_IDS or any(
            type(item) is not str for item in supplied
        ):
            raise ValueError("water_ids must equal the registered two-water order")
        return TASK4_WATER_IDS

    @field_validator("records", mode="before")
    @classmethod
    def reconstruct_records(
        cls, value: object
    ) -> tuple[NominalForcingRecord, ...]:
        supplied = _sequence(value, "records")
        rebuilt: list[NominalForcingRecord] = []
        for index, item in enumerate(supplied):
            if isinstance(item, NominalForcingRecord) and type(
                item
            ) is not NominalForcingRecord:
                raise ValueError(f"records.{index} must be an exact model")
            if type(item) is NominalForcingRecord:
                payload: object = {
                    name: getattr(item, name)
                    for name in NominalForcingRecord.model_fields
                }
            else:
                payload = item
            rebuilt.append(NominalForcingRecord.model_validate(payload))
        return tuple(rebuilt)

    @field_validator("evidence_label", mode="before")
    @classmethod
    def validate_evidence_label(cls, value: object) -> EvidenceLabel:
        return _evidence_value(value, "evidence_label")

    @model_validator(mode="after")
    def validate_registered_sequence(self) -> "NominalForcingArtifact":
        if len(self.records) != 336:
            raise ValueError("nominal records must contain exactly 336 entries")
        for ordinal, record in enumerate(self.records):
            water_id = TASK4_WATER_IDS[ordinal // 168]
            step_index = ordinal % 168
            if record.water_id != water_id or record.step_index != step_index:
                raise ValueError("nominal records are not in registered order")
            expected_day = step_index % 2 == 0
            expected = {
                "measured_osmolality_osmol_kg": 0.02
                if water_id == TASK4_WATER_IDS[0]
                else 0.1,
                "temperature_k": 297.15 if expected_day else 293.15,
                "water_density_kg_l": 0.9973 if expected_day else 0.9982,
                "matric_potential_mpa": -0.08 if expected_day else -0.04,
                "leaf_critical_potential_mpa": -1.8,
                "apar_mol_h": 0.8 if expected_day else 0.0,
                "temperature_factor": 0.85 if expected_day else 0.65,
                "potential_transpiration_l_day": 0.8 if expected_day else 0.15,
                "duration_hours": 12.0,
            }
            if any(getattr(record.forcing, name) != value for name, value in expected.items()):
                raise ValueError("nominal forcing values differ from registration")
        return self


class CalibrationForcingRecord(_StrictForcingModel):
    panel_index: int = Field(ge=0, le=127)
    water_id: str
    recipe_id: str
    step_index: int = Field(ge=0, le=167)
    start_hour: float
    forcing: Annotated[RootZoneForcing, SkipValidation]

    _water = field_validator("water_id", mode="before")(_water_id)
    _recipe = field_validator("recipe_id", mode="before")(_recipe_id)

    @field_validator("panel_index", mode="before")
    @classmethod
    def validate_panel_index(cls, value: object) -> int:
        return _exact_integer(value, "panel_index", maximum=127)

    @field_validator("step_index", mode="before")
    @classmethod
    def validate_step_index(cls, value: object) -> int:
        return _exact_integer(value, "step_index", maximum=167)

    @field_validator("start_hour", mode="before")
    @classmethod
    def validate_start_hour(cls, value: object) -> float:
        return _exact_float(value, "start_hour")

    @field_validator("forcing", mode="before")
    @classmethod
    def validate_forcing(cls, value: object) -> RootZoneForcing:
        return _reconstruct_forcing(value)

    @model_validator(mode="after")
    def validate_coordinate(self) -> "CalibrationForcingRecord":
        if self.recipe_id != TASK4_RECIPE_IDS[self.water_id]:
            raise ValueError("recipe_id does not match water_id")
        if self.start_hour != float(12 * self.step_index):
            raise ValueError("start_hour does not match step_index")
        return self


class CalibrationForcingPanel(_StrictForcingModel):
    panel_index: int = Field(ge=0, le=127)
    forcings_by_water_id: Annotated[
        Mapping[str, tuple[RootZoneForcing, ...]], SkipValidation
    ]

    @field_validator("panel_index", mode="before")
    @classmethod
    def validate_panel_index(cls, value: object) -> int:
        return _exact_integer(value, "panel_index", maximum=127)

    @field_validator("forcings_by_water_id", mode="before")
    @classmethod
    def reconstruct_forcings(
        cls, value: object
    ) -> Mapping[str, tuple[RootZoneForcing, ...]]:
        supplied = _mapping(
            value,
            expected=frozenset(TASK4_WATER_IDS),
            field_path="forcings_by_water_id",
        )
        if tuple(supplied) != TASK4_WATER_IDS:
            raise ValueError("forcings_by_water_id must use registered key order")
        rebuilt: dict[str, tuple[RootZoneForcing, ...]] = {}
        for water_id in TASK4_WATER_IDS:
            schedule = _sequence(
                supplied[water_id], f"forcings_by_water_id.{water_id}"
            )
            if len(schedule) != 168:
                raise ValueError(
                    f"forcings_by_water_id.{water_id} must have 168 entries"
                )
            rebuilt[water_id] = tuple(_reconstruct_forcing(item) for item in schedule)
        return MappingProxyType(rebuilt)

    @model_validator(mode="after")
    def freeze_mapping(self) -> "CalibrationForcingPanel":
        object.__setattr__(
            self,
            "forcings_by_water_id",
            MappingProxyType(
                {
                    water_id: tuple(self.forcings_by_water_id[water_id])
                    for water_id in TASK4_WATER_IDS
                }
            ),
        )
        return self


class CalibrationForcingPanelBundle(_StrictForcingModel):
    schema_version: Literal["1.1.0"]
    panel_kind: Literal["fit", "holdout"]
    panel_size: int
    water_ids: tuple[str, str]
    panels: tuple[CalibrationForcingPanel, ...]
    canonical_sha256: str
    evidence_label: Literal[EvidenceLabel.SYNTHETIC_ONLY]

    @field_validator("panel_size", mode="before")
    @classmethod
    def validate_panel_size(cls, value: object) -> int:
        checked = _exact_integer(value, "panel_size", maximum=128)
        if checked not in _PANEL_SIZES:
            raise ValueError("panel_size must be 32, 64, or 128")
        return checked

    @field_validator("water_ids", mode="before")
    @classmethod
    def validate_water_ids(cls, value: object) -> tuple[str, str]:
        supplied = _sequence(value, "water_ids")
        if tuple(supplied) != TASK4_WATER_IDS or any(
            type(item) is not str for item in supplied
        ):
            raise ValueError("water_ids must equal the registered two-water order")
        return TASK4_WATER_IDS

    @field_validator("panels", mode="before")
    @classmethod
    def reconstruct_panels(
        cls, value: object
    ) -> tuple[CalibrationForcingPanel, ...]:
        supplied = _sequence(value, "panels")
        rebuilt: list[CalibrationForcingPanel] = []
        for index, item in enumerate(supplied):
            if isinstance(item, CalibrationForcingPanel) and type(
                item
            ) is not CalibrationForcingPanel:
                raise ValueError(f"panels.{index} must be an exact model")
            if type(item) is CalibrationForcingPanel:
                payload: object = {
                    "panel_index": item.panel_index,
                    "forcings_by_water_id": item.forcings_by_water_id,
                }
            else:
                payload = item
            rebuilt.append(CalibrationForcingPanel.model_validate(payload))
        return tuple(rebuilt)

    @field_validator("canonical_sha256", mode="before")
    @classmethod
    def validate_sha256(cls, value: object) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("canonical_sha256 must be lowercase SHA-256")
        return value

    @field_validator("evidence_label", mode="before")
    @classmethod
    def validate_evidence_label(cls, value: object) -> EvidenceLabel:
        return _evidence_value(value, "evidence_label")

    @model_validator(mode="after")
    def validate_registered_structure(self) -> "CalibrationForcingPanelBundle":
        if len(self.panels) != self.panel_size:
            raise ValueError("panel count must equal panel_size")
        if tuple(panel.panel_index for panel in self.panels) != tuple(
            range(self.panel_size)
        ):
            raise ValueError("panel indices must be the exact ordered range")
        return self


def _require_exact_runtime_tuple(value: object, field_path: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        # Deliberately probe inside the public exception boundary so hostile
        # iterators retain their structured cause while benign alternate
        # containers are still rejected as noncanonical runtime state.
        tuple(value)  # type: ignore[arg-type]
        raise ValueError(f"{field_path} must be an exact tuple")
    return value


def _require_exact_runtime_evidence(value: object, field_path: str) -> EvidenceLabel:
    if type(value) is not EvidenceLabel:
        raise ValueError(f"{field_path} must be an exact EvidenceLabel")
    return value


def _require_exact_nominal_runtime(value: NominalForcingArtifact) -> None:
    _exact_string(value.schema_version, "schema_version")
    _exact_string(value.materialization_algorithm, "materialization_algorithm")
    water_ids = _require_exact_runtime_tuple(value.water_ids, "water_ids")
    if any(type(water_id) is not str for water_id in water_ids):
        raise ValueError("water_ids must contain exact strings")
    records = _require_exact_runtime_tuple(value.records, "records")
    _require_exact_runtime_evidence(value.evidence_label, "evidence_label")
    for index, record in enumerate(records):
        if type(record) is not NominalForcingRecord:
            raise ValueError(f"records.{index} must be an exact NominalForcingRecord")
        _exact_string(record.water_id, f"records.{index}.water_id")
        _exact_string(record.recipe_id, f"records.{index}.recipe_id")
        _exact_integer(record.step_index, f"records.{index}.step_index", maximum=167)
        _exact_float(record.start_hour, f"records.{index}.start_hour")
        _require_exact_runtime_forcing(record.forcing, f"records.{index}.forcing")


def _require_exact_calibration_runtime(
    value: CalibrationForcingPanelBundle,
) -> None:
    _exact_string(value.schema_version, "schema_version")
    _exact_string(value.panel_kind, "panel_kind")
    _exact_integer(value.panel_size, "panel_size", maximum=128)
    water_ids = _require_exact_runtime_tuple(value.water_ids, "water_ids")
    if any(type(water_id) is not str for water_id in water_ids):
        raise ValueError("water_ids must contain exact strings")
    panels = _require_exact_runtime_tuple(value.panels, "panels")
    _exact_string(value.canonical_sha256, "canonical_sha256")
    _require_exact_runtime_evidence(value.evidence_label, "evidence_label")
    for panel_ordinal, panel in enumerate(panels):
        if type(panel) is not CalibrationForcingPanel:
            raise ValueError(
                f"panels.{panel_ordinal} must be an exact CalibrationForcingPanel"
            )
        _exact_integer(
            panel.panel_index,
            f"panels.{panel_ordinal}.panel_index",
            maximum=127,
        )
        forcing_map = panel.forcings_by_water_id
        if type(forcing_map) is not _MAPPING_PROXY_TYPE:
            tuple(forcing_map)
            raise ValueError(
                f"panels.{panel_ordinal}.forcings_by_water_id "
                "must be an exact immutable mapping"
            )
        if tuple(forcing_map) != TASK4_WATER_IDS:
            raise ValueError(
                f"panels.{panel_ordinal}.forcings_by_water_id has wrong keys"
            )
        for water_id in TASK4_WATER_IDS:
            schedule = _require_exact_runtime_tuple(
                forcing_map[water_id],
                f"panels.{panel_ordinal}.forcings_by_water_id.{water_id}",
            )
            for step_index, forcing in enumerate(schedule):
                _require_exact_runtime_forcing(
                    forcing,
                    f"panels.{panel_ordinal}.forcings_by_water_id."
                    f"{water_id}.{step_index}",
                )


def _nominal_record_payload(value: NominalForcingRecord) -> dict[str, object]:
    return {
        "water_id": value.water_id,
        "recipe_id": value.recipe_id,
        "step_index": value.step_index,
        "start_hour": value.start_hour,
        "forcing": _forcing_payload(value.forcing),
    }


def _nominal_artifact_payload(value: NominalForcingArtifact) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "materialization_algorithm": value.materialization_algorithm,
        "water_ids": list(value.water_ids),
        "records": [_nominal_record_payload(record) for record in value.records],
        "evidence_label": value.evidence_label.value,
    }


def _calibration_artifact_payload(
    value: CalibrationForcingPanelBundle,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for panel in value.panels:
        for water_id in value.water_ids:
            for step_index, forcing in enumerate(
                panel.forcings_by_water_id[water_id]
            ):
                records.append(
                    {
                        "panel_index": panel.panel_index,
                        "water_id": water_id,
                        "recipe_id": TASK4_RECIPE_IDS[water_id],
                        "step_index": step_index,
                        "start_hour": float(12 * step_index),
                        "forcing": _forcing_payload(forcing),
                    }
                )
    return {
        "schema_version": value.schema_version,
        "panel_kind": value.panel_kind,
        "materialization_algorithm": _CALIBRATION_ALGORITHM,
        "root_seed": TASK4_ROOT_SEED,
        "spawn_key": [11, 0 if value.panel_kind == "fit" else 1],
        "bit_generator": "PCG64",
        "numpy_version": "2.5.2",
        "panel_size": value.panel_size,
        "water_ids": list(value.water_ids),
        "forcing_schema_version": _FORCING_SCHEMA_VERSION,
        "records": records,
        "evidence_label": value.evidence_label.value,
    }


def _invalid(
    code: str,
    message: str,
    field_path: str,
    *,
    cause: Exception | None = None,
) -> Never:
    details: dict[str, object] | None = None
    if cause is not None:
        details = {"cause_type": type(cause).__name__}
        if isinstance(cause, AlmondLabError):
            details.update(
                {"cause_code": cause.code, "cause_field_path": cause.field_path}
            )
    fail(code, message, field_path, details)


def revalidate_nominal_forcing_artifact(
    value: object,
) -> NominalForcingArtifact:
    """Detach and authenticate the sole registered nominal forcing artifact."""

    code = "NOMINAL_FORCING_INVALID"
    try:
        # Every read or iteration of caller-influenced state stays inside this
        # normalization boundary so an adversarial model_copy container cannot
        # leak its own exception type across the public API.
        if type(value) is not NominalForcingArtifact:
            raise ValueError("nominal forcing artifact must be an exact model")
        _require_exact_nominal_runtime(value)
        caller_digest = hashlib.sha256(
            canonical_json_bytes(_nominal_artifact_payload(value))
        ).hexdigest()
        if not hmac.compare_digest(caller_digest, TASK4_NOMINAL_FORCING_SHA256):
            raise ValueError(
                "caller nominal forcing state does not match registered authority"
            )
        rebuilt = NominalForcingArtifact.model_validate(
            {
                "schema_version": value.schema_version,
                "materialization_algorithm": value.materialization_algorithm,
                "water_ids": list(value.water_ids),
                "records": [
                    {
                        name: getattr(record, name)
                        for name in NominalForcingRecord.model_fields
                    }
                    for record in value.records
                ],
                "evidence_label": value.evidence_label,
            }
        )
        digest = hashlib.sha256(
            canonical_json_bytes(_nominal_artifact_payload(rebuilt))
        ).hexdigest()
        if not hmac.compare_digest(digest, TASK4_NOMINAL_FORCING_SHA256):
            raise ValueError(
                "nominal forcing artifact does not match registered authority"
            )
    except Exception as error:
        _invalid(code, "nominal forcing artifact is invalid", "artifact", cause=error)
    return rebuilt


def revalidate_calibration_forcing_panel_bundle(
    value: object,
    *,
    sensitivity_id: str | None = None,
    sensitivity_value: object = None,
) -> CalibrationForcingPanelBundle:
    """Detach and authenticate one primary or registered S031 panel bundle.

    Fit/holdout equality and pair selection are calibration-caller gates: this
    function authenticates one side and intentionally cannot infer its mate.
    """

    code = "CALIBRATION_FORCING_INVALID"
    try:
        # Normalize the complete caller-controlled object graph before using
        # any of its scientific metadata for authority selection.
        if type(value) is not CalibrationForcingPanelBundle:
            raise ValueError("calibration forcing bundle must be an exact model")
        _require_exact_calibration_runtime(value)
        if value.panel_size == 64:
            if sensitivity_id is not None or sensitivity_value is not None:
                raise ValueError("primary K=64 cannot claim sensitivity identity")
        else:
            if (
                type(sensitivity_id) is not str
                or sensitivity_id != _SENSITIVITY_ID
                or type(sensitivity_value) is not int
                or sensitivity_value != value.panel_size
            ):
                raise ValueError(
                    "K=32/128 requires exact S031_panel_size identity and value"
                )
        expected_digest = TASK4_CALIBRATION_FORCING_SHA256.get(
            (value.panel_kind, value.panel_size)
        )
        if expected_digest is None or not hmac.compare_digest(
            value.canonical_sha256, expected_digest
        ):
            raise ValueError("canonical_sha256 is not the registered digest")
        caller_digest = hashlib.sha256(
            canonical_json_bytes(_calibration_artifact_payload(value))
        ).hexdigest()
        if not hmac.compare_digest(caller_digest, expected_digest):
            raise ValueError(
                "caller runtime panels do not reproduce registered artifact hash"
            )
        rebuilt = CalibrationForcingPanelBundle.model_validate(
            {
                "schema_version": value.schema_version,
                "panel_kind": value.panel_kind,
                "panel_size": value.panel_size,
                "water_ids": list(value.water_ids),
                "panels": [
                    {
                        "panel_index": panel.panel_index,
                        "forcings_by_water_id": {
                            water_id: list(panel.forcings_by_water_id[water_id])
                            for water_id in panel.forcings_by_water_id
                        },
                    }
                    for panel in value.panels
                ],
                "canonical_sha256": value.canonical_sha256,
                "evidence_label": value.evidence_label,
            }
        )
        observed_digest = hashlib.sha256(
            canonical_json_bytes(_calibration_artifact_payload(rebuilt))
        ).hexdigest()
        if not hmac.compare_digest(observed_digest, expected_digest):
            raise ValueError("runtime panels do not reproduce registered artifact hash")
    except Exception as error:
        _invalid(code, "calibration forcing bundle is invalid", "bundle", cause=error)
    return rebuilt


__all__ = [
    "CalibrationForcingPanel",
    "CalibrationForcingPanelBundle",
    "CalibrationForcingRecord",
    "NominalForcingArtifact",
    "NominalForcingRecord",
    "revalidate_calibration_forcing_panel_bundle",
    "revalidate_nominal_forcing_artifact",
]
