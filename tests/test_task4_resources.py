"""Task 4 package-resource and locked-runtime preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from typing import Callable
import zipfile

import numpy
from packaging.requirements import Requirement
import pytest
import scipy
import yaml

from almondlab.biology_surrogate import load_candidate_effects
from almondlab.domains import load_model_domains
from almondlab.errors import AlmondLabError
import almondlab.paper1_contracts as paper1_contracts
from almondlab.paper1_contracts import (
    inspect_v13_scenario_migration,
    load_candidate_specs,
    load_paper1_design,
    load_paper1_water_recipes,
    load_synthetic_scenarios,
    load_task4_stop_policy,
    migrate_paper1_design_water_recipes,
    validate_active_paper1_water_recipes,
)
from almondlab.provenance import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[1]
AUTHORING_CONFIGS = ROOT / "configs"
AUTHORING_FIXTURES = ROOT / "tests" / "fixtures"
PACKAGED_ROOT = ROOT / "src" / "almondlab" / "resources"
PACKAGED_CONFIGS = PACKAGED_ROOT / "configs"
PACKAGED_FIXTURES = PACKAGED_ROOT / "fixtures"

TASK4_RUNTIME_CONFIGS = frozenset(
    {
        "candidates.yaml",
        "experiment_paper1.yaml",
        "model_domains.yaml",
        "paper1_task4_stop_policy.yaml",
        "paper1_water_recipes.yaml",
        "synthetic_scenarios.yaml",
    }
)
TASK4_ARCHIVE_CONFIGS = frozenset(
    {
        "archive/experiment_paper1_v1_3.yaml",
        "archive/synthetic_scenarios_v1_3.yaml",
    }
)
EXISTING_POLICY_CONFIGS = frozenset({"thresholds.yaml", "verification.yaml"})
EXPECTED_CONFIGS = (
    TASK4_RUNTIME_CONFIGS | TASK4_ARCHIVE_CONFIGS | EXISTING_POLICY_CONFIGS
)

TASK4_FIXTURES = frozenset(
    {
        "candidate_effects.yaml",
        "global_null.yaml",
        "known_effect.yaml",
        "winner_curse.yaml",
    }
)
EXISTING_FIXTURES = frozenset(
    {
        "all_conserved_entities.yaml",
        "candidate_effects.yaml",
        "chained_transaction_ids.yaml",
        "chemistry_handcheck.yaml",
        "conservation_case_manifest.candidates.json",
        "conservation_case_manifest.yaml",
        "entity_units_density.yaml",
        "internal_plant_flux_cap.yaml",
        "ions_conservative.yaml",
        "no_purge.yaml",
        "paper1_small.yaml",
        "perfect_na_exclusion.yaml",
        "ro_remineralization.yaml",
        "shared_reservoir_trap.csv",
        "sufficient_purge.yaml",
        "water_one_day.yaml",
    }
)
EXPECTED_FIXTURES = EXISTING_FIXTURES | TASK4_FIXTURES
TASK4_MIRRORS = tuple(
    ("configs", name)
    for name in sorted(TASK4_RUNTIME_CONFIGS | TASK4_ARCHIVE_CONFIGS)
) + tuple(("fixtures", name) for name in sorted(TASK4_FIXTURES))

REGISTERED_ARCHIVE_HASHES = {
    "archive/experiment_paper1_v1_3.yaml": (
        "d402889dac8b4580b0d2f01e65b6caf750b8af65e0550fe6283c630109e465e0"
    ),
    "archive/synthetic_scenarios_v1_3.yaml": (
        "46286eb006fbfbaf13281dfe52d4c63c9dc00ff7b3ef0a8ee704146908f759cb"
    ),
}
REGISTERED_CANDIDATE_EFFECTS_SHA256 = (
    "4e92c1567227b9e1f6e0713b79890bfc652a5b21a8de013769eaaa01ac939c21"
)
REGISTERED_RECIPE_REGISTRY_SHA256 = (
    "8a902441d143017fddfddf5b174302187dd8da1d9a46f98af9a94d18e317b1bd"
)
RESOURCE_SUFFIXES = frozenset({".yaml", ".json", ".csv"})


def _recursive_inventory(directory: Path) -> frozenset[str]:
    return frozenset(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in RESOURCE_SUFFIXES
    )


def _assert_lf_text(raw: bytes, path: str) -> None:
    assert raw, f"{path} must not be empty"
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path} must not contain a BOM"
    assert b"\r" not in raw, f"{path} must use LF only"
    assert raw.endswith(b"\n"), f"{path} must end with one LF"
    assert not raw.endswith(b"\n\n"), f"{path} must end with exactly one LF"
    raw.decode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _config_resource_path(name: str) -> Path:
    return AUTHORING_CONFIGS.joinpath(*name.split("/"))


def _packaged_resource_path(kind: str, name: str) -> Path:
    return PACKAGED_ROOT.joinpath(kind, *name.split("/"))


def _build_test_wheel(destination: Path) -> Path:
    """Build a minimal PEP 427 wheel from the declared Hatch include patterns."""

    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]
    include_patterns = document["tool"]["hatch"]["build"]["include"]
    selected = {
        path.relative_to(ROOT).as_posix(): path
        for pattern in include_patterns
        for path in ROOT.glob(pattern)
        if path.is_file()
    }
    distribution = project["name"].replace("-", "_")
    version = project["version"]
    dist_info = f"{distribution}-{version}.dist-info"
    wheel = destination / f"{distribution}-{version}-py3-none-any.whl"
    metadata = "\n".join(
        [
            "Metadata-Version: 2.3",
            f"Name: {project['name']}",
            f"Version: {version}",
            *(
                f"Requires-Dist: {requirement}"
                for requirement in project["dependencies"]
            ),
            "",
        ]
    ).encode("utf-8")
    wheel_metadata = (
        "Wheel-Version: 1.0\n"
        "Generator: task4-resource-preflight\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")
    members = {
        relative.removeprefix("src/"): path.read_bytes()
        for relative, path in selected.items()
    }
    members[f"{dist_info}/METADATA"] = metadata
    members[f"{dist_info}/WHEEL"] = wheel_metadata
    record_name = f"{dist_info}/RECORD"
    members[record_name] = (
        "".join(f"{name},,\n" for name in sorted((*members, record_name)))
    ).encode("utf-8")
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        for name, raw in sorted(members.items()):
            stream.writestr(name, raw)
    return wheel


def _assert_runtime_error(
    call: Callable[[], object], *, expected_field_path: str
) -> AlmondLabError:
    with pytest.raises(AlmondLabError) as captured:
        call()
    assert captured.value.code == "TASK4_RUNTIME_VERSION_MISMATCH"
    assert captured.value.field_path == expected_field_path
    return captured.value


def test_recursive_authoring_config_inventory_is_exact() -> None:
    """Catches an omitted archive, stop policy, or unregistered extra config."""

    assert _recursive_inventory(AUTHORING_CONFIGS) == EXPECTED_CONFIGS


def test_recursive_packaged_config_inventory_is_exact() -> None:
    """Catches a wheel mirror set that omits Task 4 or flattens its archive."""

    assert _recursive_inventory(PACKAGED_CONFIGS) == EXPECTED_CONFIGS


def test_authoring_fixture_inventory_is_exact() -> None:
    """Catches Task 4 generation starting before all prospective fixtures exist."""

    assert _recursive_inventory(AUTHORING_FIXTURES) == EXPECTED_FIXTURES


def test_packaged_fixture_inventory_is_exact() -> None:
    """Catches a future generator fixture that is not installed with the package."""

    assert _recursive_inventory(PACKAGED_FIXTURES) == EXPECTED_FIXTURES


@pytest.mark.parametrize(("kind", "name"), TASK4_MIRRORS)
def test_task4_authoring_and_packaged_resources_are_exact_lf_mirrors(
    kind: str,
    name: str,
) -> None:
    """Catches stale package bytes, CRLF checkout drift, BOMs, or truncated text."""

    authoring_root = AUTHORING_CONFIGS if kind == "configs" else AUTHORING_FIXTURES
    authoring = authoring_root.joinpath(*name.split("/"))
    packaged = _packaged_resource_path(kind, name)
    assert authoring.is_file(), f"missing authoring resource: {kind}/{name}"
    assert packaged.is_file(), f"missing packaged resource: {kind}/{name}"
    authoring_bytes = authoring.read_bytes()
    packaged_bytes = packaged.read_bytes()
    _assert_lf_text(authoring_bytes, f"authoring/{kind}/{name}")
    _assert_lf_text(packaged_bytes, f"packaged/{kind}/{name}")
    assert packaged_bytes == authoring_bytes


def test_active_and_archive_authorities_are_recursive_and_noncolliding() -> None:
    """Catches archive bytes overwriting or masquerading as an active registry."""

    pairs = (
        ("experiment_paper1.yaml", "archive/experiment_paper1_v1_3.yaml"),
        ("synthetic_scenarios.yaml", "archive/synthetic_scenarios_v1_3.yaml"),
    )
    for active_name, archive_name in pairs:
        active = _config_resource_path(active_name)
        archive = _config_resource_path(archive_name)
        assert active.resolve() != archive.resolve()
        assert active.read_bytes() != archive.read_bytes()
        assert _sha256(archive.read_bytes()) == REGISTERED_ARCHIVE_HASHES[archive_name]
    assert _sha256((AUTHORING_FIXTURES / "candidate_effects.yaml").read_bytes()) == (
        REGISTERED_CANDIDATE_EFFECTS_SHA256
    )


def test_every_authority_loads_and_cross_hashes_revalidate() -> None:
    """Catches a byte-complete package containing an unusable or stale authority."""

    candidates = load_candidate_specs(AUTHORING_CONFIGS / "candidates.yaml")
    assert len(candidates.candidates) == 6
    effects = load_candidate_effects(AUTHORING_FIXTURES / "candidate_effects.yaml")
    assert tuple(effects) == tuple(f"C{number}" for number in range(1, 7))

    active_design = load_paper1_design(AUTHORING_CONFIGS / "experiment_paper1.yaml")
    archived_design = load_paper1_design(
        AUTHORING_CONFIGS / "archive" / "experiment_paper1_v1_3.yaml"
    )
    domains = load_model_domains(AUTHORING_CONFIGS / "model_domains.yaml")
    assert domains.sha256 == _sha256(
        (AUTHORING_CONFIGS / "model_domains.yaml").read_bytes()
    )
    core_domain = next(domain for domain in domains.domains if domain.model_id == "core_v1")
    recipes = load_paper1_water_recipes(
        AUTHORING_CONFIGS / "paper1_water_recipes.yaml"
    )
    assert _sha256(canonical_json_bytes(recipes.model_dump(mode="json"))) == (
        REGISTERED_RECIPE_REGISTRY_SHA256
    )
    migrated = migrate_paper1_design_water_recipes(archived_design, recipes)
    assert migrated.model_dump(mode="json") == active_design.model_dump(mode="json")
    assert len(
        validate_active_paper1_water_recipes(
            recipes,
            design=active_design,
            domain=core_domain,
        )
    ) == 2
    assert load_task4_stop_policy(
        AUTHORING_CONFIGS / "paper1_task4_stop_policy.yaml"
    ).policy_id == "paper1_task4_stop_policy@1.0.0"

    scenarios = load_synthetic_scenarios(
        AUTHORING_CONFIGS / "synthetic_scenarios.yaml"
    )
    assert scenarios.water_recipe_registry_sha256 == REGISTERED_RECIPE_REGISTRY_SHA256
    assert len(scenarios.all_scenarios) == 10
    assert len(scenarios.sensitivities) == 36
    migration = inspect_v13_scenario_migration(
        AUTHORING_CONFIGS / "archive" / "synthetic_scenarios_v1_3.yaml"
    )
    assert migration.source_raw_sha256 == REGISTERED_ARCHIVE_HASHES[
        "archive/synthetic_scenarios_v1_3.yaml"
    ]

    for name in TASK4_FIXTURES - {"candidate_effects.yaml"}:
        payload = yaml.safe_load((AUTHORING_FIXTURES / name).read_bytes())
        assert isinstance(payload, dict) and payload


def test_git_archive_and_autocrlf_materialize_identical_task4_bytes(
    tmp_path: Path,
) -> None:
    """Catches missing eol attributes for active, archived, or packaged mirrors."""

    relative_files = tuple(
        Path("configs", *name.split("/")) for name in sorted(EXPECTED_CONFIGS)
    ) + tuple(
        Path("tests", "fixtures", *name.split("/"))
        for name in sorted(EXPECTED_FIXTURES)
    ) + tuple(
        Path("src", "almondlab", "resources", "configs", *name.split("/"))
        for name in sorted(EXPECTED_CONFIGS)
    ) + tuple(
        Path("src", "almondlab", "resources", "fixtures", *name.split("/"))
        for name in sorted(EXPECTED_FIXTURES)
    )
    missing = tuple(path.as_posix() for path in relative_files if not (ROOT / path).is_file())
    assert not missing, f"resources required for git stability are missing: {missing}"

    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copy2(ROOT / ".gitattributes", repository / ".gitattributes")
    expected: dict[Path, bytes] = {}
    for relative in relative_files:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / relative).read_bytes()
        _assert_lf_text(raw, relative.as_posix())
        destination.write_bytes(raw)
        expected[relative] = raw
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "core.autocrlf=true", "add", "."],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Task4 Resource Test",
            "-c",
            "user.email=task4-resource-test@invalid.example",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    archive_path = tmp_path / "resources.zip"
    subprocess.run(
        ["git", "archive", "--format=zip", f"--output={archive_path}", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    with zipfile.ZipFile(archive_path) as stream:
        for relative, raw in expected.items():
            assert stream.read(relative.as_posix()) == raw

    checkout = tmp_path / "autocrlf-checkout"
    checkout.mkdir()
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "checkout-index",
            "--all",
            "--force",
            f"--prefix={checkout.as_posix()}/",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    for relative, raw in expected.items():
        assert (checkout / relative).read_bytes() == raw


def test_wheel_installs_and_exposes_every_task4_resource(
    tmp_path: Path,
) -> None:
    """Catches a source-tree-only mirror omitted from an installed wheel."""

    wheel = _build_test_wheel(tmp_path)
    target = tmp_path / "installed"
    subprocess.run(
        [
            sys._base_executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-index",
            "--target",
            str(target),
            str(wheel),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    missing_authoring = tuple(
        sorted(
            f"fixtures/{name}"
            for name in TASK4_FIXTURES
            if not (AUTHORING_FIXTURES / name).is_file()
        )
    )
    assert not missing_authoring, (
        f"wheel smoke authorities are missing from authoring: {missing_authoring}"
    )
    expected = {
        f"configs/{name}": _sha256(_config_resource_path(name).read_bytes())
        for name in TASK4_RUNTIME_CONFIGS | TASK4_ARCHIVE_CONFIGS
    } | {
        f"fixtures/{name}": _sha256((AUTHORING_FIXTURES / name).read_bytes())
        for name in TASK4_FIXTURES
    }
    script = (
        "from importlib import resources; import hashlib,json,sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "root=resources.files('almondlab.resources'); "
        "names=json.loads(sys.argv[2]); "
        "observed={name:hashlib.sha256(root.joinpath(*name.split('/')).read_bytes()).hexdigest() "
        "for name in names}; print(json.dumps(observed,sort_keys=True))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(target), json.dumps(sorted(expected))],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == expected


def test_task4_numpy_and_scipy_metadata_are_exactly_pinned() -> None:
    """Catches a resolver selecting transformed-normal or solver drift."""

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    requirements = {
        requirement.name.lower(): requirement
        for raw in project["dependencies"]
        for requirement in (Requirement(raw),)
    }
    assert str(requirements["numpy"].specifier) == "==2.5.2"
    assert str(requirements["scipy"].specifier) == "==1.18.0"
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = {
        package["name"]: package["version"]
        for package in lock["package"]
        if package["name"] in {"numpy", "scipy"}
    }
    assert locked == {"numpy": "2.5.2", "scipy": "1.18.0"}
    assert numpy.__version__ == "2.5.2"
    assert scipy.__version__ == "1.18.0"


@pytest.mark.parametrize(
    ("module", "received", "expected_field_path"),
    [
        (numpy, "2.5.3", "numpy_version"),
        (scipy, "1.18.1", "scipy_version"),
    ],
    ids=["numpy", "scipy"],
)
def test_task4_scientific_runtime_guard_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    received: str,
    expected_field_path: str,
) -> None:
    """Catches version metadata being pinned while runtime execution stays open."""

    guard = getattr(paper1_contracts, "require_task4_scientific_runtime", None)
    assert callable(guard), "public Task 4 scientific-runtime guard is missing"
    assert guard() is None
    monkeypatch.setattr(module, "__version__", received)
    _assert_runtime_error(guard, expected_field_path=expected_field_path)


@pytest.mark.parametrize(
    ("distribution", "expected_version", "expected_field_path"),
    [
        ("numpy", "2.5.2", "numpy_version"),
        ("scipy", "1.18.0", "scipy_version"),
    ],
)
def test_task4_scientific_runtime_guard_converts_hostile_version_access(
    monkeypatch: pytest.MonkeyPatch,
    distribution: str,
    expected_version: str,
    expected_field_path: str,
) -> None:
    """Catches ``__version__`` access leaking an ordinary dependency error."""

    class HostileVersionModule:
        @property
        def __version__(self) -> str:
            raise RuntimeError("hostile version metadata")

    real_import = paper1_contracts.import_module

    def import_for_test(name: str) -> object:
        if name == distribution:
            return HostileVersionModule()
        return real_import(name)

    monkeypatch.setattr(paper1_contracts, "import_module", import_for_test)
    error = _assert_runtime_error(
        paper1_contracts.require_task4_scientific_runtime,
        expected_field_path=expected_field_path,
    )
    assert error.details == {
        "expected": expected_version,
        "received": "unavailable",
        "cause_type": "RuntimeError",
    }
    assert isinstance(error.__context__, RuntimeError)


@pytest.mark.parametrize("distribution", ["numpy", "scipy"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_task4_scientific_runtime_guard_preserves_process_control_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    distribution: str,
    exception_type: type[BaseException],
) -> None:
    """Catches the runtime boundary swallowing process-control exceptions."""

    class InterruptingVersionModule:
        @property
        def __version__(self) -> str:
            raise exception_type("stop")

    real_import = paper1_contracts.import_module

    def import_for_test(name: str) -> object:
        if name == distribution:
            return InterruptingVersionModule()
        return real_import(name)

    monkeypatch.setattr(paper1_contracts, "import_module", import_for_test)
    with pytest.raises(exception_type, match="stop"):
        paper1_contracts.require_task4_scientific_runtime()
