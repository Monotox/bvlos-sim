"""Typer CLI adapter for estimator execution."""

import json
from enum import IntEnum, StrEnum
from typing import NoReturn

import typer

from adapters.cli_batch_support import BatchOutputFormat
from adapters.envelope import OutputFormat
from adapters.version import tool_version
from estimator import try_estimate_mission_distance_time
from estimator.execution.monte_carlo import run_monte_carlo
from estimator.execution.propagator import run_stochastic_propagation

app = typer.Typer(name="bvlos-sim", add_completion=False, no_args_is_help=True)


class CliExitCode(IntEnum):
    SUCCESS = 0
    INFEASIBLE = 10
    INVALID_INPUT = 11
    UNSUPPORTED = 12
    INTERNAL_ERROR = 13


class ScenarioExitCode(IntEnum):
    PASSED = 0
    FAILED = 10
    INVALID_INPUT = 11
    INTERNAL_ERROR = 13


class DocumentOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class SummaryOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"


class BatterySizingOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"


class SoraOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


_DOCUMENT_OUTPUT_FORMATS: dict[DocumentOutputFormat, OutputFormat] = {
    DocumentOutputFormat.JSON: OutputFormat.JSON,
    DocumentOutputFormat.MARKDOWN: OutputFormat.MARKDOWN,
}

_SUMMARY_OUTPUT_FORMATS: dict[SummaryOutputFormat, OutputFormat] = {
    SummaryOutputFormat.JSON: OutputFormat.JSON,
    SummaryOutputFormat.MARKDOWN: OutputFormat.MARKDOWN,
    SummaryOutputFormat.SUMMARY: OutputFormat.SUMMARY,
}


__all__ = [
    "app",
    "BatterySizingOutputFormat",
    "BatchOutputFormat",
    "CliExitCode",
    "DocumentOutputFormat",
    "ScenarioExitCode",
    "SoraOutputFormat",
    "SummaryOutputFormat",
    "run_monte_carlo",
    "run_stochastic_propagation",
    "try_estimate_mission_distance_time",
]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bvlos-sim {tool_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """BVLOS simulator command group."""


def _render_cli_error(
    message: str,
    command: str,
    *,
    details: dict | None = None,
) -> str:
    payload: dict = {"command": command, "status": "error", "message": message}
    if details:
        payload["details"] = details
    return json.dumps(payload, indent=2) + "\n"


def _exit_with_cli_error(
    message: str,
    *,
    command: str,
    code: CliExitCode,
    details: dict | None = None,
) -> NoReturn:
    typer.echo(_render_cli_error(message, command, details=details), nl=False)
    raise typer.Exit(code=int(code))


def _document_output_format(output_format: DocumentOutputFormat) -> OutputFormat:
    return _DOCUMENT_OUTPUT_FORMATS[output_format]


def _summary_output_format(output_format: SummaryOutputFormat) -> OutputFormat:
    return _SUMMARY_OUTPUT_FORMATS[output_format]


def _register_commands() -> None:
    from adapters.commands.batch import batch
    from adapters.commands.compare import compare
    from adapters.commands.convert import convert
    from adapters.commands.estimate import estimate
    from adapters.commands.export import export
    from adapters.commands.propagate import propagate
    from adapters.commands.sample import sample
    from adapters.commands.scenario import scenario
    from adapters.commands.sitl import sitl
    from adapters.commands.size_battery import size_battery
    from adapters.commands.sora import sora

    app.command()(convert)
    app.command()(estimate)
    app.command()(export)
    app.command("size-battery")(size_battery)
    app.command()(batch)
    app.command()(compare)
    app.command()(scenario)
    app.command()(sample)
    app.command()(propagate)
    app.command()(sitl)
    app.command()(sora)


_register_commands()
