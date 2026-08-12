from typer.testing import CliRunner

from almondlab.cli import app


def test_public_cli_app_shows_help() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "AlmondLab virtual-lab command line interface." in result.stdout
