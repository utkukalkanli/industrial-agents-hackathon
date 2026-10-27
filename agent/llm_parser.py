"""LLM question parser: Claude reads the question and returns the raw slot text; code resolves it to ids.

Claude never produces ids or numbers we score on. It fills the same slots the regex templates capture
(core/question_parser.py), choosing names from the building's own vocabulary, and the shared Resolver turns
them into ids. A resolution error is sent back once so the model can correct its slot text.

Route questions use one general spec (P1, 2026-10-25): start, destination and ordered stops — each a room name, a
room type or an item, the nearest one taken — plus any mix of step-free, forklift, minimum door width and
closures (lifts, stairs, rooms, corridors, doors). A spec that fits a warm-up kind exactly (route, route_step_free,
route_with_closure, tour) keeps that kind and its solver; anything richer becomes `route_query`
(core/route_query.py). `asks_for` names what the question wants back: a kind that cannot answer it, or kind
`other`, raises NeedsAgent and agent/answer.py hands the question to the solver agent.

Every decision is stored in the decision cache (agent/llm_cache.py) before it is used, so a re-run reproduces it
without the model."""

import json
import os
from dataclasses import dataclass

from agent import llm_client
from agent.llm_cache import DecisionCache, decision_key
from core.building_map import BuildingMap, MapError
from core.question_parser import ANSWER_INSTRUCTION, ParsedQuestion, ParseError, Resolver, normalise
from core.route_query import resolve_place

MODEL = os.environ.get("PARSER_LLM_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("PARSER_LLM_EFFORT", "medium")
MAX_TOKENS = 16000
MAX_ATTEMPTS = 2
API_RETRIES = 4  # the SDK retries connection errors, 429 and 5xx with backoff; a benchmark run must not lose a question
FALLBACK_BETA = "server-side-fallback-2026-07-01"
VERSION = "3"  # bump when the schema or the instructions change: cached decisions of another version are not reused
KINDS = [
    "largest_room",
    "floor_area_total",
    "errand",
    "shared_walls_count",
    "wide_delivery_count",
    "straight_line_3d",
    "room_stacked",
    "step_free_reachable_count",
    "what_if_door",
    "locate",
    "count",
    "route",
    "nearest_item",
    "lift_closed",
    "add_door",
    "other",
]
ASKS_FOR = ["room", "item_location", "area_m2", "count", "distance_m", "route", "other"]
ANSWERS = {  # what each kind's solver gives back; a question asking for anything else goes to the agent
    "largest_room": {"room", "area_m2"},
    "room_stacked": {"room"},
    "floor_area_total": {"area_m2"},
    "errand": {"distance_m", "route"},
    "straight_line_3d": {"distance_m"},
    "shared_walls_count": {"count"},
    "wide_delivery_count": {"count"},
    "step_free_reachable_count": {"count"},
    "what_if_door": {"count"},
    "count": {"count"},
    "locate": {"item_location", "room"},
    "route": {"route", "distance_m"},
    "nearest_item": {"item_location", "room", "distance_m", "other"},
    "lift_closed": set(ASKS_FOR),  # "what changes?" has no fixed answer type
    "add_door": {"distance_m", "route", "other"},
}
OLD_ROUTE_KINDS = {"route_step_free", "route_with_closure", "tour"}  # earlier schema; read as `route`
NULLABLE_TEXT = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
NULLABLE_BOOL = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}
# The API rejects a schema with more than 16 union-typed parameters (HTTP 400 on every call), so flags are plain
# booleans, lists are empty when unused and a place's floor is "" when the question names none.
PLACE = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "floor": {"type": "string"}, "is_item": {"type": "boolean"}},
    "required": ["name", "floor", "is_item"],
    "additionalProperties": False,
}
PLACE_SLOT = {"anyOf": [PLACE, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": KINDS},
        "asks_for": {"type": "string", "enum": ASKS_FOR},
        "start": PLACE_SLOT,
        "first": PLACE_SLOT,
        "second": PLACE_SLOT,
        "destination": PLACE_SLOT,
        "stops": {"type": "array", "items": PLACE},
        "floor": NULLABLE_TEXT,
        "room_type": NULLABLE_TEXT,
        "asset_type": NULLABLE_TEXT,
        "min_width_m": NULLABLE_NUMBER,
        "item": NULLABLE_TEXT,
        "closed": NULLABLE_TEXT,
        "direction": {"anyOf": [{"type": "string", "enum": ["above", "below"]}, {"type": "null"}]},
        "may_use_stairs": NULLABLE_BOOL,
        "step_free": {"type": "boolean"},
        "forklift": {"type": "boolean"},
        "closures": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "kind", "asks_for", "start", "first", "second", "destination", "stops", "floor", "room_type", "asset_type",
        "min_width_m", "item", "closed", "direction", "may_use_stairs", "step_free", "forklift", "closures",
    ],
    "additionalProperties": False,
}

INSTRUCTIONS = """You turn one question about a building into structured slots. You do not answer it.

asks_for: what the question wants back — room (which room), item_location (where something is), area_m2,
count, distance_m, route (how to get somewhere, or whether one can), other (anything else: a width, a list, a
yes/no about something that is not a route, a name that is not a room …).

Kinds and the slots each needs (every other slot is null, false or [] by its type):
- largest_room: room_type, floor. "Which is the largest <room type> on <floor>?" (only the largest — the smallest,
  second largest etc. is `other`)
- floor_area_total: room_type, floor. Total floor area of every <room type> on <floor>.
- errand: start, asset_type, room_type, floor, may_use_stairs. From start, fetch the nearest <asset type>, carry
  it to THE LARGEST <room type> on <floor>; total walking distance. If the target is a named room or anything but
  "the largest <room type>", use `route` with the item as a stop instead.
- shared_walls_count: start. How many rooms on the same floor share a wall with start.
- wide_delivery_count: start (the room the entrance opens into), min_width_m, item, floor. How many rooms on
  <floor> a wide load can reach without stairs or steps.
- straight_line_3d: first, second. Straight-line distance between the two room centres.
- room_stacked: start, direction ("above" if something comes from the ceiling / the room above, "below" if it
  leaks down to the room below).
- step_free_reachable_count: closed (the lift or stair out of service), start, floor. Rooms on <floor> a
  wheelchair user can still reach.
- what_if_door: first, second (the two spaces the new door joins), floor (the floor whose rooms are counted).
- locate: asset_type. Where is a piece of equipment ("Where is the coffee machine?").
- count: asset_type, floor. How many items of that type are on <floor>.
- route: any question about getting from one place to another (directions, the shortest / fastest way, whether a
  route exists, its length). start, destination, stops (places visited in between, in order; [] if none), and
  the constraints the question states (step_free and forklift are false unless stated):
  step_free true for wheelchairs, prams, trolleys, carts, "without stairs / steps", "lifts only";
  forklift true when driving a forklift or pallet truck through the hall;
  min_width_m when a load or vehicle of a stated width must pass every door;
  closures: every lift, stair, room, corridor, aisle or door named as closed, blocked, out of service or to be
  avoided (names copied from the vocabulary), else [].
- nearest_item: start, item. Which <item> (an asset type or name: fire extinguisher, delivery point, defibrillator
  …) is closest to start by walking. Not for "the nearest toilet / room of a type" in a route — that is `route`.
- lift_closed: closed (the lift, its name or its lift space copied from the vocabulary). "The lift is closed /
  out of service — what changes?": which rooms lose step-free access.
- add_door: first, second (the two rooms the new door joins). "Add a door between X and Y; how far is it now from X
  to Y?" (a door added and the new route between the same two rooms; a count of improved rooms is what_if_door).
- other: anything none of these kinds answers completely. Prefer `other` over a kind that answers a different
  question; another solver will handle it.

Places (start, first, second, destination, stops) are {"name", "floor", "is_item"}:
- a room or space: its name exactly as listed, its floor name ("" if the question gives none), is_item false;
- an entrance or dock ("from Dock 1", "at gate E2"): the phrase as the question says it, or the entrance's id or
  name from "Entrances and docks", is_item false (it resolves to the space the entrance opens into);
- a room type when the question means "the nearest toilet / kitchen …": name = the room type, is_item false;
- an item when the question means the room holding it ("to the coffee machine", "pick up a pallet jack"): name =
  the asset type or asset name, is_item true, floor "" unless the question names one. Starting "at the
  entrance" means the room the entrance opens into.

Rules:
- Copy every name, floor, room type, asset type and lift/stair name EXACTLY from the building vocabulary below
  (the canonical spelling, e.g. room_type "meeting_room", floor "Floor 1"). Never invent one.
- Numbers only for min_width_m, in metres as written in the question."""


def make_client() -> object:
    return llm_client.make(max_retries=API_RETRIES)  # Anthropic or OpenAI (agent/llm_client.py)


class NeedsAgent(ParseError):
    """The question is understood but no solver kind answers it: agent/answer.py hands it to the solver agent."""


@dataclass
class LlmUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def building_vocabulary(building_map: BuildingMap) -> str:
    floors = sorted(building_map.floors.values(), key=lambda floor: floor["level"])
    lines = ["Floors: " + "; ".join(floor["name"] for floor in floors)]
    lines.append("Room types: " + ", ".join(sorted({s["room_type"] for s in building_map.spaces.values()})))
    lines.append("Asset types: " + ", ".join(sorted({a["type"] for a in building_map.assets.values()})))
    lines.append("Lifts and stairs: " + "; ".join(sorted(c["name"] for c in building_map.connectors.values())))
    entrances = sorted(
        f"{opening.get('name') or opening['id']} (into {building_map.spaces[space_id]['name']})"
        for opening in building_map.openings.values() if opening["kind"] == "entrance"
        for space_id in opening["space_ids"] if space_id in building_map.spaces
    )
    lines.append("Entrances and docks: " + "; ".join(entrances))
    for floor in floors:
        names = sorted({s["name"] for s in building_map.spaces.values() if s["floor_id"] == floor["id"]})
        lines.append(f"Spaces on {floor['name']}: " + "; ".join(names))
    return "\n".join(lines)


def floor_of(building_map: BuildingMap, name: str) -> str:
    """The floor name of the space(s) called `name` (or with that ref) when they all lie on one floor."""
    wanted = normalise(name)
    floors = {space["floor_id"] for space in building_map.spaces.values()
              if wanted in (normalise(space["name"]), normalise(space.get("ref") or ""))}
    if len(floors) == 1:
        return building_map.floor_name(floors.pop())
    if not floors:
        raise ParseError(f"No space named '{name}'")
    names = sorted(building_map.floor_name(floor_id) for floor_id in floors)
    raise ParseError(f"'{name}' exists on several floors ({', '.join(names)}); give its floor")


def check_kind(slots: dict) -> str:
    """The kind to use, after reading old route kinds as `route`; raises NeedsAgent for `other` or a mismatch."""
    kind = slots.get("kind")
    if kind in ("other", "unsupported"):
        raise NeedsAgent("The parser found no solver kind that answers this question completely")
    if kind in OLD_ROUTE_KINDS:
        kind = "route"
    if kind not in ANSWERS:
        raise ParseError(f"Unknown kind '{kind}'")
    asks_for = slots.get("asks_for")
    if asks_for is not None and asks_for not in ANSWERS[kind]:
        raise NeedsAgent(f"The question asks for {asks_for}, which kind {kind} does not answer")
    return kind


def slots_to_groups(slots: dict, building_map: BuildingMap) -> tuple[str, dict[str, str | None]]:
    """Map the LLM's slots onto the Resolver's regex-group names (non-route kinds)."""
    kind = slots["kind"]
    groups: dict[str, str | None] = {}
    for slot in ("start", "first", "second", "destination"):
        if slots.get(slot):
            groups[slot] = slots[slot]["name"]
            groups[f"{slot}_floor"] = slots[slot].get("floor") or floor_of(building_map, slots[slot]["name"])
    for slot in ("floor", "room_type", "asset_type", "item", "closed"):
        groups[slot] = slots.get(slot)
    if slots.get("min_width_m") is not None:
        groups["min_width"] = str(slots["min_width_m"])
        groups["item"] = groups["item"] or "load"
    if kind == "errand":
        groups["carry"] = "I can carry it on the stairs" if slots.get("may_use_stairs") is not False else (
            "I can't use the stairs"
        )
    template_name = kind
    if kind == "room_stacked":
        if slots.get("direction") not in ("above", "below"):
            raise ParseError("room_stacked needs direction above or below")
        template_name = f"room_stacked_{slots['direction']}"
    return template_name, groups


def place_ids(building_map: BuildingMap, place: dict) -> list[str]:
    floor_id = Resolver(building_map).floor_id(place["floor"]) if place.get("floor") else None
    found = resolve_place(building_map, place["name"], floor_id, bool(place.get("is_item")))
    if not found:
        raise ParseError(f"No place matches '{place['name']}'" + (f" on {place['floor']}" if place.get("floor") else ""))
    return found


def route_spec(slots: dict, building_map: BuildingMap) -> ParsedQuestion:
    """A route question: the warm-up kind it matches exactly, else `route_query` with every constraint."""
    if not slots.get("start") or not slots.get("destination"):
        raise ParseError("A route needs a start and a destination")
    stops = [place_ids(building_map, slots["start"]),
             *[place_ids(building_map, stop) for stop in slots.get("stops") or []],
             place_ids(building_map, slots["destination"])]
    names = list(slots.get("closures") or [])
    if slots.get("kind") == "route_with_closure" and slots.get("closed"):
        names.append(slots["closed"])
    try:
        closed = list(dict.fromkeys(building_map.find_element(name) for name in names))
    except MapError as error:
        raise ParseError(f"Closure: {error}") from error
    step_free = bool(slots.get("step_free")) or slots.get("kind") == "route_step_free"
    forklift, min_width = bool(slots.get("forklift")), slots.get("min_width_m")
    if all(len(candidates) == 1 for candidates in stops) and not forklift and min_width is None:
        ids = [candidates[0] for candidates in stops]
        ends = {"start": ids[0], "destination": ids[-1]}
        if len(ids) > 2 and not step_free and not closed:
            return ParsedQuestion("tour", {**ends, "stops": ids})
        if len(ids) == 2 and not closed:
            return ParsedQuestion("route_step_free" if step_free else "route", ends)
        if len(ids) == 2 and not step_free and len(closed) == 1 and closed[0] in building_map.connectors:
            return ParsedQuestion("route_with_closure", {**ends, "closed": closed[0]})
    return ParsedQuestion("route_query", {"stops": stops, "step_free": step_free, "forklift": forklift,
                                          "min_width": min_width, "closed": closed})


def one_place(building_map: BuildingMap, slots: dict, slot: str) -> str:
    if not slots.get(slot):
        raise ParseError(f"The question needs a {slot} place")
    found = place_ids(building_map, slots[slot])
    if len(found) != 1:
        raise ParseError(f"'{slots[slot]['name']}' fits {len(found)} places")
    return found[0]


def change_spec(kind: str, slots: dict, building_map: BuildingMap) -> ParsedQuestion:
    """nearest_item / lift_closed / add_door slots → ids for core/solvers/changes.py."""
    if kind == "nearest_item":
        item = slots.get("item") or slots.get("asset_type")
        if not item:
            raise ParseError("nearest_item needs the item")
        return ParsedQuestion(kind, {"start": one_place(building_map, slots, "start"), "item": item})
    if kind == "lift_closed":
        name = slots.get("closed") or next(iter(slots.get("closures") or []), None)
        if not name:
            raise ParseError("lift_closed needs the closed lift")
        try:
            return ParsedQuestion(kind, {"closed": building_map.find_element(name)})
        except MapError as error:
            raise ParseError(f"Closure: {error}") from error
    return ParsedQuestion(kind, {"first": one_place(building_map, slots, "first"),
                                 "second": one_place(building_map, slots, "second")})


def build(slots: dict, building_map: BuildingMap) -> ParsedQuestion:
    """Slots (from the model or the cache) → resolved question; ParseError/NeedsAgent when they don't resolve."""
    kind = check_kind(slots)
    if kind == "route":
        return route_spec(slots, building_map)
    if kind in ("nearest_item", "lift_closed", "add_door"):
        return change_spec(kind, slots, building_map)
    template_name, groups = slots_to_groups(slots, building_map)
    return Resolver(building_map).build(template_name, groups)


class LlmQuestionParser:
    def __init__(self, client: object | None = None, cache: DecisionCache | None = None) -> None:
        self._client = client  # created on the first model call, so cached decisions need no API key
        self.cache = cache if cache is not None else DecisionCache.configured()
        self.usage = LlmUsage()

    @property
    def client(self) -> object:
        if self._client is None:
            self._client = make_client()
        return self._client

    def parse(self, text: str, building_map: BuildingMap) -> ParsedQuestion:
        key = decision_key("parser", VERSION, building_map, text)
        cached = self.cache.get(key)
        if isinstance(cached, dict):
            try:
                parsed = build(cached, building_map)
                parsed.notes["parser"] = "llm-cache"
                return parsed
            except NeedsAgent:
                raise
            except (ParseError, KeyError, TypeError):
                pass  # a decision that no longer resolves: ask the model again
        system = [
            {"type": "text", "text": INSTRUCTIONS},
            {
                "type": "text",
                "text": "Building vocabulary:\n" + building_vocabulary(building_map),
                "cache_control": {"type": "ephemeral"},
            },
        ]
        messages: list[dict] = [{"role": "user", "content": ANSWER_INSTRUCTION.sub("", text.strip())}]
        error: ParseError | None = None
        for _ in range(MAX_ATTEMPTS):
            reply = self.request(system, messages)
            try:
                slots = json.loads(reply)
                parsed = build(slots, building_map)
            except NeedsAgent:
                self.cache.put(key, slots)
                raise
            except (ParseError, KeyError, TypeError, ValueError) as caught:
                error = ParseError(str(caught))
                messages += [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"Those slots could not be resolved: {caught}. Correct them."},
                ]
                continue
            self.cache.put(key, slots)
            parsed.notes["parser"] = "llm"
            return parsed
        raise error or ParseError("LLM parser failed")

    def request(self, system: list[dict], messages: list[dict]) -> str:
        response = self.client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self.track(response.usage)
        if response.stop_reason == "refusal":
            raise ParseError("The model declined to parse the question")
        if response.stop_reason == "max_tokens":
            raise ParseError("The parser response was cut off")
        return next(block.text for block in response.content if block.type == "text")

    def track(self, usage: object) -> None:
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cache_read_input_tokens += usage.cache_read_input_tokens or 0
        self.usage.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0
