from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from almondlab import verification
from almondlab.contracts import ConservedEntity, EvidenceLabel, StockUnit
from almondlab.verification import (
    VerificationRecord,
    capture_code_provenance,
    code_version_from_provenance,
    evaluate_run_stops,
    run_core_acceptance,
    write_verification_record,
)
from almondlab.verification_policy import (
    CANONICAL_PHYSICAL_STOPS,
    CANONICAL_VERIFICATION_TOLERANCES,
    load_threshold_policy,
    load_verification_policy,
    validate_threshold_policy,
    validate_verification_policy,
)


_PROVENANCE_UNAVAILABLE = {
    "package_version": None,
    "git_sha": None,
    "git_dirty": None,
    "git_status_sha256": None,
    "unavailable": (
        "package_version",
        "git_sha",
        "git_dirty",
        "git_status_sha256",
    ),
}


def _record(**overrides: object) -> VerificationRecord:
    values: dict[str, object] = {
        "acceptance_test": 13,
        "fixture_sha256": "a" * 64,
        "observed_value": {"value": 0.5000001},
        "oracle": {"value": 0.5},
        "tolerance": {"value": 1e-6},
        "comparison": {"value": "abs_le"},
        "code_version": "unavailable:explicit-test-gate",
        "code_provenance": _PROVENANCE_UNAVAILABLE,
        "evidence_label": EvidenceLabel.PHYSICS_CONSTRAINED,
    }
    values.update(overrides)
    return VerificationRecord(**values)  # type: ignore[arg-type]


def test_verification_record_pass_state_is_read_only_and_caller_unsettable() -> None:
    record = _record()

    assert record.passed is True
    assert "passed" not in record.__dataclass_fields__
    with pytest.raises(TypeError):
        _record(passed=True)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        record.passed = False  # type: ignore[misc]


@pytest.mark.parametrize("observed", ["0.5", True])
def test_numeric_observation_wrong_type_fails_without_coercion(observed: object) -> None:
    record = _record(observed_value={"value": observed})

    assert record.passed is False


@pytest.mark.parametrize("tolerance", [True, False])
def test_boolean_tolerance_is_invalid_schema(tolerance: bool) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        _record(tolerance={"value": tolerance})


@pytest.mark.parametrize(
    ("observed", "oracle"),
    [(1, 1.0), (1, True), (False, 0)],
)
def test_equality_requires_exact_json_scalar_kind(
    observed: object, oracle: object
) -> None:
    record = _record(
        observed_value=observed,
        oracle=oracle,
        tolerance=0,
        comparison="eq",
    )

    assert record.passed is False


def test_eq_rejects_boolean_tolerance_even_though_bool_equals_zero() -> None:
    with pytest.raises(ValueError, match="eq tolerance"):
        _record(
            observed_value=1,
            oracle=1,
            tolerance=False,
            comparison="eq",
        )


@pytest.mark.parametrize(
    "bad_mapping",
    [
        {1: "numeric-key"},
        {"1": "string-key", 1: "collides-after-stringification"},
    ],
)
def test_record_rejects_non_string_and_colliding_mapping_keys(
    bad_mapping: dict[object, object],
) -> None:
    with pytest.raises(ValueError, match="string keys"):
        _record(observed_value=bad_mapping, oracle=bad_mapping)


@pytest.mark.parametrize(
    "field_name",
    ("fixture_sha256s", "auxiliary_artifacts_sha256s"),
)
def test_record_rejects_non_string_resource_hash_keys(field_name: str) -> None:
    with pytest.raises(ValueError, match="string keys"):
        _record(**{field_name: {1: "b" * 64}})


def test_record_validates_primary_digest_independently_of_hash_map_collision() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        _record(
            fixture_sha256="not-a-digest",
            fixture_sha256s={"primary": "b" * 64},
        ).validate()


def test_record_reserves_primary_name_from_auxiliary_artifacts() -> None:
    with pytest.raises(ValueError, match="primary"):
        _record(auxiliary_artifacts_sha256s={"primary": "b" * 64}).validate()


def test_record_rejects_boolean_acceptance_test() -> None:
    with pytest.raises(ValueError, match="acceptance_test"):
        _record(acceptance_test=True).validate()


@pytest.mark.parametrize(
    ("overrides", "expected_pass"),
    [
        ({"observed_value": {"value": 10**400}}, False),
        (
            {
                "observed_value": {"value": 10**400},
                "oracle": {"value": 10**400},
                "tolerance": {"value": 0},
            },
            True,
        ),
    ],
)
def test_numeric_comparison_handles_finite_arbitrary_precision_integers(
    overrides: dict[str, object], expected_pass: bool
) -> None:
    record = _record(**overrides)

    assert record.passed is expected_pass


def test_invalid_oracle_schema_is_validated_even_when_observed_shape_differs() -> None:
    with pytest.raises(ValueError, match="tolerance.*shape"):
        _record(observed_value={}, oracle={"a": 0}, tolerance={})


def test_invalid_later_oracle_branch_is_not_hidden_by_earlier_failure() -> None:
    with pytest.raises(ValueError, match="unknown comparison"):
        _record(
            observed_value={"a": 1, "b": 0},
            oracle={"a": 0, "b": 0},
            tolerance={"a": 0, "b": 0},
            comparison={"a": "eq", "b": "invented"},
        )


def test_record_deep_freezes_provenance_and_nested_unavailable() -> None:
    nested = {
        **_PROVENANCE_UNAVAILABLE,
        "unavailable": [
            "package_version",
            "git_sha",
            "git_dirty",
            "git_status_sha256",
        ],
    }
    record = _record(code_provenance=nested)

    assert isinstance(record.code_provenance, MappingProxyType)
    assert isinstance(record.code_provenance["unavailable"], tuple)
    nested["unavailable"].append("invented")  # type: ignore[union-attr]
    assert "invented" not in record.code_provenance["unavailable"]


@pytest.mark.parametrize(
    "provenance",
    [
        {
            **_PROVENANCE_UNAVAILABLE,
            "package_version": None,
            "unavailable": ("git_sha", "git_dirty", "git_status_sha256"),
        },
        {
            **_PROVENANCE_UNAVAILABLE,
            "git_sha": "not-a-sha",
            "unavailable": ("package_version", "git_dirty", "git_status_sha256"),
        },
        {
            **_PROVENANCE_UNAVAILABLE,
            "git_dirty": "false",
            "unavailable": ("package_version", "git_sha", "git_status_sha256"),
        },
    ],
)
def test_provenance_requires_exact_types_and_exact_unavailable_set(
    provenance: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="provenance|unavailable"):
        _record(code_provenance=provenance).validate()


def _git(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_code_provenance_detects_untracked_files_in_real_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = tmp_path / "src" / "almondlab" / "verification.py"
    module.parent.mkdir(parents=True)
    module.write_text("# tracked module\n")
    _git(tmp_path, "init")
    _git(tmp_path, "add", module.relative_to(tmp_path).as_posix())
    _git(
        tmp_path,
        "-c",
        "user.name=AlmondLab Test",
        "-c",
        "user.email=almondlab@example.invalid",
        "commit",
        "-m",
        "tracked module",
    )
    clean_status = _git(
        tmp_path, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout.encode()
    monkeypatch.setattr(verification, "__file__", str(module))
    clean = verification._code_provenance()
    assert clean["git_dirty"] is False
    assert clean["git_status_sha256"] == hashlib.sha256(clean_status).hexdigest()

    (tmp_path / "untracked.txt").write_text("untracked\n")
    dirty_status = _git(
        tmp_path, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout.encode()
    dirty = verification._code_provenance()
    assert dirty["git_dirty"] is True
    assert dirty["git_status_sha256"] == hashlib.sha256(dirty_status).hexdigest()
    assert dirty["git_status_sha256"] != clean["git_status_sha256"]


def test_code_provenance_rejects_untracked_module_in_unrelated_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked = tmp_path / "README.md"
    tracked.write_text("unrelated repo\n")
    _git(tmp_path, "init")
    _git(tmp_path, "add", "README.md")
    _git(
        tmp_path,
        "-c",
        "user.name=AlmondLab Test",
        "-c",
        "user.email=almondlab@example.invalid",
        "commit",
        "-m",
        "unrelated repository",
    )
    untracked_module = tmp_path / "site-packages" / "almondlab" / "verification.py"
    untracked_module.parent.mkdir(parents=True)
    untracked_module.write_text("# installed-style untracked module\n")
    monkeypatch.setattr(verification, "__file__", str(untracked_module))

    provenance = verification._code_provenance()

    assert provenance["git_sha"] is None
    assert provenance["git_dirty"] is None
    assert provenance["git_status_sha256"] is None
    assert provenance["unavailable"] == (
        "git_sha",
        "git_dirty",
        "git_status_sha256",
    )


def test_public_provenance_api_is_generic_and_matches_private_compatibility_aliases(
) -> None:
    provenance = capture_code_provenance()
    code_version = code_version_from_provenance(provenance)

    assert provenance == verification._code_provenance()
    assert code_version == verification._code_version(provenance)
    record = VerificationRecord(
        acceptance_test=6,
        fixture_sha256="b" * 64,
        observed_value={"value": 1.0},
        oracle={"value": 1.0},
        tolerance={"value": 0.0},
        comparison={"value": "abs_le"},
        code_version=code_version,
        code_provenance=provenance,
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
    )
    record.validate()
    assert record.passed is True


def test_writer_validates_before_atomic_target_creation(tmp_path: Path) -> None:
    target = tmp_path / "verification" / "record.json"
    with pytest.raises(ValueError):
        write_verification_record(
            target,
            _record(fixture_sha256="not-a-digest"),
        )
    assert not target.exists()
    assert not target.parent.exists()


def test_atomic_writer_preserves_previous_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "verification" / "record.json"
    target.parent.mkdir()
    target.write_bytes(b"previous\n")

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("injected atomic replace failure")

    monkeypatch.setattr(verification.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failure"):
        write_verification_record(target, _record())

    assert target.read_bytes() == b"previous\n"
    assert not tuple(target.parent.glob(f".{target.name}.*.tmp"))


def test_auxiliary_artifact_hashes_cover_exact_written_bytes(tmp_path: Path) -> None:
    records = run_core_acceptance(tmp_path)

    for record in records:
        for resource_id, digest in record.auxiliary_artifacts_sha256s.items():
            target = tmp_path / "verification" / resource_id
            assert target.is_file()
            assert hashlib.sha256(target.read_bytes()).hexdigest() == digest


def test_evaluate_stops_accepts_only_complete_authoritative_policy() -> None:
    policy = load_threshold_policy()
    good = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"volume_l": 10.0},
        threshold_policy=policy,
        applicable_stop_ids=("volume_l",),
    )
    assert good.valid is True

    mutated_stops = dict(policy.physical_stops)
    mutated_stops["volume_l"] = replace(
        mutated_stops["volume_l"], maximum=1001.0
    )
    weakened = replace(policy, physical_stops=mutated_stops)
    with pytest.raises(ValueError, match="canonical|locked"):
        evaluate_run_stops(
            numerical_values={"state": 1.0},
            stocks={"na": 0.0},
            ledger_relative_residuals={"water": 0.0},
            physical_values={"volume_l": 10.0},
            threshold_policy=weakened,
            applicable_stop_ids=("volume_l",),
        )


@pytest.mark.parametrize(
    ("stop_id", "field_name"),
    [
        (stop_id, field_name)
        for stop_id, (minimum, maximum, _) in CANONICAL_PHYSICAL_STOPS.items()
        for field_name, value in (("minimum", minimum), ("maximum", maximum))
        if value is not None
    ],
)
def test_every_schema_1_physical_threshold_is_locked_exactly(
    stop_id: str, field_name: str
) -> None:
    policy = load_threshold_policy()
    stops = dict(policy.physical_stops)
    original = getattr(stops[stop_id], field_name)
    assert original is not None
    stops[stop_id] = replace(
        stops[stop_id], **{field_name: original + 0.125}
    )

    with pytest.raises(ValueError, match="canonical|locked"):
        validate_threshold_policy(replace(policy, physical_stops=stops))


@pytest.mark.parametrize("stop_id", tuple(CANONICAL_PHYSICAL_STOPS))
def test_every_schema_1_physical_label_is_locked_exactly(stop_id: str) -> None:
    policy = load_threshold_policy()
    stops = dict(policy.physical_stops)
    stops[stop_id] = replace(
        stops[stop_id], evidence_label=EvidenceLabel.HYPOTHESIS_PRIOR
    )

    with pytest.raises(ValueError, match="canonical|locked"):
        validate_threshold_policy(replace(policy, physical_stops=stops))


@pytest.mark.parametrize(
    ("test_number", "name"),
    [
        (test_number, name)
        for test_number, values in CANONICAL_VERIFICATION_TOLERANCES.items()
        for name in values
    ],
)
def test_every_schema_1_verification_tolerance_is_locked_exactly(
    test_number: int, name: str
) -> None:
    policy = load_verification_policy()
    tolerances = {
        test_id: dict(values) for test_id, values in policy.tolerances.items()
    }
    original = tolerances[test_number][name]
    tolerances[test_number][name] = 1.0 if original == 0.0 else original * 0.5

    with pytest.raises(ValueError, match="canonical|locked"):
        validate_verification_policy(replace(policy, tolerances=tolerances))


def test_verification_policy_rejects_huge_numeric_scalar_as_value_error(
    tmp_path: Path,
) -> None:
    source = Path(verification.__file__).parent / "resources" / "configs" / "verification.yaml"
    payload = yaml.safe_load(source.read_text())
    payload["tolerances"][1]["absolute"] = 10**400
    corrupted = tmp_path / "verification.yaml"
    corrupted.write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match="finite"):
        load_verification_policy(corrupted)


def test_constructed_policies_reject_boolean_numeric_aliases() -> None:
    threshold = load_threshold_policy()
    stops = dict(threshold.physical_stops)
    stops["injury"] = replace(stops["injury"], maximum=True)
    with pytest.raises(ValueError, match="locked"):
        validate_threshold_policy(replace(threshold, physical_stops=stops))

    verification_policy = load_verification_policy()
    tolerances = {
        test_id: dict(values)
        for test_id, values in verification_policy.tolerances.items()
    }
    tolerances[19]["absolute"] = False
    with pytest.raises(ValueError, match="locked"):
        validate_verification_policy(
            replace(verification_policy, tolerances=tolerances)
        )


def test_verification_source_has_unique_top_level_acceptance_helpers() -> None:
    source_path = Path(verification.__file__)
    module = ast.parse(source_path.read_text())
    names = [node.name for node in module.body if isinstance(node, ast.FunctionDef)]

    assert names.count("_run_case_manifest") == 1
    assert names.count("_acceptance_20_bundle") == 1
    assert names.count("_acceptance_20") == 1
    assert "minimized_counterexample" not in source_path.read_text()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("start_ordinal", "0"),
        ("transaction_count", True),
        ("row_count", 1.5),
        ("transaction_duration_hours", "0.25"),
        ("carrier_volume_l", float("inf")),
        ("water_density_kg_l", 10**400),
    ],
)
def test_schema_v2_ledger_fixture_rejects_coercion_and_nonfinite_numbers(
    field_name: str, value: object
) -> None:
    fixture, _ = verification._fixture("water_one_day.yaml")
    expected = dict(fixture["expected_ledger"])
    expected[field_name] = value

    with pytest.raises(ValueError, match="primitive|finite|integer|row count"):
        verification._ledger_transaction_expectations(expected)


def test_acceptance_19_uses_code_owned_six_case_oracle() -> None:
    assert verification.EC_DIRECTIONAL_MISMATCH_ORACLE == (
        ("ECw", "pore_water_EC"),
        ("ECw", "ECe"),
        ("pore_water_EC", "ECw"),
        ("pore_water_EC", "ECe"),
        ("ECe", "ECw"),
        ("ECe", "pore_water_EC"),
    )
    record = verification._acceptance_19(
        cases=verification.EC_DIRECTIONAL_MISMATCH_ORACLE[:-1]
    )
    assert record.passed is False


def test_acceptance_19_default_execution_is_enum_derived_not_oracle_derived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verification,
        "EC_DIRECTIONAL_MISMATCH_ORACLE",
        verification.EC_DIRECTIONAL_MISMATCH_ORACLE[:-1],
    )

    record = verification._acceptance_19()

    assert len(record.observed_value["cases"]) == 6
    assert len(record.oracle["cases"]) == 5
    assert record.passed is False


def test_acceptance_13_oracle_owns_exact_analytic_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fixture = verification._fixture

    def corrupted_fixture(name: str) -> tuple[dict[str, object], str]:
        fixture, digest = original_fixture(name)
        if name == "perfect_na_exclusion.yaml":
            fixture = dict(fixture)
            domain = dict(fixture["hydraulic_domain"])
            domain.update(
                {
                    "model_id": "not-core-v1.acceptance-13",
                    "version": "99.0.0",
                    "purpose": "model_applicability",
                }
            )
            fixture["hydraulic_domain"] = domain
        return fixture, digest

    monkeypatch.setattr(verification, "_fixture", corrupted_fixture)

    record = verification._acceptance_13()

    assert record.observed_value["domain_policy"]["model_id"] == (
        "not-core-v1.acceptance-13"
    )
    assert record.oracle["domain_policy"]["model_id"] == "core_v1.acceptance_13"
    assert record.passed is False


@pytest.mark.parametrize("acceptance", (2, 20))
def test_all_entity_acceptances_use_code_owned_exact_quantity_scope(
    acceptance: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_fixture = verification._fixture

    def shrunk_fixture(name: str) -> tuple[dict[str, object], str]:
        fixture, digest = original_fixture(name)
        if name not in {"ions_conservative.yaml", "all_conserved_entities.yaml"}:
            return fixture, digest
        fixture = json.loads(json.dumps(fixture))
        fixture["tracked_entities"].remove("alkalinity")
        for branch_name in ("initial", "expected"):
            for branch in fixture[branch_name].values():
                branch["stocks"].pop("alkalinity")
        fixture["expected_ledger"]["per_transaction_amounts"].pop("alkalinity")
        fixture["expected_ledger"]["row_count"] -= (
            fixture["expected_ledger"]["transaction_count"] * 2
        )
        return fixture, digest

    monkeypatch.setattr(verification, "_fixture", shrunk_fixture)

    with pytest.raises(ValueError, match="canonical registry|tracked entities"):
        (verification._acceptance_02 if acceptance == 2 else verification._acceptance_20)()


def test_core_acceptance_runs_exact_registry_and_schema_v2_ledgers(tmp_path: Path) -> None:
    records = run_core_acceptance(tmp_path)

    assert tuple(record.acceptance_test for record in records) == (
        1,
        2,
        3,
        4,
        5,
        13,
        19,
        20,
    )
    assert all(record.passed for record in records)
    artifact_directory = tmp_path / "verification"
    assert {path.name for path in artifact_directory.glob("test_*.json")} == {
        "test_01.json",
        "test_02.json",
        "test_03.json",
        "test_04.json",
        "test_05.json",
        "test_13.json",
        "test_19.json",
        "test_20.json",
    }
    t1 = json.loads((artifact_directory / "test_01.json").read_text())
    ledger = t1["observed_value"]["ledger"]
    assert ledger[0]["transaction_id"].startswith("tx:ACCEPT01:main:")
    assert {row["unit"] for row in ledger if row["quantity"] == "water"} == {"kg"}
    t2 = json.loads((artifact_directory / "test_02.json").read_text())
    assert {
        row["unit"]
        for row in t2["observed_value"]["ledger"]
        if row["quantity"] == "alkalinity"
    } == {
        "mmol_c"
    }
    assert "water_mass_kg" in t1["observed_value"]["post_state"]["source"]
    assert "volume_l" in t1["observed_value"]["post_state"]["source"]

    t13 = json.loads((artifact_directory / "test_13.json").read_text())
    assert t13["observed_value"]["domain_policy"] == {
        **t13["oracle"]["domain_policy"]
    }
    assert t13["observed_value"]["domain_policy"]["model_id"] == (
        "core_v1.acceptance_13"
    )
    assert t13["observed_value"]["domain_policy"]["scope"] == (
        "numerical_oracle_not_almond_applicability"
    )

    t20 = json.loads((artifact_directory / "test_20.json").read_text())
    cases = t20["observed_value"]["case_manifest"]
    assert cases["counterexample_semantics"] == {
        "population": "frozen_manifest_cases",
        "selection": "first_in_manifest_order",
        "hypothesis_shrunk": False,
    }
    assert cases["counterexample"] is None
    assert "minimized_counterexample" not in cases
    assert set(cases["per_quantity_extrema"]["flow"]["global_relative_residual"]) == {
        "water",
        "na",
        "cl",
    }
    assert set(cases["per_quantity_extrema"]["ro"]["conservation_absolute_residual"]) == {
        "water",
        "na",
        "cl",
    }


def _empty(rows: tuple[object, ...]) -> tuple[object, ...]:
    return ()


def _delete(rows: tuple[object, ...]) -> tuple[object, ...]:
    return rows[:-1]


def _duplicate(rows: tuple[object, ...]) -> tuple[object, ...]:
    return rows + rows


def _halve(rows: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(replace(row, amount=row.amount * 0.5) for row in rows)


def _wrong_label(rows: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(
        replace(row, evidence_label=EvidenceLabel.SYNTHETIC_ONLY) for row in rows
    )


def _wrong_quantity(rows: tuple[object, ...]) -> tuple[object, ...]:
    row = rows[-1]
    return (*rows[:-1], replace(row, amount=row.amount + 0.125))


def _wrong_carrier(rows: tuple[object, ...]) -> tuple[object, ...]:
    changed = False
    result = []
    for row in rows:
        if not changed and row.carrier_volume_l is not None:
            result.append(replace(row, water_density_kg_l=row.water_density_kg_l * 1.001))
            changed = True
        else:
            result.append(row)
    return tuple(result)


def _split(rows: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(
        replace(
            row,
            transaction_id=row.transaction_id[:-12]
            + f"{(int(row.transaction_id[-12:]) + split_id + 100_000):012d}",
            amount=row.amount * 0.5,
            carrier_volume_l=(
                None
                if row.carrier_volume_l is None
                else row.carrier_volume_l * 0.5
            ),
        )
        for row in rows
        for split_id in (0, 1)
    )


def _redistribute(rows: tuple[object, ...]) -> tuple[object, ...]:
    transaction_ids = tuple(dict.fromkeys(row.transaction_id for row in rows))
    first, second = transaction_ids[:2]
    return tuple(
        replace(
            row,
            amount=row.amount
            * (
                0.5
                if row.transaction_id == first
                else 1.5
                if row.transaction_id == second
                else 1.0
            ),
            carrier_volume_l=(
                row.carrier_volume_l
                if row.carrier_volume_l is None
                or row.transaction_id not in {first, second}
                else row.carrier_volume_l
                * (0.5 if row.transaction_id == first else 1.5)
            ),
        )
        for row in rows
    )


def _wrong_entity_same_count(rows: tuple[object, ...]) -> tuple[object, ...]:
    for index, row in enumerate(rows):
        if row.entity is ConservedEntity.NA:
            replacement = replace(
                row,
                entity=ConservedEntity.K,
                unit=StockUnit.MMOL,
            )
            return (*rows[:index], replacement, *rows[index + 1 :])
    return rows[:-1]


def _duplicate_transaction_ids(rows: tuple[object, ...]) -> tuple[object, ...]:
    transaction_ids = tuple(dict.fromkeys(row.transaction_id for row in rows))
    first, second = transaction_ids[:2]
    return tuple(
        replace(row, transaction_id=first)
        if row.transaction_id == second
        else row
        for row in rows
    )


@pytest.mark.parametrize(
    "transform",
    [
        _empty,
        _delete,
        _duplicate,
        _halve,
        _wrong_label,
        _wrong_quantity,
        _wrong_carrier,
        _split,
        _redistribute,
        _wrong_entity_same_count,
        _duplicate_transaction_ids,
    ],
)
@pytest.mark.parametrize(
    "acceptance",
    [verification._acceptance_01, verification._acceptance_02, verification._acceptance_20],
)
def test_ledger_acceptances_reject_structural_and_metadata_adversaries(
    acceptance: object,
    transform: object,
) -> None:
    record = acceptance(ledger_transform=transform)  # type: ignore[operator]
    assert record.passed is False


def test_wrong_unit_is_rejected_before_a_ledger_can_self_authorize() -> None:
    fixture, _ = verification._fixture("ions_conservative.yaml")
    result = verification.step_state(
        verification._state(fixture),
        dt_hours=fixture["duration_hours"],
        cursor=verification._cursor(fixture),
        water_flows=(verification._water_flow(fixture),),
    )
    solute_row = next(
        row for row in result.ledger if row.entity is ConservedEntity.NA
    )
    with pytest.raises(Exception, match="unit"):
        # The typed shared contract prevents construction of an invalid-unit row.
        replace(solute_row, unit=StockUnit.KG)


def test_ledger_oracle_never_uses_observed_compartment_branches() -> None:
    fixture, _ = verification._fixture("water_one_day.yaml")
    oracle = verification._ledger_oracle(
        fixture["expected_ledger"],
        required_quantities=(ConservedEntity.WATER,),
        expected_compartments=("source", "target"),
    )
    corrupted = dict(oracle["audit"])
    residuals = dict(corrupted["compartment_relative_residuals"])
    del residuals["target"]
    corrupted["compartment_relative_residuals"] = residuals
    record = _record(
        observed_value=corrupted,
        oracle=oracle["audit"],
        tolerance=verification._tolerance_tree(oracle["audit"], 1e-10),
        comparison=verification._comparison_tree(oracle["audit"]),
    )
    assert record.passed is False


def test_manifest_runner_reports_first_frozen_failure_without_shrinking() -> None:
    def faulty_flow(case: object) -> object:
        return {"volumes_l": {"source": -1.0, "target": -1.0}, "stocks": {}}

    record = verification._acceptance_20(flow_case_model=faulty_flow)
    result = record.observed_value["case_manifest"]
    assert record.passed is False
    assert result["counterexample_semantics"]["hypothesis_shrunk"] is False
    assert result["counterexample"]["property_id"] == "flow"
    assert result["counterexample"]["case_id"] == "flow_seed_20260812_01"
    assert result["counterexample"]["input"]
    assert result["counterexample"]["failing_metrics"]


@pytest.mark.parametrize("model_name", ("flow", "ro", "blend"))
def test_manifest_runner_rejects_nonfinite_injected_model_output(
    model_name: str,
) -> None:
    def nonfinite_flow(case: object) -> object:
        output = verification._flow_case_default(case)  # type: ignore[arg-type]
        output["global_relative_residual"]["water"] = float("nan")
        return output

    def nonfinite_ro(case: object) -> object:
        output = verification._ro_case_default(case)  # type: ignore[arg-type]
        output["permeate"]["water_mass_kg"] = float("nan")
        return output

    def nonfinite_blend(case: object, chemistry: object) -> object:
        output = verification._blend_case_default(case, chemistry)  # type: ignore[arg-type]
        output["alkalinity_mmol_c_l"] = float("nan")
        return output

    keyword = {
        "flow": {"flow_case_model": nonfinite_flow},
        "ro": {"ro_case_model": nonfinite_ro},
        "blend": {"blend_case_model": nonfinite_blend},
    }[model_name]
    record = verification._acceptance_20(**keyword)
    result = record.observed_value["case_manifest"]

    assert record.passed is False
    assert result["counterexample"]["property_id"] == model_name
    assert result["counterexample"]["case_id"].endswith("_01")


def test_manifest_runner_rejects_boolean_before_numeric_arithmetic() -> None:
    def boolean_ro(case: object) -> object:
        output = verification._ro_case_default(case)  # type: ignore[arg-type]
        if case["id"] == "ro_seed_20260813_02":  # type: ignore[index]
            output["permeate"]["stocks"]["cl"] = False
        return output

    record = verification._acceptance_20(ro_case_model=boolean_ro)
    result = record.observed_value["case_manifest"]

    assert record.passed is False
    assert result["counterexample"]["case_id"] == "ro_seed_20260813_02"
    assert result["counterexample"]["failing_metrics"]["error_type"] == "ValueError"


def test_manifest_runner_turns_malformed_ro_output_into_frozen_counterexample() -> None:
    def malformed_ro(case: object) -> object:
        output = verification._ro_case_default(case)  # type: ignore[arg-type]
        output["feed"] = None
        return output

    record = verification._acceptance_20(ro_case_model=malformed_ro)
    result = record.observed_value["case_manifest"]

    assert record.passed is False
    assert result["counterexample"]["property_id"] == "ro"
    assert result["counterexample"]["failing_metrics"]["error_type"] == "ValueError"


@pytest.mark.parametrize(
    ("model_name", "branch"),
    (("flow", "source"), ("ro", "feed"), ("ro", "permeate")),
)
def test_manifest_runner_compares_explicit_volume_l_literals(
    model_name: str, branch: str
) -> None:
    def wrong_flow_volume(case: object) -> object:
        output = verification._flow_case_default(case)  # type: ignore[arg-type]
        output["post"][branch]["volume_l"] += 1.0
        return output

    def wrong_ro_volume(case: object) -> object:
        output = verification._ro_case_default(case)  # type: ignore[arg-type]
        output[branch]["volume_l"] += 1.0
        return output

    keyword = (
        {"flow_case_model": wrong_flow_volume}
        if model_name == "flow"
        else {"ro_case_model": wrong_ro_volume}
    )
    record = verification._acceptance_20(**keyword)
    result = record.observed_value["case_manifest"]

    assert record.passed is False
    assert result["counterexample"]["property_id"] == model_name
