"""Execution-context assembly and option/capability derivation."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pyproj import Geod

from estimator.core.constants import (
    DEFAULT_MAX_CRAB_ANGLE_DEG,
    DEFAULT_MIN_GROUNDSPEED_MPS,
)
from estimator.core.enums import (
    CapabilitySource,
    FailureCode,
    FailureKind,
    FidelityMode,
    OptionSource,
)
from estimator.core.errors import InvalidEstimatorInputError
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.options import EstimationOptions
from estimator.core.results import EstimatorContextValue, EstimatorFailure
from estimator.environment.population import (
    GridPopulationProvider,
    population_provider_id,
)
from estimator.environment.terrain import TerrainProvider, terrain_provider_id
from estimator.environment.wind import (
    ConstantWindProvider,
    LayeredWindProvider,
    WindLayer,
    WindProvider,
    wind_provider_id,
)
from estimator.execution.runtime import (
    Capabilities,
    EstimationContext,
    FlightState,
    ResolvedOptions,
)
from schemas.mission import MissionPlan
from schemas.vehicle import VehicleClass, VehicleProfile


@dataclass(frozen=True)
class OptionSourceValues:
    source: OptionSource
    wind_east_mps: float
    wind_north_mps: float
    min_groundspeed_mps: float | None
    max_segment_length_m: float | None = None
    fidelity: FidelityMode | None = None


_DERIVED_CAPABILITIES: dict[VehicleClass, tuple[bool, bool]] = {
    VehicleClass.FIXED_WING: (False, True),
    VehicleClass.MULTIROTOR: (True, False),
    VehicleClass.VTOL: (True, True),
}


def derive_capabilities(vehicle: VehicleProfile) -> Capabilities:
    if vehicle.capabilities is not None:
        return Capabilities(
            hover=vehicle.capabilities.hover,
            forward_flight=vehicle.capabilities.forward_flight,
            source=CapabilitySource.EXPLICIT,
        )

    caps = _DERIVED_CAPABILITIES.get(vehicle.vehicle_class)
    if caps is None:
        raise ValueError(
            f"No derived capabilities defined for vehicle_class={vehicle.vehicle_class!r}. "
            "Add an entry to _DERIVED_CAPABILITIES or set explicit capabilities on the vehicle."
        )
    hover, forward_flight = caps
    return Capabilities(
        hover=hover,
        forward_flight=forward_flight,
        source=CapabilitySource.DERIVED_FROM_VEHICLE_CLASS,
    )


def _mission_fidelity(mission: MissionPlan) -> FidelityMode:
    if mission.estimation is not None:
        return FidelityMode(mission.estimation.fidelity)
    return FidelityMode.V1


def resolve_option_source_values(
    mission: MissionPlan,
    options: EstimationOptions | None,
) -> OptionSourceValues:
    if options is not None:
        return OptionSourceValues(
            source=OptionSource.RUNTIME_OPTIONS,
            wind_east_mps=options.wind_east_mps,
            wind_north_mps=options.wind_north_mps,
            min_groundspeed_mps=options.min_groundspeed_mps,
            max_segment_length_m=(
                options.max_segment_length_m
                or (
                    mission.estimation.max_segment_length_m
                    if mission.estimation is not None
                    else None
                )
            ),
            fidelity=options.fidelity or _mission_fidelity(mission),
        )

    if mission.estimation is not None:
        return OptionSourceValues(
            source=OptionSource.MISSION_ESTIMATION,
            wind_east_mps=mission.estimation.wind_east_mps,
            wind_north_mps=mission.estimation.wind_north_mps,
            min_groundspeed_mps=mission.estimation.min_groundspeed_mps,
            max_segment_length_m=mission.estimation.max_segment_length_m,
            fidelity=FidelityMode(mission.estimation.fidelity),
        )

    return OptionSourceValues(
        source=OptionSource.LIBRARY_DEFAULTS,
        wind_east_mps=0.0,
        wind_north_mps=0.0,
        min_groundspeed_mps=None,
    )


def resolve_options(
    mission: MissionPlan,
    options: EstimationOptions | None,
) -> ResolvedOptions:
    source_values = resolve_option_source_values(mission, options)
    min_ground = source_values.min_groundspeed_mps
    if min_ground is None:
        min_ground = DEFAULT_MIN_GROUNDSPEED_MPS

    return ResolvedOptions(
        wind_east_mps=source_values.wind_east_mps,
        wind_north_mps=source_values.wind_north_mps,
        min_groundspeed_mps=min_ground,
        options_source=source_values.source,
        max_segment_length_m=source_values.max_segment_length_m,
        fidelity=source_values.fidelity or FidelityMode.V1,
    )


def resolve_max_crab_angle_deg(
    vehicle: VehicleProfile,
    metadata: dict[str, EstimatorContextValue],
) -> float:
    max_crab_angle = vehicle.performance.max_crab_angle_deg
    if max_crab_angle is None:
        max_crab_angle = DEFAULT_MAX_CRAB_ANGLE_DEG
        metadata["applied_default_max_crab_angle_deg"] = DEFAULT_MAX_CRAB_ANGLE_DEG
    return max_crab_angle


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_estimation_inputs(
    mission: MissionPlan,
    vehicle: VehicleProfile,
) -> None:
    if mission.vehicle_profile == vehicle.vehicle_id:
        return
    raise InvalidEstimatorInputError(
        EstimatorFailure(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message="mission.vehicle_profile must match vehicle.vehicle_id.",
            context={
                "mission_vehicle_profile": mission.vehicle_profile,
                "vehicle_id": vehicle.vehicle_id,
            },
        )
    )


def build_estimation_context(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    options: EstimationOptions | None = None,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    population_provider: GridPopulationProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
) -> EstimationContext:
    validate_estimation_inputs(mission, vehicle)
    resolved_options = resolve_options(mission, options)
    metadata: dict[str, EstimatorContextValue] = {
        "estimator_version": resolved_options.fidelity.value,
        "options_source": resolved_options.options_source,
    }
    if mission.departure_time is not None:
        metadata["departure_time"] = _utc_isoformat(mission.departure_time)
    capabilities = derive_capabilities(vehicle)
    metadata["capabilities_source"] = capabilities.source

    mission_wind_layers_ignored = (
        mission.estimation is not None
        and mission.estimation.wind_layers is not None
        and resolved_options.options_source == OptionSource.RUNTIME_OPTIONS
        and wind_provider is None
    )
    if mission_wind_layers_ignored:
        metadata["mission_wind_layers_ignored"] = True
        metadata["mission_wind_layers_ignored_reason"] = "runtime_options"

    if wind_provider is None:
        if (
            mission.estimation is not None
            and mission.estimation.wind_layers is not None
            and resolved_options.options_source != OptionSource.RUNTIME_OPTIONS
        ):
            wind_provider = LayeredWindProvider(
                [
                    WindLayer(
                        altitude_m=layer.altitude_m,
                        wind_east_mps=layer.wind_east_mps,
                        wind_north_mps=layer.wind_north_mps,
                    )
                    for layer in mission.estimation.wind_layers
                ]
            )
        else:
            wind_provider = ConstantWindProvider(
                resolved_options.wind_east_mps,
                resolved_options.wind_north_mps,
            )
    metadata["wind_provider_id"] = wind_provider_id(wind_provider)

    if terrain_provider is not None:
        metadata["terrain_provider_id"] = terrain_provider_id(terrain_provider)
    if population_provider is not None:
        metadata["population_provider_id"] = population_provider_id(
            population_provider
        )

    if resolved_options.min_groundspeed_mps == DEFAULT_MIN_GROUNDSPEED_MPS:
        metadata["applied_default_min_groundspeed_mps"] = DEFAULT_MIN_GROUNDSPEED_MPS

    return EstimationContext(
        mission=mission,
        vehicle=vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        geod=Geod(ellps="WGS84"),
        capabilities=capabilities,
        geofences=None if geofences is None else tuple(geofences),
        landing_zones=None if landing_zones is None else tuple(landing_zones),
        resolved_options=resolved_options,
        max_crab_angle_deg=resolve_max_crab_angle_deg(vehicle, metadata),
        metadata=metadata,
        warnings=[],
        route_legs=[],
        state=FlightState(
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            alt_amsl_m=mission.planned_home.altitude_amsl_m,
            elapsed_time_s=0.0,
        ),
    )
