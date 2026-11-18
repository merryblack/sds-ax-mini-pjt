"""CLI entry point: `a11y-investigator analyze` (SERVICE_MVP.md 2.2). Implemented in T16."""
from __future__ import annotations

import typer

app = typer.Typer(help="Evidence-based React accessibility analysis and improvement agent.")


@app.callback()
def main() -> None:
    """A11y Investigator."""


@app.command()
def analyze(
    file: str | None = typer.Option(None, "--file", help="React component file (.jsx / .tsx)."),
    project: str | None = typer.Option(None, "--project", help="Project ID for policy lookup."),
    level: str = typer.Option("AA", "--level", help="Target WCAG level: A, AA, AAA."),
    json_output: bool = typer.Option(False, "--json", help="Print DiagnosisReport JSON."),
) -> None:
    """Analyze a React component for accessibility issues."""
    typer.echo("Not implemented yet (T16).", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
