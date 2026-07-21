"""Canonical envelope for battery sizing CLI outputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from adapters.battery_sizer import (
    BatterySizingResult,
    battery_capacity_recommendations,
)
from adapters.canonical_json import render_canonical_json
from adapters.envelope import DeterminismMetadata, EnvelopeInputs, ProvenanceInput
from adapters.version import tool_version

BATTERY_SIZING_REPORT_SCHEMA_VERSION = "battery-sizing-report.v2"


class BatteryCapacityRecommendationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    margin_percent: int
    requested_capacity_wh: float
    recommended_capacity_wh: float | None
    unavailable_reason: str | None


class BatterySizingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_energy_wh: float
    reserve_threshold_wh: float
    minimum_capacity_wh: float
    maximum_feasible_capacity_wh: float
    maximum_capacity_at_mtow_wh: float
    search_tolerance_wh: float
    current_capacity_wh: float
    current_reserve_wh: float
    current_reserve_pct: float
    is_current_feasible: bool
    recommendations: list[BatteryCapacityRecommendationPayload]


class BatterySizingProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator_api: str
    inputs: dict[str, ProvenanceInput]


class BatterySizingEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tool_version: str
    mission_id: str
    status: Literal["feasible", "sized"]
    determinism_metadata: DeterminismMetadata
    provenance: BatterySizingProvenance
    result: BatterySizingPayload


def build_battery_sizing_envelope(
    *,
    result: BatterySizingResult,
    mission_id: str,
    inputs: EnvelopeInputs,
    safety_margins: list[int] | None = None,
) -> BatterySizingEnvelope:
    """Construct the canonical battery sizing report envelope."""
    recommendations = battery_capacity_recommendations(
        result,
        safety_margins=safety_margins,
    )
    return BatterySizingEnvelope(
        schema_version=BATTERY_SIZING_REPORT_SCHEMA_VERSION,
        tool_version=tool_version(),
        mission_id=mission_id,
        status="feasible" if result.is_current_feasible else "sized",
        determinism_metadata=DeterminismMetadata(
            deterministic=True,
            randomness_used=False,
            external_network_access_used=False,
            canonical_json=True,
            canonical_json_sort_keys=True,
        ),
        provenance=BatterySizingProvenance(
            estimator_api="adapters.battery_sizer.compute_minimum_battery_capacity",
            inputs=_provenance_inputs(inputs),
        ),
        result=BatterySizingPayload(
            mission_energy_wh=result.mission_energy_wh,
            reserve_threshold_wh=result.reserve_threshold_wh,
            minimum_capacity_wh=result.minimum_capacity_wh,
            maximum_feasible_capacity_wh=result.maximum_feasible_capacity_wh,
            maximum_capacity_at_mtow_wh=result.maximum_capacity_at_mtow_wh,
            search_tolerance_wh=result.search_tolerance_wh,
            current_capacity_wh=result.current_capacity_wh,
            current_reserve_wh=result.current_reserve_wh,
            current_reserve_pct=result.current_reserve_pct,
            is_current_feasible=result.is_current_feasible,
            recommendations=[
                BatteryCapacityRecommendationPayload(
                    margin_percent=recommendation.margin_percent,
                    requested_capacity_wh=recommendation.requested_capacity_wh,
                    recommended_capacity_wh=(recommendation.recommended_capacity_wh),
                    unavailable_reason=recommendation.unavailable_reason,
                )
                for recommendation in recommendations
            ],
        ),
    )


def render_battery_sizing_envelope_json(envelope: BatterySizingEnvelope) -> str:
    """Render the battery sizing envelope as canonical JSON."""
    return render_canonical_json(envelope.model_dump(mode="json"), ensure_ascii=False)


def _provenance_inputs(inputs: EnvelopeInputs) -> dict[str, ProvenanceInput]:
    provenance_inputs = {
        "mission": _provenance_input(inputs.mission),
        "vehicle": _provenance_input(inputs.vehicle),
    }
    optional_inputs = (
        ("geofences", inputs.geofences),
        ("landing_zones", inputs.landing_zones),
        ("terrain", inputs.terrain),
        ("wind_grid", inputs.wind_grid),
    )
    for name, document in optional_inputs:
        if document is not None:
            provenance_inputs[name] = _provenance_input(document)
    return provenance_inputs


def _provenance_input(document) -> ProvenanceInput:
    return ProvenanceInput(format=document.format, sha256=document.sha256)
