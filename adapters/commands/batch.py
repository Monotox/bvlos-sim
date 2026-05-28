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
from adapters.cli_batch_support import BatchOutputFormat, _batch_exit_code, write_batch_outputs
from adapters.cli_support import OutputWriteError, _write_output
from adapters.envelope import OutputFormat
from adapters.io import InputLoadError, load_mission, load_vehicle


BatchStdoutRenderer = Callable[[list[BatchRunResult]], str]

_BATCH_STDOUT_RENDERERS: dict[BatchOutputFormat, BatchStdoutRenderer] = {
    BatchOutputFormat.CSV: render_batch_csv,
}
_BATCH_FILE_OUTPUT_FORMATS = frozenset(
    output_format for output_format in BatchOutputFormat if output_format != BatchOutputFormat.CSV
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


def _validate_batch_manifest(manifest: Path) -> None:
    batch_manifest = load_batch_manifest(manifest)
    typer.echo(f"batch: {manifest.name}: OK ({len(batch_manifest.runs)} runs)")
    for run in batch_manifest.runs:
        load_mission(run.mission)
        typer.echo(f"  mission: {run.mission.name}: OK")
        load_vehicle(run.vehicle)
        typer.echo(f"  vehicle: {run.vehicle.name}: OK")


def batch(
    manifest: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Directory for per-run output files. Required when --format is not csv or summary."),
    format: BatchOutputFormat = typer.Option(
        BatchOutputFormat.SUMMARY,
        "--format",
        help="Stdout format. Use csv for spreadsheet import. Use --output-dir with json/markdown/geojson/kml/checklist/profile to write per-run files.",
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate the manifest and all referenced mission and vehicle files "
            "against their schemas and exit without running estimates. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
) -> None:
    """Run batch mission estimates from a batch.v1 manifest file."""

    try:
        if validate_only:
            _validate_batch_manifest(manifest)
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
        if output_dir is not None and format not in _BATCH_FILE_OUTPUT_FORMATS:
            typer.echo(
                f"Warning: --output-dir is ignored when --format {format} is used "
                "(csv writes to stdout only).",
                err=True,
            )
        batch_manifest = load_batch_manifest(manifest)
        results = run_batch_manifest(batch_manifest)
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
