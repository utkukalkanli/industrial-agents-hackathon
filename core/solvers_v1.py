"""Deterministic solvers for the benchmark question kinds.

Every function takes a BuildingMap plus ids (the same ids as a question's `inputs`) and returns plain
data. The agent's job is only to turn a question's names into these ids."""

import math

import networkx as nx
from shapely.geometry import Polygon

from core.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap, MapError
from core.route_query import route_query
from core.solvers import solve as shared_solve

ROOM = "room"
WALL_TOLERANCE_M = 0.35
MIN_SHARED_WALL_M = 1.0
WHAT_IF_MIN_GAIN_M = 1.0
WALL_NEIGHBOUR_TYPES = {"room", "hall"}  # verified on train+dev: corridors, stairs, lifts and outdoor don't count


def polygon(bmap: BuildingMap, space_id: str) -> Polygon:
    return Polygon(bmap.spaces[space_id]["polygon"])


def area(bmap: BuildingMap, space_id: str) -> float:
    return polygon(bmap, space_id).area


def level_of(bmap: BuildingMap, floor_id: str) -> int:
    return bmap.floors[floor_id]["level"]


def spaces_on(bmap: BuildingMap, floor_id: str, room_type: str | None = None, rooms_only: bool = False):
    return [
        space
        for space in bmap.spaces.values()
        if space["floor_id"] == floor_id
        and (room_type is None or space["room_type"] == room_type)
        and (not rooms_only or space["type"] == ROOM)
    ]


def label(bmap: BuildingMap, space_id: str) -> dict:
    space = bmap.spaces[space_id]
    return {"space_id": space_id, "name": space["name"], "ref": space.get("ref"),
            "floor": bmap.floor_name(space["floor_id"])}


# ---------- room geometry ----------

def largest_room(bmap: BuildingMap, floor_id: str, room_type: str) -> dict:
    ranked = sorted(spaces_on(bmap, floor_id, room_type), key=lambda s: area(bmap, s["id"]), reverse=True)
    if not ranked:
        raise ValueError(f"no {room_type} on {floor_id}")
    best = ranked[0]
    return {**label(bmap, best["id"]), "area_m2": round(area(bmap, best["id"]), 2)}


def floor_area_total(bmap: BuildingMap, floor_id: str, room_type: str) -> dict:
    members = spaces_on(bmap, floor_id, room_type)
    return {"count": len(members), "total_m2": round(sum(area(bmap, s["id"]) for s in members), 2)}


def shared_walls(bmap: BuildingMap, start: str) -> dict:
    """Rooms on the same floor with >= 1 m of outline within 0.35 m of this room's outline."""
    own = polygon(bmap, start)
    band = own.exterior.buffer(WALL_TOLERANCE_M)
    neighbours = []
    for space in spaces_on(bmap, bmap.spaces[start]["floor_id"]):
        if space["id"] == start or space["type"] not in WALL_NEIGHBOUR_TYPES:
            continue
        other = Polygon(space["polygon"])
        shared = max(other.exterior.intersection(band).length,
                     own.exterior.intersection(other.exterior.buffer(WALL_TOLERANCE_M)).length)
        if shared >= MIN_SHARED_WALL_M:
            neighbours.append({**label(bmap, space["id"]), "shared_m": round(shared, 2)})
    return {"count": len(neighbours), "rooms": neighbours}


def room_stacked(bmap: BuildingMap, start: str, direction: str) -> dict:
    floor = bmap.floors[bmap.spaces[start]["floor_id"]]
    step = 1 if direction == "above" else -1
    levels = sorted({f["level"] for f in bmap.floors.values()})
    target_levels = [lv for lv in levels if (lv - floor["level"]) * step > 0]
    if not target_levels:
        raise ValueError(f"no floor {direction} {floor['name']}")
    target_level = min(target_levels, key=lambda lv: abs(lv - floor["level"]))
    target_floor = next(f["id"] for f in bmap.floors.values() if f["level"] == target_level)
    own = polygon(bmap, start)
    ranked = sorted(
        ((own.intersection(Polygon(s["polygon"])).area, s["id"]) for s in spaces_on(bmap, target_floor)),
        reverse=True,
    )
    if not ranked or ranked[0][0] <= 0:
        raise ValueError(f"nothing {direction} {start}")
    return {**label(bmap, ranked[0][1]), "overlap_m2": round(ranked[0][0], 2)}


def straight_line_3d(bmap: BuildingMap, first: str, second: str) -> dict:
    points = []
    for space_id in (first, second):
        centre = polygon(bmap, space_id).centroid
        points.append((centre.x, centre.y, bmap.floors[bmap.spaces[space_id]["floor_id"]]["elevation_m"]))
    return {"distance_m": round(math.dist(*points), 2)}


# ---------- routing ----------

def distances_from(graph: nx.MultiGraph, source: str) -> dict[str, float]:
    if source not in graph:
        return {}
    return nx.single_source_dijkstra_path_length(graph, source, weight="weight")


def errand(bmap: BuildingMap, start: str, asset_type: str, floor_id: str, room_type: str,
           step_free: bool = False) -> dict:
    """step_free=False: "I can carry it on the stairs" (all train/dev questions); True if they can't."""
    graph = bmap.graph(step_free=step_free)
    from_start = distances_from(graph, start)
    holders = {a["space_id"] for a in bmap.assets.values() if a["type"] == asset_type}
    reachable = [(from_start[s], s) for s in holders if s in from_start]
    if not reachable:
        raise ValueError(f"no reachable room with a {asset_type}")
    first_leg, via = min(reachable)
    target = largest_room(bmap, floor_id, room_type)["space_id"]
    second_leg = distances_from(graph, via).get(target)
    if second_leg is None:
        raise ValueError("target unreachable")
    legs = [bmap.leg(graph, nodes, length)
            for length, nodes in (nx.single_source_dijkstra(graph, start, via, weight="weight"),
                                  nx.single_source_dijkstra(graph, via, target, weight="weight"))]
    return {"via": label(bmap, via), "target": label(bmap, target),
            "first_leg_m": round(first_leg, 2), "second_leg_m": round(second_leg, 2),
            "total_m": round(first_leg + second_leg, 2), "legs": legs}


def reachable_rooms(bmap: BuildingMap, start: str, floor_id: str, step_free: bool = True,
                    min_width: float | None = None, closed: list[str] | None = None) -> dict:
    saved = set(bmap.closed)
    bmap.closed |= set(closed or [])
    try:
        graph = bmap.graph(step_free=step_free)
    finally:
        bmap.closed = saved
    if min_width is not None:
        graph.remove_nodes_from([DOOR_PREFIX + o["id"] for o in bmap.openings.values() if o["width_m"] < min_width])
    reached = nx.node_connected_component(graph, start) if start in graph else set()
    rooms = [s["id"] for s in spaces_on(bmap, floor_id, rooms_only=True) if s["id"] in reached]
    return {"count": len(rooms), "rooms": [label(bmap, r)["name"] for r in rooms]}


def shared_wall_midpoint(bmap: BuildingMap, first: str, second: str) -> tuple[float, float]:
    a, b = polygon(bmap, first), polygon(bmap, second)
    wall = a.exterior.intersection(b.exterior.buffer(WALL_TOLERANCE_M))
    if wall.is_empty or wall.length == 0:
        raise ValueError(f"{first} and {second} do not share a wall")
    if wall.geom_type == "MultiLineString":
        wall = max(wall.geoms, key=lambda g: g.length)
    middle = wall.interpolate(0.5, normalized=True)
    # move onto the midpoint between the two outlines
    other = b.exterior.interpolate(b.exterior.project(middle))
    return ((middle.x + other.x) / 2, (middle.y + other.y) / 2)


def exit_distances(bmap: BuildingMap, floor_id: str) -> dict[str, float]:
    graph = bmap.graph(step_free=False, outside=True)
    from_outside = distances_from(graph, OUTSIDE)
    return {s["id"]: from_outside.get(s["id"], math.inf) for s in spaces_on(bmap, floor_id, rooms_only=True)}


def what_if_door(bmap: BuildingMap, first: str, second: str, floor_id: str, door_floor_id: str | None = None) -> dict:
    before = exit_distances(bmap, floor_id)
    position = shared_wall_midpoint(bmap, first, second)
    opening_id = f"{bmap.spaces[first]['floor_id']}-O-whatif"
    bmap.openings[opening_id] = {"id": opening_id, "floor_id": bmap.spaces[first]["floor_id"],
                                 "space_ids": [first, second], "kind": "door", "position": list(position),
                                 "width_m": 0.9, "step_free": True, "synthetic": True}
    try:
        after = exit_distances(bmap, floor_id)
    finally:
        del bmap.openings[opening_id]
    improved = [s for s in before if before[s] - after[s] > WHAT_IF_MIN_GAIN_M]
    return {"count": len(improved), "rooms": [label(bmap, s)["name"] for s in improved]}


# ---------- warm-up kinds (questions_basic.jsonl) ----------

def locate(bmap: BuildingMap, asset_type: str) -> dict:
    found = sorted((a for a in bmap.assets.values() if a["type"] == asset_type), key=lambda a: a["id"])
    if not found:
        raise ValueError(f"no {asset_type} in this building")
    asset = found[0]
    return {"asset_id": asset["id"], "asset_name": asset["name"], **label(bmap, asset["space_id"]),
            "floor_level": level_of(bmap, asset["floor_id"]), "position": asset["position"],
            "others": [a["id"] for a in found[1:]]}


def count_assets(bmap: BuildingMap, asset_type: str, floor_id: str) -> dict:
    return {"count": sum(a["type"] == asset_type and a["floor_id"] == floor_id for a in bmap.assets.values()),
            "asset_type": asset_type, "floor_level": level_of(bmap, floor_id)}


def route(bmap: BuildingMap, start: str, destination: str, step_free: bool = False,
          closed: str | None = None, via: list[str] | None = None) -> dict:
    """Shortest route in the kit's route model; `reachable: False` when closures or step-free rules cut it off."""
    saved = set(bmap.closed)
    bmap.closed |= {closed} if closed else set()
    try:
        result = bmap.route(start, destination, step_free=step_free, via=via)
    except MapError as error:
        return {"reachable": False, "from_space_id": start, "to_space_id": destination, "reason": str(error)}
    finally:
        bmap.closed = saved
    return {"reachable": True, "from_space_id": start, "to_space_id": destination,
            "optimal_length_m": result.length_m, "space_path": result.space_path,
            "element_path": result.element_path, "legs": result.legs, "steps": result.steps}


SOLVERS = {
    "largest_room": largest_room,
    "floor_area_total": floor_area_total,
    "shared_walls_count": shared_walls,
    "room_stacked": room_stacked,
    "straight_line_3d": straight_line_3d,
    "errand": errand,
    "what_if_door": what_if_door,
    "locate": locate,
    "count": count_assets,
}


def solve(bmap: BuildingMap, kind: str, inputs: dict) -> dict:
    """Oracle entry point: run the solver for a question kind on its `inputs`."""
    if kind == "wide_delivery_count":
        return reachable_rooms(bmap, inputs["start"], inputs["floor_id"], step_free=True,
                               min_width=inputs["min_width"])
    if kind == "step_free_reachable_count":
        return reachable_rooms(bmap, inputs["start"], inputs["floor_id"], step_free=True,
                               closed=[inputs["closed"]])
    if kind in ("route", "route_step_free", "route_with_closure"):
        return route(bmap, inputs["start"], inputs["destination"], step_free=kind == "route_step_free",
                     closed=inputs.get("closed"))
    if kind == "tour":
        return route(bmap, inputs["stops"][0], inputs["stops"][-1], via=inputs["stops"][1:-1])
    if kind in ("nearest_item", "lift_closed", "add_door"):  # shared with the Guide's solve tool (core/solvers)
        result = shared_solve(bmap, kind, inputs)
        return {"value": result.value, "explanation": result.explanation, **result.evidence}
    if kind == "route_query":  # reworded route questions with combined constraints (agent/llm_parser.py)
        return route_query(bmap, inputs["stops"], step_free=inputs.get("step_free", False),
                           forklift=inputs.get("forklift", False), min_width=inputs.get("min_width"),
                           closed=inputs.get("closed", ()))
    return SOLVERS[kind](bmap, **inputs)
