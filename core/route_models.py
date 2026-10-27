"""Route model and route rules for core/navigation.py — docs/kit/route-model.md, Q-014.

One route model: the kit 1.1.0 graph of `BuildingMap.graph` (door to door 15 cm off the walls, 30 cm door landings,
stairs 2 m per metre climbed, a lift ride 15 m + 1 m per metre), which reproduces every expected answer. `KIT` is
its name; `GEODESIC`, our pre-1.1.0 approximation of the same rule, is now an alias kept for callers. `route_graph`
adds an `outside` node at the entrances that is only ever a start or an end: no way round the outside (kit 1.1.0).

Rules (`RouteRules`; the organisers' route validity note, Q-014/Q-015 — NOT part of the kit 1.1.0 answers):
- production bays (factory halls: production, assembly, logistics, warehouse, additive zones, "bay") are
  destinations only — a leg may start or end in one but never pass through it;
- `no_outside`: kept for callers; outside is always endpoint-only now;
- forklift: openings ≥ 3 m wide only (every opening kind), no stairs, walkway-like spaces removed; lifts allowed
  (no width in the data) — UNVERIFIED, Q-014 (4).
Rules are hard filters: no route under them gives `reachable=False` with a reason, never a rule-breaking route."""

import itertools
import math
from dataclasses import dataclass

import networkx as nx

from core.building_map import DOOR_PREFIX, LIFT, OUTSIDE, BuildingMap, cheapest, connector_cost, expand  # noqa: F401 (re-exported)

KIT = "kit"
GEODESIC = "geodesic"  # alias of KIT since kit 1.1.0
MODELS = (KIT, GEODESIC)
FORKLIFT_MIN_WIDTH_M = 3.0
BAY_WORDS = {"production", "assembly", "logistics", "warehouse", "additive", "manufacturing", "bay", "bays"}
WALKWAY_WORDS = {"walkway", "walkways", "pedestrian", "footpath", "footway", "sidewalk", "gehweg", "fussweg"}


@dataclass(frozen=True)
class RouteRules:
    bays_destination_only: bool = False
    no_outside: bool = False
    forklift: bool = False

    def describe(self) -> list[str]:
        return [
            text
            for active, text in (
                (self.bays_destination_only, "production bays are destinations only"),
                (self.no_outside, "no shortcut outside the building"),
                (self.forklift, f"forklift: openings at least {FORKLIFT_MIN_WIDTH_M:g} m, no stairs, no walkways"),
            )
            if active
        ]


NO_RULES = RouteRules()
SUNDAY_RULES = RouteRules(bays_destination_only=True, no_outside=True)


def words(*texts: str) -> set[str]:
    return {word for text in texts for word in text.lower().replace("_", " ").replace("-", " ").split()}


def is_production_bay(space: dict) -> bool:
    """A factory hall by `type`/`room_type` words (production_zone, assembly_zone, …), or a hall named "… bay"."""
    if space["room_type"] == "lobby":
        return False
    if words(space["type"], space["room_type"]) & BAY_WORDS:
        return True
    return space["type"] == "hall" and bool(words(space["name"]) & BAY_WORDS)


def is_walkway(space: dict) -> bool:
    """A pedestrian walkway by `type`, `room_type` or name (none in the kit data; Sunday may add them)."""
    return bool(words(space["type"], space["room_type"], space["name"]) & WALKWAY_WORDS)


def endpoint_only(view: BuildingMap, rules: RouteRules) -> frozenset[str]:
    """Nodes a leg may start or end at but never pass through."""
    nodes = {OUTSIDE, *view.destination_only}
    if rules.bays_destination_only:
        nodes |= {space_id for space_id, space in view.spaces.items() if is_production_bay(space)}
    return frozenset(nodes)


# ---------- graphs ----------


def route_graph(view: BuildingMap, step_free: bool, model: str = KIT, rules: RouteRules = NO_RULES) -> nx.MultiGraph:
    """The routing graph (with the `outside` endpoint node) and the rules' global filters (forklift).
    Endpoint-only nodes: `leg_graph`."""
    if model not in MODELS:
        raise ValueError(f"Unknown route model '{model}' (use one of {', '.join(MODELS)}).")
    graph = view.graph(step_free, outside=True)
    if rules.forklift:
        walkways = {space_id for space_id, space in view.spaces.items() if is_walkway(space)}
        graph.remove_nodes_from(
            [DOOR_PREFIX + o["id"] for o in view.openings.values() if o["width_m"] < FORKLIFT_MIN_WIDTH_M]
            + list(walkways)
        )
        stairs = {c["id"] for c in view.connectors.values() if c["kind"] != LIFT}
        graph.remove_edges_from(  # stair flights, and door-to-door walks across a walkway
            [(u, v, k) for u, v, k, data in graph.edges(keys=True, data=True)
             if data.get("via") in stairs or data.get("space") in walkways]
        )
    return graph


def leg_graph(graph: nx.MultiGraph, endpoints_only: frozenset[str], start: str, end: str) -> nx.MultiGraph:
    """View of `graph` where endpoint-only nodes other than `start`/`end` are gone and can't be crossed inside."""
    blocked = endpoints_only - {start, end}
    if not blocked:
        return graph
    return nx.subgraph_view(
        graph,
        filter_node=lambda node: node not in blocked,
        filter_edge=lambda u, v, k: graph[u][v][k].get("space") not in blocked,
    )


def single_source(
    graph: nx.MultiGraph, endpoints_only: frozenset[str], start: str
) -> dict[str, float]:
    """Route distance from `start` to every node, endpoint-only nodes reached but never passed through."""
    walk = leg_graph(graph, endpoints_only, start, start)
    distances = nx.single_source_dijkstra_path_length(walk, start, weight="weight")
    for node in endpoints_only - {start}:
        if node not in graph:
            continue
        reached = [
            distances[neighbour] + data["weight"]
            for neighbour, edges in graph[node].items()
            if neighbour in distances
            for data in edges.values()
            if data.get("space") in (None, node) or data.get("space") not in endpoints_only
        ]
        if reached:
            distances[node] = min(reached)
    return distances


# ---------- paths ----------


def sequence_length(
    view: BuildingMap,
    space_path: list[str],
    *,
    step_free: bool = False,
    model: str = KIT,
    rules: RouteRules = NO_RULES,
) -> float | None:
    """Shortest length of a walk that visits exactly `space_path` in order — how the organisers re-measure an answer.

    Each consecutive pair must be joined by an open opening (an entrance when one side is `outside`) or a stair/lift
    hop, and the walk must obey `rules` (endpoint-only nodes only first or last); otherwise None (scored 0). Door
    choices between the same two spaces are optimised; the first/last space starts/ends at its anchor."""
    graph = route_graph(view, step_free, model, rules)
    blocked = endpoint_only(view, rules) - {space_path[0], space_path[-1]}
    if any(space not in graph or space in blocked for space in space_path):
        return None
    best = {space_path[0]: 0.0}  # entry node into the current space → cost so far
    for index, (here, there) in enumerate(itertools.pairwise(space_path)):
        exits: dict[str, tuple[str, float]] = {}  # entry node into `there` → (exit node of `here`, hop cost)
        for opening in view.openings.values():
            if set(opening["space_ids"]) == {here, there} and DOOR_PREFIX + opening["id"] in graph:
                door = DOOR_PREFIX + opening["id"]
                exits[door] = (door, 0.0)
        hops = [
            edge["weight"]
            for edge in graph.get_edge_data(here, there, default={}).values()
            if edge.get("via") in view.connectors
        ]
        if hops:
            exits[there] = (here, min(hops))
        following: dict[str, float] = {}
        for entry, cost in best.items():
            for arrival, (leave, hop) in exits.items():
                inside = inside_cost(graph, here, entry, leave)
                if inside is not None:
                    total = cost + inside + hop
                    if total < following.get(arrival, math.inf):
                        following[arrival] = total
        if not following:
            return None
        best = following
    last = space_path[-1]
    finals = [
        cost + inside
        for entry, cost in best.items()
        if (inside := inside_cost(graph, last, entry, last)) is not None
    ]
    return round(min(finals), 2) if finals else None


def inside_cost(graph: nx.MultiGraph, space: str, entry: str, leave: str) -> float | None:
    """Metres walked inside `space` from `entry` to `leave` (door nodes or the space's own anchor node)."""
    if entry == leave:
        return 0.0
    if space == OUTSIDE:  # never walked through: only a first or last stop
        return 0.0 if graph.has_node(OUTSIDE) and OUTSIDE in (entry, leave) else None
    options = [
        data["weight"]
        for data in graph.get_edge_data(entry, leave, default={}).values()
        if data.get("space") == space or space in (entry, leave)
    ]
    if space not in (entry, leave) and graph.has_edge(entry, space) and graph.has_edge(space, leave):
        options.append(cheapest(graph, entry, space)["weight"] + cheapest(graph, space, leave)["weight"])
    return min(options) if options else None
