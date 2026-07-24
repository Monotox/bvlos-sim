"""Transit geometry and forward-flight leg estimation.

Fidelity v2 replaces each feasible waypoint corner with a connected circular
fillet: the incoming leg ends at its tangent point, a materialized arc joins the
two tangent points, and the outgoing leg starts at the arc exit.
"""

import math
from dataclasses import dataclass
from typing import Callable

from bvlos_sim.estimator.core.constants import (
    CRAB_ANGLE_WARNING_MARGIN,
    EPS_DISTANCE_M,
    GROUNDSPEED_WARNING_MARGIN,
    MIN_TURN_ANGLE_DEG,
)
from bvlos_sim.estimator.core.enums import (
    FailureCode,
    FailureKind,
    FidelityMode,
    LegPhase,
    WarningCode,
)
from bvlos_sim.estimator.core.results import (
    EstimatorContextValue,
    LegEstimate,
    LegTimingProfile,
    WindVector,
)
from bvlos_sim.estimator.environment.wind import (
    LayeredWindProvider,
    TimeVaryingWindProvider,
    WindProvider,
)
from bvlos_sim.estimator.execution.rules import resolve_transit_tas
from bvlos_sim.estimator.execution.runtime import EstimationContext, TargetPhase
from bvlos_sim.estimator.execution.vertical import VerticalProfile, compute_vertical_time
from bvlos_sim.estimator.math.turn_arc import TurnArcGeometry, compute_turn_arc_geometry
from bvlos_sim.estimator.math.wind_triangle import (
    WindTriangleSolution,
    normalize_deg,
    solve_wind_triangle,
)
from bvlos_sim.schemas.mission import RouteItem

_WIND_TIME_CONVERGENCE_TOLERANCE_S = 1e-7
_WIND_TIME_MAX_ITERATIONS = 24
_WIND_EVENT_TOLERANCE_S = 1e-9
_DISTANCE_TOLERANCE_M = 1e-9


@dataclass(frozen=True)
class TransitGeometry:
    track_deg: float
    horizontal_distance_m: float


@dataclass(frozen=True)
class TransitConstraintCheck:
    violated: bool
    code: FailureCode
    message: str
    context: dict[str, EstimatorContextValue]


@dataclass(frozen=True)
class TransitWarningCheck:
    triggered: bool
    code: WarningCode


@dataclass(frozen=True)
class EvaluatedWindSample:
    wind: WindVector
    solution: WindTriangleSolution


@dataclass(frozen=True)
class HorizontalPathEvaluation:
    time_s: float
    wind: WindVector
    wind_speed_mps: float
    groundspeed_mps: float
    required_heading_deg: float
    crab_angle_deg: float
    wind_along_track_mps: float
    wind_cross_track_mps: float
    warnings: tuple[WarningCode, ...]
    timing_points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class TimedSegmentEvaluation:
    time_s: float
    samples: tuple[EvaluatedWindSample, ...]
    timing_points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class MaterializedTurnArc:
    geometry: TurnArcGeometry
    entry_lat: float
    entry_lon: float
    exit_lat: float
    exit_lon: float
    coordinates: tuple[tuple[float, float], ...]


def compute_transit_geometry(
    context: EstimationContext,
    *,
    start_lat: float,
    start_lon: float,
    target: TargetPhase,
) -> TransitGeometry:
    azimuth_deg, _, horizontal_distance_m = context.geod.inv(
        start_lon,
        start_lat,
        target.target_lon,
        target.target_lat,
    )
    if horizontal_distance_m <= EPS_DISTANCE_M:
        horizontal_distance_m = 0.0

    return TransitGeometry(
        track_deg=normalize_deg(azimuth_deg),
        horizontal_distance_m=horizontal_distance_m,
    )


def build_vertical_only_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
    vertical: VerticalProfile,
    start_lat: float,
    start_lon: float,
    start_alt: float,
) -> LegEstimate:
    leg = LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=target.phase,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt_amsl_m=start_alt,
        end_lat=target.target_lat,
        end_lon=target.target_lon,
        end_alt_amsl_m=target.target_alt_amsl_m,
        horizontal_distance_m=0.0,
        vertical_delta_m=vertical.delta_m,
        vertical_distance_m=vertical.distance_m,
        path_distance_m=vertical.distance_m,
        time_s=vertical.time_s,
    )
    leg._set_timing_profile(
        LegTimingProfile(
            distance_time_points=((0.0, 0.0), (1.0, vertical.time_s)),
            vertical_time_s=vertical.time_s,
        )
    )
    return leg


def sub_segment_midpoint_fractions(
    horizontal_distance_m: float,
    max_segment_length_m: float | None,
) -> tuple[float, ...]:
    if horizontal_distance_m <= 0.0:
        return (0.0,)
    if max_segment_length_m is None or horizontal_distance_m <= max_segment_length_m:
        return (0.5,)
    n = max(1, math.ceil(horizontal_distance_m / max_segment_length_m))
    return tuple((i + 0.5) / n for i in range(n))


def _wind_at_fraction(
    context: EstimationContext,
    *,
    provider: WindProvider,
    start_lon: float,
    start_lat: float,
    track_deg: float,
    horizontal_distance_m: float,
    altitude_m: float,
    elapsed_s: float,
    fraction: float,
) -> WindVector:
    mid_lon, mid_lat, _ = context.geod.fwd(
        start_lon, start_lat, track_deg, horizontal_distance_m * fraction
    )
    return provider.wind_at(
        lat=mid_lat, lon=mid_lon, altitude_amsl_m=altitude_m, elapsed_time_s=elapsed_s
    )


def _check_wind_solution(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    track_deg: float,
    tas_mps: float,
    wind: WindVector,
    solution: WindTriangleSolution | None,
    segment_index: int,
    n_segments: int,
    leg_index: int | None = None,
) -> WindTriangleSolution:
    base_context = {
        "action": item.action.value,
        "track_azimuth_deg": track_deg,
        "wind_east_mps": wind.wind_east_mps,
        "wind_north_mps": wind.wind_north_mps,
        "tas_mps": tas_mps,
    }
    if n_segments > 1:
        base_context |= {
            "segment_index": segment_index,
            "n_segments": n_segments,
        }
    if solution is None:
        context.fail(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.WIND_TRIANGLE_NO_SOLUTION,
            message=(
                "No wind-triangle solution exists for required crosswind correction."
                if n_segments == 1
                else (
                    f"No wind-triangle solution in sub-segment "
                    f"{segment_index + 1}/{n_segments}."
                )
            ),
            route_item_index=route_item_index,
            route_item_id=item.id,
            context=base_context,
            leg_index=leg_index,
        )

    checks = (
        TransitConstraintCheck(
            violated=abs(solution.crab_angle_deg) > context.max_crab_angle_deg,
            code=FailureCode.CRAB_ANGLE_LIMIT_EXCEEDED,
            message="Required crab angle exceeds max_crab_angle_deg.",
            context=base_context
            | {
                "crab_angle_deg": solution.crab_angle_deg,
                "max_crab_angle_deg": context.max_crab_angle_deg,
                "groundspeed_mps": solution.groundspeed_mps,
            },
        ),
        TransitConstraintCheck(
            violated=solution.groundspeed_mps <= 0.0,
            code=FailureCode.GROUNDSPEED_NON_POSITIVE,
            message="Solved groundspeed is non-positive.",
            context=base_context | {"groundspeed_mps": solution.groundspeed_mps},
        ),
        TransitConstraintCheck(
            violated=(
                solution.groundspeed_mps < context.resolved_options.min_groundspeed_mps
            ),
            code=FailureCode.GROUNDSPEED_BELOW_MIN,
            message="Solved groundspeed is below min_groundspeed_mps.",
            context=base_context
            | {
                "groundspeed_mps": solution.groundspeed_mps,
                "min_groundspeed_mps": context.resolved_options.min_groundspeed_mps,
            },
        ),
    )
    for check in checks:
        if check.violated:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=check.code,
                message=check.message,
                route_item_index=route_item_index,
                route_item_id=item.id,
                context=check.context,
                leg_index=leg_index,
            )
    return solution


def _summarize_horizontal_path(
    context: EstimationContext,
    *,
    samples: list[EvaluatedWindSample],
    time_s: float,
    timing_points: list[tuple[float, float]],
) -> HorizontalPathEvaluation:
    max_wind_sample = max(samples, key=lambda sample: context.wind_speed(sample.wind))
    min_groundspeed_sample = min(
        samples, key=lambda sample: sample.solution.groundspeed_mps
    )
    max_crab_sample = max(
        samples, key=lambda sample: abs(sample.solution.crab_angle_deg)
    )
    max_crosswind_sample = max(
        samples, key=lambda sample: abs(sample.solution.wind_cross_track_mps)
    )
    warning_codes: list[WarningCode] = []
    if any(
        sample.solution.groundspeed_mps
        < GROUNDSPEED_WARNING_MARGIN * context.resolved_options.min_groundspeed_mps
        for sample in samples
    ):
        warning_codes.append(WarningCode.LOW_GROUNDSPEED_MARGIN)
    if any(
        abs(sample.solution.crab_angle_deg)
        > CRAB_ANGLE_WARNING_MARGIN * context.max_crab_angle_deg
        for sample in samples
    ):
        warning_codes.append(WarningCode.HIGH_CRAB_MARGIN)

    return HorizontalPathEvaluation(
        time_s=time_s,
        wind=max_wind_sample.wind,
        wind_speed_mps=context.wind_speed(max_wind_sample.wind),
        groundspeed_mps=min_groundspeed_sample.solution.groundspeed_mps,
        required_heading_deg=max_crab_sample.solution.required_heading_deg,
        crab_angle_deg=max_crab_sample.solution.crab_angle_deg,
        wind_along_track_mps=min_groundspeed_sample.solution.wind_along_track_mps,
        wind_cross_track_mps=max_crosswind_sample.solution.wind_cross_track_mps,
        warnings=tuple(warning_codes),
        timing_points=tuple(timing_points),
    )


def _active_wind_regime(
    provider: WindProvider,
    *,
    elapsed_time_s: float,
) -> tuple[WindProvider, float | None]:
    """Resolve nested scheduled providers and their next discontinuity."""

    next_change_s: float | None = None
    active = provider
    while isinstance(active, TimeVaryingWindProvider):
        candidate = active.next_change_after(elapsed_time_s)
        if candidate is not None and (
            next_change_s is None or candidate < next_change_s
        ):
            next_change_s = candidate
        active = active.provider_for_elapsed_time(elapsed_time_s)
    return active, next_change_s


def _timing_convergence_failure(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    segment_index: int,
    n_segments: int,
    last_duration_s: float,
    revised_duration_s: float,
    reason: str,
    leg_index: int | None,
) -> None:
    context.fail(
        kind=FailureKind.INVALID_INPUT,
        code=FailureCode.INVALID_GEOMETRY,
        message="Wind-coupled transit timing did not converge.",
        route_item_index=route_item_index,
        route_item_id=item.id,
        leg_index=leg_index,
        context={
            "action": item.action.value,
            "segment_index": segment_index,
            "n_segments": n_segments,
            "last_duration_s": last_duration_s,
            "revised_duration_s": revised_duration_s,
            "reason": reason,
        },
    )


def _solve_distance_duration_in_regime(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    provider: WindProvider,
    distance_m: float,
    tas_mps: float,
    track_deg: float,
    leg_elapsed_s: float,
    sample_fraction: float,
    wind_sampler: Callable[[WindProvider, float, float], WindVector],
    segment_index: int,
    n_segments: int,
    use_midpoint_iteration: bool,
    sample_duration_cap_s: float | None,
    leg_index: int | None,
) -> tuple[float, EvaluatedWindSample]:
    """Solve one continuous wind regime without accepting a stale iterate."""

    duration_s = distance_m / tas_mps
    if not use_midpoint_iteration or isinstance(provider, LayeredWindProvider):
        wind = wind_sampler(provider, sample_fraction, leg_elapsed_s)
        solution = _check_wind_solution(
            context,
            item,
            route_item_index=route_item_index,
            track_deg=track_deg,
            tas_mps=tas_mps,
            wind=wind,
            solution=solve_wind_triangle(
                track_deg=track_deg,
                tas_mps=tas_mps,
                wind_east_mps=wind.wind_east_mps,
                wind_north_mps=wind.wind_north_mps,
            ),
            segment_index=segment_index,
            n_segments=n_segments,
            leg_index=leg_index,
        )
        return distance_m / solution.groundspeed_mps, EvaluatedWindSample(
            wind=wind,
            solution=solution,
        )

    two_back_duration_s: float | None = None
    for _ in range(_WIND_TIME_MAX_ITERATIONS):
        sample_duration_s = (
            duration_s
            if sample_duration_cap_s is None
            else min(duration_s, sample_duration_cap_s)
        )
        sample_leg_elapsed_s = leg_elapsed_s + sample_duration_s * 0.5
        wind = wind_sampler(provider, sample_fraction, sample_leg_elapsed_s)
        solution = solve_wind_triangle(
            track_deg=track_deg,
            tas_mps=tas_mps,
            wind_east_mps=wind.wind_east_mps,
            wind_north_mps=wind.wind_north_mps,
        )
        if solution is None or solution.groundspeed_mps <= 0.0:
            checked = _check_wind_solution(
                context,
                item,
                route_item_index=route_item_index,
                track_deg=track_deg,
                tas_mps=tas_mps,
                wind=wind,
                solution=solution,
                segment_index=segment_index,
                n_segments=n_segments,
                leg_index=leg_index,
            )
            raise AssertionError(f"unreachable wind solution: {checked}")
        revised_duration_s = distance_m / solution.groundspeed_mps
        if math.isclose(
            revised_duration_s,
            duration_s,
            rel_tol=1e-10,
            abs_tol=_WIND_TIME_CONVERGENCE_TOLERANCE_S,
        ):
            solution = _check_wind_solution(
                context,
                item,
                route_item_index=route_item_index,
                track_deg=track_deg,
                tas_mps=tas_mps,
                wind=wind,
                solution=solution,
                segment_index=segment_index,
                n_segments=n_segments,
                leg_index=leg_index,
            )
            return revised_duration_s, EvaluatedWindSample(
                wind=wind,
                solution=solution,
            )
        if two_back_duration_s is not None and math.isclose(
            revised_duration_s,
            two_back_duration_s,
            rel_tol=1e-10,
            abs_tol=_WIND_TIME_CONVERGENCE_TOLERANCE_S,
        ):
            _timing_convergence_failure(
                context,
                item,
                route_item_index=route_item_index,
                segment_index=segment_index,
                n_segments=n_segments,
                last_duration_s=duration_s,
                revised_duration_s=revised_duration_s,
                reason="two_cycle",
                leg_index=leg_index,
            )
        two_back_duration_s = duration_s
        duration_s = revised_duration_s

    _timing_convergence_failure(
        context,
        item,
        route_item_index=route_item_index,
        segment_index=segment_index,
        n_segments=n_segments,
        last_duration_s=duration_s,
        revised_duration_s=revised_duration_s,
        reason="iteration_limit",
        leg_index=leg_index,
    )


def _integrate_horizontal_segment(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    distance_m: float,
    path_fraction_start: float,
    path_fraction_end: float,
    sample_fraction: float,
    track_deg: float,
    tas_mps: float,
    mission_elapsed_s: float,
    leg_elapsed_s: float,
    wind_sampler: Callable[[WindProvider, float, float], WindVector],
    segment_index: int,
    n_segments: int,
    use_midpoint_iteration: bool = True,
    leg_index: int | None = None,
) -> TimedSegmentEvaluation:
    """Integrate a segment causally across scheduled wind discontinuities."""

    remaining_distance_m = distance_m
    travelled_distance_m = 0.0
    segment_elapsed_s = 0.0
    samples: list[EvaluatedWindSample] = []
    timing_points: list[tuple[float, float]] = []

    while remaining_distance_m > _DISTANCE_TOLERANCE_M:
        absolute_elapsed_s = mission_elapsed_s + leg_elapsed_s + segment_elapsed_s
        provider, next_change_s = _active_wind_regime(
            context.wind_provider,
            elapsed_time_s=absolute_elapsed_s,
        )
        time_to_change_s = (
            math.inf
            if next_change_s is None
            else max(0.0, next_change_s - absolute_elapsed_s)
        )
        completion_s, completion_sample = _solve_distance_duration_in_regime(
            context,
            item,
            route_item_index=route_item_index,
            provider=provider,
            distance_m=remaining_distance_m,
            tas_mps=tas_mps,
            track_deg=track_deg,
            leg_elapsed_s=leg_elapsed_s + segment_elapsed_s,
            sample_fraction=sample_fraction,
            wind_sampler=wind_sampler,
            segment_index=segment_index,
            n_segments=n_segments,
            use_midpoint_iteration=use_midpoint_iteration,
            sample_duration_cap_s=(
                None if not math.isfinite(time_to_change_s) else time_to_change_s
            ),
            leg_index=leg_index,
        )
        if completion_s <= time_to_change_s + _WIND_EVENT_TOLERANCE_S:
            segment_elapsed_s += completion_s
            travelled_distance_m = distance_m
            remaining_distance_m = 0.0
            samples.append(completion_sample)
        else:
            if time_to_change_s <= _WIND_EVENT_TOLERANCE_S:
                _timing_convergence_failure(
                    context,
                    item,
                    route_item_index=route_item_index,
                    segment_index=segment_index,
                    n_segments=n_segments,
                    last_duration_s=completion_s,
                    revised_duration_s=time_to_change_s,
                    reason="non_advancing_wind_event",
                    leg_index=leg_index,
                )
            event_sample = completion_sample
            distance_to_change_m = (
                event_sample.solution.groundspeed_mps * time_to_change_s
            )
            if (
                distance_to_change_m <= _DISTANCE_TOLERANCE_M
                or distance_to_change_m >= remaining_distance_m
            ):
                _timing_convergence_failure(
                    context,
                    item,
                    route_item_index=route_item_index,
                    segment_index=segment_index,
                    n_segments=n_segments,
                    last_duration_s=completion_s,
                    revised_duration_s=time_to_change_s,
                    reason="inconsistent_event_bracket",
                    leg_index=leg_index,
                )
            travelled_distance_m += distance_to_change_m
            remaining_distance_m -= distance_to_change_m
            segment_elapsed_s += time_to_change_s
            samples.append(event_sample)

        travelled_fraction = min(1.0, travelled_distance_m / distance_m)
        path_fraction = (
            path_fraction_start
            + (path_fraction_end - path_fraction_start) * travelled_fraction
        )
        timing_points.append((path_fraction, leg_elapsed_s + segment_elapsed_s))

    return TimedSegmentEvaluation(
        time_s=segment_elapsed_s,
        samples=tuple(samples),
        timing_points=tuple(timing_points),
    )


def _evaluate_straight_horizontal_path(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    geometry: TransitGeometry,
    start_lat: float,
    start_lon: float,
    start_alt: float,
    end_alt: float,
    tas_mps: float,
    elapsed_s: float,
    vertical_time_s: float,
    leg_index: int | None = None,
) -> HorizontalPathEvaluation:
    max_segment_length_m = context.resolved_options.max_segment_length_m
    # Always sample at sub-segment midpoints. Sampling at the departure end
    # (fraction 0.0) bills the whole leg at the wind it left home in, which
    # understates energy whenever the wind builds along the route.
    sample_fractions = sub_segment_midpoint_fractions(
        geometry.horizontal_distance_m, max_segment_length_m
    )
    n_segments = len(sample_fractions)
    segment_length_m = geometry.horizontal_distance_m / n_segments
    total_s = 0.0
    samples: list[EvaluatedWindSample] = []
    timing_points: list[tuple[float, float]] = [(0.0, 0.0)]

    def sample_wind(
        provider: WindProvider,
        fraction: float,
        leg_elapsed_time_s: float,
    ) -> WindVector:
        altitude_fraction = (
            min(1.0, leg_elapsed_time_s / vertical_time_s)
            if vertical_time_s > 0.0
            else 1.0
        )
        altitude_m = start_alt + (end_alt - start_alt) * altitude_fraction
        return _wind_at_fraction(
            context,
            provider=provider,
            start_lon=start_lon,
            start_lat=start_lat,
            track_deg=geometry.track_deg,
            horizontal_distance_m=geometry.horizontal_distance_m,
            altitude_m=altitude_m,
            elapsed_s=elapsed_s + leg_elapsed_time_s,
            fraction=fraction,
        )

    for segment_index, sample_fraction in enumerate(sample_fractions):
        path_fraction_start = segment_index / n_segments
        path_fraction_end = (segment_index + 1) / n_segments
        segment = _integrate_horizontal_segment(
            context,
            item,
            route_item_index=route_item_index,
            distance_m=segment_length_m,
            path_fraction_start=path_fraction_start,
            path_fraction_end=path_fraction_end,
            sample_fraction=sample_fraction,
            track_deg=geometry.track_deg,
            tas_mps=tas_mps,
            mission_elapsed_s=elapsed_s,
            leg_elapsed_s=total_s,
            wind_sampler=sample_wind,
            segment_index=segment_index,
            n_segments=n_segments,
            use_midpoint_iteration=True,
            leg_index=leg_index,
        )
        total_s += segment.time_s
        samples.extend(segment.samples)
        timing_points.extend(segment.timing_points)
    return _summarize_horizontal_path(
        context,
        samples=samples,
        time_s=total_s,
        timing_points=timing_points,
    )


def build_forward_transit_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
    geometry: TransitGeometry,
    vertical: VerticalProfile,
    start_lat: float,
    start_lon: float,
    start_alt: float,
    tangent_offset_m: float = 0.0,
) -> LegEstimate:
    if not context.capabilities.forward_flight:
        context.fail(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message="forward-flight transit requires forward_flight capability.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )

    tas_mps, speed_source = resolve_transit_tas(
        context,
        item,
        route_item_index=route_item_index,
    )
    path = _evaluate_straight_horizontal_path(
        context,
        item,
        route_item_index=route_item_index,
        geometry=geometry,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt=start_alt,
        end_alt=target.target_alt_amsl_m,
        tas_mps=tas_mps,
        elapsed_s=context.state.elapsed_time_s,
        vertical_time_s=vertical.time_s,
    )
    leg_time_s = max(path.time_s, vertical.time_s)

    leg = LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=target.phase,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt_amsl_m=start_alt,
        end_lat=target.target_lat,
        end_lon=target.target_lon,
        end_alt_amsl_m=target.target_alt_amsl_m,
        horizontal_distance_m=geometry.horizontal_distance_m,
        vertical_delta_m=vertical.delta_m,
        vertical_distance_m=vertical.distance_m,
        path_distance_m=max(0.0, geometry.horizontal_distance_m - tangent_offset_m),
        time_s=leg_time_s,
        tas_mps=tas_mps,
        groundspeed_mps=path.groundspeed_mps,
        ground_track_deg=geometry.track_deg,
        required_heading_deg=path.required_heading_deg,
        crab_angle_deg=path.crab_angle_deg,
        wind_east_mps=path.wind.wind_east_mps,
        wind_north_mps=path.wind.wind_north_mps,
        wind_speed_mps=path.wind_speed_mps,
        wind_along_track_mps=path.wind_along_track_mps,
        wind_cross_track_mps=path.wind_cross_track_mps,
        speed_source=speed_source,
        warnings=list(path.warnings),
    )
    leg._set_timing_profile(
        LegTimingProfile(
            distance_time_points=path.timing_points,
            vertical_time_s=vertical.time_s,
        )
    )
    return leg


def _materialize_turn_arc(
    context: EstimationContext,
    *,
    vertex_lat: float,
    vertex_lon: float,
    incoming_track_deg: float,
    outgoing_track_deg: float,
    turn_radius_m: float,
    arc: TurnArcGeometry,
) -> MaterializedTurnArc:
    entry_lon, entry_lat, _ = context.geod.fwd(
        vertex_lon,
        vertex_lat,
        incoming_track_deg + 180.0,
        arc.tangent_offset_m,
    )
    exit_lon, exit_lat, _ = context.geod.fwd(
        vertex_lon,
        vertex_lat,
        outgoing_track_deg,
        arc.tangent_offset_m,
    )
    right_turn = arc.signed_turn_angle_deg > 0.0
    center_bearing_deg = incoming_track_deg + (90.0 if right_turn else -90.0)
    center_lon, center_lat, _ = context.geod.fwd(
        entry_lon,
        entry_lat,
        center_bearing_deg,
        turn_radius_m,
    )
    radial_start_deg = incoming_track_deg + (-90.0 if right_turn else 90.0)
    angle_segments = max(1, math.ceil(arc.turn_angle_deg / 5.0))
    max_segment_length_m = context.resolved_options.max_segment_length_m
    length_segments = (
        1
        if max_segment_length_m is None
        else math.ceil(arc.arc_length_m / max_segment_length_m)
    )
    segment_count = max(2, angle_segments, length_segments)
    coordinates: list[tuple[float, float]] = []
    for index in range(segment_count + 1):
        fraction = index / segment_count
        radial_bearing_deg = radial_start_deg + arc.signed_turn_angle_deg * fraction
        lon, lat, _ = context.geod.fwd(
            center_lon,
            center_lat,
            radial_bearing_deg,
            turn_radius_m,
        )
        coordinates.append((lon, lat))
    # Preserve exact connectivity despite small geodesic/local-circle drift.
    coordinates[0] = (entry_lon, entry_lat)
    coordinates[-1] = (exit_lon, exit_lat)
    return MaterializedTurnArc(
        geometry=arc,
        entry_lat=entry_lat,
        entry_lon=entry_lon,
        exit_lat=exit_lat,
        exit_lon=exit_lon,
        coordinates=tuple(coordinates),
    )


def _evaluate_turn_arc_path(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    incoming_track_deg: float,
    materialized: MaterializedTurnArc,
    altitude_m: float,
    tas_mps: float,
    elapsed_s: float,
) -> HorizontalPathEvaluation:
    coordinates = materialized.coordinates
    n_segments = len(coordinates) - 1
    segment_length_m = materialized.geometry.arc_length_m / n_segments
    samples: list[EvaluatedWindSample] = []
    total_s = 0.0
    timing_points: list[tuple[float, float]] = [(0.0, 0.0)]
    for segment_index, ((start_lon, start_lat), (end_lon, end_lat)) in enumerate(
        zip(coordinates, coordinates[1:])
    ):
        chord_track_deg, _, chord_distance_m = context.geod.inv(
            start_lon, start_lat, end_lon, end_lat
        )
        mid_lon, mid_lat, _ = context.geod.fwd(
            start_lon,
            start_lat,
            chord_track_deg,
            chord_distance_m * 0.5,
        )
        track_deg = normalize_deg(
            incoming_track_deg
            + materialized.geometry.signed_turn_angle_deg
            * ((segment_index + 0.5) / n_segments)
        )

        def sample_wind(
            provider: WindProvider,
            fraction: float,
            leg_elapsed_time_s: float,
        ) -> WindVector:
            del fraction
            return provider.wind_at(
                lat=mid_lat,
                lon=mid_lon,
                altitude_amsl_m=altitude_m,
                elapsed_time_s=elapsed_s + leg_elapsed_time_s,
            )

        segment = _integrate_horizontal_segment(
            context,
            item,
            route_item_index=route_item_index,
            distance_m=segment_length_m,
            path_fraction_start=segment_index / n_segments,
            path_fraction_end=(segment_index + 1) / n_segments,
            sample_fraction=(segment_index + 0.5) / n_segments,
            track_deg=track_deg,
            tas_mps=tas_mps,
            mission_elapsed_s=elapsed_s,
            leg_elapsed_s=total_s,
            wind_sampler=sample_wind,
            segment_index=segment_index,
            n_segments=n_segments,
        )
        total_s += segment.time_s
        samples.extend(segment.samples)
        timing_points.extend(segment.timing_points)
    return _summarize_horizontal_path(
        context,
        samples=samples,
        time_s=total_s,
        timing_points=timing_points,
    )


def _trim_previous_transit_leg(
    context: EstimationContext,
    *,
    entry_lat: float,
    entry_lon: float,
) -> None:
    previous = context.route_legs[-1]
    if previous.tas_mps is None:
        raise ValueError("A turn fillet requires an incoming forward-flight leg.")
    previous_item = context.mission.route[previous.route_item_index]
    incoming_track_deg, _, horizontal_distance_m = context.geod.inv(
        previous.start_lon,
        previous.start_lat,
        entry_lon,
        entry_lat,
    )
    geometry = TransitGeometry(
        track_deg=normalize_deg(incoming_track_deg),
        horizontal_distance_m=horizontal_distance_m,
    )
    vertical = compute_vertical_time(
        context,
        previous_item,
        route_item_index=previous.route_item_index,
        start_alt_amsl_m=previous.start_alt_amsl_m,
        end_alt_amsl_m=previous.end_alt_amsl_m,
    )
    elapsed_start_s = context.state.elapsed_time_s - previous.time_s
    path = _evaluate_straight_horizontal_path(
        context,
        previous_item,
        route_item_index=previous.route_item_index,
        geometry=geometry,
        start_lat=previous.start_lat,
        start_lon=previous.start_lon,
        start_alt=previous.start_alt_amsl_m,
        end_alt=previous.end_alt_amsl_m,
        tas_mps=previous.tas_mps,
        elapsed_s=elapsed_start_s,
        vertical_time_s=vertical.time_s,
        leg_index=previous.leg_index,
    )
    updated = previous.model_copy(
        update={
            "end_lat": entry_lat,
            "end_lon": entry_lon,
            "horizontal_distance_m": horizontal_distance_m,
            "path_distance_m": horizontal_distance_m,
            "time_s": max(path.time_s, vertical.time_s),
            "ground_track_deg": geometry.track_deg,
            "groundspeed_mps": path.groundspeed_mps,
            "required_heading_deg": path.required_heading_deg,
            "crab_angle_deg": path.crab_angle_deg,
            "wind_east_mps": path.wind.wind_east_mps,
            "wind_north_mps": path.wind.wind_north_mps,
            "wind_speed_mps": path.wind_speed_mps,
            "wind_along_track_mps": path.wind_along_track_mps,
            "wind_cross_track_mps": path.wind_cross_track_mps,
            "warnings": list(path.warnings),
        }
    )
    updated._set_timing_profile(
        LegTimingProfile(
            distance_time_points=path.timing_points,
            vertical_time_s=vertical.time_s,
        )
    )
    context.route_legs[-1] = updated
    context.state.lat = entry_lat
    context.state.lon = entry_lon
    context.state.elapsed_time_s += updated.time_s - previous.time_s


def _build_turn_arc_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    incoming_track_deg: float,
    outgoing_track_deg: float,
    materialized: MaterializedTurnArc,
) -> LegEstimate:
    tas_mps, speed_source = resolve_transit_tas(
        context, item, route_item_index=route_item_index
    )
    path = _evaluate_turn_arc_path(
        context,
        item,
        route_item_index=route_item_index,
        incoming_track_deg=incoming_track_deg,
        materialized=materialized,
        altitude_m=context.state.alt_amsl_m,
        tas_mps=tas_mps,
        elapsed_s=context.state.elapsed_time_s,
    )
    _, _, chord_distance_m = context.geod.inv(
        materialized.entry_lon,
        materialized.entry_lat,
        materialized.exit_lon,
        materialized.exit_lat,
    )
    leg = LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=LegPhase.TURN_ARC,
        start_lat=materialized.entry_lat,
        start_lon=materialized.entry_lon,
        start_alt_amsl_m=context.state.alt_amsl_m,
        end_lat=materialized.exit_lat,
        end_lon=materialized.exit_lon,
        end_alt_amsl_m=context.state.alt_amsl_m,
        horizontal_distance_m=chord_distance_m,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=materialized.geometry.arc_length_m,
        time_s=path.time_s,
        tas_mps=tas_mps,
        groundspeed_mps=path.groundspeed_mps,
        ground_track_deg=outgoing_track_deg,
        required_heading_deg=path.required_heading_deg,
        crab_angle_deg=path.crab_angle_deg,
        wind_east_mps=path.wind.wind_east_mps,
        wind_north_mps=path.wind.wind_north_mps,
        wind_speed_mps=path.wind_speed_mps,
        wind_along_track_mps=path.wind_along_track_mps,
        wind_cross_track_mps=path.wind_cross_track_mps,
        speed_source=speed_source,
        warnings=list(path.warnings),
    )
    leg._set_path_coordinates(materialized.coordinates)
    leg._set_timing_profile(
        LegTimingProfile(
            distance_time_points=path.timing_points,
            vertical_time_s=0.0,
        )
    )
    return leg


def append_transit_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
) -> None:
    """Build and append a transit leg, prepending a TURN_ARC leg in v2 fidelity.

    In fidelity v2, a turn arc is injected whenever:
    - the vehicle has a known incoming track from the previous leg,
    - the vehicle has forward-flight capability with a defined turn radius, and
    - the new transit leg has a non-trivial horizontal distance.

    When a TURN_ARC is injected, both adjacent transit legs are connected to
    its actual tangent points and their distance/time fields are recomputed.
    """
    if (
        context.resolved_options.fidelity == FidelityMode.V2
        and context.state.last_track_deg is not None
        and context.capabilities.forward_flight
        and context.vehicle.performance.turn_radius_m is not None
    ):
        geometry = compute_transit_geometry(
            context,
            start_lat=context.state.lat,
            start_lon=context.state.lon,
            target=target,
        )
        if geometry.horizontal_distance_m > EPS_DISTANCE_M:
            incoming_track_deg = context.state.last_track_deg
            turn_radius_m = context.vehicle.performance.turn_radius_m
            assert incoming_track_deg is not None
            assert turn_radius_m is not None
            arc = compute_turn_arc_geometry(
                incoming_track_deg=incoming_track_deg,
                outgoing_track_deg=geometry.track_deg,
                radius_m=turn_radius_m,
            )
            if arc.turn_angle_deg >= MIN_TURN_ANGLE_DEG:
                previous_distance_m = context.route_legs[-1].horizontal_distance_m
                if (
                    not math.isfinite(arc.tangent_offset_m)
                    or arc.tangent_offset_m >= previous_distance_m
                    or arc.tangent_offset_m >= geometry.horizontal_distance_m
                ):
                    context.fail(
                        kind=FailureKind.INFEASIBLE,
                        code=FailureCode.INVALID_GEOMETRY,
                        message=(
                            "The configured turn radius cannot form a connected "
                            "tangent arc within the adjacent route legs."
                        ),
                        route_item_index=route_item_index,
                        route_item_id=item.id,
                        context={
                            "incoming_track_deg": incoming_track_deg,
                            "outgoing_track_deg": geometry.track_deg,
                            "turn_angle_deg": arc.turn_angle_deg,
                            "turn_radius_m": turn_radius_m,
                            "tangent_offset_m": arc.tangent_offset_m,
                            "incoming_leg_distance_m": previous_distance_m,
                            "outgoing_leg_distance_m": geometry.horizontal_distance_m,
                        },
                    )
                materialized = _materialize_turn_arc(
                    context,
                    vertex_lat=context.state.lat,
                    vertex_lon=context.state.lon,
                    incoming_track_deg=incoming_track_deg,
                    outgoing_track_deg=geometry.track_deg,
                    turn_radius_m=turn_radius_m,
                    arc=arc,
                )
                _trim_previous_transit_leg(
                    context,
                    entry_lat=materialized.entry_lat,
                    entry_lon=materialized.entry_lon,
                )
                turn_arc = _build_turn_arc_leg(
                    context,
                    item,
                    route_item_index=route_item_index,
                    incoming_track_deg=incoming_track_deg,
                    outgoing_track_deg=geometry.track_deg,
                    materialized=materialized,
                )
                context.append_leg(turn_arc)

    context.append_leg(
        estimate_transit_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=target,
        )
    )


def estimate_transit_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
    tangent_offset_m: float = 0.0,
) -> LegEstimate:
    start_lat = context.state.lat
    start_lon = context.state.lon
    start_alt = context.state.alt_amsl_m

    geometry = compute_transit_geometry(
        context,
        start_lat=start_lat,
        start_lon=start_lon,
        target=target,
    )
    vertical = compute_vertical_time(
        context,
        item,
        route_item_index=route_item_index,
        start_alt_amsl_m=start_alt,
        end_alt_amsl_m=target.target_alt_amsl_m,
    )

    if geometry.horizontal_distance_m == 0.0:
        return build_vertical_only_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=target,
            vertical=vertical,
            start_lat=start_lat,
            start_lon=start_lon,
            start_alt=start_alt,
        )

    return build_forward_transit_leg(
        context,
        item,
        route_item_index=route_item_index,
        target=target,
        geometry=geometry,
        vertical=vertical,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt=start_alt,
        tangent_offset_m=tangent_offset_m,
    )
