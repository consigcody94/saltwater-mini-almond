import hashlib
import json
from dataclasses import replace
from importlib import resources
from pathlib import Path

import pytest

from almondlab import verification
from almondlab.contracts import EvidenceLabel
from almondlab.contracts import ConservedEntity
from almondlab.mass_balance import LedgerEntry, StepResult
from almondlab.treatment import ROResult
from almondlab.verification import (
    VerificationRecord,
    evaluate_run_stops,
    load_conservation_case_manifest,
    load_threshold_policy,
    load_verification_policy,
    load_physical_stops,
    run_core_acceptance,
    write_verification_record,
)


def test_core_acceptance_writes_only_owned_records_to_run_directory(tmp_path: Path) -> None:
    fixture = resources.files("almondlab.resources").joinpath(
        "fixtures/perfect_na_exclusion.yaml"
    )

    records = run_core_acceptance(tmp_path)

    assert [record.acceptance_test for record in records] == [1, 2, 3, 4, 5, 13, 19, 20]
    artifact_directory = tmp_path / "verification"
    assert sorted(path.name for path in artifact_directory.glob("*.json")) == [
        "test_01.json", "test_02.json", "test_03.json", "test_04.json",
        "test_05.json", "test_13.json", "test_19.json", "test_20.json",
    ]
    payload = json.loads((artifact_directory / "test_13.json").read_text())
    assert payload["fixture_sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert payload["observed_value"] == pytest.approx(
        {"fresh_l_day": 0.888212, "saline_l_day": 0.455696, "ratio": 0.513049}
    )
    assert payload["oracle"] == pytest.approx(
        {"fresh_l_day": 0.888212, "saline_l_day": 0.455696, "ratio": 0.513049}
    )
    assert payload["tolerance"] == pytest.approx(1e-6)

    ec_payload = json.loads((artifact_directory / "test_19.json").read_text())
    assert ec_payload["observed_value"]["records_reached_analysis"] == 0
    assert [case["code"] for case in ec_payload["observed_value"]["cases"]] == [
        "EC_TYPE_MISMATCH"
    ] * 6

    stop_payload = json.loads((artifact_directory / "test_03.json").read_text())
    assert stop_payload["validity"] == "valid"
    assert stop_payload["censored"] is True
    assert stop_payload["reason_code"] == "PHYSICAL_STOP_CONCENTRATION_MMOL_L_MAXIMUM"
    assert stop_payload["evidence_label"] == "synthetic_only"

    conservation_payload = json.loads((artifact_directory / "test_20.json").read_text())
    assert conservation_payload["observed_value"]["water_residual"] <= 1e-10
    assert conservation_payload["observed_value"]["registered_entities"] == 12
    assert set(conservation_payload["observed_value"]["entities"]) == {
        "water", "na", "cl", "ca", "mg", "k", "total_b", "n", "p", "s",
        "dissolved_inorganic_carbon", "alkalinity",
    }
    assert set(conservation_payload["fixture_sha256s"]) >= {
        "all_conserved_entities.yaml", "ions_conservative.yaml", "chemistry_handcheck.yaml",
    }
    assert conservation_payload["observed_value"]["transfer"]["volumes_l"] == {
        "source": pytest.approx(80.0),
        "receiving": pytest.approx(20.0),
    }
    assert conservation_payload["oracle"]["transfer"]["volumes_l"] == {
        "source": 80.0,
        "receiving": 20.0,
    }
    assert conservation_payload["observed_value"]["transfer"]["stocks_mmol"]["source"]["na"] == pytest.approx(160.0)
    assert conservation_payload["observed_value"]["transfer"]["stocks_mmol"]["receiving"]["na"] == pytest.approx(40.0)
    assert conservation_payload["observed_value"]["ro"]["volumes_l"] == {
        "feed": 100.0,
        "permeate": 60.0,
        "concentrate": 40.0,
    }
    assert conservation_payload["observed_value"]["ro"]["inputs"]["recovery"] == 0.60
    assert conservation_payload["observed_value"]["ro"]["inputs"]["rejection"]["na"] == 0.90
    assert conservation_payload["observed_value"]["ro"]["stocks_mmol"]["feed"]["na"] == 200.0
    assert conservation_payload["observed_value"]["ro"]["stocks_mmol"]["permeate"]["na"] == pytest.approx(12.0)
    assert conservation_payload["observed_value"]["ro"]["stocks_mmol"]["concentrate"]["na"] == pytest.approx(188.0)
    assert conservation_payload["observed_value"]["ions_anchor"]["post_quantities"]["source"]["water"] == pytest.approx(80.0)
    assert conservation_payload["observed_value"]["ions_anchor"]["post_quantities"]["source"]["total_b"] == pytest.approx(0.8)
    assert conservation_payload["observed_value"]["ions_anchor"]["ledger_audit"]["valid"] is True
    assert conservation_payload["oracle"]["ions_anchor"]["post_quantities"]["receiving"]["alkalinity"] == 7.0
    assert conservation_payload["comparison"]["minimum_state"] == "ge"
    assert conservation_payload["oracle"]["minimum_state"] == -1e-12
    assert conservation_payload["tolerance"]["minimum_state"] == 0.0
    assert conservation_payload["passed"] is True
    assert conservation_payload["observed_value"]["case_manifest"]["counts"] == {
        "blend": 2,
        "flow": 2,
        "ro": 2,
    }
    assert conservation_payload["observed_value"]["case_manifest"]["minimized_counterexample"] is None
    assert "conservation_case_manifest.yaml" in conservation_payload["fixture_sha256s"]
    property_extrema = conservation_payload["observed_value"]["case_manifest"][
        "per_quantity_extrema"
    ]
    assert set(property_extrema["flow"]["global_relative_residual"]) == {
        "water",
        "na",
        "cl",
    }
    assert set(property_extrema["ro"]["conservation_absolute_residual"]) == {
        "water",
        "na",
        "cl",
    }
    assert set(property_extrema["blend"]["literal_absolute_error"]) == {
        "alkalinity_mmol_c_l",
        "na_mmol_l",
        "cl_mmol_l",
        "ca_mmol_l",
        "mg_mmol_l",
        "k_mmol_l",
        "total_b_mmol_l",
        "sulfate_mmol_l",
        "bicarbonate_mmol_l",
        "nitrate_mmol_l",
        "phosphate_mmol_l",
    }

    expected_auxiliary = {
        "auxiliary/test_01_ledger.json",
        "auxiliary/test_02_ledger.json",
        "auxiliary/test_03_trajectory.json",
        "auxiliary/test_04_trajectory.json",
        "auxiliary/test_20_ledger.json",
    }
    observed_auxiliary = {
        path.relative_to(artifact_directory).as_posix()
        for path in (artifact_directory / "auxiliary").glob("*.json")
    }
    assert observed_auxiliary == expected_auxiliary
    records_by_test = {record.acceptance_test: record for record in records}
    for test_number, artifact_name in (
        (1, "auxiliary/test_01_ledger.json"),
        (2, "auxiliary/test_02_ledger.json"),
        (3, "auxiliary/test_03_trajectory.json"),
        (4, "auxiliary/test_04_trajectory.json"),
        (20, "auxiliary/test_20_ledger.json"),
    ):
        artifact = artifact_directory / artifact_name
        assert records_by_test[test_number].auxiliary_artifacts_sha256s[artifact_name] == hashlib.sha256(
            artifact.read_bytes()
        ).hexdigest()

    t3_trajectory = json.loads(
        (artifact_directory / "auxiliary/test_03_trajectory.json").read_text()
    )
    assert t3_trajectory[0] == {"concentration_mmol_l": 2.0, "time_hours": 0.0}
    assert t3_trajectory[-1]["time_hours"] == 10.0
    assert t3_trajectory[-1]["concentration_mmol_l"] == pytest.approx(4.0)
    assert len(t3_trajectory) == 21
    assert stop_payload["observed_value"]["stop_time_hours"] == 10.0
    assert stop_payload["oracle"]["stop_time_hours"] == 10.0
    assert stop_payload["comparison"]["stop_time_hours"] == "rel_le"
    assert stop_payload["tolerance"]["stop_time_hours"] == 1e-6

    t4_trajectory = json.loads(
        (artifact_directory / "auxiliary/test_04_trajectory.json").read_text()
    )
    assert len(t4_trajectory) == 13
    assert t4_trajectory[0]["time_hours"] == 0.0
    assert t4_trajectory[-1]["time_hours"] == 60.0

    t2_payload = json.loads((artifact_directory / "test_02.json").read_text())
    assert set(t2_payload["observed_value"]["post_state"]["source"]) == {
        entity.value for entity in ConservedEntity if entity is not ConservedEntity.WATER
    }
    assert t2_payload["observed_value"]["post_state"]["source"]["total_b"] == pytest.approx(0.8)
    assert t2_payload["oracle"]["post_state"]["receiving"]["alkalinity"] == 7.0

    for record in records:
        provenance = record.code_provenance
        assert set(provenance) == {"package_version", "git_sha", "git_dirty", "unavailable"}
        assert provenance["package_version"] == "0.1.0"

    chemistry_payload = json.loads((artifact_directory / "test_05.json").read_text())
    assert chemistry_payload["observed_value"]["sar"]["value"] == pytest.approx(5.773502692)
    assert chemistry_payload["oracle"]["sar"]["value"] == pytest.approx(5.773502692)
    assert chemistry_payload["observed_value"]["sar"]["inputs_mmol_c_l"] == {
        "na": 10.0,
        "ca": 4.0,
        "mg": 2.0,
    }
    assert chemistry_payload["observed_value"]["sar"][
        "denominator_mmol_c_l"
    ] == pytest.approx(3.0**0.5)
    assert chemistry_payload["observed_value"]["sar"]["value"] == pytest.approx(
        5.773502691896258
    )
    assert {
        key: chemistry_payload["oracle"]["charge_balance"][key]
        for key in (
            "cations_mmol_c_l",
            "anions_mmol_c_l",
            "numerator_mmol_c_l",
            "denominator_mmol_c_l",
            "percent",
        )
    } == {
        "cations_mmol_c_l": 17.0,
        "anions_mmol_c_l": 15.0,
        "numerator_mmol_c_l": 2.0,
        "denominator_mmol_c_l": 32.0,
        "percent": 6.25,
    }
    assert chemistry_payload["observed_value"]["blend"]["provenance"] == {
        "data_origin": "model_derived",
        "evidence_label": "synthetic_only",
        "source_data_origins": ["synthetic", "synthetic"],
        "source_evidence_labels": ["synthetic_only", "synthetic_only"],
        "measurement_id": "acceptance-blend",
        "measurement_data_origin": "synthetic",
        "measurement_evidence_label": "synthetic_only",
    }
    assert conservation_payload["observed_value"]["blend"]["provenance"] == (
        chemistry_payload["observed_value"]["blend"]["provenance"]
    )
    assert payload["passed"] is True
    assert payload["evidence_label"] == "physics_constrained"
    assert payload["code_version"]


@pytest.mark.parametrize(
    ("numerical_values", "stocks", "ledger_relative_residuals"),
    [
        ({"state": float("nan")}, {"na": 0.0}, {"water": 0.0}),
        ({"state": 0.0}, {"na": float("inf")}, {"water": 0.0}),
        ({"state": 0.0}, {"na": 0.0}, {"water": float("-inf")}),
    ],
)
def test_numerical_invalidity_rejects_nonfinite_values_everywhere(
    numerical_values: dict[str, float], stocks: dict[str, float], ledger_relative_residuals: dict[str, float]
) -> None:
    numerical = evaluate_run_stops(
        numerical_values=numerical_values,
        stocks=stocks,
        ledger_relative_residuals=ledger_relative_residuals,
        physical_values={},
        physical_stops={},
    )

    assert numerical.valid is False
    assert numerical.censored is False
    assert numerical.reason_code.startswith("NONFINITE_")


def test_configured_minimum_and_maximum_stops_are_loaded_and_censor_at_boundary(
    tmp_path: Path,
) -> None:
    config = Path(__file__).parents[1] / "configs" / "thresholds.yaml"
    stops = load_physical_stops(config)
    policy = load_threshold_policy(config)
    below_minimum = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"volume_l": 0.09},
        physical_stops=stops,
        applicable_stop_ids=("volume_l",),
        numerical_policy=policy.numerical_stops,
    )
    exact_maximum = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"injury": 1.0},
        physical_stops=stops,
        applicable_stop_ids=("injury",),
        numerical_policy=policy.numerical_stops,
    )
    within_bounds = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"volume_l": 10.0, "injury": 0.99},
        physical_stops=stops,
        applicable_stop_ids=("volume_l", "injury"),
        numerical_policy=policy.numerical_stops,
    )
    mutated = tmp_path / "thresholds.yaml"
    mutated.write_text(config.read_text().replace("synthetic_only", "empirically_calibrated", 1))
    with pytest.raises(ValueError, match="evidence_label"):
        load_physical_stops(mutated)

    assert below_minimum.reason_code == "PHYSICAL_STOP_VOLUME_L_MINIMUM"
    assert below_minimum.evidence_label is EvidenceLabel.SYNTHETIC_ONLY
    assert exact_maximum.reason_code == "PHYSICAL_STOP_INJURY_MAXIMUM"
    assert exact_maximum.evidence_label is EvidenceLabel.SYNTHETIC_ONLY
    assert within_bounds == type(within_bounds)(True, False, None, None)

    missing_applicable = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={},
        physical_stops=stops,
        applicable_stop_ids=("volume_l",),
        numerical_policy=policy.numerical_stops,
    )
    assert missing_applicable.valid is False
    assert missing_applicable.reason_code == "MISSING_APPLICABLE_PHYSICAL_VALUE"


def test_default_runtime_policies_are_strict_hashed_and_packaged(tmp_path: Path) -> None:
    thresholds = load_threshold_policy()
    verification_policy = load_verification_policy()

    assert len(thresholds.sha256) == 64
    assert thresholds.numerical_stops.require_finite_state is True
    assert thresholds.numerical_stops.minimum_stock == -1e-12
    assert thresholds.numerical_stops.maximum_relative_ledger_residual == 1e-10
    assert len(verification_policy.sha256) == 64
    assert verification_policy.core_acceptance_tests == (1, 2, 3, 4, 5, 13, 19, 20)
    assert verification_policy.tolerances[1]["absolute"] == 1e-10
    assert verification_policy.tolerances[3]["relative"] == 1e-6
    assert verification_policy.tolerances[4] == {
        "terminal_absolute": 1e-6,
        "trajectory_relative": 1e-5,
    }
    assert verification_policy.tolerances[5] == {
        "mass_blend_absolute": 1e-10,
        "sar_absolute": 1e-9,
    }
    assert verification_policy.tolerances[13]["absolute"] == 1e-6
    assert verification_policy.tolerances[20]["absolute"] == 1e-10

    packaged = resources.files("almondlab.resources")
    repo = Path(__file__).parents[1]
    assert packaged.joinpath("configs/thresholds.yaml").read_bytes() == (
        repo / "configs" / "thresholds.yaml"
    ).read_bytes()
    assert packaged.joinpath("configs/verification.yaml").read_bytes() == (
        repo / "configs" / "verification.yaml"
    ).read_bytes()

    malformed = tmp_path / "thresholds.yaml"
    malformed.write_text("schema_version: '1.0'\nphysical_stops: {}\n")
    with pytest.raises(ValueError, match="numerical_stops"):
        load_threshold_policy(malformed)

    previous = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        portable_records = run_core_acceptance(tmp_path / "portable-run")
    finally:
        os.chdir(previous)
    assert all(record.passed for record in portable_records)


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("require_finite_state: true", "require_finite_state: false"),
        ("minimum_stock: -1.0e-12", "minimum_stock: -2.0e-12"),
        (
            "maximum_relative_ledger_residual: 1.0e-10",
            "maximum_relative_ledger_residual: 2.0e-10",
        ),
    ],
)
def test_schema_1_threshold_policy_cannot_weaken_locked_numerical_stops(
    tmp_path: Path, original: str, replacement: str
) -> None:
    source = (Path(__file__).parents[1] / "configs" / "thresholds.yaml").read_text()
    malformed = tmp_path / "thresholds.yaml"
    malformed.write_text(source.replace(original, replacement))

    with pytest.raises(ValueError, match="locked"):
        load_threshold_policy(malformed)


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("ro_seed_20260813_01", "ro_seed_20260812_01", "seed"),
        ("ro_seed_20260813_02", "ro_seed_20260813_01", "unique"),
        ("source_volume_l: 12.0", 'source_volume_l: "12.0"', "numeric"),
        ("recovery: 0.25", "recovery: 0.0", "RO numeric domain"),
        ("rate_l_per_hour: 2.0", "rate_l_per_hour: 12.0", "exceeds"),
    ],
)
def test_conservation_manifest_loader_rejects_false_or_malformed_provenance(
    tmp_path: Path, original: str, replacement: str, message: str
) -> None:
    contents = (
        resources.files("almondlab.resources")
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_text()
    )
    malformed = tmp_path / "conservation_case_manifest.yaml"
    malformed.write_text(contents.replace(original, replacement))

    with pytest.raises(ValueError, match=message):
        load_conservation_case_manifest(malformed)


def test_test20_rejects_a_noop_transfer_even_when_ledger_residual_is_zero() -> None:
    def no_op_step(state: object, flows: object, external: object, duration: float) -> StepResult:
        return StepResult(state=state, ledger=(), substeps=0)  # type: ignore[arg-type]

    record = verification._acceptance_20(stepper=no_op_step)

    assert record.passed is False
    assert record.observed_value["transfer"]["volumes_l"] == {
        "source": 100.0,
        "receiving": 0.0,
    }
    assert record.oracle["transfer"]["volumes_l"] == {
        "source": 80.0,
        "receiving": 20.0,
    }


@pytest.mark.parametrize("permeate_volume", [50.0, -10.0])
def test_test20_rejects_conserving_but_wrong_ro_branches(permeate_volume: float) -> None:
    def wrong_ro(
        feed_volume_l: float,
        feed_stock_mmol: dict[str, float],
        recovery: float,
        rejection: dict[str, float],
    ) -> ROResult:
        fraction = permeate_volume / feed_volume_l
        permeate = {entity: stock * fraction for entity, stock in feed_stock_mmol.items()}
        concentrate = {
            entity: stock - permeate[entity]
            for entity, stock in feed_stock_mmol.items()
        }
        return ROResult(
            feed_volume_l=feed_volume_l,
            permeate_volume_l=permeate_volume,
            concentrate_volume_l=feed_volume_l - permeate_volume,
            feed_stock_mmol=dict(feed_stock_mmol),
            permeate_stock_mmol=permeate,
            concentrate_stock_mmol=concentrate,
            rejection=dict(rejection),
        )

    record = verification._acceptance_20(ro_model=wrong_ro)

    assert record.passed is False
    assert record.observed_value["ro"]["water_conserved"] is True
    if permeate_volume < 0.0:
        assert record.observed_value["ro"]["branches_within_bounds"] is False


def _empty_ledger(rows: tuple[LedgerEntry, ...]) -> tuple[LedgerEntry, ...]:
    return ()


def _delete_ledger_row(rows: tuple[LedgerEntry, ...]) -> tuple[LedgerEntry, ...]:
    return rows[:-1]


def _duplicate_ledger(rows: tuple[LedgerEntry, ...]) -> tuple[LedgerEntry, ...]:
    return rows + rows


def _consistently_corrupt_ledger(rows: tuple[LedgerEntry, ...]) -> tuple[LedgerEntry, ...]:
    return tuple(replace(row, amount=row.amount * 0.5) for row in rows)


def _split_every_transaction(rows: tuple[LedgerEntry, ...]) -> tuple[LedgerEntry, ...]:
    return tuple(
        replace(
            row,
            transaction_id=f"{row.transaction_id}:split-{split_id}",
            amount=row.amount * 0.5,
        )
        for row in rows
        for split_id in ("a", "b")
    )


def _redistribute_between_transactions(
    rows: tuple[LedgerEntry, ...],
) -> tuple[LedgerEntry, ...]:
    transaction_ids = tuple(dict.fromkeys(row.transaction_id for row in rows))
    first, second = transaction_ids[:2]
    return tuple(
        replace(
            row,
            amount=row.amount
            * (0.5 if row.transaction_id == first else 1.5 if row.transaction_id == second else 1.0),
        )
        for row in rows
    )


@pytest.mark.parametrize(
    "acceptance",
    [verification._acceptance_01, verification._acceptance_02, verification._acceptance_20],
    ids=["test-01", "test-02", "test-20"],
)
@pytest.mark.parametrize(
    "ledger_transform",
    [
        _empty_ledger,
        _delete_ledger_row,
        _duplicate_ledger,
        _consistently_corrupt_ledger,
        _split_every_transaction,
        _redistribute_between_transactions,
    ],
    ids=[
        "empty",
        "deleted-row",
        "duplicated",
        "consistent-corruption",
        "split-transactions",
        "redistributed-transactions",
    ],
)
def test_acceptance_rejects_correct_snapshot_without_complete_paired_ledger(
    acceptance: object,
    ledger_transform: object,
) -> None:
    record = acceptance(ledger_transform=ledger_transform)  # type: ignore[operator]

    assert record.passed is False
    ledger_branch = (
        record.observed_value["ledger_audit"]
        if "ledger_audit" in record.observed_value
        else record.observed_value["transfer_ledger"]
    )
    assert ledger_branch["valid"] is False


def test_verification_record_derives_passed_and_rejects_inconsistent_claim() -> None:
    derived = VerificationRecord(
        acceptance_test=13,
        fixture_sha256="a" * 64,
        observed_value={"value": 0.5000001, "minimum": 0.0},
        oracle={"value": 0.5, "minimum": -1e-12},
        tolerance={"value": 1e-6, "minimum": 0.0},
        comparison={"value": "abs_le", "minimum": "ge"},
        code_version="unavailable:explicit-test-gate",
        code_provenance={
            "package_version": None,
            "git_sha": None,
            "git_dirty": None,
            "unavailable": ["package_version", "git_sha", "git_dirty"],
        },
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    assert derived.passed is True

    with pytest.raises(ValueError, match="inconsistent"):
        VerificationRecord(
            acceptance_test=13,
            fixture_sha256="a" * 64,
            observed_value=1.0,
            oracle=0.0,
            tolerance=0.0,
            comparison="abs_le",
            passed=True,
            code_version="unavailable:explicit-test-gate",
            code_provenance={
                "package_version": None,
                "git_sha": None,
                "git_dirty": None,
                "unavailable": ["package_version", "git_sha", "git_dirty"],
            },
            evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        )

    type_wrong = VerificationRecord(
        acceptance_test=13,
        fixture_sha256="a" * 64,
        observed_value=1,
        oracle=True,
        tolerance=0.0,
        comparison="eq",
        code_version="unavailable:explicit-test-gate",
        code_provenance={
            "package_version": None,
            "git_sha": None,
            "git_dirty": None,
            "unavailable": ["package_version", "git_sha", "git_dirty"],
        },
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    assert type_wrong.passed is False


def test_writer_validates_before_creating_target_and_record_is_immutable(tmp_path: Path) -> None:
    target = tmp_path / "verification" / "record.json"
    invalid = VerificationRecord(
        acceptance_test=13,
        fixture_sha256="not-a-digest",
        observed_value=0.5,
        oracle=0.5,
        tolerance=1e-6,
        code_version="unavailable:explicit-test-gate",
        code_provenance={"package_version": None, "git_sha": None, "git_dirty": None, "unavailable": ["package_version", "git_sha", "git_dirty"]},
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )

    with pytest.raises(ValueError):
        write_verification_record(target, invalid)
    assert not target.exists()

    valid = VerificationRecord(
        acceptance_test=13,
        fixture_sha256="a" * 64,
        observed_value=0.5,
        oracle=0.5,
        tolerance=1e-6,
        code_version="unavailable:explicit-test-gate",
        code_provenance={"package_version": None, "git_sha": None, "git_dirty": None, "unavailable": ["package_version", "git_sha", "git_dirty"]},
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    with pytest.raises((AttributeError, TypeError)):
        valid.passed = False  # type: ignore[misc]
    write_verification_record(target, valid)
    assert json.loads(target.read_text())["acceptance_test"] == 13

    invalid_run = VerificationRecord(
        acceptance_test=13,
        fixture_sha256="b" * 64,
        observed_value=0.5,
        oracle=0.5,
        tolerance=1e-6,
        code_version="unavailable:explicit-test-gate",
        code_provenance={"package_version": None, "git_sha": None, "git_dirty": None, "unavailable": ["package_version", "git_sha", "git_dirty"]},
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
        validity="invalid",
        reason_code="NONFINITE_STATE",
    )
    assert invalid_run.passed is False
