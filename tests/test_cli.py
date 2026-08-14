from pathlib import Path
from typer.testing import CliRunner

from almondlab.cli import app


runner = CliRunner()


def test_public_cli_app_shows_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AlmondLab virtual-lab command line interface." in result.stdout
    for cmd in ("init", "validate", "design", "simulate", "analyze", "rank", "verify", "demo", "audit", "report"):
        assert cmd in result.stdout


def test_cli_demo_and_report(tmp_path: Path) -> None:
    demo_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--output", str(demo_dir)])
    assert result.exit_code == 0
    assert "SYNTHETIC — NOT BIOLOGICAL EVIDENCE" in result.stdout

    report_file = tmp_path / "report.md"
    result_report = runner.invoke(app, ["report", "--output", str(report_file)])
    assert result_report.exit_code == 0
    assert report_file.exists()
