"""Independent verification of the prospective Task 4 materializer."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
import subprocess
import tarfile
from types import ModuleType

import pytest
from numpy.random import SeedSequence

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


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _import_materializer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "task4_registration_hash_materializer_under_test", MATERIALIZER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class MaterializedPanels:
    payloads: dict[str, dict[str, object]]
    ranges: dict[str, tuple[tuple[float, float], ...]]


@pytest.fixture(scope="module")
def module() -> ModuleType:
    return _import_materializer()


@pytest.fixture(scope="module")
def panels(module: ModuleType) -> MaterializedPanels:
    family = SeedSequence(ROOT_SEED).spawn(12)[11]
    fit_seed, holdout_seed = family.spawn(2)
    seeds = {"fit": fit_seed, "holdout": holdout_seed}
    innovations = {
        kind: module.calibration_innovations(seed)
        for kind, seed in seeds.items()
    }
    payloads: dict[str, dict[str, object]] = {}
    observed_ranges: dict[str, tuple[tuple[float, float], ...]] = {}
    for size in (32, 64, 128):
        for kind in ("fit", "holdout"):
            key = f"{kind}_{size}"
            payload, ranges = module.calibration_panel_payload(
                panel_kind=kind,
                seed_sequence=seeds[kind],
                panel_size=size,
                innovations=innovations[kind],
            )
            payloads[key] = payload
            observed_ranges[key] = ranges
    return MaterializedPanels(payloads=payloads, ranges=observed_ranges)


def test_materializer_is_tracked_lf_stable_and_archive_reproduces_bytes() -> None:
    """Catches an untracked authority or checkout-dependent registered hash."""

    raw = MATERIALIZER.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MATERIALIZER_SHA256
    assert b"\r\n" not in raw
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", MATERIALIZER.relative_to(ROOT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert tracked.returncode == 0
    archive = subprocess.check_output(
        [
            "git",
            "archive",
            "--format=tar",
            "HEAD",
            MATERIALIZER.relative_to(ROOT).as_posix(),
        ],
        cwd=ROOT,
    )
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as stream:
        member = stream.extractfile(MATERIALIZER.relative_to(ROOT).as_posix())
        assert member is not None
        archived = member.read()
    assert archived == raw


def test_materializer_constants_and_nominal_schemas_are_exact(module: ModuleType) -> None:
    """Catches a new seed, water, recipe, domain, schema, or schedule authority."""

    assert module.SCHEMA_VERSION == "1.1.0"
    assert module.ROOT_SEED == ROOT_SEED
    assert module.WATER_IDS == WATER_IDS
    assert module.RECIPE_IDS == RECIPE_IDS
    assert module.HYDRAULIC_DOMAIN == {
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
    nominal = module.nominal_schedule_payload()
    operator = module.operator_times_payload()
    sample = module.sample_times_payload()
    assert _sha256_json(nominal) == EXPECTED_HASHES["nominal"]
    assert _sha256_json(operator) == EXPECTED_HASHES["operator_times"]
    assert _sha256_json(sample) == EXPECTED_HASHES["sample_times"]
    assert len(nominal["records"]) == 2 * 168
    assert nominal["water_ids"] == list(WATER_IDS)
    assert operator["operator_event_times_days"] == [
        0.25 + index for index in range(84)
    ]
    assert sample["reservoir_sample_times_days"] == [
        0.0, 14.0, 28.0, 42.0, 56.0, 70.0, 84.0
    ]


def test_panel_hashes_counts_ranges_and_fixed_prefixes_are_independent(
    panels: MaterializedPanels,
) -> None:
    """Catches redraws, changed ordering, wrong dimensions, or non-prefix panels."""

    for key, payload in panels.payloads.items():
        size = int(key.rsplit("_", 1)[1])
        assert payload["panel_size"] == size
        assert payload["water_ids"] == list(WATER_IDS)
        assert len(payload["records"]) == size * 2 * 168
        assert _sha256_json(payload) == EXPECTED_HASHES[key]
        assert panels.ranges[key] == EXPECTED_RANGES[key]
    for kind in ("fit", "holdout"):
        rows_32 = panels.payloads[f"{kind}_32"]["records"]
        rows_64 = panels.payloads[f"{kind}_64"]["records"]
        rows_128 = panels.payloads[f"{kind}_128"]["records"]
        assert rows_32 == rows_64[: len(rows_32)]
        assert rows_64 == rows_128[: len(rows_64)]
        assert rows_128[-1]["panel_index"] == 127
        assert rows_128[-1]["water_id"] == WATER_IDS[-1]
        assert rows_128[-1]["step_index"] == 167


def test_materializer_has_no_outcome_generation_or_solver_dependency() -> None:
    """Catches registration tooling growing a plant-outcome calibration path."""

    source = MATERIALIZER.read_text(encoding="utf-8")
    tree = ast.parse(source)
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
    assert imported <= {
        "__future__",
        "hashlib",
        "math",
        "numpy",
        "numpy.random",
        "almondlab.provenance",
    }
    forbidden = (
        "almondlab.simulate",
        "biology_surrogate",
        "SimulationResult",
        "solve_ivp",
        "brentq",
        "calibrate_mechanism_to_estimand",
    )
    assert all(token not in source for token in forbidden)
