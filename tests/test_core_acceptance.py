import hashlib
import json
from pathlib import Path

import pytest

from almondlab.contracts import EvidenceLabel
from almondlab.verification import (
    VerificationRecord,
    evaluate_run_stops,
    run_core_acceptance,
    write_verification_record,
)


def test_core_acceptance_writes_only_owned_records_to_run_directory(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "perfect_na_exclusion.yaml"

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
    assert ec_payload["observed_value"] == {
        "records_reached_analysis": 0,
        "rejected_substitutions": 6,
    }

    stop_payload = json.loads((artifact_directory / "test_03.json").read_text())
    assert stop_payload["validity"] == "valid"
    assert stop_payload["censored"] is True
    assert stop_payload["reason_code"] == "PHYSICAL_STOP_CONCENTRATION_MMOL_L"

    conservation_payload = json.loads((artifact_directory / "test_20.json").read_text())
    assert conservation_payload["observed_value"]["water_residual"] <= 1e-10
    assert conservation_payload["observed_value"]["registered_entities"] == 12
    assert payload["passed"] is True
    assert payload["evidence_label"] == "physics_constrained"
    assert payload["code_version"]


def test_numerical_invalidity_and_physical_censoring_are_distinct() -> None:
    numerical = evaluate_run_stops(
        numerical_values={"state": float("nan")},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={},
        physical_maxima={},
    )
    physical = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"injury": 1.1},
        physical_maxima={"injury": 1.0},
    )

    assert numerical.valid is False
    assert numerical.censored is False
    assert numerical.reason_code == "NONFINITE_STATE"
    assert physical.valid is True
    assert physical.censored is True
    assert physical.reason_code == "PHYSICAL_STOP_INJURY"


def test_writer_validates_before_creating_target_and_record_is_immutable(tmp_path: Path) -> None:
    target = tmp_path / "verification" / "record.json"
    invalid = VerificationRecord(
        acceptance_test=13,
        fixture_sha256="not-a-digest",
        observed_value=0.5,
        oracle=0.5,
        tolerance=1e-6,
        passed=True,
        code_version="unavailable:explicit-test-gate",
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
        passed=True,
        code_version="unavailable:explicit-test-gate",
        evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
    )
    with pytest.raises((AttributeError, TypeError)):
        valid.passed = False  # type: ignore[misc]
    write_verification_record(target, valid)
    assert json.loads(target.read_text())["acceptance_test"] == 13
