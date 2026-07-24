"""Leaf CLI contract: exit codes, output formats, and error helpers.

Command modules import this instead of ``adapters.cli`` so that importing a
single command does not pull in the command registry that imports every
command back. ``adapters.cli`` re-exports everything here.
"""

import json
from enum import IntEnum, StrEnum
from typing import NoReturn

import typer

from adapters.cli_batch_support import BatchOutputFormat
from adapters.envelope import OutputFormat
from estimator import try_estimate_mission_distance_time
from estimator.execution.monte_carlo import run_monte_carlo
from estimator.execution.propagator import run_stochastic_propagation


class CliExitCode(IntEnum):
    SUCCESS = 0
    INFEASIBLE = 10
    INVALID_INPUT = 11
    UNSUPPORTED = 12
    INTERNAL_ERROR = 13
    CANCELLED = 14


class ScenarioExitCode(IntEnum):
    PASSED = 0
    FAILED = 10
    INVALID_INPUT = 11
    INTERNAL_ERROR = 13


class VerifyExitCode(IntEnum):
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


class ProgressFormat(StrEnum):
    NONE = "none"
    JSONL = "jsonl"


class PreflightFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


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
    "BatterySizingOutputFormat",
    "BatchOutputFormat",
    "CliExitCode",
    "DocumentOutputFormat",
    "PreflightFormat",
    "ProgressFormat",
    "ScenarioExitCode",
    "SoraOutputFormat",
    "SummaryOutputFormat",
    "VerifyExitCode",
    "run_monte_carlo",
    "run_stochastic_propagation",
    "try_estimate_mission_distance_time",
]


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


