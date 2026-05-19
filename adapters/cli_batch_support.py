"""Batch-specific CLI support helpers."""

from pathlib import Path

from adapters.batch_support import BatchRunResult, summarize_batch
from adapters.cli_support import (
    OutputWriteError,
    _envelope_output_format,
    _render_output,
    _write_output,
)
from adapters.envelope import OutputFormat


def _batch_exit_code(results: list[BatchRunResult]) -> int:
    summary = summarize_batch(results)
    if summary.error_count > 0:
        return 11  # INVALID_INPUT
    if summary.infeasible_count > 0:
        return 10  # INFEASIBLE
    return 0  # SUCCESS


def _batch_output_extension(output_format: OutputFormat) -> str:
    if output_format == OutputFormat.MARKDOWN:
        return ".md"
    if output_format == OutputFormat.SUMMARY:
        return ".txt"
    return ".json"


def write_batch_outputs(
    *,
    output_dir: Path,
    output_format: OutputFormat,
    results: list[BatchRunResult],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_format = _envelope_output_format(output_format)
    extension = _batch_output_extension(rendered_format)
    for result in results:
        if result.envelope is None:
            continue
        _write_output(
            _render_output(rendered_format, result.envelope),
            output_dir / f"{result.id}{extension}",
        )


__all__ = [
    "OutputWriteError",
    "_batch_exit_code",
    "_batch_output_extension",
    "write_batch_outputs",
]
