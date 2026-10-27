"""core.route_query: one route question with any mix of constraints, places that may be items or room types (the
nearest one is taken), and stops. Facts about proc-factory-dev-004 used below (checked by hand on its building.json
and warm-up answers): floors are joined only by "Office staircase" and "Office lift"; the offices open through
doors narrower than 3 m; forklift charging stations stand in Logistics zone H-C1 (next to Main aisle H-B1) and
Logistics zone H-C2 (next to Main aisle H-B2); toilets: Toilet 0.20 and Toilet 1.05."""

from pathlib import Path

import pytest

from core.building_map import BuildingMap
from core.route_query import resolve_place, route_query

DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"


@pytest.fixture(scope="module")
def bmap() -> BuildingMap:
    return BuildingMap.load(DIRECTORY)


def space(bmap: BuildingMap, name: str) -> str:
    return next(space_id for space_id, item in bmap.spaces.items() if item["name"] == name)


def names(bmap: BuildingMap, space_ids: list[str]) -> list[str]:
    return [bmap.spaces[space_id]["name"] for space_id in space_ids]


def test_plain_route_matches_the_warm_up_answer(bmap: BuildingMap) -> None:
    result = route_query(bmap, [[space(bmap, "Kitchen 1.12")], [space(bmap, "Office 0.31")]])  # Q05
    assert result["reachable"] is True
    assert result["optimal_length_m"] == pytest.approx(92.01, abs=0.01)
    assert names(bmap, result["space_path"]) == ["Kitchen 1.12", "Office corridor 1.01", "Staircase 1.02",
                                                 "Staircase 0.14", "Office corridor 0.13", "Office 0.31"]


def test_closed_space_is_avoided(bmap: BuildingMap) -> None:
    stops = [[space(bmap, "Logistics zone H-C1")], [space(bmap, "Warehouse zone H-C3")]]
    open_route = route_query(bmap, stops)
    blocked = route_query(bmap, stops, closed=["Main aisle H-B2"])
    assert "Main aisle H-B2" in names(bmap, open_route["space_path"])
    assert blocked["reachable"] is True
    assert "Main aisle H-B2" not in names(bmap, blocked["space_path"])
    assert blocked["optimal_length_m"] > open_route["optimal_length_m"]


def test_step_free_with_the_only_lift_closed_has_no_route(bmap: BuildingMap) -> None:
    stops = [[space(bmap, "Kitchen 1.15")], [space(bmap, "Meeting room 0.22")]]
    assert route_query(bmap, stops, step_free=True)["reachable"] is True
    assert route_query(bmap, stops, closed=["Office lift"])["reachable"] is True  # stairs still there
    result = route_query(bmap, stops, step_free=True, closed=["Office lift"])
    assert result["reachable"] is False


@pytest.mark.parametrize(("start", "nearest"), [("Main aisle H-B1", "Logistics zone H-C1"),
                                                 ("Main aisle H-B2", "Logistics zone H-C2")])
def test_item_destination_goes_to_the_nearest_holder(bmap: BuildingMap, start: str, nearest: str) -> None:
    chargers = resolve_place(bmap, "forklift charging station", is_item=True)
    assert sorted(names(bmap, chargers)) == ["Logistics zone H-C1", "Logistics zone H-C2"]
    result = route_query(bmap, [[space(bmap, start)], chargers])
    assert names(bmap, [result["to_space_id"]]) == [nearest]


def test_forklift_keeps_to_wide_openings_and_cannot_reach_the_offices(bmap: BuildingMap) -> None:
    hall = route_query(bmap, [[space(bmap, "Logistics zone H-C1")], [space(bmap, "Production zone H-A2")]],
                       forklift=True)
    assert hall["reachable"] is True
    used = [bmap.openings[element] for element in hall["element_path"] if element in bmap.openings]
    assert used and all(opening["width_m"] >= 3.0 for opening in used)
    office = route_query(bmap, [[space(bmap, "Office 0.31")], [space(bmap, "Production zone H-A2")]], forklift=True)
    assert office["reachable"] is False


def test_min_width_closes_narrow_doors(bmap: BuildingMap) -> None:
    stops = [[space(bmap, "Logistics zone H-C1")], [space(bmap, "Warehouse zone H-C4")]]
    result = route_query(bmap, stops, min_width=12.0)
    assert result["reachable"] is True
    assert all(bmap.openings[element]["width_m"] >= 12.0 for element in result["element_path"]
               if element in bmap.openings)
    # the only ways into Warehouse zone H-C4 are a 12.8 m opening and a 4 m entrance
    assert route_query(bmap, stops, min_width=13.0)["reachable"] is False
    assert route_query(bmap, [[space(bmap, "Office 0.31")], [space(bmap, "Office 0.29")]],
                       min_width=3.0)["reachable"] is False


def test_room_type_comes_before_items_unless_an_item_is_meant(bmap: BuildingMap) -> None:
    moved = BuildingMap.load(DIRECTORY)
    asset_id = next(i for i, asset in moved.assets.items() if asset["type"] == "toilet")
    moved.assets[asset_id] = {**moved.assets[asset_id], "space_id": space(moved, "Office 1.04")}
    assert sorted(names(moved, resolve_place(moved, "toilet"))) == ["Toilet 0.20", "Toilet 1.05"]
    assert "Office 1.04" in names(moved, resolve_place(moved, "toilet", is_item=True))


def test_room_type_place_means_the_nearest_room_of_that_type(bmap: BuildingMap) -> None:
    toilets = resolve_place(bmap, "toilet")
    assert sorted(names(bmap, toilets)) == ["Toilet 0.20", "Toilet 1.05"]
    result = route_query(bmap, [[space(bmap, "Office 1.04")], toilets])
    assert names(bmap, [result["to_space_id"]]) == ["Toilet 1.05"]


def test_resolve_place_by_name_ref_and_floor(bmap: BuildingMap) -> None:
    assert names(bmap, resolve_place(bmap, "Office 0.31")) == ["Office 0.31"]
    assert names(bmap, resolve_place(bmap, "office 0.31")) == ["Office 0.31"]
    ground = next(floor_id for floor_id, floor in bmap.floors.items() if floor["name"] == "Ground floor")
    assert names(bmap, resolve_place(bmap, "toilet", floor_id=ground)) == ["Toilet 0.20"]
    assert resolve_place(bmap, "no such place xyz") == []


def test_stops_give_one_leg_each_and_join_into_one_path(bmap: BuildingMap) -> None:
    jacks = resolve_place(bmap, "pallet jack", is_item=True)
    assert names(bmap, jacks) == ["Warehouse zone H-C3"]
    result = route_query(bmap, [[space(bmap, "Main aisle H-B1")], jacks, [space(bmap, "Warehouse zone H-C4")]])
    assert result["reachable"] is True
    assert [names(bmap, [leg["from_space_id"], leg["to_space_id"]]) for leg in result["legs"]] == [
        ["Main aisle H-B1", "Warehouse zone H-C3"], ["Warehouse zone H-C3", "Warehouse zone H-C4"]]
    assert result["optimal_length_m"] == pytest.approx(sum(leg["optimal_length_m"] for leg in result["legs"]),
                                                       abs=0.02)
    assert result["space_path"][0] == space(bmap, "Main aisle H-B1")
    assert result["space_path"][-1] == space(bmap, "Warehouse zone H-C4")


def test_an_entrance_is_a_place_by_its_name_or_its_id() -> None:
    from tests.test_route_models import factory, opening

    building = factory()
    building.openings["DOCK01"] = opening("DOCK01", "outside", "A", [0, 2], 3.5, "entrance")
    building.openings["E-C"]["name"] = "Main gate"
    assert resolve_place(building, "Dock 1") == ["A"]
    assert resolve_place(building, "dock 01") == ["A"]
    assert resolve_place(building, "the Main gate") == ["C"]
    assert resolve_place(building, "Dock 2") == []
