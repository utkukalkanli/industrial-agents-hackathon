"""Deterministic core: load a building.json, search it, route through it, edit it.

Extracted from the organiser starter kit (archive/initial-repo/starter_agent/building_map.py). The route model is
the kit 1.1.0 one the judges grade with and the expected answers use (README §3, docs/kit/route-model.md): walking
inside a space goes door to door, 15 cm off the walls and round corners; a door lands 30 cm inside each space;
stairs cost 2 m per metre climbed, a lift ride 15 m once plus 1 m per metre climbed; no way round the outside.
Geometry helpers and `graph` are the starter's code unchanged — keep them exact.
The agent is only the conversation layer; every fact it states comes from this module."""

import itertools
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

OUTSIDE = "outside"
DOOR_PREFIX = "door:"
LIFT = "lift"
# Vertical movement in equivalent walking metres per metre of height (floors' elevation_m), the grading rule.
STAIRS_M_PER_RISE = 2.0
LIFT_FIXED_M = 15.0
LIFT_M_PER_RISE = 1.0
# Walking inside a space: stay 15 cm off the walls; a door lands 30 cm inside the space.
WALL_CLEARANCE_M = 0.15
DOOR_LANDING_M = 0.30
NARROW_LANDING_M = 0.05
COVER_TOLERANCE_M = 0.02
BLOCKED_DETOUR_FACTOR = 1.5  # used when no clear walk exists between two points of a space
LENGTH_DECIMALS = 3
MAX_SEARCH_RESULTS = 15
ADJACENT_DISTANCE_M = 0.6
NEW_DOOR_WIDTH_M = 0.9


Point2 = tuple[float, float]
# Walking lengths per space, keyed by (space id, outline, openings): see BuildingMap.space_walks.
_WALKS: dict[tuple, list[tuple[str, str, float]]] = {}


# ---------- geometry (starter kit 1.1.0, unchanged) ----------


def entrance_key(text: str) -> str:
    """"Dock 1", "dock 01" and "DOCK01" → "dock 1": lower-case letter and number runs, numbers without leading zeros."""
    return " ".join(str(int(run)) if run.isdigit() else run for run in re.findall(r"[a-z]+|\d+", text.lower()))


def outline(points: list[Point2]) -> Polygon:
    polygon = Polygon(points)
    return polygon if polygon.is_valid else polygon.buffer(0)


def door_landing(polygon: Polygon, position: Point2) -> Point2:
    """Where a door at `position` lands inside the space: 30 cm in from the walls."""
    inner = polygon.buffer(-DOOR_LANDING_M)
    if inner.is_empty:
        inner = polygon.buffer(-NARROW_LANDING_M)
    if inner.is_empty:
        point = polygon.representative_point()
        return (point.x, point.y)
    if inner.contains(Point(position)):
        return (position[0], position[1])
    landing = nearest_points(inner, Point(position))[0]
    return (landing.x, landing.y)


def visibility_matrix(allowed: Polygon, nodes: list[Point2]) -> np.ndarray:
    """Straight-line lengths between nodes that see each other inside `allowed`, infinite where blocked."""
    coordinates = np.asarray(nodes, dtype=float)
    straight = np.hypot(*(coordinates[:, None, :] - coordinates[None, :, :]).transpose(2, 0, 1))
    first, second = np.triu_indices(len(nodes), k=1)
    shapely.prepare(allowed)
    clear = shapely.covers(
        allowed, shapely.linestrings(np.stack([coordinates[first], coordinates[second]], axis=1))
    )
    usable = clear | (straight[first, second] == 0)
    matrix = np.full(straight.shape, np.inf)
    np.fill_diagonal(matrix, 0.0)
    matrix[first[usable], second[usable]] = straight[first[usable], second[usable]]
    matrix[second[usable], first[usable]] = straight[first[usable], second[usable]]
    return matrix


def shortest_lengths(matrix: np.ndarray) -> np.ndarray:
    """All-pairs shortest path lengths (Floyd-Warshall)."""
    for middle in range(len(matrix)):
        matrix = np.minimum(matrix, matrix[:, middle, None] + matrix[None, middle, :])
    return matrix


def walking_lengths(polygon: Polygon, points: list[Point2]) -> dict[tuple[int, int], float]:
    """Shortest walks between points inside a space, 15 cm off the walls and round its corners: a
    visibility graph over the points and the corners of the walkable area."""
    walkable = polygon.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = polygon
    allowed = walkable.buffer(COVER_TOLERANCE_M)
    corners = [
        corner for ring in [walkable.exterior, *walkable.interiors] for corner in list(ring.coords)[:-1]
    ]
    walks = shortest_lengths(visibility_matrix(allowed, list(points) + corners))
    lengths = {}
    for source in range(len(points)):
        for target in range(len(points)):
            walk = float(walks[source, target])
            fallback = math.dist(points[source], points[target]) * BLOCKED_DETOUR_FACTOR
            lengths[(source, target)] = walk if math.isfinite(walk) else fallback
    return lengths


def connector_cost(connector: dict, rise_m: float) -> float:
    """Stairs 2 m per metre climbed; a lift ride 15 m once plus 1 m per metre climbed."""
    if connector["kind"] == LIFT:
        return LIFT_FIXED_M + LIFT_M_PER_RISE * abs(rise_m)
    return STAIRS_M_PER_RISE * abs(rise_m)


# ---------- route paths ----------


def cheapest(graph: nx.MultiGraph, first: str, second: str) -> dict:
    return min(graph[first][second].values(), key=lambda edge: edge["weight"])


def expand(graph: nx.MultiGraph, nodes: list[str]) -> tuple[list[str], nx.MultiGraph]:
    """A Dijkstra node path → (space/door node path, graph of the hops walked), for directions and paths.

    Every hop of the result has `via` (the opening or connector) and alternates spaces and doors: a door–door walk
    inside space S becomes door → S (0 m) → door (the metres walked in S), so a corridor crossed door to door shows
    up as a space, and directions report the walk when leaving S."""
    walked = nx.MultiGraph()
    expanded = [nodes[0]]

    def hop(first: str, second: str, weight: float, via: str) -> None:
        walked.add_edge(first, second, weight=weight, via=via)
        expanded.append(second)

    for first, second in itertools.pairwise(nodes):
        edge = cheapest(graph, first, second)
        space = edge.get("space")
        door = first if first.startswith(DOOR_PREFIX) else second
        if space is None:  # stairs, lift, or the outside link
            hop(first, second, edge["weight"], edge["via"])
        elif space in (first, second):  # the space's own centre point to one of its doors
            hop(first, second, edge["weight"], door.removeprefix(DOOR_PREFIX))
        else:
            hop(first, space, 0.0, first.removeprefix(DOOR_PREFIX))
            hop(space, second, edge["weight"], second.removeprefix(DOOR_PREFIX))
    return expanded, walked


def path_parts(graph: nx.MultiGraph, nodes: list[str]) -> tuple[list[str], list[str]]:
    """(space_path, element_path) of a Dijkstra node path in the kit 1.1.0 answer format: every space passed in
    order (incl. corridors crossed door to door, "outside" when it is an endpoint), each opening once, each stair
    flight / lift ride once."""
    expanded, walked = expand(graph, nodes)
    spaces: list[str] = []
    for node in expanded:
        if not node.startswith(DOOR_PREFIX) and (not spaces or spaces[-1] != node):
            spaces.append(node)
    elements: list[str] = []
    for first, second in itertools.pairwise(expanded):
        if second.startswith(DOOR_PREFIX):
            elements.append(second.removeprefix(DOOR_PREFIX))
        elif not first.startswith(DOOR_PREFIX):
            elements.append(cheapest(walked, first, second)["via"])  # space → space: stairs or lift
    return spaces, elements


class MapError(ValueError):
    """Raised for anything the user should be told about (unknown place, no route, ...)."""


@dataclass
class RouteResult:
    start_space_id: str
    destination_space_id: str
    length_m: float
    space_path: list[str]
    steps: list[str]
    step_free: bool
    closed: list[str] = field(default_factory=list)
    element_path: list[str] = field(default_factory=list)
    legs: list[dict] = field(default_factory=list)


class BuildingMap:
    def __init__(self, building: dict) -> None:
        self.data = building
        self.floors = {floor["id"]: floor for floor in building["floors"]}
        self.spaces = {space["id"]: space for space in building["spaces"]}
        self.assets = {asset["id"]: asset for asset in building["assets"]}
        self.connectors = {connector["id"]: connector for connector in building["vertical_connectors"]}
        self.openings = {opening["id"]: opening for opening in building["openings"]}
        self.closed: set[str] = set()
        self.last_route: RouteResult | None = None
        self.located_asset_ids: list[str] = []

    @classmethod
    def load(cls, path: Path) -> "BuildingMap":
        building_file = path / "building.json" if path.is_dir() else path
        return cls(json.loads(building_file.read_text(encoding="utf-8")))

    # ---------- descriptions ----------

    def floor_name(self, floor_id: str) -> str:
        return self.floors[floor_id]["name"]

    def describe_space(self, space_id: str) -> str:
        space = self.spaces[space_id]
        return f"{space['name']} [{space_id}] on {self.floor_name(space['floor_id'])}"

    def overview(self) -> dict:
        info = self.data["building"]
        floors = []
        for floor in sorted(self.floors.values(), key=lambda item: item["level"]):
            rooms = [space for space in self.spaces.values() if space["floor_id"] == floor["id"]]
            floors.append({"level": floor["level"], "name": floor["name"], "spaces": len(rooms)})
        return {
            "name": info["name"],
            "source": info["source"],
            "floors": floors,
            "stairs_and_lifts": [
                {
                    "id": connector["id"],
                    "name": connector["name"],
                    "kind": connector["kind"],
                    "floors": [self.floor_name(floor_id) for floor_id in connector["floor_ids"]],
                }
                for connector in self.connectors.values()
            ],
            "entrances": [
                {
                    "id": opening["id"],
                    "into": self.describe_space(self.other_side(opening, OUTSIDE)),
                    "step_free": opening["step_free"],
                }
                for opening in self.openings.values()
                if OUTSIDE in opening["space_ids"]
            ],
            "asset_count": len(self.assets),
            "closed": sorted(self.closed),
        }

    @staticmethod
    def other_side(opening: dict, space_id: str) -> str:
        first, second = opening["space_ids"]
        return second if first == space_id else first

    # ---------- search ----------

    def entrance_spaces(self, phrase: str) -> list[str]:
        """Spaces an entrance (a dock is one) opens into, for a phrase naming it by `name` or by id: "Dock 1" fits
        id DOCK01 (letters and numbers compared, leading zeros dropped). Empty when no entrance fits."""
        wanted = entrance_key(phrase)
        return sorted({
            space_id
            for opening in self.openings.values()
            if opening["kind"] == "entrance" and wanted in (entrance_key(opening["id"]), entrance_key(opening.get("name", "")))
            for space_id in opening["space_ids"] if space_id != OUTSIDE
        }) if wanted else []

    def search(self, query: str, floor_level: int | None = None) -> list[dict]:
        """Spaces and assets whose name, ref or type contains every word of the query."""
        words = [word for word in query.lower().replace("_", " ").split() if word]
        results = []
        for space in self.spaces.values():
            room_type = space["room_type"].replace("_", " ")
            text = f"{space['name']} {space.get('ref') or ''} {room_type} {space['id']}"
            if self.matches(text, words, space["floor_id"], floor_level):
                results.append(
                    {
                        "kind": "space",
                        "id": space["id"],
                        "name": space["name"],
                        "room_type": space["room_type"],
                        "floor": self.floor_name(space["floor_id"]),
                    }
                )
        for asset in self.assets.values():
            text = f"{asset['name']} {asset['type'].replace('_', ' ')} {asset['id']}"
            if self.matches(text, words, asset["floor_id"], floor_level):
                results.append(
                    {
                        "kind": "asset",
                        "id": asset["id"],
                        "name": asset["name"],
                        "type": asset["type"],
                        "in": self.describe_space(asset["space_id"]),
                    }
                )
        if any(result["kind"] == "asset" for result in results):
            self.located_asset_ids = [result["id"] for result in results if result["kind"] == "asset"]
        return results

    def matches(self, text: str, words: list[str], floor_id: str, floor_level: int | None) -> bool:
        if floor_level is not None and self.floors[floor_id]["level"] != floor_level:
            return False
        lowered = text.lower()
        return all(word in lowered for word in words)

    def resolve_space(self, reference: str) -> str:
        """Accept a space id, asset id, exact room ref/name or asset name; return a space id."""
        if reference in self.spaces:
            return reference
        if reference in self.assets:
            return self.assets[reference]["space_id"]
        lowered = reference.strip().lower()
        exact_spaces = [
            space["id"]
            for space in self.spaces.values()
            if lowered in ((space.get("ref") or "").lower(), space["name"].lower())
        ]
        if len(exact_spaces) == 1:
            return exact_spaces[0]
        exact_assets = [
            asset["space_id"] for asset in self.assets.values() if asset["name"].lower() == lowered
        ]
        if len(exact_assets) == 1:
            return exact_assets[0]
        candidates = self.search(reference)[:MAX_SEARCH_RESULTS]
        if not candidates:
            raise MapError(f"No place matches '{reference}'. Try search_building with fewer words.")
        raise MapError(
            f"'{reference}' is ambiguous or not exact. Use one of these ids: "
            + "; ".join(f"{item['id']} ({item['name']})" for item in candidates)
        )

    # ---------- routing ----------

    def anchor(self, space_id: str) -> Point2:
        point = outline(self.spaces[space_id]["polygon"]).representative_point()
        return (point.x, point.y)

    def space_walks(self, space_id: str) -> list[tuple[str, str, float]]:
        """Walking lengths between the room's centre point and each of its doors, and between its doors.

        Cached by the space's geometry and openings (module-level `_WALKS`), so copies of a building, sessions and
        edits reuse them; an added door or changed outline is a new key."""
        space = self.spaces[space_id]
        doors = [
            (opening["id"], (opening["position"][0], opening["position"][1]))
            for opening in self.openings.values()
            if space_id in opening["space_ids"]
        ]
        key = (space_id, tuple(map(tuple, space["polygon"])), tuple(doors))
        if key not in _WALKS:
            polygon = outline(space["polygon"])
            members = [(space_id, self.anchor(space_id), 0.0)]
            for opening_id, position in doors:
                landing = door_landing(polygon, position)
                members.append((DOOR_PREFIX + opening_id, landing, math.dist(landing, position)))
            lengths = walking_lengths(polygon, [landing for _, landing, _ in members])
            _WALKS[key] = [
                (
                    members[first][0],
                    members[second][0],
                    lengths[(first, second)] + members[first][2] + members[second][2],
                )
                for first, second in itertools.combinations(range(len(members)), 2)
            ]
        return _WALKS[key]

    def graph(self, step_free: bool, outside: bool = False) -> nx.MultiGraph:
        """The kit 1.1.0 route graph (archive/initial-repo/starter_agent/building_map.py, built in the same order so
        Dijkstra breaks ties the same way). Walk edges inside a space carry `space`, stair/lift edges `via`.

        `outside=True` adds an `outside` node joined at 0 m to every open entrance — only for routes that start or
        end outside; never walk through it (no way round the outside, route_models.endpoint_only)."""
        # MultiGraph: a stair and a lift may join the same two spaces; both edges must be kept.
        graph = nx.MultiGraph()
        open_doors = {
            DOOR_PREFIX + opening["id"]
            for opening in self.openings.values()
            if opening["id"] not in self.closed and (opening["step_free"] or not step_free)
        }
        open_spaces = [space_id for space_id in self.spaces if space_id not in self.closed]
        graph.add_nodes_from(open_spaces)
        for space_id in open_spaces:
            for first, second, length in self.space_walks(space_id):
                if (first == space_id or first in open_doors) and second in open_doors:
                    graph.add_edge(first, second, weight=round(length, LENGTH_DECIMALS), space=space_id)
        levels = {floor_id: floor["level"] for floor_id, floor in self.floors.items()}
        elevations = {floor_id: floor["elevation_m"] for floor_id, floor in self.floors.items()}
        for connector in self.connectors.values():
            if connector["id"] in self.closed or (step_free and not connector["step_free"]):
                continue
            stops = sorted(
                zip(connector["floor_ids"], connector["space_ids"], strict=True),
                key=lambda stop: levels[stop[0]],
            )
            # A lift ride pays the fixed 15 m once however many floors it passes, so every pair of stops
            # gets an edge; stairs keep one edge per flight.
            is_lift = connector["kind"] == LIFT
            pairs = itertools.combinations(stops, 2) if is_lift else itertools.pairwise(stops)
            for (low_floor, low_space), (high_floor, high_space) in pairs:
                if low_space not in graph or high_space not in graph:
                    continue
                rise = abs(elevations[high_floor] - elevations[low_floor])
                graph.add_edge(
                    low_space, high_space, weight=round(connector_cost(connector, rise), LENGTH_DECIMALS),
                    via=connector["id"],
                )
        if outside:
            for opening in self.openings.values():
                door = DOOR_PREFIX + opening["id"]
                if OUTSIDE in opening["space_ids"] and door in graph:
                    graph.add_edge(OUTSIDE, door, weight=0.0, via=opening["id"])
        return graph

    @property
    def destination_only(self) -> frozenset[str]:
        """Spaces marked `through: false` (none in the kit data): a route may start or end there, never pass through."""
        return frozenset(space_id for space_id, space in self.spaces.items() if space.get("through") is False)

    def route(
        self, start: str, destination: str, step_free: bool = False, via: list[str] | None = None
    ) -> RouteResult:
        stops = [
            self.resolve_space(start),
            *[self.resolve_space(stop) for stop in via or []],
            self.resolve_space(destination),
        ]
        graph = self.graph(step_free)
        length = 0.0
        legs = []
        steps: list[str] = []
        for leg_start, leg_end in itertools.pairwise(stops):
            blocked = self.destination_only - {leg_start, leg_end}
            leg_graph = graph if not blocked else nx.subgraph_view(
                graph,
                filter_node=lambda node: node not in blocked,
                filter_edge=lambda u, v, k: graph[u][v][k].get("space") not in blocked,
            )
            try:
                leg_length, leg_nodes = nx.single_source_dijkstra(leg_graph, leg_start, leg_end, weight="weight")
            except (nx.NetworkXNoPath, nx.NodeNotFound) as error:
                reason = "step-free " if step_free else ""
                raise MapError(
                    f"No {reason}route from {self.describe_space(leg_start)} to "
                    f"{self.describe_space(leg_end)} with the current closures {sorted(self.closed)}."
                ) from error
            length += leg_length
            legs.append(self.leg(graph, leg_nodes, leg_length))
            walk_nodes, walked = expand(graph, leg_nodes)
            leg_steps = self.directions(walked, walk_nodes)
            steps += leg_steps if not steps else leg_steps[1:]
        result = RouteResult(
            start_space_id=stops[0],
            destination_space_id=stops[-1],
            length_m=round(length, 2),
            space_path=[stops[0], *(space for leg in legs for space in leg["space_path"][1:])],
            steps=steps,
            step_free=step_free,
            closed=sorted(self.closed),
            element_path=[element for leg in legs for element in leg["element_path"]],
            legs=legs,
        )
        self.last_route = result
        return result

    @staticmethod
    def edge(graph: nx.MultiGraph, first: str, second: str) -> dict:
        """The edge a shortest path uses between two nodes: the cheapest of any parallel ones (stair vs lift)."""
        return min(graph[first][second].values(), key=lambda candidate: candidate["weight"])

    def leg(self, graph: nx.MultiGraph, nodes: list[str], length: float) -> dict:
        """One stop-to-stop leg in the warm-up answer format (questions_basic.jsonl `route` / `tour` legs)."""
        space_path, element_path = path_parts(graph, nodes)
        return {
            "from_space_id": nodes[0],
            "to_space_id": nodes[-1],
            "optimal_length_m": round(length, 2),
            "space_path": space_path,
            "element_path": element_path,
        }

    def directions(self, graph: nx.MultiGraph, nodes: list[str]) -> list[str]:
        """Turn an expanded node path (`expand`: space, door, space, …) into followable steps: one line per room
        change or floor change."""
        steps = [f"Start in {self.describe_space(nodes[0])}."]
        walked = 0.0
        for previous, current in itertools.pairwise(nodes):
            edge = self.edge(graph, previous, current)
            walked += edge["weight"]
            element = edge["via"]
            if element in self.connectors:
                connector = self.connectors[element]
                verb = "Take" if connector["kind"] == LIFT else "Use"
                steps.append(
                    f"{verb} {connector['name']} ({connector['kind']}) to "
                    f"{self.floor_name(self.spaces[current]['floor_id'])}."
                )
                walked = 0.0
            elif current == OUTSIDE:
                steps.append(f"Walk about {walked:.0f} m and leave the building through the entrance.")
                walked = 0.0
            elif not current.startswith(DOOR_PREFIX):
                opening = self.openings[element]
                passage = "through the door" if opening["kind"] == "door" else "through the opening"
                steps.append(f"Walk about {walked:.0f} m {passage} into {self.spaces[current]['name']}.")
                walked = 0.0
        steps.append(f"You have arrived at {self.describe_space(nodes[-1])}.")
        return steps

    # ---------- changes ----------

    def find_element(self, reference: str) -> str:
        """Connector, opening or space id/name that can be closed."""
        if reference in self.connectors or reference in self.openings or reference in self.spaces:
            return reference
        lowered = reference.strip().lower()
        named = [
            connector["id"] for connector in self.connectors.values() if connector["name"].lower() == lowered
        ]
        if len(named) == 1:
            return named[0]
        return self.resolve_space(reference)

    def set_closed(self, reference: str, closed: bool) -> str:
        element = self.find_element(reference)
        if closed:
            self.closed.add(element)
        else:
            self.closed.discard(element)
        return element

    def add_door(self, first: str, second: str, step_free: bool = True) -> dict:
        first_id, second_id = self.resolve_space(first), self.resolve_space(second)
        first_space, second_space = self.spaces[first_id], self.spaces[second_id]
        if first_space["floor_id"] != second_space["floor_id"]:
            raise MapError("A door can only join two spaces on the same floor.")
        first_polygon, second_polygon = Polygon(first_space["polygon"]), Polygon(second_space["polygon"])
        if first_polygon.distance(second_polygon) > ADJACENT_DISTANCE_M:
            raise MapError(f"{first_space['name']} and {second_space['name']} do not share a wall.")
        point_a, point_b = nearest_points(first_polygon, second_polygon)
        opening = {
            "id": f"{first_space['floor_id']}-O-new{len(self.openings) + 1}",
            "floor_id": first_space["floor_id"],
            "space_ids": [first_id, second_id],
            "kind": "door",
            "position": [round((point_a.x + point_b.x) / 2, 3), round((point_a.y + point_b.y) / 2, 3)],
            "width_m": NEW_DOOR_WIDTH_M,
            "step_free": step_free,
            "synthetic": True,
        }
        self.openings[opening["id"]] = opening
        self.data["openings"].append(opening)
        return opening

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
