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
    _batch_output_extension,
    write_batch_outputs,
)
from adapters.cli_support import OutputWriteError, _write_output
from adapters.envelope import OutputFormat
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.preflight import (
    check_file,
    emit_preflight,
    is_json_format,
    mission_asset_checks,
)
from adapters.progress import progress_reporter
from schemas.batch import BatchManifest
from schemas.mission import MissionPlan


BatchStdoutRenderer = Callable[[list[BatchRunResult]], str]

_BATCH_STDOUT_RENDERERS: dict[BatchOutputFormat, BatchStdoutRenderer] = {
    BatchOutputFormat.CSV: render_batch_csv,
}
_BATCH_FILE_OUTPUT_FORMATS = frozenset(
    output_format
    for output_format in BatchOutputFormat
    if output_format != BatchOutputFormat.CSV
)


def _batch_protected_input_paths(
    manifest: Path,
    batch_manifest: BatchManifest,
) -> tuple[tuple[Path, ...], dict[Path, tuple[MissionPlan, InputDocument]]]:
    """Resolve every file a batch run may read before opening sidecars.

    Missions are parsed here anyway to enumerate their asset paths, so the
    parsed models are returned for the run loop to reuse instead of parsing
    every mission a second time.
    """
    protected = [manifest]
    preloaded: dict[Path, tuple[MissionPlan, InputDocument]] = {}
    for run in batch_manifest.runs:
        protected.extend((run.mission, run.vehicle))
        mission_key = run.mission.resolve(strict=False)
        if mission_key not in preloaded:
            preloaded[mission_key] = load_mission(run.mission)
        mission_model, _mission_document = preloaded[mission_key]
        for asset_path in mission_model.assets.model_dump().values():
            if not isinstance(asset_path, Path):
                continue
            protected.append(
                asset_path
                if asset_path.is_absolute()
                else run.mission.parent / asset_path
            )
    return tuple(protected), preloaded


def _validate_batch_output_paths(
    *,
    output_dir: Path | None,
    output_format: BatchOutputFormat,
    batch_manifest: BatchManifest,
    protected_paths: tuple[Path, ...],
) -> None:
    if output_dir is None or output_format not in _BATCH_FILE_OUTPUT_FORMATS:
        return
    inputs = {path.resolve(strict=False) for path in protected_paths}
    extension = _batch_output_extension(output_format)
    expected_names = {f"{run.id}{extension}" for run in batch_manifest.runs}
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"Batch output directory is not a directory: {output_dir}")
        unexpected = sorted(
            child.name
            for child in output_dir.iterdir()
            if child.name not in expected_names
        )
        if unexpected:
            names = ", ".join(unexpected[:5])
            suffix = " ..." if len(unexpected) > 5 else ""
            raise ValueError(
                "Batch output directory contains files not produced by this run: "
                f"{names}{suffix}; use a new or matching output directory"
            )
    for run in batch_manifest.runs:
        target = (output_dir / f"{run.id}{extension}").resolve(strict=False)
        if target in inputs:
            raise ValueError(
                f"Batch output {target} would overwrite a manifest input or asset"
            )
        if target.exists() and not target.is_file():
            raise ValueError(f"Batch output target is not a regular file: {target}")


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
    manifest: Path = typer.Argument(..., resolve_path=True),
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
    engineering_only: bool = typer.Option(
        False,
        "--engineering-only",
        help=(
            "Treat computationally feasible runs as successful even when "
            "operational evidence is missing. Default batch status is fail-closed."
        ),
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
        protected_paths, preloaded_missions = _batch_protected_input_paths(
            manifest, batch_manifest
        )
        _validate_batch_output_paths(
            output_dir=output_dir,
            output_format=format,
            batch_manifest=batch_manifest,
            protected_paths=protected_paths,
        )
        if (
            progress_file is not None
            and output_dir is not None
            and progress_file.resolve(strict=False).is_relative_to(
                output_dir.resolve(strict=False)
            )
        ):
            raise ValueError(
                "--progress-file must be outside --output-dir to prevent artifact collisions"
            )
        with progress_reporter(
            "batch",
            enabled=progress_format is cli.ProgressFormat.JSONL,
            progress_file=progress_file,
            protected_paths=protected_paths,
        ) as reporter:
            results = run_batch_manifest(
                batch_manifest,
                progress=reporter,
                engineering_only=engineering_only,
                preloaded_missions=preloaded_missions,
            )
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
    except ValueError as exc:
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
