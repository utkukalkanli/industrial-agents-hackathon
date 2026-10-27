"""Place resolution in the Guide's tool layer (agent/places.py via BuildingSession) and the grounding additions
ported from the v1 Guide: articles, asset types, typo suggestions, described candidates, route fan-out."""

import json
from pathlib import Path

import pytest

from agent.guide import ungrounded
from agent.offline_llm import CANDIDATES
from agent.tools import BuildingSession
from core.building_map import MapError

BUILDING = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"
PREFIX = "proc-campus-train-000"


@pytest.fixture(scope="module")
def session() -> BuildingSession:
    return BuildingSession.load(BUILDING)


def test_ids_and_exact_names_resolve_as_before(session):
    assert session.resolve(f"{PREFIX}-F0-S002") == f"{PREFIX}-F0-S002"
    assert session.resolve("Office 0.02") == f"{PREFIX}-F0-S002"
    assert session.resolve("0.02") == f"{PREFIX}-F0-S002"


def test_leading_article_and_room_word_are_ignored(session):
    assert session.resolve("the Office 0.02") == f"{PREFIX}-F0-S002"
    assert session.resolve("room 0.02") == f"{PREFIX}-F0-S002"


def test_asset_type_held_by_one_room_resolves_to_that_room(session):
    room = next(a["space_id"] for a in session.building.assets.values() if a["type"] == "3d_printer")
    assert session.resolve("the 3D printer") == room
    defib = next(a["space_id"] for a in session.building.assets.values() if a["type"] == "defibrillator")
    assert session.resolve("defibrillator") == defib


def test_repeated_name_is_ambiguous_and_names_what_tells_them_apart(session):
    with pytest.raises(MapError) as error:
        session.resolve("Staircase 1")
    message = str(error.value)
    assert "ambiguous" in message and "4 places" in message
    options = CANDIDATES.findall(message)
    assert len(options) == 4 and all("floor" in option.lower() for option in options)
    assert len({option for option in options}) == 4  # each option is distinguishable


def test_typo_gets_suggestions(session):
    with pytest.raises(MapError) as error:
        session.resolve("Ofice 0.02")
    assert "Did you mean" in str(error.value) and "Office 0.02" in str(error.value)


def test_unknown_place_says_so_without_suggestions(session):
    with pytest.raises(MapError, match="No place matches"):
        session.resolve("zzzz qqqq")


def test_route_to_an_asset_in_several_rooms_lists_each_with_its_length(session):
    events = len(session.events)
    result = session.call("find_route", {"start": "Office 0.02", "destination": "printer"})
    assert "ambiguous" in result["error"]
    lengths = [option["length_m"] for option in result["options"]]
    assert len(lengths) == 4 and lengths == sorted(lengths)
    assert all(f"{option['length_m']} m" in result["error"] for option in result["options"])
    assert len(session.events) == events  # no route drawn while the destination is open


def test_route_with_resolvable_names_still_works(session):
    result = session.call("find_route", {"start": "the Office 0.02", "destination": "the 3D printer"})
    assert result["reachable"] and result["space_path"][0] == f"{PREFIX}-F0-S002"
    assert session.events[-1]["type"] == "route"


def test_grounding_catches_numbers_glued_to_a_unit():
    corpus = json.dumps({"length_m": 42.5})
    assert ungrounded("It is 120m away.", corpus) == ["120"]
    assert ungrounded("It is 42.5m away, 43 m roughly.", corpus) == []


def test_grounding_counts_list_lengths_and_skips_clock_times():
    corpus = json.dumps({"options": [{"id": "a"}, {"id": "b"}], "results": ["x", "y", "z"]})
    assert ungrounded("I found 2 options and 3 results.", corpus) == []
    assert ungrounded("The canteen opens at 10:30.", corpus) == []
    assert ungrounded("I found 4 options.", corpus) == ["4"]


def test_an_entrance_resolves_to_the_space_it_opens_into():
    from agent.places import candidates
    from tests.test_route_models import factory, opening

    building = factory()
    building.openings["DOCK01"] = opening("DOCK01", "outside", "A", [0, 2], 3.5, "entrance")
    assert candidates(building, "Dock 1") == ["A"]
