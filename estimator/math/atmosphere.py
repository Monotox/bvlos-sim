"""Atmosphere helpers for closed-form energy scaling."""

_SEA_LEVEL_TEMPERATURE_K = 288.15
_SEA_LEVEL_PRESSURE_PA = 101_325.0
_TEMPERATURE_LAPSE_K_PER_M = 0.0065
_GRAVITY_MPS2 = 9.80665
_DRY_AIR_GAS_CONSTANT = 287.05287


def isa_air_density_kgm3(
    altitude_amsl_m: float,
    *,
    temperature_offset_c: float = 0.0,
) -> float:
    """Return ISA troposphere density in kg/m3 for a geometric altitude."""

    isa_temperature_k = (
        _SEA_LEVEL_TEMPERATURE_K - _TEMPERATURE_LAPSE_K_PER_M * altitude_amsl_m
    )
    pressure_pa = _SEA_LEVEL_PRESSURE_PA * (
        isa_temperature_k / _SEA_LEVEL_TEMPERATURE_K
    ) ** (_GRAVITY_MPS2 / (_DRY_AIR_GAS_CONSTANT * _TEMPERATURE_LAPSE_K_PER_M))
    actual_temperature_k = isa_temperature_k + temperature_offset_c
    return pressure_pa / (_DRY_AIR_GAS_CONSTANT * actual_temperature_k)


__all__ = ["isa_air_density_kgm3"]
