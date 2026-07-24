"""Controller flight-log ingestion command."""

from pathlib import Path

import typer
from pydantic import ValidationError

import bvlos_sim.adapters.cli_contract as cli
from bvlos_sim.adapters.canonical_json import render_canonical_json
from bvlos_sim.adapters.cli_support import (
    NO_CLOBBER_OPTION,
    OutputWriteError,
    _refuse_output_clobber,
    _write_output,
)
from bvlos_sim.adapters.flight_log import (
    DEFAULT_MAX_FLIGHT_LOG_BYTES,
    FlightLogIngestionError,
    ingest_flight_log,
)
from bvlos_sim.adapters.io import InputLoadError, load_mission, load_vehicle
from bvlos_sim.schemas.flight_log import FlightTraceMissionRef


def ingest_log(
    log: Path = typer.Argument(
        ...,
        resolve_path=True,
        help="ArduPilot DataFlash .log/.bin or PX4 .ulg file.",
    ),
    trace_id: str = typer.Option(
        ...,
        "--trace-id",
        help="Stable identifier to embed in the flight-trace artifact.",
    ),
    mission: Path | None = typer.Option(
        None,
        "--mission",
        resolve_path=True,
        help="Paired mission file; requires --vehicle and embeds its SHA-256.",
    ),
    vehicle: Path | None = typer.Option(
        None,
        "--vehicle",
        resolve_path=True,
        help="Paired vehicle file; requires --mission and embeds its SHA-256.",
    ),
    max_size_mib: int = typer.Option(
        DEFAULT_MAX_FLIGHT_LOG_BYTES // (1024 * 1024),
        "--max-size-mib",
        min=1,
        help=(
            "Reject larger logs before parsing; the process-safety ceiling is 64 MiB."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write flight-trace.v1 JSON to a file instead of stdout.",
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
) -> None:
    """Normalize a controller log into a content-addressed flight trace."""
    _refuse_output_clobber(output, no_clobber=no_clobber, command="ingest-log")
    try:
        _reject_output_collision(output, log, mission, vehicle)
        mission_ref = _mission_ref(mission, vehicle)
        trace = ingest_flight_log(
            log,
            trace_id=trace_id,
            mission_ref=mission_ref,
            max_bytes=max_size_mib * 1024 * 1024,
        )
        _write_output(
            render_canonical_json(trace.model_dump(mode="json")),
            output,
        )
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except (
        FlightLogIngestionError,
        InputLoadError,
        ValidationError,
        ValueError,
    ) as exc:
        details = (
            {"reason": exc.reason, "path": str(exc.path)}
            if isinstance(exc, FlightLogIngestionError)
            else None
        )
        cli._exit_with_cli_error(
            str(exc),
            command="ingest-log",
            code=cli.CliExitCode.INVALID_INPUT,
            details=details,
        )
    except OutputWriteError:
        cli._exit_with_cli_error(
            "Failed to write flight-trace output.",
            command="ingest-log",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="ingest-log",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )


def _reject_output_collision(
    output: Path | None,
    *inputs: Path | None,
) -> None:
    if output is None:
        return
    target = output.resolve(strict=False)
    for input_path in inputs:
        if input_path is not None and target == input_path.resolve(strict=False):
            raise ValueError(
                f"--output {output} would overwrite input file {input_path}"
            )


def _mission_ref(
    mission: Path | None,
    vehicle: Path | None,
) -> FlightTraceMissionRef | None:
    if (mission is None) != (vehicle is None):
        raise ValueError("--mission and --vehicle must be supplied together")
    if mission is None or vehicle is None:
        return None
    _mission_model, mission_document = load_mission(mission)
    _vehicle_model, vehicle_document = load_vehicle(vehicle)
    return FlightTraceMissionRef(
        mission_file=str(mission),
        mission_sha256=mission_document.sha256,
        vehicle_file=str(vehicle),
        vehicle_sha256=vehicle_document.sha256,
    )


__all__ = ["ingest_log"]
