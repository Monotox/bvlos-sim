"""Deterministic parameter fitting from observed flight data.

Derives a narrow set of vehicle performance parameters from normalized flight
traces and their phase segmentations, emitting a versioned
``CalibrationProfile`` that layers on a base vehicle. The fit is pure and
deterministic: the same base vehicle and the same ordered set of
trace/segmentation pairs always produce the same artifact.

Core estimator formulas are untouched — this module only summarizes observed
data into parameters. Parameters with no supporting samples are reported in
``notes``, never fabricated. Energy coefficients are out of scope (Ticket 083).
"""

from __future__ import annotations

import math
import json
from dataclasses import dataclass
from hashlib import sha256

from adapters.phase_segmentation import CLIMB_VERT_RATE_MPS, LOITER_SPEED_MPS
from schemas.calibration import (
    CALIBRATION_PROFILE_SCHEMA_VERSION,
    CalibratedParameter,
    CalibratedParameterName,
    CalibrationProfile,
    CalibrationProvenance,
)
from schemas.flight_log import FlightTraceRecord, NormalizedFlightTrace
from schemas.phase_segment import PhaseSegment, PhaseSegmentResult, TracePhase
from schemas.vehicle import VehicleProfile

# Estimator leg-phase keys (the bridge populated by segmentation) the fitter reads.
_TRANSIT_PHASE = "transit"
_LOITER_DWELL_PHASE = "loiter_dwell"

# Trace phases that carry vertical motion. Climb/descent have no estimator
# leg-phase, so the fitter selects them by TracePhase rather than by the bridge.
_CLIMB_PHASES = frozenset({TracePhase.TAKEOFF, TracePhase.CLIMB})
_DESCENT_PHASES = frozenset({TracePhase.DESCENT, TracePhase.LANDING})


@dataclass(frozen=True)
class CalibrationInput:
    """One observed flight: a normalized trace and its phase segmentation."""

    trace: NormalizedFlightTrace
    segments: PhaseSegmentResult


@dataclass(frozen=True)
class _SampleStats:
    """Summary statistics over an ordered list of observed samples."""

    count: int
    mean: float
    low: float
    high: float
    spread: float

    @classmethod
    def of(cls, samples: list[float]) -> _SampleStats | None:
        if not samples:
            return None
        mean = sum(samples) / len(samples)
        variance = sum((value - mean) ** 2 for value in samples) / len(samples)
        return cls(
            count=len(samples),
            mean=mean,
            low=min(samples),
            high=max(samples),
            spread=math.sqrt(variance),
        )


def fit_calibration_profile(
    *,
    vehicle: VehicleProfile,
    inputs: list[CalibrationInput],
    calibration_id: str,
    tool_version: str,
    validation_report_ids: list[str] | None = None,
) -> CalibrationProfile:
    """Fit a calibration profile from a base vehicle and observed flights.

    Raises ValueError if any input's segmentation describes a different trace
    than its paired trace (mirrors the validation trace-id guard).
    """
    for item in inputs:
        if item.segments.trace_id != item.trace.trace_id:
            raise ValueError(
                f"segmentation trace_id ({item.segments.trace_id}) does not match "
                f"trace_id ({item.trace.trace_id})"
            )

    trace_ids = sorted({item.trace.trace_id for item in inputs})
    dataset_version = _dataset_version(inputs)

    notes: list[str] = []
    parameters: list[CalibratedParameter] = []
    for fit in (
        _fit_cruise_speed,
        _fit_climb_rate,
        _fit_descent_rate,
        _fit_station_keep_authority,
    ):
        parameter = fit(inputs, dataset_version, notes)
        if parameter is not None:
            parameters.append(parameter)

    parameters.sort(key=lambda record: record.parameter.value)

    return CalibrationProfile(
        schema_version=CALIBRATION_PROFILE_SCHEMA_VERSION,
        calibration_id=calibration_id,
        base_vehicle_id=vehicle.vehicle_id,
        provenance=CalibrationProvenance(
            tool_version=tool_version,
            calibration_dataset_version=dataset_version,
            source_trace_ids=trace_ids,
            validation_report_ids=sorted(validation_report_ids or []),
        ),
        parameters=parameters,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Per-parameter fitters
# ---------------------------------------------------------------------------


def _fit_cruise_speed(
    inputs: list[CalibrationInput],
    dataset_version: str,
    notes: list[str],
) -> CalibratedParameter | None:
    true_airspeeds: list[float] = []
    winds: list[float] = []
    for item in inputs:
        for record in _phase_records(item, _TRANSIT_PHASE):
            true_airspeed = _true_airspeed(record)
            if true_airspeed is None:
                continue
            true_airspeeds.append(true_airspeed)
            wind = _wind_speed(record)
            if wind is not None:
                winds.append(wind)

    stats = _SampleStats.of(true_airspeeds)
    if stats is None:
        notes.append(
            "cruise_speed_mps not fit: transit records require groundspeed, "
            "ground course, and both east/north wind components to derive true airspeed."
        )
        return None

    conditions: list[str] = []
    if winds:
        conditions.append(f"observed wind speed up to {max(winds):.2f} m/s")
    return CalibratedParameter(
        parameter=CalibratedParameterName.CRUISE_SPEED_MPS,
        fitted_value=stats.mean,
        unit="m/s",
        sample_count=stats.count,
        confidence_low=stats.low,
        confidence_high=stats.high,
        spread=stats.spread,
        calibration_dataset_version=dataset_version,
        applicable_conditions=conditions,
        derivation=(
            "mean wind-corrected true airspeed derived from ground-velocity "
            "and wind vectors over transit-phase trace records"
        ),
    )


def _fit_climb_rate(
    inputs: list[CalibrationInput],
    dataset_version: str,
    notes: list[str],
) -> CalibratedParameter | None:
    rates: list[float] = []
    altitudes: list[float] = []
    for item in inputs:
        item_rates, item_alts = _vertical_rate_samples(
            item, _CLIMB_PHASES, climbing=True
        )
        rates.extend(item_rates)
        altitudes.extend(item_alts)

    stats = _SampleStats.of(rates)
    if stats is None:
        notes.append(
            "climb_rate_mps not fit: no climbing records "
            f"(vertical rate >= {CLIMB_VERT_RATE_MPS} m/s) in takeoff/climb segments."
        )
        return None

    return CalibratedParameter(
        parameter=CalibratedParameterName.CLIMB_RATE_MPS,
        fitted_value=stats.mean,
        unit="m/s",
        sample_count=stats.count,
        confidence_low=stats.low,
        confidence_high=stats.high,
        spread=stats.spread,
        calibration_dataset_version=dataset_version,
        applicable_conditions=[_altitude_band(altitudes)],
        derivation="mean positive vertical rate over takeoff/climb-phase records",
    )


def _fit_descent_rate(
    inputs: list[CalibrationInput],
    dataset_version: str,
    notes: list[str],
) -> CalibratedParameter | None:
    rates: list[float] = []
    altitudes: list[float] = []
    for item in inputs:
        item_rates, item_alts = _vertical_rate_samples(
            item, _DESCENT_PHASES, climbing=False
        )
        rates.extend(item_rates)
        altitudes.extend(item_alts)

    stats = _SampleStats.of(rates)
    if stats is None:
        notes.append(
            "descent_rate_mps not fit: no descending records "
            f"(vertical rate <= -{CLIMB_VERT_RATE_MPS} m/s) in descent/landing segments."
        )
        return None

    return CalibratedParameter(
        parameter=CalibratedParameterName.DESCENT_RATE_MPS,
        fitted_value=stats.mean,
        unit="m/s",
        sample_count=stats.count,
        confidence_low=stats.low,
        confidence_high=stats.high,
        spread=stats.spread,
        calibration_dataset_version=dataset_version,
        applicable_conditions=[_altitude_band(altitudes)],
        derivation="mean descent rate (positive magnitude) over descent/landing-phase records",
    )


def _fit_station_keep_authority(
    inputs: list[CalibrationInput],
    dataset_version: str,
    notes: list[str],
) -> CalibratedParameter | None:
    winds: list[float] = []
    for item in inputs:
        for record in _phase_records(item, _LOITER_DWELL_PHASE):
            if record.groundspeed_mps is not None and record.groundspeed_mps >= (
                LOITER_SPEED_MPS
            ):
                continue
            wind = _wind_speed(record)
            if wind is not None:
                winds.append(wind)

    stats = _SampleStats.of(winds)
    if stats is None:
        notes.append(
            "max_station_keep_wind_mps not fit: no loiter-dwell records holding "
            "position with a wind estimate."
        )
        return None

    # Station-keep authority is the strongest wind the vehicle was observed to
    # hold against, so the fitted value is the demonstrated maximum, not the mean.
    return CalibratedParameter(
        parameter=CalibratedParameterName.MAX_STATION_KEEP_WIND_MPS,
        fitted_value=stats.high,
        unit="m/s",
        sample_count=stats.count,
        confidence_low=stats.low,
        confidence_high=stats.high,
        spread=stats.spread,
        calibration_dataset_version=dataset_version,
        applicable_conditions=[
            f"held position (groundspeed < {LOITER_SPEED_MPS:.1f} m/s) during loiter dwell"
        ],
        derivation="maximum observed wind speed while holding position in loiter dwell",
    )


# ---------------------------------------------------------------------------
# Sample extraction helpers
# ---------------------------------------------------------------------------


def _phase_records(
    item: CalibrationInput, estimator_leg_phase: str
) -> list[FlightTraceRecord]:
    records = item.trace.records
    selected: list[FlightTraceRecord] = []
    for segment in item.segments.segments:
        if segment.estimator_leg_phase == estimator_leg_phase:
            selected.extend(_segment_records(records, segment))
    return selected


def _segment_records(
    records: list[FlightTraceRecord], segment: PhaseSegment
) -> list[FlightTraceRecord]:
    return records[segment.start_index : segment.end_index + 1]


def _vertical_rate_samples(
    item: CalibrationInput,
    phases: frozenset[TracePhase],
    *,
    climbing: bool,
) -> tuple[list[float], list[float]]:
    """Return (rates, altitudes) for vertical motion inside the given phases.

    Rates are finite differences over adjacent record pairs *within* each
    qualifying segment (never across a segment boundary), with known altitude and
    positive dt, gated by the segmenter's climb/descent threshold. Descent rates
    are returned as positive magnitudes. Altitudes are the endpoint AMSL values of
    the qualifying pairs, used to report the observed altitude band. Restricting to
    climb/descent (and takeoff/landing) segments keeps flat-cruise or loiter
    altitude jitter from being mistaken for a sustained climb or descent.
    """
    rates: list[float] = []
    altitudes: list[float] = []
    for segment in item.segments.segments:
        if segment.phase not in phases:
            continue
        records = _segment_records(item.trace.records, segment)
        for prev, nxt in zip(records, records[1:], strict=False):
            if prev.alt_amsl_m is None or nxt.alt_amsl_m is None:
                continue
            dt = nxt.timestamp_s - prev.timestamp_s
            if dt <= 0.0:
                continue
            rate = (nxt.alt_amsl_m - prev.alt_amsl_m) / dt
            if climbing and rate >= CLIMB_VERT_RATE_MPS:
                rates.append(rate)
                altitudes.extend((prev.alt_amsl_m, nxt.alt_amsl_m))
            elif not climbing and rate <= -CLIMB_VERT_RATE_MPS:
                rates.append(-rate)
                altitudes.extend((prev.alt_amsl_m, nxt.alt_amsl_m))
    return rates, altitudes


def _wind_speed(record: FlightTraceRecord) -> float | None:
    if record.wind_east_mps is None or record.wind_north_mps is None:
        return None
    return math.hypot(record.wind_east_mps, record.wind_north_mps)


def _true_airspeed(record: FlightTraceRecord) -> float | None:
    """Derive TAS magnitude from ground course/speed and the EN wind vector."""
    if (
        record.groundspeed_mps is None
        or record.heading_deg is None
        or record.wind_east_mps is None
        or record.wind_north_mps is None
    ):
        return None
    course_rad = math.radians(record.heading_deg)
    ground_east_mps = record.groundspeed_mps * math.sin(course_rad)
    ground_north_mps = record.groundspeed_mps * math.cos(course_rad)
    air_east_mps = ground_east_mps - record.wind_east_mps
    air_north_mps = ground_north_mps - record.wind_north_mps
    return math.hypot(air_east_mps, air_north_mps)


def _altitude_band(altitudes: list[float]) -> str:
    return f"AMSL band {min(altitudes):.1f} to {max(altitudes):.1f} m"


def _dataset_version(inputs: list[CalibrationInput]) -> str:
    """Hash complete trace and segmentation content, independent of input order."""
    canonical_items = sorted(
        json.dumps(
            {
                "trace": item.trace.model_dump(mode="json"),
                "segmentation": item.segments.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        for item in inputs
    )
    payload = json.dumps(
        {
            "format": "calibration-dataset.v2",
            "items": canonical_items,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"ds-{len(inputs)}-{digest}"


__all__ = [
    "CalibrationInput",
    "fit_calibration_profile",
]
