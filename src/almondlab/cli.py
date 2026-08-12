"""Command-line entry point for AlmondLab."""

import typer


app = typer.Typer(help="AlmondLab virtual-lab command line interface.")


@app.callback()
def main() -> None:
    """AlmondLab virtual-lab command line interface."""
