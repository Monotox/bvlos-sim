import math
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bvlos_sim.adapters.assets.population_grid import (
    PopulationGridLoadError,
    load_population_grid,
)
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.sora import GroundRiskFootprint
from bvlos_sim.schemas.vehicle import VehicleProfile
from tests.helpers import make_mission_payload, make_vehicle_payload


@pytest.mark.parametrize(
    ("section", "field", "invalid"),
    [
        ("energy", "battery_capacity_wh", math.inf),
        ("energy", "battery_capacity_wh", math.nan),
        ("energy", "battery_capacity_wh", True),
        ("performance", "max_speed_mps", True),
        ("mass", "max_takeoff_kg", True),
    ],
)
def test_vehicle_rejects_nonfinite_and_boolean_safety_numbers(
    section: str,
    field: str,
    invalid: object,
) -> None:
    payload = make_vehicle_payload()
    payload[section][field] = invalid
    with pytest.raises(ValidationError, match=field):
        VehicleProfile.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "invalid"),
    [
        (("planned_home", "lat"), True),
        (("planned_home", "altitude_amsl_m"), False),
        (("route", 0, "altitude_m"), True),
        (("constraints", "max_wind_mps"), True),
    ],
)
def test_mission_rejects_boolean_numeric_fields(
    path: tuple[object, ...],
    invalid: object,
) -> None:
    payload = make_mission_payload()
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = invalid  # type: ignore[index]
    with pytest.raises(ValidationError):
        MissionPlan.model_validate(payload)


def test_sora_footprint_rejects_boolean_distances() -> None:
    with pytest.raises(ValidationError, match="operational_volume_margin_m"):
        GroundRiskFootprint(
            operational_volume_margin_m=True,
            ground_risk_buffer_m=130.0,
            vertical_contingency_margin_m=10.0,
            maximum_height_agl_m=130.0,
            derivation="Test footprint",
        )


@pytest.mark.parametrize("invalid", [True, False, math.inf, math.nan])
def test_population_grid_rejects_boolean_or_nonfinite_cells(
    tmp_path: Path,
    invalid: object,
) -> None:
    path = tmp_path / "population.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "origin_lat": 52.0,
                "origin_lon": 4.0,
                "step_lat_deg": 0.01,
                "step_lon_deg": 0.01,
                "density_ppl_km2": [[0.0, invalid], [0.0, 0.0]],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PopulationGridLoadError, match="density_ppl_km2"):
        load_population_grid(path)
