"""Public-contract preflight for Task 4 registered forcing artifacts.

These tests intentionally depend only on the public ``paper1_contracts`` API
and the separately tracked registration materializer.  The materializer emits
exogenous forcing only; it is never an oracle for a plant outcome or solver.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from copy import copy
from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import importlib.util
from pathlib import Path
import tomllib
from types import ModuleType

import numpy
import pytest
import scipy
from numpy.random import SeedSequence
from pydantic import BaseModel, ValidationError

from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import (
    CalibrationForcingPanel,
    CalibrationForcingPanelBundle,
    CalibrationForcingRecord,
    NominalForcingArtifact,
    NominalForcingRecord,
    revalidate_calibration_forcing_panel_bundle,
    revalidate_nominal_forcing_artifact,
)
from almondlab.provenance import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = (
    ROOT / "scripts" / "registration" / "task4_registration_hash_materializer.py"
)
MATERIALIZER_SHA256 = (
    "0397fb262931c08f197ea841c24e055bbb751cbdec06dbc7473a87c9981497d5"
)
ROOT_SEED = 420260813
WATER_IDS = (
    "nonsaline_nutrient_matched_control",
    "pilot_selected_full_ion_marine_challenge",
)
RECIPE_IDS = {
    WATER_IDS[0]: "paper1_base_nutrient_control_v1@1.0.0",
    WATER_IDS[1]: "paper1_base_plus_nacl40_challenge_v1@1.0.0",
}
HYDRAULIC_DOMAIN = {
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
EXPECTED_HASHES = {
    "nominal": "329cb311b6a5915e1090a2e6b059857af9531bec3cbc26779d112eb9a5cbbc96",
    "operator_times": "33ab36479f1500aef066b0f495010ff73ea86c8a4a8c4c2bac78603deb8da224",
    "sample_times": "5fc3952a1b60b5282a97543577b0ff6aaac6463b654cc5ba9fd59748d1ffae14",
    "fit_32": "8b042b703b1c5148886182b344317986776fef8d68e795688741f74d54d790e3",
    "holdout_32": "80224dfe438556e8caa0ae561d79649acf465d8c09218bd429edb7d1bbc5f41a",
    "fit_64": "4e32c2831ea039c5a1939aed19091160f9c8c112d99a9e2bc937f05539b51eaf",
    "holdout_64": "d1f5b6b185458f50f6453391065e6af970ce5069921507431ce46fede0f9ca5a",
    "fit_128": "91b9c4d937b0417097f6e4b7272eff4efcf4a6dfdc23e76c73876a7e5ae02cc9",
    "holdout_128": "3df1fde7553bd5942a195e67eb7438f501e6ce6df3bd22f08397b623f5b97f11",
}
EXPECTED_RANGES = {
    "fit_32": (
        (291.3926391411616, 298.7281070996637),
        (0.0, 1.25972567775521),
        (-0.1164879822580775, -0.004705176034776416),
        (0.10869459560526429, 1.0345452226753669),
    ),
    "holdout_32": (
        (291.5408547116821, 298.88344664294243),
        (0.0, 1.299704845541121),
        (-0.11182186298881373, -0.0004547261506736011),
        (0.11407399066395506, 1.0588583972041723),
    ),
    "fit_64": (
        (290.89421868483754, 298.7281070996637),
        (0.0, 1.25972567775521),
        (-0.1164879822580775, -0.004594178437707541),
        (0.10869459560526429, 1.086546918085342),
    ),
    "holdout_64": (
        (291.387644840006, 298.88344664294243),
        (0.0, 1.299704845541121),
        (-0.12064296468066651, -0.0004547261506736011),
        (0.10420996700536547, 1.0588583972041723),
    ),
    "fit_128": (
        (290.89421868483754, 298.900281776376),
        (0.0, 1.25972567775521),
        (-0.12056731475474103, -0.0034183698000421273),
        (0.10869459560526429, 1.086546918085342),
    ),
    "holdout_128": (
        (291.1388193975223, 299.31926514526134),
        (0.0, 1.299704845541121),
        (-0.12064296468066651, -0.0004547261506736011),
        (0.10420996700536547, 1.0960330562326226),
    ),
}
NOMINAL_ARTIFACT_FIELDS = {
    "schema_version",
    "materialization_algorithm",
    "water_ids",
    "records",
    "evidence_label",
}
NOMINAL_RECORD_FIELDS = {
    "water_id",
    "recipe_id",
    "step_index",
    "start_hour",
    "forcing",
}
CALIBRATION_ARTIFACT_FIELDS = {
    "schema_version",
    "panel_kind",
    "materialization_algorithm",
    "root_seed",
    "spawn_key",
    "bit_generator",
    "numpy_version",
    "panel_size",
    "water_ids",
    "forcing_schema_version",
    "records",
    "evidence_label",
}
CALIBRATION_RECORD_FIELDS = {
    "panel_index",
    "water_id",
    "recipe_id",
    "step_index",
    "start_hour",
    "forcing",
}
RUNTIME_PANEL_FIELDS = {"panel_index", "forcings_by_water_id"}
RUNTIME_BUNDLE_FIELDS = {
    "schema_version",
    "panel_kind",
    "panel_size",
    "water_ids",
    "panels",
    "canonical_sha256",
    "evidence_label",
}
FORCING_FIELDS = {
    "measured_osmolality_osmol_kg",
    "temperature_k",
    "water_density_kg_l",
    "matric_potential_mpa",
    "leaf_critical_potential_mpa",
    "apar_mol_h",
    "temperature_factor",
    "potential_transpiration_l_day",
    "duration_hours",
    "evidence_label",
    "hydraulic_domain",
}


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _import_materializer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "task4_forcing_panel_materializer_under_test", MATERIALIZER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plain(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return {
            name: _plain(getattr(value, name))
            for name in type(value).model_fields
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _registered_panel_payload(bundle: CalibrationForcingPanelBundle) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for panel in bundle.panels:
        for water_id in bundle.water_ids:
            for step_index, forcing in enumerate(panel.forcings_by_water_id[water_id]):
                records.append(
                    {
                        "panel_index": panel.panel_index,
                        "water_id": water_id,
                        "recipe_id": RECIPE_IDS[water_id],
                        "step_index": step_index,
                        "start_hour": float(12 * step_index),
                        "forcing": _plain(forcing),
                    }
                )
    return {
        "schema_version": bundle.schema_version,
        "panel_kind": bundle.panel_kind,
        "materialization_algorithm": "paper1_calibration_forcing_panel_v2",
        "root_seed": ROOT_SEED,
        "spawn_key": [11, 0 if bundle.panel_kind == "fit" else 1],
        "bit_generator": "PCG64",
        "numpy_version": "2.5.2",
        "panel_size": bundle.panel_size,
        "water_ids": list(bundle.water_ids),
        "forcing_schema_version": "paper1_root_zone_forcing@1.0.0",
        "records": records,
        "evidence_label": _plain(bundle.evidence_label),
    }


def _assert_invalid(call: Callable[[], object], code: str) -> AlmondLabError:
    with pytest.raises(AlmondLabError) as captured:
        call()
    error = captured.value
    assert error.code == code
    assert error.field_path
    assert error.to_dict()["code"] == code
    assert str(error).startswith(f"{code}:")
    return error


class MaterializedAuthority:
    def __init__(self, module: ModuleType) -> None:
        self.nominal = module.nominal_schedule_payload()
        self.operator = module.operator_times_payload()
        self.sample = module.sample_times_payload()
        family = SeedSequence(ROOT_SEED).spawn(12)[11]
        fit_seed, holdout_seed = family.spawn(2)
        self.payloads: dict[str, dict[str, object]] = {}
        self.ranges: dict[str, tuple[tuple[float, float], ...]] = {}
        for kind, seed in (("fit", fit_seed), ("holdout", holdout_seed)):
            innovations = module.calibration_innovations(seed)
            complete, complete_ranges = module.calibration_panel_payload(
                panel_kind=kind,
                seed_sequence=seed,
                panel_size=128,
                innovations=innovations,
            )
            self.payloads[f"{kind}_128"] = complete
            self.ranges[f"{kind}_128"] = complete_ranges
            for panel_size in (32, 64):
                prefix = dict(complete)
                prefix["panel_size"] = panel_size
                prefix["records"] = prefix["records"][: panel_size * 2 * 168]
                self.payloads[f"{kind}_{panel_size}"] = prefix
                self.ranges[f"{kind}_{panel_size}"] = _forcing_ranges(prefix)


def _forcing_ranges(payload: Mapping[str, object]) -> tuple[tuple[float, float], ...]:
    records = payload["records"]
    assert type(records) is list
    names = (
        "temperature_k",
        "apar_mol_h",
        "matric_potential_mpa",
        "potential_transpiration_l_day",
    )
    ranges: list[tuple[float, float]] = []
    for name in names:
        values = [record["forcing"][name] for record in records]
        ranges.append((min(values), max(values)))
    return tuple(ranges)


@pytest.fixture(scope="module")
def materializer() -> ModuleType:
    return _import_materializer()


@pytest.fixture(scope="module")
def authority(materializer: ModuleType) -> MaterializedAuthority:
    return MaterializedAuthority(materializer)


@pytest.fixture(scope="module")
def nominal_artifact(authority: MaterializedAuthority) -> NominalForcingArtifact:
    return NominalForcingArtifact.model_validate(authority.nominal)


def _bundle_from_payload(payload: Mapping[str, object]) -> CalibrationForcingPanelBundle:
    records = payload["records"]
    assert type(records) is list
    panel_size = payload["panel_size"]
    assert type(panel_size) is int
    panels: list[dict[str, object]] = []
    for panel_index in range(panel_size):
        offset = panel_index * 2 * 168
        panels.append(
            {
                "panel_index": panel_index,
                "forcings_by_water_id": {
                    WATER_IDS[0]: [
                        records[offset + step]["forcing"] for step in range(168)
                    ],
                    WATER_IDS[1]: [
                        records[offset + 168 + step]["forcing"] for step in range(168)
                    ],
                },
            }
        )
    kind = payload["panel_kind"]
    assert type(kind) is str
    return CalibrationForcingPanelBundle.model_validate(
        {
            "schema_version": payload["schema_version"],
            "panel_kind": kind,
            "panel_size": panel_size,
            "water_ids": payload["water_ids"],
            "panels": panels,
            "canonical_sha256": EXPECTED_HASHES[f"{kind}_{panel_size}"],
            "evidence_label": payload["evidence_label"],
        }
    )


@pytest.fixture(scope="module")
def registered_bundles(
    authority: MaterializedAuthority,
) -> dict[str, CalibrationForcingPanelBundle]:
    """Build each 128 authority once and share its immutable prefix objects."""

    bundles: dict[str, CalibrationForcingPanelBundle] = {}
    for kind in ("fit", "holdout"):
        complete = _bundle_from_payload(authority.payloads[f"{kind}_128"])
        bundles[f"{kind}_128"] = complete
        for panel_size in (32, 64):
            bundles[f"{kind}_{panel_size}"] = complete.model_copy(
                update={
                    "panel_size": panel_size,
                    "panels": complete.panels[:panel_size],
                    "canonical_sha256": EXPECTED_HASHES[f"{kind}_{panel_size}"],
                }
            )
    return bundles


@pytest.fixture(scope="module")
def primary_fit(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
) -> CalibrationForcingPanelBundle:
    return registered_bundles["fit_64"]


@pytest.fixture(scope="module")
def primary_holdout(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
) -> CalibrationForcingPanelBundle:
    return registered_bundles["holdout_64"]


def _replace_panel(
    bundle: CalibrationForcingPanelBundle,
    index: int,
    panel: CalibrationForcingPanel,
) -> CalibrationForcingPanelBundle:
    panels = list(bundle.panels)
    panels[index] = panel
    return bundle.model_copy(update={"panels": tuple(panels)})


def _mutate_forcing(
    bundle: CalibrationForcingPanelBundle,
    *,
    panel_index: int = 0,
    water_id: str = WATER_IDS[0],
    step_index: int = 0,
    field: str,
    value: object,
) -> CalibrationForcingPanelBundle:
    panel = bundle.panels[panel_index]
    copied_forcing = copy(panel.forcings_by_water_id[water_id][step_index])
    object.__setattr__(copied_forcing, field, value)
    forcings = {
        key: tuple(sequence)
        for key, sequence in panel.forcings_by_water_id.items()
    }
    selected = list(forcings[water_id])
    selected[step_index] = copied_forcing
    forcings[water_id] = tuple(selected)
    changed_panel = panel.model_copy(update={"forcings_by_water_id": forcings})
    return _replace_panel(bundle, panel_index, changed_panel)


def _mutate_nominal_forcing(
    artifact: NominalForcingArtifact,
    *,
    field: str,
    value: object,
) -> NominalForcingArtifact:
    record = artifact.records[0]
    copied_forcing = copy(record.forcing)
    object.__setattr__(copied_forcing, field, value)
    changed_record = record.model_copy(update={"forcing": copied_forcing})
    return artifact.model_copy(
        update={"records": (changed_record, *artifact.records[1:])}
    )


class _AlwaysEqual:
    def __hash__(self) -> int:
        # Pydantic's literal lookup uses the input hash before equality.
        return hash("1.1.0")

    def __eq__(self, other: object) -> bool:
        return True


class _RegisteredStringSubclass(str):
    pass


def test_public_models_expose_only_the_registered_fields() -> None:
    assert set(NominalForcingRecord.model_fields) == NOMINAL_RECORD_FIELDS
    assert set(NominalForcingArtifact.model_fields) == NOMINAL_ARTIFACT_FIELDS
    assert set(CalibrationForcingRecord.model_fields) == CALIBRATION_RECORD_FIELDS
    assert set(CalibrationForcingPanel.model_fields) == RUNTIME_PANEL_FIELDS
    assert set(CalibrationForcingPanelBundle.model_fields) == RUNTIME_BUNDLE_FIELDS
    for model in (
        NominalForcingRecord,
        NominalForcingArtifact,
        CalibrationForcingRecord,
        CalibrationForcingPanel,
        CalibrationForcingPanelBundle,
    ):
        assert model.model_config["extra"] == "forbid"
        assert model.model_config["frozen"] is True
        assert model.model_config["allow_inf_nan"] is False
        assert model.model_config["revalidate_instances"] == "always"


def test_scientific_runtime_versions_are_the_exact_locked_authority() -> None:
    assert numpy.__version__ == "2.5.2"
    assert scipy.__version__ == "1.18.0"
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = {
        package["name"]: package["version"]
        for package in lock["package"]
        if package["name"] in {"numpy", "scipy"}
    }
    assert locked == {"numpy": "2.5.2", "scipy": "1.18.0"}


def test_materializer_is_exact_and_has_no_solver_or_outcome_import() -> None:
    raw = MATERIALIZER.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MATERIALIZER_SHA256
    assert b"\r\n" not in raw
    tree = ast.parse(raw.decode("utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported == {
        "__future__",
        "hashlib",
        "math",
        "numpy",
        "numpy.random",
        "almondlab.provenance",
    }
    forbidden_import_roots = {
        "almondlab.biology_surrogate",
        "almondlab.simulate",
        "scipy",
        "scipy.integrate",
        "scipy.optimize",
    }
    assert imported.isdisjoint(forbidden_import_roots)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint(
        {"brentq", "solve", "solve_ivp", "simulate", "calibrate_mechanism_to_estimand"}
    )


def test_each_child_makes_one_exact_128_standard_normal_draw(
    materializer: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    sentinel = object()

    class RecordingGenerator:
        def __init__(self, bit_generator: object) -> None:
            self.seed = bit_generator

        def standard_normal(self, shape: tuple[int, ...]) -> object:
            assert isinstance(self.seed, SeedSequence)
            calls.append((self.seed.spawn_key, shape))
            return sentinel

    monkeypatch.setattr(materializer, "PCG64", lambda seed: seed)
    monkeypatch.setattr(materializer, "Generator", RecordingGenerator)
    family = SeedSequence(ROOT_SEED).spawn(12)[11]
    fit_seed, holdout_seed = family.spawn(2)
    assert materializer.calibration_innovations(fit_seed) is sentinel
    assert materializer.calibration_innovations(holdout_seed) is sentinel
    assert calls == [((11, 0), (128, 4, 232)), ((11, 1), (128, 4, 232))]


def test_all_nine_registered_artifact_hashes_reproduce(
    authority: MaterializedAuthority,
) -> None:
    observed = {
        "nominal": _sha256_json(authority.nominal),
        "operator_times": _sha256_json(authority.operator),
        "sample_times": _sha256_json(authority.sample),
        **{key: _sha256_json(payload) for key, payload in authority.payloads.items()},
    }
    assert len(observed) == 9
    assert observed == EXPECTED_HASHES


def test_nominal_artifact_schema_types_count_and_order_are_exact(
    authority: MaterializedAuthority,
) -> None:
    payload = authority.nominal
    assert set(payload) == NOMINAL_ARTIFACT_FIELDS
    assert payload["schema_version"] == "1.1.0"
    assert payload["materialization_algorithm"] == "paper1_nominal_forcing_schedule_v2"
    assert payload["water_ids"] == list(WATER_IDS)
    assert payload["evidence_label"] == "synthetic_only"
    records = payload["records"]
    assert type(records) is list and len(records) == 336
    for ordinal, record in enumerate(records):
        water_id = WATER_IDS[ordinal // 168]
        step_index = ordinal % 168
        assert type(record) is dict and set(record) == NOMINAL_RECORD_FIELDS
        assert record["water_id"] == water_id
        assert record["recipe_id"] == RECIPE_IDS[water_id]
        assert type(record["step_index"]) is int
        assert record["step_index"] == step_index
        assert type(record["start_hour"]) is float
        assert record["start_hour"] == float(12 * step_index)
        forcing = record["forcing"]
        assert type(forcing) is dict and set(forcing) == FORCING_FIELDS
        assert all(
            type(forcing[name]) is float
            for name in FORCING_FIELDS
            if name not in {"evidence_label", "hydraulic_domain"}
        )
        assert forcing["evidence_label"] == "synthetic_only"
        assert forcing["hydraulic_domain"] == HYDRAULIC_DOMAIN


def test_nominal_public_revalidation_detaches_and_preserves_registered_hash(
    nominal_artifact: NominalForcingArtifact,
) -> None:
    checked = revalidate_nominal_forcing_artifact(nominal_artifact)
    assert type(checked) is NominalForcingArtifact
    assert checked is not nominal_artifact
    assert type(checked.water_ids) is tuple and checked.water_ids == WATER_IDS
    assert type(checked.records) is tuple and len(checked.records) == 336
    assert all(type(record) is NominalForcingRecord for record in checked.records)
    assert checked.records is not nominal_artifact.records
    assert checked.records[0] is not nominal_artifact.records[0]
    assert checked.records[0].forcing is not nominal_artifact.records[0].forcing
    assert type(checked.records[0].step_index) is int
    assert type(checked.records[0].start_hour) is float
    assert _sha256_json(_plain(checked)) == EXPECTED_HASHES["nominal"]


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("start_hour", float("nan")),
        ("start_hour", 1.0e300),
        ("start_hour", 0),
        ("step_index", True),
        ("recipe_id", "caller_recipe@9.9.9"),
    ],
)
def test_nominal_revalidation_rejects_numeric_type_and_hash_mutations(
    nominal_artifact: NominalForcingArtifact,
    mutation: str,
    value: object,
) -> None:
    record = nominal_artifact.records[0].model_copy(update={mutation: value})
    records = (record, *nominal_artifact.records[1:])
    changed = nominal_artifact.model_copy(update={"records": records})
    _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(changed),
        "NOMINAL_FORCING_INVALID",
    )


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "reorder"])
def test_nominal_revalidation_rejects_record_sequence_mutations(
    nominal_artifact: NominalForcingArtifact,
    mutation: str,
) -> None:
    records = list(nominal_artifact.records)
    if mutation == "drop":
        records.pop()
    elif mutation == "duplicate":
        records[-1] = records[-2]
    else:
        records[0], records[1] = records[1], records[0]
    changed = nominal_artifact.model_copy(update={"records": tuple(records)})
    _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(changed),
        "NOMINAL_FORCING_INVALID",
    )


def test_nominal_revalidation_rejects_hostile_model_subclass(
    nominal_artifact: NominalForcingArtifact,
) -> None:
    class HostileNominalArtifact(NominalForcingArtifact):
        pass

    hostile = HostileNominalArtifact.model_construct(**nominal_artifact.__dict__)
    _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(hostile),
        "NOMINAL_FORCING_INVALID",
    )


def test_nominal_revalidation_rejects_hostile_nested_record_subclass(
    nominal_artifact: NominalForcingArtifact,
) -> None:
    class HostileNominalRecord(NominalForcingRecord):
        hidden_instruction: str = "trust caller"

    hostile_record = HostileNominalRecord.model_construct(
        **nominal_artifact.records[0].__dict__,
        hidden_instruction="trust caller",
    )
    hostile = nominal_artifact.model_copy(
        update={"records": (hostile_record, *nominal_artifact.records[1:])}
    )
    _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(hostile),
        "NOMINAL_FORCING_INVALID",
    )


def test_nominal_revalidation_wraps_hostile_record_sequence_failure(
    nominal_artifact: NominalForcingArtifact,
) -> None:
    class BadSeq:
        def __iter__(self):
            raise RuntimeError("hostile nominal record iteration")

    hostile = nominal_artifact.model_copy(update={"records": BadSeq()})
    error = _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(hostile),
        "NOMINAL_FORCING_INVALID",
    )
    assert error.field_path == "artifact"
    assert error.details == {"cause_type": "RuntimeError"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", _AlwaysEqual()),
        ("schema_version", _RegisteredStringSubclass("1.1.0")),
        ("evidence_label", "synthetic_only"),
    ],
)
def test_nominal_revalidation_rejects_noncanonical_outer_runtime_types(
    nominal_artifact: NominalForcingArtifact,
    field: str,
    value: object,
) -> None:
    hostile = nominal_artifact.model_copy(update={field: value})
    _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(hostile),
        "NOMINAL_FORCING_INVALID",
    )


@pytest.mark.parametrize(
    "mutation",
    ["forcing_evidence_string", "domain_evidence_string", "domain_negative_zero"],
)
def test_nominal_revalidation_authenticates_exact_nested_runtime_state(
    nominal_artifact: NominalForcingArtifact,
    mutation: str,
) -> None:
    forcing = nominal_artifact.records[0].forcing
    if mutation == "forcing_evidence_string":
        hostile = _mutate_nominal_forcing(
            nominal_artifact,
            field="evidence_label",
            value="synthetic_only",
        )
    else:
        domain_update = (
            {"permitted_evidence_label": "physics_constrained"}
            if mutation == "domain_evidence_string"
            else {"osmolality_min": -0.0}
        )
        hostile = _mutate_nominal_forcing(
            nominal_artifact,
            field="hydraulic_domain",
            value=forcing.hydraulic_domain.model_copy(update=domain_update),
        )
    _assert_invalid(
        lambda: revalidate_nominal_forcing_artifact(hostile),
        "NOMINAL_FORCING_INVALID",
    )


def test_calibration_artifacts_have_exact_schema_types_counts_order_and_ranges(
    authority: MaterializedAuthority,
) -> None:
    expected_counts = {32: 10_752, 64: 21_504, 128: 43_008}
    for key, payload in authority.payloads.items():
        kind, size_text = key.rsplit("_", 1)
        panel_size = int(size_text)
        assert set(payload) == CALIBRATION_ARTIFACT_FIELDS
        assert "canonical_sha256" not in payload
        assert payload["schema_version"] == "1.1.0"
        assert payload["panel_kind"] == kind
        assert payload["materialization_algorithm"] == "paper1_calibration_forcing_panel_v2"
        assert type(payload["root_seed"]) is int and payload["root_seed"] == ROOT_SEED
        assert payload["spawn_key"] == [11, 0 if kind == "fit" else 1]
        assert payload["bit_generator"] == "PCG64"
        assert payload["numpy_version"] == "2.5.2"
        assert type(payload["panel_size"]) is int and payload["panel_size"] == panel_size
        assert payload["water_ids"] == list(WATER_IDS)
        assert payload["forcing_schema_version"] == "paper1_root_zone_forcing@1.0.0"
        assert payload["evidence_label"] == "synthetic_only"
        records = payload["records"]
        assert type(records) is list and len(records) == expected_counts[panel_size]
        for ordinal, record in enumerate(records):
            within_panel = ordinal % 336
            expected_panel = ordinal // 336
            expected_water = WATER_IDS[within_panel // 168]
            expected_step = within_panel % 168
            assert type(record) is dict and set(record) == CALIBRATION_RECORD_FIELDS
            assert type(record["panel_index"]) is int
            assert record["panel_index"] == expected_panel
            assert record["water_id"] == expected_water
            assert record["recipe_id"] == RECIPE_IDS[expected_water]
            assert type(record["step_index"]) is int
            assert record["step_index"] == expected_step
            assert type(record["start_hour"]) is float
            assert record["start_hour"] == float(12 * expected_step)
            forcing = record["forcing"]
            assert type(forcing) is dict and set(forcing) == FORCING_FIELDS
            assert all(
                type(forcing[name]) is float
                for name in FORCING_FIELDS
                if name not in {"evidence_label", "hydraulic_domain"}
            )
            assert forcing["evidence_label"] == "synthetic_only"
            assert forcing["hydraulic_domain"] == HYDRAULIC_DOMAIN
        assert authority.ranges[key] == EXPECTED_RANGES[key]
    for kind in ("fit", "holdout"):
        records_32 = authority.payloads[f"{kind}_32"]["records"]
        records_64 = authority.payloads[f"{kind}_64"]["records"]
        records_128 = authority.payloads[f"{kind}_128"]["records"]
        assert records_32 == records_64[:10_752]
        assert records_64 == records_128[:21_504]


def test_calibration_record_public_schema_preserves_exact_primitives(
    authority: MaterializedAuthority,
) -> None:
    first = authority.payloads["fit_128"]["records"][0]
    checked = CalibrationForcingRecord.model_validate(first)
    assert type(checked) is CalibrationForcingRecord
    assert type(checked.panel_index) is int
    assert type(checked.step_index) is int
    assert type(checked.start_hour) is float
    assert _plain(checked) == first
    for field, value in (
        ("panel_index", True),
        ("panel_index", 0.0),
        ("step_index", False),
        ("start_hour", 0),
    ):
        payload = dict(first)
        payload[field] = value
        with pytest.raises(ValidationError):
            CalibrationForcingRecord.model_validate(payload)


def test_runtime_bundle_partition_reconstructs_artifact_without_self_hash(
    primary_fit: CalibrationForcingPanelBundle,
    primary_holdout: CalibrationForcingPanelBundle,
) -> None:
    for bundle in (primary_fit, primary_holdout):
        assert set(type(bundle).model_fields) == RUNTIME_BUNDLE_FIELDS
        assert type(bundle.panels) is tuple and len(bundle.panels) == 64
        assert all(type(panel) is CalibrationForcingPanel for panel in bundle.panels)
        assert [panel.panel_index for panel in bundle.panels] == list(range(64))
        for panel in bundle.panels:
            assert tuple(panel.forcings_by_water_id) == WATER_IDS
            assert all(
                type(panel.forcings_by_water_id[water_id]) is tuple
                and len(panel.forcings_by_water_id[water_id]) == 168
                for water_id in WATER_IDS
            )
        artifact = _registered_panel_payload(bundle)
        assert set(artifact) == CALIBRATION_ARTIFACT_FIELDS
        assert "canonical_sha256" not in artifact
        assert _sha256_json(artifact) == bundle.canonical_sha256


def test_primary_revalidation_accepts_only_exact_64_bundle_and_detaches(
    primary_fit: CalibrationForcingPanelBundle,
    primary_holdout: CalibrationForcingPanelBundle,
) -> None:
    fit = revalidate_calibration_forcing_panel_bundle(primary_fit)
    holdout = revalidate_calibration_forcing_panel_bundle(primary_holdout)
    assert type(fit) is CalibrationForcingPanelBundle and fit is not primary_fit
    assert type(holdout) is CalibrationForcingPanelBundle and holdout is not primary_holdout
    assert fit.panels is not primary_fit.panels
    assert fit.panels[0] is not primary_fit.panels[0]
    assert (
        fit.panels[0].forcings_by_water_id[WATER_IDS[0]][0]
        is not primary_fit.panels[0].forcings_by_water_id[WATER_IDS[0]][0]
    )
    assert fit.panel_size == holdout.panel_size == 64
    assert fit.panel_kind == "fit" and holdout.panel_kind == "holdout"
    assert fit.canonical_sha256 == EXPECTED_HASHES["fit_64"]
    assert holdout.canonical_sha256 == EXPECTED_HASHES["holdout_64"]
    assert fit.canonical_sha256 != holdout.canonical_sha256


@pytest.mark.parametrize("panel_size", [32, 128])
@pytest.mark.parametrize("kind", ["fit", "holdout"])
def test_s031_is_the_only_nonprimary_panel_size_authority(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
    panel_size: int,
    kind: str,
) -> None:
    bundle = registered_bundles[f"{kind}_{panel_size}"]
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(bundle),
        "CALIBRATION_FORCING_INVALID",
    )
    checked = revalidate_calibration_forcing_panel_bundle(
        bundle,
        sensitivity_id="S031_panel_size",
        sensitivity_value=panel_size,
    )
    assert checked.panel_size == panel_size
    assert checked.canonical_sha256 == EXPECTED_HASHES[f"{kind}_{panel_size}"]


@pytest.mark.parametrize(
    ("panel_key", "sensitivity_id", "sensitivity_value"),
    [
        ("fit_64", "S031_panel_size", 64),
        ("fit_32", "S030_parameter_rtol", 32),
        ("fit_32", "S031_panel_size", 128),
        ("holdout_128", "S031_panel_size", 32),
        ("holdout_32", "S031_panel_size", True),
    ],
)
def test_primary_and_s031_identity_cannot_be_forged_or_mismatched(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
    panel_key: str,
    sensitivity_id: str,
    sensitivity_value: object,
) -> None:
    bundle = registered_bundles[panel_key]
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(
            bundle,
            sensitivity_id=sensitivity_id,
            sensitivity_value=sensitivity_value,
        ),
        "CALIBRATION_FORCING_INVALID",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("panel_kind", _RegisteredStringSubclass("fit")),
        ("evidence_label", "synthetic_only"),
    ],
)
def test_calibration_revalidation_rejects_noncanonical_outer_runtime_types(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
    field: str,
    value: object,
) -> None:
    hostile = registered_bundles["fit_32"].model_copy(update={field: value})
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(
            hostile,
            sensitivity_id="S031_panel_size",
            sensitivity_value=32,
        ),
        "CALIBRATION_FORCING_INVALID",
    )


@pytest.mark.parametrize(
    "mutation",
    ["forcing_evidence_string", "domain_evidence_string", "domain_negative_zero"],
)
def test_calibration_revalidation_authenticates_exact_nested_runtime_state(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
    mutation: str,
) -> None:
    bundle = registered_bundles["fit_32"]
    forcing = bundle.panels[0].forcings_by_water_id[WATER_IDS[0]][0]
    if mutation == "forcing_evidence_string":
        hostile = _mutate_forcing(
            bundle,
            field="evidence_label",
            value="synthetic_only",
        )
    else:
        domain_update = (
            {"permitted_evidence_label": "physics_constrained"}
            if mutation == "domain_evidence_string"
            else {"osmolality_min": -0.0}
        )
        hostile = _mutate_forcing(
            bundle,
            field="hydraulic_domain",
            value=forcing.hydraulic_domain.model_copy(update=domain_update),
        )
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(
            hostile,
            sensitivity_id="S031_panel_size",
            sensitivity_value=32,
        ),
        "CALIBRATION_FORCING_INVALID",
    )


def test_s031_revalidation_rejects_without_calling_hostile_comparison(
    registered_bundles: Mapping[str, CalibrationForcingPanelBundle],
) -> None:
    comparison_calls = 0

    class HostileSensitivityId:
        def __ne__(self, other: object) -> bool:
            nonlocal comparison_calls
            comparison_calls += 1
            raise RuntimeError("hostile sensitivity comparison")

    error = _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(
            registered_bundles["fit_32"],
            sensitivity_id=HostileSensitivityId(),  # type: ignore[arg-type]
            sensitivity_value=32,
        ),
        "CALIBRATION_FORCING_INVALID",
    )
    assert comparison_calls == 0
    assert error.field_path == "bundle"


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "reorder", "declared_size"])
def test_calibration_revalidation_rejects_panel_sequence_and_copy_mutations(
    primary_fit: CalibrationForcingPanelBundle,
    mutation: str,
) -> None:
    if mutation == "declared_size":
        changed = primary_fit.model_copy(update={"panel_size": 32})
    else:
        panels = list(primary_fit.panels)
        if mutation == "drop":
            panels.pop()
        elif mutation == "duplicate":
            panels[-1] = panels[-2]
        else:
            panels[0], panels[1] = panels[1], panels[0]
        changed = primary_fit.model_copy(update={"panels": tuple(panels)})
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(changed),
        "CALIBRATION_FORCING_INVALID",
    )


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "reorder", "water_keys"])
def test_calibration_revalidation_rejects_nested_sequence_mutations(
    primary_fit: CalibrationForcingPanelBundle,
    mutation: str,
) -> None:
    panel = primary_fit.panels[0]
    mapping = {
        key: tuple(sequence) for key, sequence in panel.forcings_by_water_id.items()
    }
    sequence = list(mapping[WATER_IDS[0]])
    if mutation == "drop":
        sequence.pop()
    elif mutation == "duplicate":
        sequence[-1] = sequence[-2]
    elif mutation == "reorder":
        sequence[0], sequence[1] = sequence[1], sequence[0]
    else:
        mapping = {WATER_IDS[0]: tuple(sequence), "caller_water": tuple(sequence)}
    if mutation != "water_keys":
        mapping[WATER_IDS[0]] = tuple(sequence)
    changed_panel = panel.model_copy(update={"forcings_by_water_id": mapping})
    changed = _replace_panel(primary_fit, 0, changed_panel)
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(changed),
        "CALIBRATION_FORCING_INVALID",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_k", float("nan")),
        ("temperature_k", 1.0e300),
        ("temperature_k", 289.0),
        ("apar_mol_h", -0.01),
        ("duration_hours", 12),
    ],
)
def test_calibration_revalidation_rejects_nonfinite_huge_range_and_type_mutations(
    primary_fit: CalibrationForcingPanelBundle,
    field: str,
    value: object,
) -> None:
    changed = _mutate_forcing(primary_fit, field=field, value=value)
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(changed),
        "CALIBRATION_FORCING_INVALID",
    )


def test_calibration_revalidation_rejects_stale_and_caller_recomputed_digests(
    primary_fit: CalibrationForcingPanelBundle,
) -> None:
    finite_mutation = _mutate_forcing(
        primary_fit,
        field="temperature_k",
        value=primary_fit.panels[0]
        .forcings_by_water_id[WATER_IDS[0]][0]
        .temperature_k
        + 0.01,
    )
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(finite_mutation),
        "CALIBRATION_FORCING_INVALID",
    )
    caller_digest = _sha256_json(_registered_panel_payload(finite_mutation))
    assert caller_digest != EXPECTED_HASHES["fit_64"]
    caller_signed = finite_mutation.model_copy(
        update={"canonical_sha256": caller_digest}
    )
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(caller_signed),
        "CALIBRATION_FORCING_INVALID",
    )
    stale = primary_fit.model_copy(update={"canonical_sha256": "0" * 64})
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(stale),
        "CALIBRATION_FORCING_INVALID",
    )


def test_calibration_revalidation_rejects_hostile_bundle_subclass(
    primary_fit: CalibrationForcingPanelBundle,
) -> None:
    class HostileBundle(CalibrationForcingPanelBundle):
        pass

    hostile = HostileBundle.model_construct(**primary_fit.__dict__)
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(hostile),
        "CALIBRATION_FORCING_INVALID",
    )


def test_calibration_revalidation_rejects_hostile_nested_panel_subclass(
    primary_fit: CalibrationForcingPanelBundle,
) -> None:
    class HostilePanel(CalibrationForcingPanel):
        hidden_instruction: str = "trust caller"

    hostile_panel = HostilePanel.model_construct(
        **primary_fit.panels[0].__dict__,
        hidden_instruction="trust caller",
    )
    hostile = _replace_panel(primary_fit, 0, hostile_panel)
    _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(hostile),
        "CALIBRATION_FORCING_INVALID",
    )


def test_calibration_revalidation_wraps_hostile_panel_sequence_failure(
    primary_fit: CalibrationForcingPanelBundle,
) -> None:
    class BadSeq:
        def __iter__(self):
            raise RuntimeError("hostile calibration panel iteration")

    hostile = primary_fit.model_copy(update={"panels": BadSeq()})
    error = _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(hostile),
        "CALIBRATION_FORCING_INVALID",
    )
    assert error.field_path == "bundle"
    assert error.details == {"cause_type": "RuntimeError"}


def test_calibration_revalidation_wraps_hostile_nested_mapping_failure(
    primary_fit: CalibrationForcingPanelBundle,
) -> None:
    class HostileMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError("hostile nested forcing lookup")

        def __iter__(self):
            raise RuntimeError("hostile nested forcing iteration")

        def __len__(self) -> int:
            return 2

    hostile_panel = primary_fit.panels[0].model_copy(
        update={"forcings_by_water_id": HostileMapping()}
    )
    hostile = _replace_panel(primary_fit, 0, hostile_panel)
    error = _assert_invalid(
        lambda: revalidate_calibration_forcing_panel_bundle(hostile),
        "CALIBRATION_FORCING_INVALID",
    )
    assert error.field_path == "bundle"
    assert error.details == {"cause_type": "RuntimeError"}
