"""The Guide's tools from the Sunday layers: `find_nearest` with closures for one question and a candidate shortlist
(core/route_query.shortlist), and `compute` (the solver agent's Python sandbox).
Facts about proc-factory-dev-004: tests/test_route_query.py."""

from pathlib import Path

from agent.tools import BuildingSession

DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"


def session() -> BuildingSession:
    return BuildingSession.load(DIRECTORY)


def name(guide: BuildingSession, space_id: str) -> str:
    return guide.building.spaces[space_id]["name"]


def test_nearest_room_type_is_routed_to_and_drawn() -> None:
    guide = session()
    route = guide.call("find_nearest", {"start": "Office 1.04", "query": "toilet"})
    assert route["reachable"] is True and name(guide, route["to_space_id"]) == "Toilet 1.05"
    assert route["steps"] and route["about_m"]
    drawn = [event for event in guide.events if event["type"] == "route"]
    assert drawn and drawn[-1]["space_path"] == route["space_path"]


def test_nearest_leaves_the_route_as_the_last_answer() -> None:
    # the app shows a route (and its Start card) only while it is the latest route/highlight event: a highlight
    # after it replaced the route, so "the nearest toilet" drew nothing to start (frontend/app/src/dev/story.ts)
    for query in ("meeting room", "whiteboard"):  # a room kind (find_nearest itself), an item (nearest_item)
        guide = session()
        route = guide.call("find_nearest", {"start": "Office 1.04", "query": query})
        answers = [event["type"] for event in guide.events if event["type"] in ("route", "highlight")]
        assert route["reachable"] and answers == ["route"], (query, answers)


def test_nearest_item_holder_and_a_closure_for_this_question_only() -> None:
    guide = session()
    route = guide.call("find_nearest", {"start": "Main aisle H-B2", "query": "forklift charging station"})
    assert name(guide, route["to_space_id"]) == "Logistics zone H-C2"
    guide.call("set_profile", {"preset": "wheelchair"})
    blocked = guide.call("find_nearest", {"start": "Kitchen 1.15", "query": "meeting room",
                                          "floor_id": "proc-factory-dev-004-F0", "closed": ["Office lift"]})
    assert "error" in blocked  # step-free and the only lift closed: no ground-floor meeting room is reachable
    assert guide.call("find_nearest", {"start": "Kitchen 1.15", "query": "meeting room",
                                       "floor_id": "proc-factory-dev-004-F0"})["reachable"]
    assert guide.call("find_route", {"start": "Kitchen 1.15", "destination": "Meeting room 0.22"})["reachable"]


def test_compute_runs_python_over_the_building() -> None:
    guide = session()
    result = guide.call("compute", {"code": "print(len(spaces(floor='Ground floor', type='room')))"})
    assert result == {"output": "14\n"}
    assert "error" in guide.call("compute", {"code": "import os"})
    assert len(guide.building.spaces) == 50  # the code ran on a copy


def test_both_tools_are_offered_to_the_model() -> None:
    names = {tool["name"] for tool in session().tool_definitions()}
    assert {"find_nearest", "compute"} <= names and "route_to_nearest" not in names


def test_compute_routes_like_the_guide_does() -> None:
    # Seen live: compute's route() ignored the Guide's rules and profile, so it called a place reachable that
    # find_route had just called unreachable, and the Guide told the user both.
    guide = session()
    by_tool = guide.call("find_route", {"start": "Office 0.31", "destination": "Main aisle H-B2"})
    by_code = guide.call("compute", {"code": "print(route('Office 0.31', 'Main aisle H-B2')['reachable'])"})
    assert by_tool["reachable"] is False  # production bays are destinations only: the office wing is cut off
    assert by_code == {"output": "False\n"}
    guide.call("set_profile", {"preset": "wheelchair"})
    code = "print(route('Kitchen 1.15', 'Meeting room 0.22', closed=['Office lift'])['reachable'])"
    assert guide.call("compute", {"code": code}) == {"output": "False\n"}  # step-free from the profile
