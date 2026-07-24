"""Apply a calibration profile to a base vehicle.

Opt-in and non-destructive: a calibration overrides only the fields it carries,
on a copy of the base vehicle. With no calibration the base vehicle is used
unchanged — callers simply skip this seam.
"""

from __future__ import annotations

from bvlos_sim.schemas.calibration import CalibrationProfile
from bvlos_sim.schemas.vehicle import VehicleProfile
from bvlos_sim.schemas.vehicle_enums import CalibrationStatus


class CalibrationMismatchError(ValueError):
    """Raised when a calibration profile does not match the base vehicle."""

    def __init__(self, *, base_vehicle_id: str, calibration_vehicle_id: str) -> None:
        super().__init__(
            f"calibration base_vehicle_id ({calibration_vehicle_id}) does not match "
            f"vehicle_id ({base_vehicle_id})"
        )
        self.base_vehicle_id = base_vehicle_id
        self.calibration_vehicle_id = calibration_vehicle_id


def apply_calibration(
    vehicle: VehicleProfile, calibration: CalibrationProfile
) -> VehicleProfile:
    """Return a copy of ``vehicle`` with calibrated performance fields overridden.

    The calibration must target this vehicle: ``calibration.base_vehicle_id`` has
    to equal ``vehicle.vehicle_id`` (raises ``CalibrationMismatchError`` otherwise,
    mirroring the existing vehicle-id mismatch rejection). The merged profile is
    re-validated through ``VehicleProfile``, so an override that breaks an
    invariant (for example a calibrated cruise speed above ``max_speed_mps``)
    raises a ``ValidationError`` rather than producing an invalid vehicle.

    Applying a profile that carries parameters also stamps
    ``calibration_status`` as ``log_calibrated``: the coefficients now come from
    a fitted flight trace, which is exactly what
    ``ENERGY_MODEL_UNCALIBRATED`` asks for. An empty profile changes nothing,
    so it must not clear the warning either.
    """
    if calibration.base_vehicle_id != vehicle.vehicle_id:
        raise CalibrationMismatchError(
            base_vehicle_id=vehicle.vehicle_id,
            calibration_vehicle_id=calibration.base_vehicle_id,
        )

    if not calibration.parameters:
        return vehicle

    data = vehicle.model_dump(mode="python")
    performance = data["performance"]
    for record in calibration.parameters:
        performance[record.parameter.value] = record.fitted_value
    data["calibration_status"] = CalibrationStatus.LOG_CALIBRATED
    return VehicleProfile.model_validate(data)


__all__ = [
    "CalibrationMismatchError",
    "apply_calibration",
]
