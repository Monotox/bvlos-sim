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
from adapters.preflight import check_file, emit_preflight, is_json_format
from adapters.version import tool_version


def _run_calibrate_preflight(
    *, vehicle: Path, traces: list[Path], as_json: bool
) -> None:
    """Validate the base vehicle and each flight trace without fitting."""
    files = []
    text_lines = []

    vehicle_check, _ = check_file(
        role="vehicle", path_str=vehicle.name, loader=lambda: load_vehicle(vehicle)
    )
    files.append(vehicle_check)
    if vehicle_check.ok:
        text_lines.append(f"vehicle: {vehicle.name}: OK")

    for trace_path in traces:
        trace_check, _ = check_file(
            role="flight-trace",
            path_str=trace_path.name,
            loader=lambda p=trace_path: load_flight_trace(p),
        )
        files.append(trace_check)
        if trace_check.ok:
            text_lines.append(f"flight-trace: {trace_path.name}: OK")

    emit_preflight(
        command="calibrate", files=files, as_json=as_json, text_ok_lines=text_lines
    )


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
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate the base vehicle and flight-trace files against their schemas "
            "and exit without fitting. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Fit a calibration profile from a base vehicle and one or more flight traces."""

    if validate_only:
        _run_calibrate_preflight(
            vehicle=vehicle, traces=traces, as_json=is_json_format(validate_format)
        )

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
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="calibrate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
