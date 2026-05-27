"""Batch estimate command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.batch_io import load_batch_manifest
from adapters.batch_support import render_batch_csv, render_batch_table, run_batch_manifest
from adapters.cli_batch_support import BatchOutputFormat, _batch_exit_code, write_batch_outputs
from adapters.cli_support import OutputWriteError, _write_output
from adapters.envelope import OutputFormat
from adapters.io import InputLoadError


def batch(
    manifest: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    format: BatchOutputFormat = typer.Option(BatchOutputFormat.SUMMARY, "--format"),
) -> None:
    """Run batch mission estimates from a batch.v1 manifest file."""

    try:
        batch_manifest = load_batch_manifest(manifest)
        results = run_batch_manifest(batch_manifest)
        for result in results:
            if result.error_message is None:
                continue
            typer.echo(f"Warning: run {result.id}: {result.error_message}", err=True)
        if format == BatchOutputFormat.CSV:
            _write_output(render_batch_csv(results), None)
        else:
            if output_dir is not None:
                write_batch_outputs(
                    output_dir=output_dir,
                    output_format=OutputFormat(format),
                    results=results,
                )
            _write_output(render_batch_table(results), None)
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
