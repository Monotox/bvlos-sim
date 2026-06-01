"""Batch estimate command."""

from collections.abc import Callable
from pathlib import Path

import typer

import adapters.cli as cli
from adapters.batch_io import load_batch_manifest
from adapters.batch_support import (
    BatchRunResult,
    render_batch_csv,
    render_batch_table,
    run_batch_manifest,
)
from adapters.cli_batch_support import (
    BatchOutputFormat,
    _batch_exit_code,
    write_batch_outputs,
)
from adapters.cli_support import OutputWriteError, _write_output
from adapters.envelope import OutputFormat
from adapters.io import InputLoadError, load_mission, load_vehicle
from adapters.preflight import (
    check_file,
    emit_preflight,
    is_json_format,
    mission_asset_checks,
)
from adapters.progress import progress_reporter


BatchStdoutRenderer = Callable[[list[BatchRunResult]], str]

_BATCH_STDOUT_RENDERERS: dict[BatchOutputFormat, BatchStdoutRenderer] = {
    BatchOutputFormat.CSV: render_batch_csv,
}
_BATCH_FILE_OUTPUT_FORMATS = frozenset(
    output_format
    for output_format in BatchOutputFormat
    if output_format != BatchOutputFormat.CSV
)


def _emit_batch_warnings(results: list[BatchRunResult]) -> None:
    for result in results:
        if result.error_message is None:
            continue
        typer.echo(f"Warning: run {result.id}: {result.error_message}", err=True)


def _render_batch_stdout(
    output_format: BatchOutputFormat,
    results: list[BatchRunResult],
) -> str:
    renderer = _BATCH_STDOUT_RENDERERS.get(output_format, render_batch_table)
    return renderer(results)


def _write_batch_file_outputs(
    *,
    output_dir: Path | None,
    output_format: BatchOutputFormat,
    results: list[BatchRunResult],
) -> None:
    if output_dir is None or output_format not in _BATCH_FILE_OUTPUT_FORMATS:
        return
    write_batch_outputs(
        output_dir=output_dir,
        output_format=OutputFormat(output_format),
        results=results,
    )


def _run_batch_preflight(*, manifest: Path, as_json: bool) -> None:
    """Validate the manifest and every run's mission, vehicle, and assets."""
    files = []
    text_lines = []

    manifest_check, manifest_loaded = check_file(
        role="batch",
        path_str=manifest.name,
        loader=lambda: load_batch_manifest(manifest),
    )
    files.append(manifest_check)
    if manifest_check.ok and manifest_loaded is not None:
        text_lines.append(
            f"batch: {manifest.name}: OK ({len(manifest_loaded.runs)} runs)"
        )
        for run in manifest_loaded.runs:
            mission_check, mission_result = check_file(
                role="mission",
                path_str=run.mission.name,
                loader=lambda r=run: load_mission(r.mission),
            )
            files.append(mission_check)
            if mission_check.ok:
                text_lines.append(f"  mission: {run.mission.name}: OK")
            vehicle_check, _ = check_file(
                role="vehicle",
                path_str=run.vehicle.name,
                loader=lambda r=run: load_vehicle(r.vehicle),
            )
            files.append(vehicle_check)
            if vehicle_check.ok:
                text_lines.append(f"  vehicle: {run.vehicle.name}: OK")
            if mission_result is not None:
                files.extend(
                    mission_asset_checks(mission_result[0], mission_path=run.mission)
                )

    emit_preflight(
        command="batch", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def batch(
    manifest: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Directory for per-run output files. Required when --format is not csv or summary.",
    ),
    format: BatchOutputFormat = typer.Option(
        BatchOutputFormat.SUMMARY,
        "--format",
        help="Stdout format. Use csv for spreadsheet import. Use --output-dir with json/markdown/geojson/kml/checklist/profile to write per-run files.",
    ),
    progress_format: cli.ProgressFormat = typer.Option(
        cli.ProgressFormat.NONE,
        "--progress-format",
        help="Emit machine-readable progress. Use jsonl for one JSON record per run on stderr.",
    ),
    progress_file: Path | None = typer.Option(
        None,
        "--progress-file",
        help="Write JSONL progress to this file instead of stderr (implies --progress-format jsonl).",
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate the manifest and all referenced mission and vehicle files "
            "(and referenced assets) against their schemas and exit without "
            "running estimates. Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Run batch mission estimates from a batch.v1 manifest file."""

    if validate_only:
        _run_batch_preflight(manifest=manifest, as_json=is_json_format(validate_format))

    try:
        if output_dir is not None and format not in _BATCH_FILE_OUTPUT_FORMATS:
            typer.echo(
                f"Warning: --output-dir is ignored when --format {format} is used "
                "(csv writes to stdout only).",
                err=True,
            )
        batch_manifest = load_batch_manifest(manifest)
        with progress_reporter(
            "batch",
            enabled=progress_format is cli.ProgressFormat.JSONL,
            progress_file=progress_file,
        ) as reporter:
            results = run_batch_manifest(batch_manifest, progress=reporter)
        _emit_batch_warnings(results)
        _write_batch_file_outputs(
            output_dir=output_dir,
            output_format=format,
            results=results,
        )
        _write_output(_render_batch_stdout(format, results), None)
        raise typer.Exit(code=_batch_exit_code(results))
    except InputLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
