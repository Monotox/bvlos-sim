"""Batch-specific CLI support helpers."""

from enum import StrEnum
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


class BatchOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"
    GEOJSON = "geojson"
    KML = "kml"
    CHECKLIST = "checklist"
    PROFILE = "profile"
    CSV = "csv"


_OUTPUT_EXTENSIONS: dict[OutputFormat | BatchOutputFormat, str] = {
    OutputFormat.MARKDOWN: ".md",
    OutputFormat.CHECKLIST: ".md",
    OutputFormat.PROFILE: ".md",
    OutputFormat.SUMMARY: ".txt",
    OutputFormat.GEOJSON: ".geojson",
    OutputFormat.KML: ".kml",
    BatchOutputFormat.CSV: ".csv",
}

_ROUTE_EXPORT_BUILDERS = {
    OutputFormat.GEOJSON: build_geojson_export,
    OutputFormat.KML: build_kml_export,
}


def _batch_exit_code(results: list[BatchRunResult]) -> int:
    summary = summarize_batch(results)
    if summary.error_count > 0:
        return 11  # INVALID_INPUT
    if summary.infeasible_count > 0:
        return 10  # INFEASIBLE
    return 0  # SUCCESS


def _batch_output_extension(output_format: OutputFormat | BatchOutputFormat) -> str:
    return _OUTPUT_EXTENSIONS.get(output_format, ".json")


def _batch_route_export(output_format: OutputFormat, result: BatchRunResult) -> str | None:
    builder = _ROUTE_EXPORT_BUILDERS.get(output_format)
    if builder is None or result.envelope is None or result.envelope.result is None:
        return None
    if output_format == OutputFormat.GEOJSON:
        return build_geojson_export(
            result.envelope.result,
            geofence_zones=result.geofences,
            landing_zones=result.landing_zones,
            obstacles=result.obstacles,
        )
    return builder(
        result.envelope.result,
        geofence_zones=result.geofences,
        landing_zones=result.landing_zones,
    )


def _render_batch_run_output(output_format: OutputFormat, result: BatchRunResult) -> str:
    route_export = _batch_route_export(output_format, result)
    if route_export is not None:
        return route_export
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
    "BatchOutputFormat",
    "OutputWriteError",
    "_batch_exit_code",
    "_batch_output_extension",
    "_render_batch_run_output",
    "write_batch_outputs",
]
