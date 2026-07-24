"""Value normalization helpers for SITL comparison reports."""

from collections.abc import Mapping

from bvlos_sim.schemas.sitl import SitlJsonValue


class _SitlComparisonValueCoercer:
    """Coerce loose artifact payload values into typed comparison values."""

    def json_value(self, value: object) -> SitlJsonValue:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Mapping):
            return {str(key): self.json_value(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self.json_value(item) for item in value]
        return str(value)

    def optional_string(self, value: object) -> str | None:
        return None if value is None else str(value)

    def integer_field(self, value: object, field_name: str) -> int | None:
        return (
            self.integer_value(value.get(field_name))
            if isinstance(value, Mapping)
            else None
        )

    def integer_value(self, value: object) -> int | None:
        match value:
            case bool():
                return None
            case int():
                return value
            case float() if value.is_integer():
                return int(value)
            case _:
                return None

    def float_value(self, value: object) -> float | None:
        match value:
            case bool():
                return None
            case int() | float():
                return float(value)
            case _:
                return None


__all__: list[str] = []
