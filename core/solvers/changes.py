"""nearest_item, lift_closed, add_door — questions about the nearest item, a closed lift and an added door.

Shared by the benchmark pipeline (core/solvers_v1.solve) and the Guide's `solve` tool, so both answer the same way.

nearest_item: every asset matching `item` (core/navigation.match_assets: id, type, name, then words), ranked by the
  route distance from `start` to the space holding it (route model `model` under `rules`, default the kit graph
  with no rules — the benchmark; stairs allowed unless `step_free`; `closed` names or ids shut; endpoint-only
  spaces, incl. `through: false`, never crossed); ties → smaller asset id. The Guide's find_nearest ranks items
  with it under its own model, rules and the user's profile, then routes to the nearest holders.
lift_closed: the spaces reachable without steps from `start` (default: where the lowest floor's entrances open
  into), inside the building — never round the outside — before and after `closed` (a lift's connector or its lift
  space) is shut; the lost ones, and the rooms and halls among them (not corridors, stairs or lifts).
add_door: a 0.9 m door at the middle of the wall `first` and `second` share (routing.with_new_door, on a copy), and
  the route between them before and after.
"""

from collections import deque

from core import navigation, route_models
from core.building_map import OUTSIDE, BuildingMap, MapError
from core.solvers import SolverResult, solver
from core.solvers.reachability import adjacency
from core.solvers.routing import with_new_door

CIRCULATION = {"corridor", "stair", "lift", "outdoor"}


@solver("nearest_item")
def nearest_item(building: BuildingMap, start: str, item: str, step_free: bool = False,
                 closed: list[str] | tuple[str, ...] = (), model: str = route_models.KIT,
                 rules: route_models.RouteRules = route_models.NO_RULES, **_) -> SolverResult:
    _, assets = navigation.match_assets(building, item)
    if not assets:
        raise ValueError(f"No item matching '{item}' in this building.")
    view = navigation.routing_view(building, closed)
    graph = route_models.route_graph(view, step_free, model, rules)
    distances = route_models.single_source(graph, route_models.endpoint_only(view, rules), start)
    ranking = sorted(
        (round(distances[asset["space_id"]], 2), asset["id"])
        for asset in assets
        if asset["space_id"] in distances
    )
    if not ranking:
        raise MapError(f"No '{item}' can be reached from {building.describe_space(start)}.")
    length, asset_id = ranking[0]
    asset = building.assets[asset_id]
    return SolverResult(
        kind="nearest_item",
        value=asset_id,
        unit="m",
        explanation=[f"Nearest by walking: {asset['name']} ({asset_id}) in {building.describe_space(asset['space_id'])}, "
                     f"{length:.2f} m from {building.describe_space(start)}."],
        evidence={
            "start": start,
            "asset_id": asset_id,
            "asset_name": asset["name"],
            "space_id": asset["space_id"],
            "length_m": length,
            "step_free": step_free,
            "closed": sorted(view.closed),
            "ranking": [{"asset_id": other, "space_id": building.assets[other]["space_id"], "length_m": metres}
                        for metres, other in ranking[:5]],
            "holders": list(dict.fromkeys(building.assets[other]["space_id"] for _, other in ranking)),
        },
    )


def ground_entrance_spaces(building: BuildingMap) -> list[str]:
    """The spaces the entrances on the lowest floor that has any open into."""
    inside = [(building.floors[building.spaces[space_id]["floor_id"]]["level"], space_id)
              for opening in building.openings.values() if opening["kind"] == "entrance"
              for space_id in opening["space_ids"] if space_id != OUTSIDE]
    lowest = min((level for level, _ in inside), default=None)
    return sorted({space_id for level, space_id in inside if level == lowest})


def reachable_inside(building: BuildingMap, starts: list[str], closed: list[str]) -> set[str]:
    """Spaces reachable without steps from `starts` inside the building (no way round through `outside`)."""
    graph = adjacency(building, step_free=True, closed=closed)
    seen = {start for start in starts if start in graph}
    queue = deque(seen)
    while queue:
        for neighbour in graph[queue.popleft()]:
            if neighbour != OUTSIDE and neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen


@solver("lift_closed")
def lift_closed(building: BuildingMap, closed: str, start: str | None = None, **_) -> SolverResult:
    starts = [start] if start else ground_entrance_spaces(building)
    before = reachable_inside(building, starts, [])
    after = reachable_inside(building, starts, [closed])
    lost = sorted(before - after)
    rooms = [space_id for space_id in lost if building.spaces[space_id]["type"] not in CIRCULATION]
    floors = sorted({building.spaces[space_id]["floor_id"] for space_id in rooms},
                    key=lambda floor_id: building.floors[floor_id]["level"])
    name = building.connectors[closed]["name"] if closed in building.connectors else building.spaces[closed]["name"]
    where = ", ".join(building.floor_name(floor_id) for floor_id in floors) or "no floor"
    return SolverResult(
        kind="lift_closed",
        value=len(rooms),
        unit="rooms",
        explanation=[f"With {name} closed, {len(rooms)} rooms can no longer be reached without stairs from the "
                     f"entrance ({where}); the stairs still reach them."],
        evidence={"closed": closed, "rooms": rooms, "spaces": lost, "floors": floors},
    )


@solver("add_door")
def add_door(building: BuildingMap, first: str, second: str, **_) -> SolverResult:
    before = building.route(first, second)
    changed, opening = with_new_door(building, first, second)
    after = changed.route(first, second)
    return SolverResult(
        kind="add_door",
        value=after.length_m,
        unit="m",
        explanation=[
            f"New 0.9 m door between {building.describe_space(first)} and {building.describe_space(second)} at "
            f"({opening['position'][0]:.2f}, {opening['position'][1]:.2f}), the middle of their shared wall.",
            f"The walk between them goes from {before.length_m:.2f} m to {after.length_m:.2f} m.",
        ],
        evidence={
            "door": {"space_ids": [first, second], "floor_id": opening["floor_id"],
                     "position": opening["position"], "width_m": opening["width_m"]},
            "length_before_m": before.length_m,
            "length_after_m": after.length_m,
            "space_path": after.space_path,
            "steps": after.steps,
        },
    )
