"""Pure, chained schema-migration registry."""

from collections.abc import Callable
from copy import deepcopy

Migration = Callable[[dict[str, object]], dict[str, object]]

_REGISTRY: dict[tuple[str, str], tuple[str, Migration]] = {}


def register_migration(
    schema_name: str,
    *,
    from_version: str,
    to_version: str,
) -> Callable[[Migration], Migration]:
    """Register one forward-only migration edge."""

    def decorator(function: Migration) -> Migration:
        key = (schema_name, from_version)
        if key in _REGISTRY:
            raise RuntimeError(f"duplicate migration for {schema_name} {from_version}")
        _REGISTRY[key] = (to_version, function)
        return function

    return decorator


def migrate_payload(
    schema_name: str,
    payload: dict[str, object],
    *,
    from_version: str,
    target_version: str,
) -> dict[str, object]:
    """Apply registered migration edges until ``target_version`` is reached."""

    migrated = deepcopy(payload)
    version = from_version
    visited: set[str] = set()
    while version != target_version:
        if version in visited:
            raise ValueError(f"migration cycle detected at {schema_name} {version}")
        visited.add(version)
        step = _REGISTRY.get((schema_name, version))
        if step is None:
            raise ValueError(
                f"no migration path for {schema_name} {version} to {target_version}"
            )
        next_version, function = step
        migrated = function(migrated)
        version = next_version
    return migrated


__all__ = ["migrate_payload", "register_migration"]
