import hashlib
import json
from pathlib import Path

import pytest

from almondlab import verification
from almondlab.contracts import EvidenceLabel
from almondlab.mass_balance import StepResult
from almondlab.treatment import ROResult
from almondlab.verification import (
    VerificationRecord,
    evaluate_run_stops,
    load_physical_stops,
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
    assert conservation_payload["comparison"]["minimum_state"] == "ge"
    assert conservation_payload["oracle"]["minimum_state"] == -1e-12
    assert conservation_payload["tolerance"]["minimum_state"] == 0.0

    chemistry_payload = json.loads((artifact_directory / "test_05.json").read_text())
    assert chemistry_payload["observed_value"]["sar"] == pytest.approx(5.773502692)
    assert chemistry_payload["oracle"]["sar"] == pytest.approx(5.773502692)
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
    below_minimum = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"volume_l": 0.09},
        physical_stops=stops,
    )
    exact_maximum = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"injury": 1.0},
        physical_stops=stops,
    )
    within_bounds = evaluate_run_stops(
        numerical_values={"state": 1.0},
        stocks={"na": 0.0},
        ledger_relative_residuals={"water": 0.0},
        physical_values={"volume_l": 10.0, "injury": 0.99},
        physical_stops=stops,
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

    with pytest.raises(ValueError, match="invalid record"):
        VerificationRecord(
            acceptance_test=13,
            fixture_sha256="b" * 64,
            observed_value=0.5,
            oracle=0.5,
            tolerance=1e-6,
            passed=True,
            code_version="unavailable:explicit-test-gate",
            evidence_label=EvidenceLabel.PHYSICS_CONSTRAINED,
            validity="invalid",
            reason_code="NONFINITE_STATE",
        )
