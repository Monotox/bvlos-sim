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
from adapters.geojson_export import build_geojson_export
from adapters.kml_export import build_kml_export
from adapters.profile_markdown import render_profile_markdown


def _batch_exit_code(results: list[BatchRunResult]) -> int:
    summary = summarize_batch(results)
    if summary.error_count > 0:
        return 11  # INVALID_INPUT
    if summary.infeasible_count > 0:
        return 10  # INFEASIBLE
    return 0  # SUCCESS


def _batch_output_extension(output_format: OutputFormat) -> str:
    if output_format in (OutputFormat.MARKDOWN, OutputFormat.CHECKLIST, OutputFormat.PROFILE):
        return ".md"
    if output_format == OutputFormat.SUMMARY:
        return ".txt"
    if output_format == OutputFormat.GEOJSON:
        return ".geojson"
    if output_format == OutputFormat.KML:
        return ".kml"
    if str(output_format) == "csv":
        return ".csv"
    return ".json"


def _render_batch_run_output(output_format: OutputFormat, result: BatchRunResult) -> str:
    if output_format == OutputFormat.GEOJSON and result.envelope is not None and result.envelope.result is not None:
        return build_geojson_export(
            result.envelope.result,
            geofence_zones=result.geofences,
            landing_zones=result.landing_zones,
        )
    if output_format == OutputFormat.KML and result.envelope is not None and result.envelope.result is not None:
        return build_kml_export(
            result.envelope.result,
            geofence_zones=result.geofences,
            landing_zones=result.landing_zones,
        )
    if output_format == OutputFormat.PROFILE and result.envelope is not None:
        return render_profile_markdown(result.envelope, terrain_provider=None)
    rendered_format = _envelope_output_format(output_format)
    return _render_output(rendered_format, result.envelope, mission_id=result.id)


def write_batch_outputs(
    *,
    output_dir: Path,
    output_format: OutputFormat,
    results: list[BatchRunResult],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = _batch_output_extension(output_format)
    for result in results:
        if result.envelope is None:
            continue
        _write_output(
            _render_batch_run_output(output_format, result),
            output_dir / f"{result.id}{extension}",
        )


__all__ = [
    "OutputWriteError",
    "_batch_exit_code",
    "_batch_output_extension",
    "_render_batch_run_output",
    "write_batch_outputs",
]
