"""Registry and dispatch for route-item executors."""

from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
from estimator.core.enums import LegPhase
from estimator.execution.executors.base import RouteActionExecutor
from estimator.execution.executors.loiter_action import LoiterTimeActionExecutor
from estimator.execution.executors.rtl_action import RtlActionExecutor
from estimator.execution.executors.transit_action import TransitActionExecutor
from estimator.execution.runtime import EstimationContext
from schemas.mission import MissionAction
from schemas.mission import ROUTE_ACTION_REQUIREMENTS
from schemas.mission import RouteItemInvariantError
from schemas.mission import RouteItem
from schemas.mission import validate_route_item_invariants

ACTION_EXECUTORS: dict[MissionAction, RouteActionExecutor] = {
    MissionAction.TAKEOFF: TransitActionExecutor(
        phase=LegPhase.VERTICAL_TAKEOFF,
        require_hover=True,
    ),
    MissionAction.VTOL_TAKEOFF: TransitActionExecutor(
        phase=LegPhase.VERTICAL_TAKEOFF,
        require_hover=True,
    ),
    MissionAction.WAYPOINT: TransitActionExecutor(phase=LegPhase.TRANSIT),
    MissionAction.LOITER_TIME: LoiterTimeActionExecutor(),
    MissionAction.LAND: TransitActionExecutor(phase=LegPhase.LANDING_TRANSIT),
    MissionAction.RTL: RtlActionExecutor(),
}


def _validate_executor_coverage() -> None:
    supported_actions = set(MissionAction)
    registered_actions = set(ACTION_EXECUTORS)
    schema_actions = set(ROUTE_ACTION_REQUIREMENTS)
    if supported_actions != schema_actions or supported_actions != registered_actions:
        missing_schema_actions = sorted(
            action.value for action in supported_actions - schema_actions
        )
        missing_executor_actions = sorted(
            action.value for action in supported_actions - registered_actions
        )
        extra_schema_actions = sorted(action.value for action in schema_actions - supported_actions)
        extra_executor_actions = sorted(
            action.value for action in registered_actions - supported_actions
        )
        raise RuntimeError(
            "MissionAction, ROUTE_ACTION_REQUIREMENTS, and ACTION_EXECUTORS must stay aligned. "
            f"missing_schema={missing_schema_actions} "
            f"missing_executors={missing_executor_actions} "
            f"extra_schema={extra_schema_actions} "
            f"extra_executors={extra_executor_actions}"
        )


_validate_executor_coverage()


def execute_route_item(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> None:
    """Dispatch a route item to its action-specific executor."""

    try:
        validate_route_item_invariants(item)
    except RouteItemInvariantError as exc:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message=str(exc),
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={
                "action": item.action.value,
                "route_item_invariant": exc.reason.value,
            },
        )

    ACTION_EXECUTORS[item.action].execute(
        context,
        item,
        route_item_index=route_item_index,
    )
