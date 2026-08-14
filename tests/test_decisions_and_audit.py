from __future__ import annotations

import json
import sys
from pathlib import Path
from typer.testing import CliRunner
import pytest

from almondlab.contracts import EvidenceLabel
from almondlab.decisions import (
    CandidateDiscoveryScore,
    DiscoveryDecisionResult,
    compute_advancement_score,
    evaluate_discovery_candidates,
)
from almondlab.paper1_contracts import ScientificLabel
from almondlab.analyze import analyze_discovery_cohort
from almondlab.report import (
    SYNTHETIC_WATERMARK,
    ArtifactInventory,
    prepare_artifact,
    generate_markdown_summary_report,
)
from almondlab.audit import audit_run_directory
from almondlab.cli import app

sys.path.insert(0, str(Path(__file__).parent))
from test_simulate import _simulation_config  # type: ignore


runner = CliRunner()


def test_compute_advancement_score_min_formula() -> None:
    # A[k] = min(pH1, pH2_good, pH3), never multiplied
    score = compute_advancement_score(p_h1=0.95, p_h2_good=0.96, p_h3=0.91)
    assert score == pytest.approx(0.91, abs=1e-5)


def test_evaluate_discovery_candidates_leader_relative_ties_and_capping() -> None:
    # candidate probabilities
    probs = {
        "C1_SOS1": {"p_h1": 0.96, "p_h2_good": 0.98, "p_h2_bad": 0.02, "p_h3": 0.95},  # A = 0.95
        "C2_HKT1": {"p_h1": 0.95, "p_h2_good": 0.99, "p_h2_bad": 0.01, "p_h3": 0.94},  # A = 0.94 (diff <= 0.02 -> tie)
        "C3_NHX1": {"p_h1": 0.92, "p_h2_good": 0.95, "p_h2_bad": 0.05, "p_h3": 0.90},  # A = 0.90 (diff > 0.02)
        "C4_SDH":  {"p_h1": 0.85, "p_h2_good": 0.95, "p_h2_bad": 0.05, "p_h3": 0.88},  # Inconclusive (p_h1 < 0.90)
        "C5_GOLS": {"p_h1": 0.93, "p_h2_good": 0.97, "p_h2_bad": 0.03, "p_h3": 0.92},  # A = 0.92
        "C6_SUB":  {"p_h1": 0.91, "p_h2_good": 0.96, "p_h2_bad": 0.04, "p_h3": 0.91},  # A = 0.91
    }

    result = evaluate_discovery_candidates(probs)
    assert isinstance(result, DiscoveryDecisionResult)
    assert len(result.finalist_candidate_ids) <= 4  # Cap = 4

    c1_score = result.scores["C1_SOS1"]
    c2_score = result.scores["C2_HKT1"]
    c4_score = result.scores["C4_SDH"]

    assert c1_score.scientific_label == ScientificLabel.CO_LEADING
    assert c2_score.scientific_label == ScientificLabel.CO_LEADING
    assert c4_score.scientific_label == ScientificLabel.INCONCLUSIVE
    assert c1_score.allocated_confirmation_slot is True
    assert c2_score.allocated_confirmation_slot is True


def test_analyze_discovery_cohort() -> None:
    sim_cfg = _simulation_config()
    res = analyze_discovery_cohort(sim_cfg)
    assert res.cohort_id == "discovery"
    assert res.converged is True
    assert len(res.summaries) == 6
    assert res.decision is not None


def test_evidence_label_and_watermarking_enforcement(tmp_path: Path) -> None:
    meta = prepare_artifact(tmp_path / "test.csv", evidence_label=EvidenceLabel.SYNTHETIC_ONLY)
    assert meta.required_watermark == SYNTHETIC_WATERMARK

    inv = ArtifactInventory(
        run_id="RUN-100",
        artifacts=(meta,),
        manifest_sha256="abc12345",
    )
    report_text = generate_markdown_summary_report(inv, executive_summary="Automated pipeline test.")
    assert SYNTHETIC_WATERMARK in report_text
    assert "RUN-100" in report_text


def test_audit_run_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_sample"
    run_dir.mkdir()
    data_file = run_dir / "results.csv"
    data_file.write_text("cand,score\nC1,0.95\n", encoding="utf-8")

    from almondlab.provenance import sha256_file
    file_hash = sha256_file(data_file)
    manifest = {
        "run_id": "RUN-001",
        "evidence_label": "SYNTHETIC_ONLY",
        "artifacts": [
            {
                "path": "results.csv",
                "sha256": file_hash,
                "evidence_label": "SYNTHETIC_ONLY",
                "domain_version": "1.0",
            }
        ]
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = audit_run_directory(run_dir)
    assert report.passed is True
    assert report.checked_artifact_count == 1
    assert len(report.findings) == 0


def test_cli_subcommands(tmp_path: Path) -> None:
    # test init
    init_dir = tmp_path / "init_proj"
    res_init = runner.invoke(app, ["init", "--output", str(init_dir)])
    assert res_init.exit_code == 0
    assert init_dir.exists()

    # test validate
    cfg_file = tmp_path / "sample_config.yaml"
    cfg_file.write_text("name: test_run\nvolume: 10.0\n", encoding="utf-8")
    res_val = runner.invoke(app, ["validate", "--config", str(cfg_file)])
    assert res_val.exit_code == 0
    assert "Validated config" in res_val.stdout

    # test design
    res_des = runner.invoke(app, ["design", "--seed", "20260812"])
    assert res_des.exit_code == 0

    # test simulate
    res_sim = runner.invoke(app, ["simulate"])
    assert res_sim.exit_code == 0

    # test analyze
    res_ana = runner.invoke(app, ["analyze", "--run-dir", str(init_dir)])
    assert res_ana.exit_code == 0

    # test rank
    res_rank = runner.invoke(app, ["rank"])
    assert res_rank.exit_code == 0

    # test verify
    res_ver = runner.invoke(app, ["verify"])
    assert res_ver.exit_code == 0

    # test audit on valid directory
    run_dir = tmp_path / "audited_run"
    run_dir.mkdir()
    res_aud = runner.invoke(app, ["audit", "--run-dir", str(run_dir)])
    assert res_aud.exit_code == 5  # No manifest -> Exit 5 with findings
