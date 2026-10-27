"""nearest_item, lift_closed, add_door (core/solvers): small hand-made buildings from tests/test_route_models.py."""

import pytest

from core.building_map import BuildingMap
from core.solvers import solve
from core.solvers_v1 import solve as solve_v1
from tests.test_route_models import factory, opening, rect, space


def with_assets(building: BuildingMap, assets: list[tuple[str, str, str]]) -> BuildingMap:
    for asset_id, name, space_id in assets:
        asset = {"id": asset_id, "name": name, "type": "fire_extinguisher", "space_id": space_id,
                 "floor_id": building.spaces[space_id]["floor_id"], "position": [0, 0]}
        building.assets[asset_id] = asset
        building.data["assets"].append(asset)
    return building


def two_floors() -> BuildingMap:
    """Ground: hall G (entrance), stair S0, lift L0. Upper: landing U joined to stair S1 and lift L1, room R."""
    spaces = [space("G", rect(0, 0, 6, 4)), space("S0", rect(6, 0, 8, 2), "stair", "stairwell"),
              space("L0", rect(6, 2, 8, 4), "lift", "lift"),
              space("S1", rect(6, 0, 8, 2), "stair", "stairwell", floor="F1"),
              space("L1", rect(6, 2, 8, 4), "lift", "lift", floor="F1"),
              space("U", rect(0, 0, 6, 4), "corridor", "corridor", floor="F1"),
              space("R", rect(0, 4, 6, 8), floor="F1")]
    openings = [opening("E", "outside", "G", [0, 2], 1.2, "entrance"), opening("G-S0", "G", "S0", [6, 1]),
                opening("G-L0", "G", "L0", [6, 3]), opening("U-S1", "U", "S1", [6, 1], floor="F1"),
                opening("U-L1", "U", "L1", [6, 3], floor="F1"), opening("U-R", "U", "R", [3, 4], floor="F1")]
    return BuildingMap({
        "building": {"name": "Two floors", "source": "test"},
        "floors": [{"id": "F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0, "height_m": 3.0},
                   {"id": "F1", "level": 1, "name": "First floor", "elevation_m": 3.0, "height_m": 3.0}],
        "spaces": spaces, "assets": [], "openings": openings,
        "vertical_connectors": [
            {"id": "V-S", "kind": "stairs", "name": "Stairs", "floor_ids": ["F0", "F1"], "space_ids": ["S0", "S1"],
             "step_free": False},
            {"id": "V-L", "kind": "lift", "name": "Lift", "floor_ids": ["F0", "F1"], "space_ids": ["L0", "L1"],
             "step_free": True}],
    })


def test_nearest_item_is_by_walking_distance_not_straight_line():
    building = with_assets(factory(), [("X-B", "Fire extinguisher", "B"), ("X-C", "Fire extinguisher", "C")])
    building.spaces["BAY"]["through"] = False  # A → B now goes round by the corridor, so C is nearer
    result = solve(building, "nearest_item", {"start": "A", "item": "fire extinguisher"})
    assert result.value == "X-C"
    assert [row["asset_id"] for row in result.evidence["ranking"]] == ["X-C", "X-B"]
    assert result.evidence["ranking"][0]["length_m"] < result.evidence["ranking"][1]["length_m"]
    assert solve_v1(building, "nearest_item", {"start": "A", "item": "fire extinguisher"})["asset_id"] == "X-C"


def test_nearest_item_with_nothing_matching_is_an_error():
    with pytest.raises(ValueError):
        solve(factory(), "nearest_item", {"start": "A", "item": "coffee machine"})


def test_lift_closed_lists_rooms_that_lose_step_free_access():
    building = two_floors()
    result = solve(building, "lift_closed", {"closed": "V-L"})
    assert result.value == 1
    assert result.evidence["rooms"] == ["R"]
    assert {"U", "R"} <= set(result.evidence["spaces"]) and "G" not in result.evidence["spaces"]
    assert result.evidence["floors"] == ["F1"]
    assert solve(building, "lift_closed", {"closed": "V-S"}).value == 0  # the lift still reaches every room


def test_add_door_joins_the_two_rooms_and_gives_the_new_route():
    building = factory()  # BAY and C share the wall y = 4 but no door
    before = building.route("BAY", "C")
    assert before.space_path != ["BAY", "C"]
    result = solve(building, "add_door", {"first": "BAY", "second": "C"})
    assert result.evidence["door"]["space_ids"] == ["BAY", "C"]
    assert result.evidence["space_path"] == ["BAY", "C"]
    assert result.evidence["length_before_m"] == before.length_m
    assert result.value == result.evidence["length_after_m"] < before.length_m
    assert building.route("BAY", "C").space_path == before.space_path  # the building itself is not changed
    v1 = solve_v1(building, "add_door", {"first": "BAY", "second": "C"})
    assert v1["space_path"] == ["BAY", "C"] and v1["door"]["space_ids"] == ["BAY", "C"]


def test_llm_slots_build_the_three_kinds():
    from agent.llm_parser import build

    building = with_assets(factory(), [("X-B", "Fire extinguisher", "B")])
    empty = {"start": None, "first": None, "second": None, "destination": None, "stops": [], "floor": None,
             "room_type": None, "asset_type": None, "min_width_m": None, "item": None, "closed": None,
             "direction": None, "may_use_stairs": None, "step_free": False, "forklift": False, "closures": []}
    place = lambda name: {"name": name, "floor": "", "is_item": False}  # noqa: E731
    nearest = build({**empty, "kind": "nearest_item", "asks_for": "item_location", "start": place("A"),
                     "item": "fire extinguisher"}, building)
    assert (nearest.kind, nearest.params) == ("nearest_item", {"start": "A", "item": "fire extinguisher"})
    door = build({**empty, "kind": "add_door", "asks_for": "distance_m", "first": place("BAY"),
                  "second": place("C")}, building)
    assert (door.kind, door.params) == ("add_door", {"first": "BAY", "second": "C"})
    lift = build({**empty, "kind": "lift_closed", "asks_for": "other", "closed": "Lift"}, two_floors())
    assert (lift.kind, lift.params) == ("lift_closed", {"closed": "V-L"})


def test_nearest_item_can_be_step_free_and_avoid_closures():
    building = with_assets(two_floors(), [("X-G", "Fire extinguisher", "G"), ("X-R", "Fire extinguisher", "R")])
    assert solve(building, "nearest_item", {"start": "U", "item": "fire extinguisher"}).value == "X-R"
    assert solve(building, "nearest_item", {"start": "U", "item": "fire extinguisher", "closed": ["U-R"]}).value == "X-G"
    shut = solve(building, "nearest_item", {"start": "U", "item": "fire extinguisher", "closed": ["U-R"],
                                             "step_free": True})
    assert shut.value == "X-G" and shut.evidence["step_free"] is True


def test_guide_find_nearest_item_uses_the_shared_ranking():
    from pathlib import Path

    from agent.tools import BuildingSession

    directory = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"
    session = BuildingSession.load(directory)
    start = next(space_id for space_id, item in session.building.spaces.items() if item["name"] == "Main aisle H-B1")
    shared = solve(session.building, "nearest_item", {"start": start, "item": "forklift charging station"})
    guide = session.tool_find_nearest(start, "forklift charging station")
    assert guide["nearest"]["id"] == shared.evidence["space_id"]
    assert guide["space_path"][-1] == shared.evidence["space_id"]


def test_guide_closing_a_lift_reports_the_rooms_that_lose_step_free_access():
    from agent.tools import BuildingSession

    session = BuildingSession(two_floors())
    proposal = session.tool_propose_change("close", ["Lift"])
    assert proposal["effect"]["step_free_lost_V-L"]["rooms"] == 1
    assert session.tool_propose_change("close", ["Stairs"])["effect"].get("step_free_lost_V-S") is None


def test_guide_nearest_ranking_and_route_agree_under_the_guides_rules():
    from agent.tools import BuildingSession

    session = BuildingSession(with_assets(factory(), [("X-B", "Fire extinguisher", "B")]))
    found = session.tool_find_nearest("A", "fire extinguisher")
    assert found["space_path"] == ["A", "C", "B"]  # the Guide's bays are destinations only: round by C
    ranked = solve(session.building, "nearest_item", {"start": "A", "item": "fire extinguisher",
                                                      "rules": session.route_rules(), "model": session.route_model})
    assert ranked.evidence["length_m"] == found["length_m"]


def test_guide_nearest_with_a_forklift_profile_is_the_nearest_reachable_holder():
    from pathlib import Path

    from agent.tools import BuildingSession
    from core import navigation

    session = BuildingSession.load(Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004")
    session.tool_set_profile(forklift=True)
    start = next(space_id for space_id, item in session.building.spaces.items() if item["name"] == "Main aisle H-B1")
    lengths = {}
    for holder in {asset["space_id"] for asset in session.building.assets.values() if asset["type"] == "fire_extinguisher"}:
        route = navigation.find_route(session.building, start, holder, rules=session.route_rules(),
                                      model=session.route_model, penalties=session.profile.penalties())
        if route.reachable:
            lengths[holder] = route.length_m
    found = session.tool_find_nearest(start, "fire extinguisher")
    assert found["reachable"] is True
    assert found["nearest"]["id"] == min(lengths, key=lambda holder: (lengths[holder], holder))
