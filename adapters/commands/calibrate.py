"""Calibration profile fitting command."""

from pathlib import Path

import typer
from pydantic import ValidationError

import adapters.cli as cli
from adapters.calibration import CalibrationInput, fit_calibration_profile
from adapters.calibration_markdown import render_calibration_markdown
from adapters.canonical_json import render_canonical_json
from adapters.cli_support import OutputWriteError, _write_output
from adapters.flight_log import load_flight_trace
from adapters.io import InputLoadError, load_vehicle
from adapters.phase_segmentation import segment_trace
from adapters.version import tool_version


def calibrate(
    vehicle: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to the base vehicle profile YAML file.",
    ),
    traces: list[Path] = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="One or more flight-trace.v1 JSON files (from flight-log ingestion).",
    ),
    calibration_id: str | None = typer.Option(
        None,
        "--calibration-id",
        help="Stable calibration identifier. Defaults to <vehicle_id>-calibration.",
    ),
    format: cli.DocumentOutputFormat = typer.Option(
        cli.DocumentOutputFormat.MARKDOWN,
        "--format",
        help="Output format: markdown report, or json for the calibration-profile.v1 envelope.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
) -> None:
    """Fit a calibration profile from a base vehicle and one or more flight traces."""

    try:
        vehicle_model, _vehicle_document = load_vehicle(vehicle)

        inputs: list[CalibrationInput] = []
        for trace_path in traces:
            normalized_trace, _trace_document = load_flight_trace(trace_path)
            segments = segment_trace(normalized_trace)
            inputs.append(CalibrationInput(trace=normalized_trace, segments=segments))

        profile = fit_calibration_profile(
            vehicle=vehicle_model,
            inputs=inputs,
            calibration_id=calibration_id or f"{vehicle_model.vehicle_id}-calibration",
            tool_version=tool_version(),
        )

        if format == cli.DocumentOutputFormat.JSON:
            rendered = render_canonical_json(profile.model_dump(mode="json"))
        else:
            rendered = render_calibration_markdown(profile)
        _write_output(rendered, output)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="calibrate",
            code=cli.CliExitCode.INVALID_INPUT,
            details={"input_name": exc.input_name, "stage": str(exc.stage)},
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        cli._exit_with_cli_error(
            f"calibration_id: {first['msg']}",
            command="calibrate",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError:
        cli._exit_with_cli_error(
            "Failed to write calibration output.",
            command="calibrate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
