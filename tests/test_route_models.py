"""Route models and rules (core/route_models.py, Q-014) on small hand-made buildings, plus the Guide tool wiring.

Layout of `factory()` (one floor, metres):

    y 6 ┌──────────── C corridor (0..12 × 4..6) ────────────┐
    y 4 ├──door(2,4)──┬─────────────────┬──door(10,4)───────┤
        │  A room     │ BAY production  │  B room           │
        │      door(4,2)            door(8,2)               │
    y 0 └─────────────┴─────────────────┴───────────────────┘
        x 0          4                 8                  12

A → B through the bay is ~8 m, around through the corridor ~12 m. One entrance into C at (0, 5); with
`entrances_ab=True` also one into A at (0, 2) and one into B at (12, 2) (an outside shortcut A → B)."""

import copy
import json
import math
from pathlib import Path

import pytest

from agent.tools import BuildingSession
from core.building_map import BuildingMap
from core.navigation import find_route, tour
from core.route_models import (
    GEODESIC,
    KIT,
    NO_RULES,
    SUNDAY_RULES,
    RouteRules,
    is_production_bay,
    is_walkway,
    route_graph,
    sequence_length,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def space(space_id: str, polygon: list, type_: str = "room", room_type: str = "office", name: str | None = None,
          floor: str = "F0") -> dict:
    return {"id": space_id, "floor_id": floor, "type": type_, "room_type": room_type, "name": name or space_id,
            "ref": None, "polygon": polygon, "synthetic": True}


def opening(opening_id: str, first: str, second: str, position: list, width: float = 0.9, kind: str = "door",
            floor: str = "F0") -> dict:
    return {"id": opening_id, "floor_id": floor, "space_ids": [first, second], "kind": kind, "position": position,
            "width_m": width, "step_free": True, "synthetic": True}


def factory(wide_bay: float = 0.9, corridor_width: float = 0.9, corridor_name: str = "Main aisle",
            entrances_ab: bool = False) -> BuildingMap:
    entrances = [opening("E-C", "outside", "C", [0, 5], 1.2, "entrance")]
    if entrances_ab:
        entrances += [opening("E-A", "outside", "A", [0, 2], 1.2, "entrance"),
                      opening("E-B", "outside", "B", [12, 2], 1.2, "entrance")]
    return BuildingMap({
        "building": {"name": "Test factory", "source": "test"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 4.0}],
        "spaces": [
            space("A", rect(0, 0, 4, 4)),
            space("BAY", rect(4, 0, 8, 4), "hall", "production_zone", "Production zone H-A1"),
            space("B", rect(8, 0, 12, 4)),
            space("C", rect(0, 4, 12, 6), "corridor", "corridor", corridor_name),
        ],
        "assets": [],
        "vertical_connectors": [],
        "openings": [
            opening("A-BAY", "A", "BAY", [4, 2], wide_bay),
            opening("BAY-B", "BAY", "B", [8, 2], wide_bay),
            opening("A-C", "A", "C", [2, 4], corridor_width),
            opening("C-B", "C", "B", [10, 4], corridor_width),
            *entrances,
        ],
    })


def tower(elevations: tuple[float, ...]) -> BuildingMap:
    """One room, one stairwell and one lift lobby per floor; stairs and lift serve every floor."""
    floors = [{"id": f"F{i}", "level": i, "name": f"Floor {i}", "elevation_m": e, "height_m": 3.0}
              for i, e in enumerate(elevations)]
    spaces, openings = [], []
    for i in range(len(elevations)):
        floor = f"F{i}"
        spaces += [space(f"R{i}", rect(0, 0, 4, 4), floor=floor),
                   space(f"S{i}", rect(4, 0, 6, 4), "stair", "stairwell", floor=floor),
                   space(f"L{i}", rect(0, 4, 4, 6), "lift", "lift", floor=floor)]
        openings += [opening(f"R-S{i}", f"R{i}", f"S{i}", [4, 2], floor=floor),
                     opening(f"R-L{i}", f"R{i}", f"L{i}", [2, 4], floor=floor)]
    ids = [floor["id"] for floor in floors]
    return BuildingMap({
        "building": {"name": "Tower", "source": "test"}, "floors": floors, "spaces": spaces, "assets": [],
        "openings": openings,
        "vertical_connectors": [
            {"id": "V-S", "kind": "stairs", "name": "Stairs", "floor_ids": ids,
             "space_ids": [f"S{i}" for i in range(len(ids))], "step_free": False},
            {"id": "V-L", "kind": "lift", "name": "Lift", "floor_ids": ids,
             "space_ids": [f"L{i}" for i in range(len(ids))], "step_free": True},
        ],
    })


def connector_weights(graph, first: str, second: str) -> dict[str, float]:
    return {edge["via"]: edge["weight"] for edge in graph.get_edge_data(first, second, default={}).values()}


# ---------- route models ----------


def test_kit_model_without_rules_is_the_kit_graph_and_adds_no_fields():
    building = BuildingMap.load(DATA / "dev" / "proc-campus-dev-000")
    kit, ours = building.graph(False, outside=True), route_graph(building, False, KIT, NO_RULES)
    assert list(ours.nodes) == list(kit.nodes) and list(ours.edges(keys=True, data=True)) == list(
        kit.edges(keys=True, data=True))
    assert list(route_graph(building, False, GEODESIC).edges(keys=True, data=True)) == list(
        kit.edges(keys=True, data=True))  # GEODESIC is an alias since kit 1.1.0
    route = find_route(factory(), "A", "B").to_dict()
    assert "model" not in route and "rules" not in route


def test_convex_rooms_walk_straight_to_a_door_landing_30_cm_inside():
    building = factory()
    route = find_route(building, "A", "BAY")
    # anchor A → landing (3.7, 2) → door (4, 2) → landing (4.3, 2) → anchor BAY (convex rooms: straight lines)
    expected = math.dist(building.anchor("A"), (3.7, 2)) + 0.3 + 0.3 + math.dist((4.3, 2), building.anchor("BAY"))
    assert route.length_m == pytest.approx(expected, abs=0.01)
    assert route.space_path == ["A", "BAY"] and route.element_path == ["A-BAY"]


def test_door_to_door_inside_a_space_and_kit_1_1_paths():
    building = factory()
    route = find_route(building, "A", "B")
    # A: anchor → landing → door; the bay crossed door to door (0.3 + 3.4 + 0.3); B: door → landing → anchor
    expected = math.dist(building.anchor("A"), (3.7, 2)) + 0.3 + 4.0 + 0.3 + math.dist((8.3, 2), building.anchor("B"))
    assert route.length_m == pytest.approx(expected, abs=0.01)
    assert route.space_path == ["A", "BAY", "B"]
    assert route.element_path == ["A-BAY", "BAY-B"]  # each opening once (kit 1.1.0)
    assert route.steps[0].startswith("Start in") and route.steps[-1].startswith("You have arrived")
    assert "into Production zone H-A1" in " ".join(route.steps)  # the crossed space is named


def test_geodesic_stairs_and_lift_cost_from_elevation():
    graph = route_graph(tower((0.0, 4.5, 9.0)), step_free=False, model=GEODESIC)
    assert connector_weights(graph, "S0", "S1") == {"V-S": pytest.approx(9.0)}  # 2 m per metre climbed
    assert connector_weights(graph, "L0", "L1") == {"V-L": pytest.approx(19.5)}  # 15 m + 1 m per metre
    assert connector_weights(graph, "L0", "L2") == {"V-L": pytest.approx(24.0)}  # one ride, one wait
    assert connector_weights(graph, "S0", "S2") == {}  # stairs go floor by floor


def test_stairs_per_floor_and_one_lift_ride():
    # Three floors of 3 m. Kit: stairs 2·12 = 24, lift per hop 2·(15 + 6) = 42. New rule: stairs 2·6 = 12, one lift
    # ride 15 + 6 = 21. Same geometry → both pick the stairs; the real-data flip is in test_sequence_length_on_real…
    building = tower((0.0, 3.0, 6.0))
    kit, geodesic = find_route(building, "R0", "R2"), find_route(building, "R0", "R2", model=GEODESIC)
    assert "V-S" in kit.element_path and "V-S" in geodesic.element_path
    step_free = find_route(building, "R0", "R2", step_free=True, model=GEODESIC)
    assert step_free.space_path == ["R0", "L0", "L2", "R2"]  # a single lift ride


# ---------- rules ----------


def test_production_bay_is_destination_only():
    building = factory()
    assert find_route(building, "A", "B").space_path == ["A", "BAY", "B"]
    for model in (KIT, GEODESIC):
        ruled = find_route(building, "A", "B", model=model, rules=SUNDAY_RULES)
        assert ruled.space_path == ["A", "C", "B"]
        assert ruled.rules == ["production bays are destinations only", "no shortcut outside the building"]
        assert find_route(building, "A", "BAY", model=model, rules=SUNDAY_RULES).space_path == ["A", "BAY"]
        assert find_route(building, "BAY", "B", model=model, rules=SUNDAY_RULES).space_path == ["BAY", "B"]


def test_space_marked_through_false_is_destination_only_without_rules():
    building = factory()
    building.spaces["BAY"]["through"] = False
    assert building.route("A", "B").space_path == ["A", "C", "B"]
    assert find_route(building, "A", "B").space_path == ["A", "C", "B"]
    assert building.route("A", "BAY").space_path == ["A", "BAY"]
    assert building.route("BAY", "B").space_path == ["BAY", "B"]
    assert building.route("A", "B", via=["BAY"]).space_path == ["A", "BAY", "B"]


def test_no_route_under_the_rules_is_a_structured_answer():
    building = factory()
    building.closed.add("C")  # only the bay (or outside) is left between A and B
    assert find_route(building, "A", "B").reachable
    ruled = find_route(building, "A", "B", model=GEODESIC, rules=SUNDAY_RULES)
    assert ruled.reachable is False and ruled.length_m is None
    assert ruled.reason.startswith("no route under these rules (production bays are destinations only")
    stops = tour(building, ["A", "BAY", "B"], rules=SUNDAY_RULES)  # stopping in the bay is fine
    assert stops.reachable and [leg.space_path for leg in stops.legs] == [["A", "BAY"], ["BAY", "B"]]


def test_no_shortcut_outside_but_outside_may_be_an_end():
    building = factory(entrances_ab=True)
    building.closed |= {"C", "A-BAY"}  # A and B now meet only outside: no route (kit 1.1.0), rules or not
    assert find_route(building, "A", "B").reachable is False
    assert find_route(building, "A", "B", rules=RouteRules(no_outside=True)).reachable is False
    out = find_route(building, "A", "outside", rules=SUNDAY_RULES)
    assert out.reachable and out.space_path == ["A", "outside"] and out.element_path == ["E-A"]
    inside = find_route(building, "outside", "B")
    assert inside.reachable and inside.space_path == ["outside", "B"]


def test_forklift_needs_wide_openings_no_stairs_no_walkways():
    narrow = factory(wide_bay=3.5, corridor_width=0.9)
    forklift = RouteRules(forklift=True)
    assert find_route(narrow, "A", "B", rules=forklift).space_path == ["A", "BAY", "B"]
    # with the bay rule too, the only wide way is through the bay → no route
    assert find_route(narrow, "A", "B", rules=RouteRules(True, True, True)).reachable is False
    aisle = factory(wide_bay=3.5, corridor_width=3.2)
    assert find_route(aisle, "A", "B", model=GEODESIC, rules=RouteRules(True, True, True)).space_path == ["A", "C", "B"]
    walkway = factory(wide_bay=3.5, corridor_width=3.2, corridor_name="Pedestrian walkway")
    assert is_walkway(walkway.spaces["C"]) and not is_walkway(aisle.spaces["C"])
    assert find_route(walkway, "A", "B", rules=RouteRules(True, True, True)).reachable is False
    stairs_only = tower((0.0, 3.0))
    stairs_only.closed.add("V-L")
    assert find_route(stairs_only, "R0", "R1").reachable
    assert find_route(stairs_only, "R0", "R1", rules=forklift).reachable is False


def test_bay_and_walkway_detection_by_type_and_name():
    assert is_production_bay(space("x", [], "hall", "assembly_zone"))
    assert is_production_bay(space("x", [], "hall", "warehouse_zone"))
    assert is_production_bay(space("x", [], "hall", "generic", "Bay 3"))
    assert is_production_bay(space("x", [], "production_bay", "generic"))
    assert not is_production_bay(space("x", [], "hall", "lobby", "Hall access 0.13"))
    assert not is_production_bay(space("x", [], "room", "storage", "Storage"))
    assert is_walkway(space("x", [], "walkway", "corridor"))
    assert not is_walkway(space("x", [], "corridor", "corridor", "Main aisle H-B1"))


# ---------- re-measuring a space sequence (organiser scoring) ----------


def test_sequence_length_matches_the_route_and_rejects_invalid_lists():
    building = factory()
    route = find_route(building, "A", "B", rules=SUNDAY_RULES)
    assert sequence_length(building, route.space_path, rules=SUNDAY_RULES) == route.length_m
    assert sequence_length(building, ["A", "BAY", "B"], rules=SUNDAY_RULES) is None  # passes a bay
    assert sequence_length(building, ["A", "B"]) is None  # no door between A and B
    assert sequence_length(building, ["A", "outside", "B"]) is None  # no entrance into A or B
    shortcut = factory(entrances_ab=True)
    assert sequence_length(shortcut, ["A", "outside", "B"]) is None  # never through the outside (kit 1.1.0)
    assert sequence_length(shortcut, ["A", "outside"]) is not None  # but it may be the end
    assert sequence_length(building, ["A", "BAY", "B"]) == find_route(building, "A", "B").length_m


def test_sequence_length_on_real_warmup_routes():
    directory = DATA / "dev" / "proc-campus-dev-001"
    building = BuildingMap.load(directory)
    routes = [json.loads(line)["answer"] for line in (directory / "questions_basic.jsonl").open(encoding="utf-8")
              if json.loads(line)["kind"] == "route" and "space_path" in json.loads(line)["answer"]]
    assert routes
    for answer in routes:  # re-measuring the gold space list gives the gold length
        measured = sequence_length(building, answer["space_path"])
        assert measured == pytest.approx(answer["optimal_length_m"], abs=0.01)


# ---------- Guide tools ----------


def test_guide_routes_obey_rules_and_forklift_preset():
    session = BuildingSession(factory(wide_bay=3.5, corridor_width=3.2))
    route = session.call("find_route", {"start": "A", "destination": "B"})
    assert route["space_path"] == ["A", "C", "B"] and "production bays are destinations only" in route["rules"]
    profile = session.call("set_profile", {"preset": "forklift"})
    assert profile["profile"]["forklift"] and profile["profile"]["min_door_width_m"] == 3.0
    assert "forklift" in profile["summary"]
    assert session.call("find_route", {"start": "A", "destination": "B"})["space_path"] == ["A", "C", "B"]
    narrow = BuildingSession(factory(wide_bay=3.5, corridor_width=0.9))
    narrow.call("set_profile", {"preset": "forklift"})
    blocked = narrow.call("find_route", {"start": "A", "destination": "B"})
    assert blocked["reachable"] is False and blocked["reason"].startswith("no route under these rules")
    assert narrow.call("reachable_rooms", {"start": "A"})["rooms"] == ["A"]  # the bay is not a room
    session.route_model = GEODESIC
    assert session.call("find_route", {"start": "A", "destination": "BAY"})["model"] == GEODESIC


def test_guide_reachable_rooms_include_bays_as_destinations_only():
    session = BuildingSession(copy.deepcopy(factory()))
    session.building.closed.add("C")
    distances = session.space_distances(session.building, "A")
    assert "BAY" in distances and "B" not in distances  # B only via the bay (or outside)
