"""The Guide agent's tool layer: one building session + Anthropic tool definitions over the deterministic core.

  session = BuildingSession.load(Path("data/dev/proc-campus-dev-000"))
  session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
  client.messages.create(..., tools=TOOL_DEFINITIONS)   # then route every tool_use block to session.call

Every fact the agent states comes from these tools (D-003). The session holds what a conversation accumulates:
the user's routing profile (step-free, minimum door width, no lifts, forklift — docs/product/routing-profiles.md),
the route rules every route obeys (production bays destination-only, no shortcut outside — core/route_models.py,
Q-014) and the route model (the kit 1.1.0 one, door to door — the only one; `route_model` kept for callers), applied
building changes (closures, new doors), pending changes awaiting the user's confirmation, and UI events
(highlight rooms, draw a route). Changes go through propose → confirm → apply so the agent can show what it
understood before it edits the plan (docs/architecture/ai-agents.md#shared-tool-layer).

Errors are returned as {"error": ...} results instead of raised, so the model can repair a vague place name by
searching or ask the user which of the listed candidates they mean."""

import copy
import itertools
from dataclasses import asdict, dataclass, field
from pathlib import Path

from shapely.geometry import Point

from agent import places
from agent.solver_agent import ALLOWED_MODULES, namespace, run_code
from core.directions import about_m, guidance, guidance_steps
from core import navigation, route_models
from core.building_map import LIFT, OUTSIDE, BuildingMap, MapError
from core.preferences import Penalties
from core.route_query import route_query, shortlist
from core.route_models import FORKLIFT_MIN_WIDTH_M, KIT, RouteRules
from core.solvers import SOLVERS, solve
from core.solvers.geometry import adjacent_floor, centre_3d, polygon
from core.solvers.reachability import is_room, rooms_on_floor
from core.solvers.routing import with_new_door
from core.solvers.walls import shared_wall_neighbours

MAX_RESULTS = 15
MAX_NEAREST_MEASURED = 5  # find_nearest for an item: holders (nearest first by the solver) measured with find_route
# Kit README: some Swiss Dwellings floors are centred per floor rather than aligned (84 of 108 multi-floor Swiss
# buildings have every floor's space-bbox centre within 2 m of the origin on each axis; 82 with a Euclidean 2 m
# radius), so "directly above/below" is meaningless there.
UNALIGNED_SOURCES = {"swiss_dwellings"}


# Persona presets for set_profile, from the "Profiles per persona" table in docs/product/routing-profiles.md.
# Only presets the graph can honour today (hard filters: step-free, minimum door width, no lifts). "assumed" lists
# values the user did not give, so the Guide can say "I assumed 0.8 m; tell me if yours is wider". "needs" lists
# values that have no default and must be asked (trolley width). `avoid_stairs` is not a separate field: every
# stairs connector in the data is step_free: false, so step_free routing already excludes stairs.
PRESETS: dict[str, dict] = {
    "default": {"values": {"step_free": False, "min_door_width_m": None, "avoid_lifts": False}},
    "wheelchair": {"values": {"step_free": True, "min_door_width_m": 0.8}, "assumed": ["min_door_width_m"]},
    "pram": {"values": {"step_free": True, "min_door_width_m": 0.8}, "assumed": ["min_door_width_m"]},
    "trolley": {"values": {"step_free": True}, "needs": ["min_door_width_m"]},
    "no_lifts": {"values": {"avoid_lifts": True}},
    # Organiser rule (Q-014): forklift aisles and openings >= 3 m only, pedestrian walkways don't count.
    "forklift": {"values": {"step_free": True, "min_door_width_m": FORKLIFT_MIN_WIDTH_M, "forklift": True}},
}
PROFILE_FIELDS = ("step_free", "min_door_width_m", "avoid_lifts", "forklift")
# Route preferences (app access mode only, docs/superpowers/specs/2026-10-25-access-profiles-design.md): soft
# penalties in metres-equivalent from the persona table in docs/product/routing-profiles.md, and avoided room types.
PREFERENCE_FIELDS = ("avoid_room_types", "prefer_lifts", "fewer_doors", "quiet", "avoid_halls", "simple_routes")
PENALTIES_M = {  # field → Penalties values; several preferences combine by the larger value
    "prefer_lifts": {"stairs_per_flight_m": 20.0},  # low_stamina: stairs 20 m/floor
    "fewer_doors": {"door_m": 3.0},  # crutches: door 3 m
    "quiet": {"noisy_m": 40.0, "hall_m": 10.0},  # quiet: noisy 40 m, hall 10 m
    "avoid_halls": {"hall_m": 30.0},  # low_vision: hall 30 m
    "simple_routes": {"space_change_m": 3.0},  # simple: space change 3 m
}
GUIDE_PREFERENCES = ("language", "reply_style", "voice")  # how the Guide talks; no effect on routes


@dataclass
class RoutingProfile:
    step_free: bool = False
    min_door_width_m: float | None = None
    avoid_lifts: bool = False
    forklift: bool = False  # no stairs, openings >= 3 m, no walkway-like spaces (route_models.RouteRules)
    preset: str = "default"  # the last preset applied; explicit fields may refine it
    assumed: list[str] = field(default_factory=list)  # fields set from a preset default, not from the user
    avoid_room_types: list[str] = field(default_factory=list)  # PREFERENCE_FIELDS: app preferences only
    prefer_lifts: bool = False
    fewer_doors: bool = False
    quiet: bool = False
    avoid_halls: bool = False
    simple_routes: bool = False

    def penalties(self) -> Penalties | None:
        values: dict[str, float] = {}
        for name, spec in PENALTIES_M.items():
            if getattr(self, name):
                for key, metres in spec.items():
                    values[key] = max(values.get(key, 0.0), metres)
        penalties = Penalties(**values, avoid_room_types=frozenset(self.avoid_room_types))
        return penalties if penalties.active() else None

    def describe(self) -> str:
        parts = ["step-free" if self.step_free else "stairs allowed"]
        if self.min_door_width_m:
            assumed = " (assumed)" if "min_door_width_m" in self.assumed else ""
            parts.append(f"doors at least {self.min_door_width_m} m wide{assumed}")
        if self.avoid_lifts:
            parts.append("no lifts")
        if self.forklift:
            parts.append("forklift (no stairs, no walkways)")
        if self.avoid_room_types:
            parts.append("avoiding " + ", ".join(room.replace("_", " ") for room in self.avoid_room_types))
        labels = {"prefer_lifts": "prefers lifts", "fewer_doors": "fewer doors", "quiet": "quiet route",
                  "avoid_halls": "avoids open halls", "simple_routes": "simple routes"}
        parts += [label for name, label in labels.items() if getattr(self, name)]
        return ", ".join(parts)


@dataclass
class Change:
    id: str
    action: str  # close | reopen | add_door
    targets: list[str]
    summary: str
    effect: dict = field(default_factory=dict)


class BuildingSession:
    def __init__(self, building: BuildingMap) -> None:
        # The session owns a private copy: applied changes never leak into other sessions or cached maps.
        self.building = BuildingMap(copy.deepcopy(building.data))
        self.profile = RoutingProfile()
        self.pending: dict[str, Change] = {}
        self.applied: list[Change] = []
        self.snapshots: dict[str, tuple[BuildingMap, BuildingMap]] = {}  # applied change id → (before, after)
        self.events: list[dict] = []
        self.emitting = True  # off while predicting, so hypothetical routes never reach the UI
        self.last_route: dict | None = None
        self.route_model = KIT  # kit 1.1.0 route model ("geodesic" is an alias since 1.1.0)
        self._ids = itertools.count(1)
        # Access mode only (backend/access.py): names of spaces/assets this viewer may not see; the building above
        # is already a copy without them (core/access.py). Empty everywhere else, so nothing changes.
        self.restricted_names: set[str] = set()
        # Access mode only: remembered preferences. Off = the tool list and every route exactly as before.
        self.preferences_enabled = False
        self.auto_capture = True  # the user lets the Guide remember what they say (settings switch)
        self.guide_preferences: dict = {}  # GUIDE_PREFERENCES values (language, reply_style, voice)
        # Access mode, admin only: (object name or id, destination) → dispatch result (backend/fleet.py).
        self.object_dispatch = None
        # Where the user is, from the app's "you are here" figure: {"space_id", "name", "floor"} (+ "point", where
        # in the room it stands) or None. "here" as a place means this space (HERE), so the Guide never has to ask.
        self.user_location: dict | None = None
        # Buildings nearby (agent/campus.py), set by the backend for buildings with a real position; None = none.
        self.campus = None

    @classmethod
    def load(cls, directory: Path) -> "BuildingSession":
        return cls(BuildingMap.load(directory))

    # ---------- dispatch ----------

    def call(self, name: str, arguments: dict) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            result = handler(**arguments)
        except KeyError as error:
            result = {"error": str(error.args[0]) if error.args else "Unknown id"}
        except (MapError, ValueError, TypeError) as error:
            result = {"error": str(error)}
        if self.restricted_names and ("error" in result or result.get("total") == 0):
            named = self.restricted_hit(arguments)
            if named:
                return {"error": "restricted", "restricted": named,
                        "message": f"'{named}' is in a restricted area this user may not enter or see. Say so "
                                   "without any detail about it and offer a public place instead."}
        return result

    def restricted_hit(self, arguments: dict) -> str | None:
        """The first argument phrase that names a restricted space or asset (whole name, or a word run of ≥ 3
        letters inside one)."""
        phrases = []
        for value in arguments.values():
            phrases += value if isinstance(value, list) else [value]
        for phrase in phrases:
            if not isinstance(phrase, str) or len(phrase.strip()) < 3:
                continue
            lowered = phrase.strip().lower()
            if any(lowered == name or lowered in name or name in lowered for name in self.restricted_names):
                return phrase
        return None

    # ---------- profile → routing constraints ----------

    def profile_closures(self, building: BuildingMap | None = None) -> list[str]:
        """Openings narrower than the profile's minimum width and lifts (if avoided) act as closed."""
        building = building or self.building
        closed = []
        if self.profile.min_door_width_m:
            closed += [
                opening["id"]
                for opening in building.openings.values()
                if opening["width_m"] < self.profile.min_door_width_m
            ]
        if self.profile.avoid_lifts:
            closed += [c["id"] for c in building.connectors.values() if c["kind"] == LIFT]
        return closed

    def route_rules(self) -> RouteRules:
        """Rules every Guide route obeys; the forklift rule follows the profile."""
        return RouteRules(bays_destination_only=True, no_outside=True, forklift=self.profile.forklift)

    def space_summary(self, space_id: str) -> dict:
        space = self.building.spaces[space_id]
        return {
            "id": space_id,
            "name": space["name"],
            "ref": space.get("ref"),
            "room_type": space["room_type"],
            "floor": self.building.floor_name(space["floor_id"]),
        }

    def stop(self, reference: str) -> str:
        return OUTSIDE if reference == OUTSIDE else self.resolve(reference)

    def resolve(self, reference: str) -> str:
        """One space id for a phrase, else MapError listing the candidates or near-miss names (agent/places.py).
        "here" / "my location" is the space of the app's "you are here" figure."""
        if reference.strip().lower() in HERE:
            if self.user_location is None:
                raise MapError("The user's position is not known; ask where they are.")
            return self.user_location["space_id"]
        found = places.candidates(self.building, reference)
        if len(found) != 1:
            raise MapError(places.problem(self.building, reference, found))
        return found[0]

    def set_location(self, space_id: str | None, point: list[float] | None = None) -> dict | None:
        """The app's "you are here" figure was put down in `space_id` (None = taken away), at `point` (plan metres;
        kept only if it lies in that space). Routes are measured from the space's anchor as always; the point only
        moves where the drawn line starts (`start_point` of a route event, core/routeline.py)."""
        if space_id is None:
            self.user_location = None
            return None
        space = self.building.spaces[space_id]
        self.user_location = {"space_id": space_id, "name": space["name"], "ref": space.get("ref"),
                              "floor": self.building.floor_name(space["floor_id"])}
        if point is not None and polygon(space).buffer(0.05).contains(Point(point[0], point[1])):
            self.user_location["point"] = [round(point[0], 3), round(point[1], 3)]
        return self.user_location

    def start_point(self, space_id: str) -> dict:
        """For a route event starting in `space_id`: {"start_point": the figure's point} when the figure stands
        there, else nothing (the drawn line starts at the anchor)."""
        location = self.user_location or {}
        return {"start_point": location["point"]} if location.get("space_id") == space_id and "point" in location else {}

    def highlight(self, space_ids: list[str], asset_ids: list[str] = ()) -> None:
        """Show these rooms (and items in them) on the user's map, as the answer."""
        if self.emitting and (space_ids or asset_ids):
            spaces = list(dict.fromkeys([*space_ids, *(self.building.assets[a]["space_id"] for a in asset_ids)]))
            self.events.append({"type": "highlight", "space_ids": spaces[:MAX_RESULTS * 2],
                                "asset_ids": list(asset_ids)[:MAX_RESULTS * 2]})

    def destination_options(self, start: str, destination: str, via: list[str]) -> dict | None:
        """A destination phrase that fits several spaces: the route length to each, shortest first. find_route takes
        the nearest reachable one and lists the others (D-012, 2026-10-27); the error is for none reachable."""
        found = places.candidates(self.building, destination)
        if not 1 < len(found) <= places.MAX_OPTIONS:
            return None
        options = []
        for space_id in found:
            route = navigation.find_route(self.building, start, space_id, step_free=self.profile.step_free,
                                          closed=self.profile_closures(), via=via, model=self.route_model,
                                          rules=self.route_rules(), penalties=self.profile.penalties()).to_dict()
            options.append({**self.space_summary(space_id),
                            "length_m": route["length_m"] if route.get("reachable") else None})
        options.sort(key=lambda option: (option["length_m"] is None, option["length_m"] or 0.0))
        extras = {option["id"]: f"{option['length_m']} m" if option["length_m"] is not None else "unreachable"
                  for option in options}
        return {"error": places.problem(self.building, destination, [o["id"] for o in options], extras),
                "options": options, "destination": destination}

    # ---------- read-only tools ----------

    def tool_building_overview(self) -> dict:
        overview = self.building.overview()
        overview["profile"] = self.profile.describe()
        overview["applied_changes"] = [change.summary for change in self.applied]
        return overview

    def tool_search(self, query: str, floor_level: int | None = None) -> dict:
        results = self.building.search(query, floor_level)
        shown = results[:MAX_RESULTS]
        self.highlight([r["id"] for r in shown if r["kind"] == "space"], [r["id"] for r in shown if r["kind"] == "asset"])
        result = {"total": len(results), "results": shown}
        if not results and self.campus is not None and self.campus.neighbours():
            result["hint"] = "Nothing here; search_nearby_buildings looks in the buildings next to this one."
        return result

    def tool_locate(self, query: str, floor_id: str | None = None) -> dict:
        result = navigation.locate(self.building, query, floor_id).to_dict()
        self.highlight([], [hit["asset_id"] for hit in result.get("assets") or []])
        if not result.get("total") and self.campus is not None and self.campus.neighbours():
            result["hint"] = "Nothing here; search_nearby_buildings looks in the buildings next to this one."
        return result

    def tool_count_assets(self, asset_type: str, floor_id: str | None = None) -> dict:
        resolved = navigation.resolve_asset_type(self.building, asset_type)
        if resolved is None:
            return {"error": f"No asset type matches '{asset_type}'"}
        return navigation.count_assets(self.building, resolved, floor_id).to_dict()

    def tool_room_facts(self, space: str) -> dict:
        space_id = self.resolve(space)
        record = self.building.spaces[space_id]
        x, y, z = centre_3d(self.building, space_id)
        stacked: dict = {}
        if self.building.data["building"]["source"] in UNALIGNED_SOURCES:
            stacked["note"] = "floors of this building are not aligned in the data, so rooms above/below are unknown"
        for direction in ("above", "below") if not stacked else ():
            if adjacent_floor(self.building, record["floor_id"], direction) is not None:
                stacked[direction] = self.space_summary(solve(self.building, "room_stacked", {
                    "start": space_id, "direction": direction}).value)
        doors = [
            {
                "id": opening["id"],
                "kind": opening["kind"],
                "to": opening["space_ids"][1] if opening["space_ids"][0] == space_id else opening["space_ids"][0],
                "width_m": opening["width_m"],
                "step_free": opening["step_free"],
            }
            for opening in self.building.openings.values()
            if space_id in opening["space_ids"]
        ]
        self.highlight([space_id])
        return {
            **self.space_summary(space_id),
            "area_m2": round(polygon(record).area, 2),
            "centre": [round(x, 2), round(y, 2), round(z, 2)],
            "shared_walls": [
                {"id": item["id"], "name": item["name"], "shared_m": item["shared_m"]}
                for item in shared_wall_neighbours(self.building, space_id)
            ],
            "doors": doors,
            "stacked": stacked,
            "assets": [
                asset["name"] for asset in self.building.assets.values() if asset["space_id"] == space_id
            ][:MAX_RESULTS],
        }

    def tool_find_route(self, start: str, destination: str, via: list[str] | None = None,
                        closed: list[str] | None = None) -> dict:
        start, via = self.stop(start), [self.stop(item) for item in via or ()]
        options = self.destination_options(start, destination, via) if destination != OUTSIDE else None
        if options and options["options"][0]["length_m"] is None:
            return options
        destination = options["options"][0]["id"] if options else self.stop(destination)
        route = navigation.find_route(
            self.building,
            start,
            destination,
            step_free=self.profile.step_free,
            closed=[*self.profile_closures(), *(closed or [])],
            via=via or (),
            model=self.route_model,
            rules=self.route_rules(),
            penalties=self.profile.penalties(),
        ).to_dict()
        route["profile"] = self.profile.describe()
        if options:
            route["chosen"] = {"note": f"'{options['destination']}' fits {len(options['options'])} places: routed to "
                                       "the nearest. Name it in a few words; list the others only if asked.",
                               "others": [option for option in options["options"][1:3]
                                          if option["length_m"] is not None]}
        self.guide_steps(route)
        if route.get("reachable") and self.emitting:
            self.last_route = {"start": start, "destination": destination, "via": via or []}
            self.events.append({"type": "route", "space_path": route["space_path"],
                                "element_path": route["element_path"], "length_m": route["length_m"],
                                "profile": route["profile"], **self.start_point(start)})
        return route

    def tool_find_nearest(self, start: str, query: str, floor_id: str | None = None,
                          closed: list[str] | None = None) -> dict:
        """The nearest room holding `query` (an item kind like "toilet", or a room kind/name) by walking distance
        under the profile: routes to it (one route event, the map shows only that one) and lists the next ones.
        `closed`: closures for this question only (names or ids). Only the 12 candidates nearest in a straight line
        are routed to (core/route_query.shortlist), so big buildings with many matches stay fast."""
        start = self.stop(start)
        closures = [*self.profile_closures(), *(closed or [])]
        if floor_id is None and start != OUTSIDE and navigation.match_assets(self.building, query)[1]:
            return self.nearest_item(start, query, closures, closed)
        found = navigation.locate(self.building, query, floor_id).to_dict()
        spaces = list(dict.fromkeys(hit["space_id"] for hit in found.get("assets") or []))
        if not spaces:
            spaces = [hit["id"] for hit in self.building.search(query) if hit["kind"] == "space"
                      and floor_id in (None, self.building.spaces[hit["id"]]["floor_id"])]
        spaces = [space for space in spaces if space != start]
        if spaces and start != OUTSIDE:
            spaces = shortlist(self.building, start, spaces)
        if not spaces:
            result = {"error": f"Nothing matching '{query}' in this building."}
            if self.campus is not None and self.campus.neighbours():
                result["hint"] = "search_nearby_buildings looks in the buildings next to this one."
            return result
        ranked = []
        for space_id in spaces:
            route = navigation.find_route(self.building, start, space_id, step_free=self.profile.step_free,
                                          closed=closures, model=self.route_model,
                                          rules=self.route_rules(), penalties=self.profile.penalties()).to_dict()
            if route.get("reachable"):
                ranked.append((route["length_m"], space_id))
        if not ranked:
            return {"error": f"No room with '{query}' is reachable from here under the current profile.",
                    "profile": self.profile.describe()}
        ranked.sort()
        route = self.tool_find_route(start, ranked[0][1], closed=closed)
        route["nearest"] = self.space_summary(ranked[0][1])
        route["next_nearest"] = [{**self.space_summary(space_id), "about_m": about_m(length)}
                                 for length, space_id in ranked[1:3]]
        return route  # the route event already focuses the room; a highlight after it would replace the route

    def nearest_item(self, start: str, query: str, closures: list[str], closed: list[str] | None) -> dict:
        """find_nearest for an item: the shared nearest_item solver (core/solvers/changes.py, the benchmark's
        ranking) under this session's route model, rules, step-free rule and closures picks the holders; the
        nearest few are then measured with the same find_route the user is shown (profile penalties included), so
        the nearest, its length and the drawn route always agree."""
        try:
            holders = solve(self.building, "nearest_item", {
                "start": start, "item": query, "step_free": self.profile.step_free, "closed": closures,
                "model": self.route_model, "rules": self.route_rules()}).evidence["holders"]
        except (ValueError, MapError) as error:
            return {"error": str(error), "profile": self.profile.describe()}
        holders = [space_id for space_id in holders if space_id != start]
        if not holders:
            return {"error": f"The nearest '{query}' is in the room you are in.", "nearest": self.space_summary(start)}
        ranked = []
        for space_id in holders[:MAX_NEAREST_MEASURED]:
            route = navigation.find_route(self.building, start, space_id, step_free=self.profile.step_free,
                                          closed=closures, model=self.route_model, rules=self.route_rules(),
                                          penalties=self.profile.penalties(), include_steps=False)
            if route.reachable:
                ranked.append((route.length_m, space_id))
        if not ranked:
            return {"error": f"No room with '{query}' is reachable from here under the current profile.",
                    "profile": self.profile.describe()}
        ranked.sort()
        route = self.tool_find_route(start, ranked[0][1], closed=closed)
        route["nearest"] = self.space_summary(ranked[0][1])
        route["next_nearest"] = [{**self.space_summary(space_id), "about_m": about_m(length)}
                                 for length, space_id in ranked[1:3]]
        return route  # the route event already focuses the room; a highlight after it would replace the route

    def tool_tour(self, stops: list[str]) -> dict:
        tour = navigation.tour(
            self.building, [self.stop(item) for item in stops], step_free=self.profile.step_free,
            closed=self.profile_closures(), model=self.route_model, rules=self.route_rules(),
            penalties=self.profile.penalties(),
        ).to_dict()
        if tour.get("reachable"):
            tour["about_m"] = about_m(tour["length_m"])
            for leg in tour.get("legs") or []:
                self.guide_steps(leg)
        return tour

    def tool_compute(self, code: str) -> dict:
        """Run Python over a copy of the building (the solver agent's sandbox): {"output"} or {"output", "error"}.
        Its route() routes as find_route does — the Guide's rules (production bays destination-only), the user's
        profile and its closures — so code and tools never disagree on whether a route exists."""
        view = copy.deepcopy(self.building)
        scope = namespace(view)

        def place(reference: str) -> list[str]:
            if reference.strip().lower() in HERE:
                return [self.resolve(reference)]
            return scope["place"](reference) or [view.resolve_space(reference)]

        def route(start: str, destination: str, stops: list[str] | tuple[str, ...] = (), step_free: bool | None = None,
                  forklift: bool | None = None, min_width: float | None = None,
                  closed: list[str] | tuple[str, ...] = ()) -> dict:
            rules = self.route_rules()
            if forklift is not None:
                rules = RouteRules(bays_destination_only=rules.bays_destination_only, no_outside=rules.no_outside,
                                   forklift=forklift)
            return route_query(view, [place(start), *[place(stop) for stop in stops], place(destination)],
                               step_free=self.profile.step_free if step_free is None else step_free,
                               min_width=min_width, closed=[*self.profile_closures(view), *closed], rules=rules,
                               include_steps=False)

        scope["route"] = route
        return run_code(code, scope)

    def guide_steps(self, route: dict) -> None:
        """Followable steps (turns, landmarks, rounded metres, no ids) instead of the kit's step text, plus the
        rounded total a person would say (`about_m`; `length_m` stays exact)."""
        if route.get("reachable") and route.get("space_path"):
            route["steps"] = guidance_steps(self.building, route["space_path"], route["element_path"])
            route["about_m"] = about_m(route["length_m"])

    def tool_reachable_rooms(self, start: str, floor_id: str | None = None) -> dict:
        """Rooms reachable from `start` under the current profile and changes."""
        start_id = self.resolve(start)
        reached = set(self.space_distances(self.building, start_id))
        rooms = rooms_on_floor(self.building, reached, floor_id) if floor_id else sorted(
            space_id for space_id in reached if is_room(self.building.spaces[space_id]))
        return {"count": len(rooms), "rooms": rooms[:MAX_RESULTS * 4], "profile": self.profile.describe()}

    def tool_solve(self, kind: str, params: dict) -> dict:
        """Run one of the benchmark solvers (areas, largest room, walls, stacking, deliveries, what-ifs...)."""
        result = solve(self.building, kind, params)
        return {"value": result.value, "unit": result.unit, "area_m2": result.area_m2,
                "explanation": result.explanation, "evidence": result.evidence}

    # ---------- profile ----------

    def tool_set_profile(
        self, preset: str | None = None, step_free: bool | None = None, min_door_width_m: float | None = None,
        avoid_lifts: bool | None = None, forklift: bool | None = None, avoid_room_types: list[str] | None = None,
        prefer_lifts: bool | None = None, fewer_doors: bool | None = None, quiet: bool | None = None,
        avoid_halls: bool | None = None, simple_routes: bool | None = None, scope: str | None = None,
    ) -> dict:
        """Apply a persona preset (its fields only; others are kept), then explicit fields, which override it.
        preset "default" resets everything. The result says what changed and which values are assumed."""
        if preset is not None and preset not in PRESETS:
            raise ValueError(f"Unknown preset '{preset}'; use one of {', '.join(PRESETS)}")
        if min_door_width_m is not None and min_door_width_m < 0:
            raise ValueError("min_door_width_m must be ≥ 0 (0 clears it)")
        fields = PROFILE_FIELDS + PREFERENCE_FIELDS
        before = {name: copy.copy(getattr(self.profile, name)) for name in fields}
        needs: list[str] = []
        if preset == "default":
            self.profile = RoutingProfile()
        elif preset is not None:
            spec = PRESETS[preset]
            for name, value in spec["values"].items():
                setattr(self.profile, name, value)
                if name in self.profile.assumed:
                    self.profile.assumed.remove(name)
            self.profile.assumed += [name for name in spec.get("assumed", []) if name not in self.profile.assumed]
            self.profile.preset = preset
            needs = [name for name in spec.get("needs", []) if min_door_width_m is None]
        explicit = {"step_free": step_free, "min_door_width_m": min_door_width_m, "avoid_lifts": avoid_lifts,
                    "forklift": forklift}
        if preset == "default":  # clears mobility constraints only; route preferences are changed by name
            for name in PREFERENCE_FIELDS:
                setattr(self.profile, name, before[name])
        explicit.update({"avoid_room_types": avoid_room_types, "prefer_lifts": prefer_lifts,
                         "fewer_doors": fewer_doors, "quiet": quiet, "avoid_halls": avoid_halls,
                         "simple_routes": simple_routes})
        if avoid_room_types is not None:
            explicit["avoid_room_types"] = sorted({str(room).strip().lower().replace(" ", "_")
                                                   for room in avoid_room_types if str(room).strip()})
        for name, value in explicit.items():
            if value is None:
                continue
            setattr(self.profile, name, (value or None) if name == "min_door_width_m" else value)
            if name in self.profile.assumed:
                self.profile.assumed.remove(name)
        changed = {name: getattr(self.profile, name) for name in fields
                   if getattr(self.profile, name) != before[name]}
        result = {"profile": asdict(self.profile), "summary": self.profile.describe(), "changed": changed,
                  "assumed": list(self.profile.assumed)}
        if preset is not None:
            result["preset"] = preset
        if needs:
            result["needs"] = needs  # ask the user, e.g. how wide the trolley is
        self.remember_preference(changed, scope, result)
        return result

    def remember_preference(self, changed: dict, scope: str | None, result: dict) -> None:
        """Access mode: tell the app to store what changed (global, or for this building only)."""
        if not (self.preferences_enabled and self.auto_capture and changed):
            return
        scope = "building" if scope == "building" else "global"
        self.events.append({"type": "preference", "scope": scope, "values": changed})
        result["remembered"] = scope

    def tool_set_preference(self, language: str | None = None, reply_style: str | None = None,
                            voice: bool | None = None, favourite: str | None = None,
                            scope: str | None = None) -> dict:
        """How the Guide talks to this user, and saved places (favourites are always per building)."""
        if not self.preferences_enabled:
            return {"error": "Preferences are not available here."}
        if reply_style is not None and reply_style not in ("brief", "detailed"):
            raise ValueError("reply_style must be 'brief' or 'detailed'")
        changed = {name: value for name, value in
                   {"language": language, "reply_style": reply_style, "voice": voice}.items()
                   if value is not None and self.guide_preferences.get(name) != value}
        self.guide_preferences.update(changed)
        result: dict = {"preferences": dict(self.guide_preferences), "changed": changed}
        if favourite is not None:
            space_id = self.resolve(favourite)
            result["favourite"] = self.space_summary(space_id)
            if self.auto_capture:
                self.events.append({"type": "preference", "scope": "building", "values": {"favourite": space_id}})
                result["remembered"] = "building"
        self.remember_preference(changed, scope, result)
        return result

    def apply_preferences(self, values: dict) -> None:
        """Effective preferences from the app (global ← this building) at session start or after a settings change;
        no events, nothing re-remembered."""
        for name in ("step_free", "avoid_lifts", *PREFERENCE_FIELDS[1:]):
            if name in values:
                setattr(self.profile, name, bool(values[name]))
        if "avoid_room_types" in values:
            rooms = values["avoid_room_types"] or []
            if not isinstance(rooms, list):
                raise ValueError("avoid_room_types must be a list")
            self.profile.avoid_room_types = sorted({str(room) for room in rooms})
        if "min_door_width_m" in values:
            width = values["min_door_width_m"]
            self.profile.min_door_width_m = float(width) if width else None
            if "min_door_width_m" in self.profile.assumed:
                self.profile.assumed.remove("min_door_width_m")
        self.guide_preferences = {name: values[name] for name in GUIDE_PREFERENCES if values.get(name) is not None}

    def tool_definitions(self) -> list[dict]:
        """TOOL_DEFINITIONS, with the preference fields and set_preference only when preferences are on,
        send_object for the building admin, and the campus tools for a building with neighbours."""
        campus = CAMPUS_TOOLS if self.campus is not None and self.campus.neighbours() else []
        if not self.preferences_enabled:
            return TOOL_DEFINITIONS + campus if campus else TOOL_DEFINITIONS
        tools = [PREFERENCE_SET_PROFILE if tool["name"] == "set_profile" else tool
                 for tool in TOOL_DEFINITIONS] + [SET_PREFERENCE]
        return (tools + [SEND_OBJECT] if self.object_dispatch is not None else tools) + campus

    def tool_send_object(self, object: str, destination: str) -> dict:
        if self.object_dispatch is None:
            return {"error": "Only the building admin can send robots or vehicles."}
        return self.object_dispatch(object, destination)

    # ---------- changes: propose → confirm → apply ----------

    def tool_propose_change(self, action: str, targets: list[str]) -> dict:
        if action in ("close", "reopen"):
            element_ids = [self.building.find_element(target) for target in targets]
            summary = f"{action} " + ", ".join(self.element_name(element) for element in element_ids)
            change = Change(f"C{next(self._ids)}", action, element_ids, summary)
        elif action == "add_door":
            if len(targets) != 2:
                return {"error": "add_door needs exactly two spaces"}
            first, second = (self.resolve(target) for target in targets)
            _, opening = with_new_door(self.building, first, second)
            summary = f"add a door between {self.building.describe_space(first)} and " \
                f"{self.building.describe_space(second)}"
            change = Change(f"C{next(self._ids)}", action, [first, second], summary,
                            {"door_position": opening["position"]})
        else:
            return {"error": "action must be close, reopen or add_door"}
        change.effect.update(self.predict(change))
        if action == "close":
            change.effect.update(self.lift_effect(change.targets))
        self.pending[change.id] = change
        try:
            comparison, _ = self.comparison(change.id)
            change.effect.update({key: comparison[key] for key in IMPACT_KEYS})
        except MapError:  # no last route and no entrance to compare from: the route prediction is all we have
            pass
        return {"change_id": change.id, "summary": summary, "effect": change.effect, "needs_confirmation": True}

    def lift_effect(self, element_ids: list[str]) -> dict:
        """Closing a lift: the rooms that lose step-free access from the entrance, whatever the user's profile —
        the shared lift_closed solver (core/solvers/changes.py), as the benchmark answers it."""
        lifts = [element for element in element_ids
                 if self.building.connectors.get(element, {}).get("kind") == "lift"
                 or self.building.spaces.get(element, {}).get("type") == "lift"]
        effect = {}
        for lift in lifts:
            result = solve(self.building, "lift_closed", {"closed": lift})
            effect[f"step_free_lost_{lift}"] = {"rooms": len(result.evidence["rooms"]),
                                                "by_floor": self.names_by_floor(result.evidence["rooms"])}
        return effect

    def tool_apply_change(self, change_id: str) -> dict:
        change = self.pending.pop(change_id, None)
        if change is None:
            return {"error": f"No pending change '{change_id}'; pending: {sorted(self.pending) or 'none'}"}
        before = self.building
        self.building = self.changed_building(change)
        self.snapshots[change.id] = (before, self.building)
        self.applied.append(change)
        self.events.append({"type": "change", "summary": change.summary, "targets": change.targets})
        return {"applied": change.summary, "applied_changes": [item.summary for item in self.applied]}

    def changed_building(self, change: Change) -> BuildingMap:
        if change.action == "add_door":
            changed, opening = with_new_door(self.building, *change.targets)
            opening["id"] = f"{opening['floor_id']}-O-new{len(self.applied) + 1}"
            changed.openings = {item["id"]: item for item in changed.data["openings"]}
            return changed
        changed = BuildingMap(self.building.data)
        changed.closed = set(self.building.closed)
        if change.action == "close":
            changed.closed |= set(change.targets)
        else:
            changed.closed -= set(change.targets)
        return changed

    def predict(self, change: Change) -> dict:
        """Effect of a change on the last route the user asked for (before → after), without applying it."""
        if self.last_route is None:
            return {}
        return self.predict_between(self.building, self.changed_building(change))

    def tool_compare_routes(self, change_id: str, start: str | None = None) -> dict:
        """Before → after a pending or applied change, from `start` under the user's profile: rooms that lost (or
        gained) access and the routes that got longer, in route-model metres."""
        result, lost = self.comparison(change_id, start)
        if lost:
            self.events.append({"type": "highlight", "space_ids": lost, "style": "lost_access"})
        return result

    def comparison(self, change_id: str, start: str | None = None) -> tuple[dict, list[str]]:
        """compare_routes without UI events: (result, ids of rooms that lost access)."""
        if change_id in self.pending:
            before, after = self.building, self.changed_building(self.pending[change_id])
            status = "pending"
        elif change_id in self.snapshots:
            before, after = self.snapshots[change_id]
            status = "applied"
        else:
            known = sorted(self.pending) + [change.id for change in self.applied]
            return {"error": f"No pending or applied change '{change_id}'; known: {known or 'none'}"}, []
        if start is None:
            start = self.last_route["start"] if self.last_route else self.main_entrance_space()
        start_id = self.resolve(start)
        old, new = self.room_distances(before, start_id), self.room_distances(after, start_id)
        longer = sorted(
            (
                {"room": self.space_summary(room)["name"], "id": room, "floor": self.space_summary(room)["floor"],
                 "before_m": round(old[room], 2), "after_m": round(new[room], 2),
                 "extra_m": round(new[room] - old[room], 2)}
                for room in old.keys() & new.keys()
                if new[room] - old[room] > 0.005
            ),
            key=lambda item: (-item["extra_m"], item["id"]),
        )
        lost = sorted(old.keys() - new.keys())
        gained = sorted(new.keys() - old.keys())
        result = {
            "change": (self.pending.get(change_id) or next(c for c in self.applied if c.id == change_id)).summary,
            "status": status,
            "from": self.building.describe_space(start_id),
            "profile": self.profile.describe(),
            "reachable_rooms_before": len(old),
            "reachable_rooms_after": len(new),
            "lost_access_count": len(lost),
            "lost_access_by_floor": self.names_by_floor(lost),
            "gained_access_count": len(gained),
            "longer_routes_count": len(longer),
            "max_extra_m": longer[0]["extra_m"] if longer else 0.0,
            "longer_routes": longer[:MAX_RESULTS],
        }
        if self.last_route and start == self.last_route["start"]:
            result["last_route"] = self.predict_between(before, after)
        return result, lost

    def names_by_floor(self, space_ids: list[str]) -> dict[str, dict]:
        """Floor name → {"count", "rooms": names}, floors bottom-up: complete, compact, counts from code."""
        grouped: dict[str, dict] = {}
        for floor in sorted(self.building.floors.values(), key=lambda floor: floor["level"]):
            names = sorted(self.building.spaces[space]["name"] for space in space_ids
                           if self.building.spaces[space]["floor_id"] == floor["id"])
            if names:
                grouped[floor["name"]] = {"count": len(names), "rooms": names}
        return grouped

    def space_distances(self, building: BuildingMap, start_id: str) -> dict[str, float]:
        """Route-model metres from `start_id` to every reachable space under the profile and rules in `building`."""
        view = navigation.routing_view(building, self.profile_closures(building))
        rules = self.route_rules()
        graph = route_models.route_graph(view, self.profile.step_free, self.route_model, rules)
        if start_id not in graph:
            return {}
        lengths = route_models.single_source(graph, route_models.endpoint_only(view, rules), start_id)
        return {node: length for node, length in lengths.items() if node in building.spaces}

    def room_distances(self, building: BuildingMap, start_id: str) -> dict[str, float]:
        """Route-model metres from `start_id` to every reachable room under the profile in `building`."""
        return {
            node: length for node, length in self.space_distances(building, start_id).items()
            if is_room(building.spaces[node])
        }

    def predict_between(self, before: BuildingMap, after: BuildingMap) -> dict:
        """The last route on `before` and on `after`; emits no events and keeps the session's last route."""
        current, last = self.building, self.last_route
        self.emitting = False
        try:
            self.building = before
            old = self.tool_find_route(**last)
            self.building = after
            new = self.tool_find_route(**last)
        finally:
            self.building, self.emitting = current, True
        effect = {"last_route": f"{last['start']} → {last['destination']}", "before_m": old.get("length_m"),
                  "after_m": new.get("length_m"), "still_reachable": new.get("reachable", False)}
        if effect["before_m"] is not None and effect["after_m"] is not None:
            effect["extra_m"] = round(effect["after_m"] - effect["before_m"], 2)
        return effect

    def main_entrance_space(self) -> str:
        entrances = [o for o in self.building.openings.values() if o["kind"] == "entrance"]
        entrances.sort(key=lambda o: (not o["step_free"], o["id"]))
        if not entrances:
            raise MapError("The building has no entrance; give a start place.")
        return next(space for space in entrances[0]["space_ids"] if space in self.building.spaces)

    def element_name(self, element_id: str) -> str:
        if element_id in self.building.connectors:
            return self.building.connectors[element_id]["name"]
        if element_id in self.building.spaces:
            return self.building.describe_space(element_id)
        return f"opening {element_id}"

    # ---------- UI ----------

    def tool_show_on_map(self, space_ids: list[str] | None = None, asset_ids: list[str] | None = None) -> dict:
        """Rooms, and items (an asset id or exact name; also accepted among space_ids), shown as the answer."""
        rooms, items = [], []
        for item in [*(space_ids or ()), *(asset_ids or ())]:
            asset = self.asset_ref(item)
            if asset is not None:
                items.append(asset)
            else:
                rooms.append(self.resolve(item))
        self.highlight(rooms, items)
        return {"shown": rooms + items}

    def tool_set_my_location(self, place: str) -> dict:
        """The user said where they are: that space is "here" from now on, and the app puts its "you are here"
        figure there (event `location`) and zooms to it."""
        space_id = self.resolve(place)
        location = self.set_location(space_id)
        if self.emitting:
            self.events.append({"type": "location", "space_id": space_id})
        return {"location": location, "note": "The app now shows the user here; pass \"here\" as the start."}

    def route_card(self) -> list[dict]:
        """The steps of the app's next-move card for the last route shown (core/directions.guidance, as
        backend/sessions.py sends them with the route event); [] when there is none."""
        route = next((event for event in reversed(self.events) if event["type"] == "route"), None)
        if route is None:
            return []
        try:
            return guidance(self.building, route.get("space_path") or [], route.get("element_path") or [])
        except (KeyError, StopIteration):  # path no longer valid on this building
            return []

    def tool_show_route_step(self, step: int) -> dict:
        """Move the app's step card (and the map) to step `step` (1-based, the card's numbering) of the route the
        user is following (event `route_step`)."""
        steps = self.route_card()
        if not steps:
            return {"error": "No route is on the map."}
        if not 1 <= int(step) <= len(steps):
            return {"error": f"The route has steps 1 to {len(steps)}."}
        if self.emitting:
            self.events.append({"type": "route_step", "index": int(step) - 1})
        return {"shown": int(step), "of": len(steps), "text": steps[int(step) - 1]["text"]}

    def tool_open_edit_mode(self, request: str | None = None) -> dict:
        """Switch the app to its Edit mode (frontend/app/src/edit/), where the Builder (agent/builder.py) takes the
        request on a draft copy; this session's building is not changed."""
        wanted = (request or "").strip() or None
        if self.emitting:
            self.events.append({"type": "edit_mode", "request": wanted})
        return {"opened": True, "request": wanted,
                "note": "The app now shows the Edit mode; its Builder takes the request from here, on a copy."}

    def asset_ref(self, reference: str) -> str | None:
        if reference in self.building.assets:
            return reference
        wanted = reference.strip().lower()
        named = [a["id"] for a in self.building.assets.values() if a["name"].lower() == wanted]
        return named[0] if len(named) == 1 else None

    # ---------- buildings nearby (agent/campus.py) ----------

    def tool_search_nearby_buildings(self, query: str) -> dict:
        if self.campus is None:
            return {"error": "This building has no known neighbours."}
        result = self.campus.search(query)
        if self.emitting and result["buildings"]:
            self.events.append({"type": "elsewhere", "query": query, "buildings": [
                {"building": item["building_id"], "name": item["name"], "distance_m": item["distance_m"],
                 "total": item["total"], "first": item["results"][0]["name"] if item["results"] else None}
                for item in result["buildings"]]})
        return result

    def tool_route_to_building(self, start: str, building: str, destination: str) -> dict:
        if self.campus is None:
            return {"error": "This building has no known neighbours."}
        return self.campus.route(self, start, building, destination)


# What propose_change adds from compare_routes, so a proposal already says who loses access and how much longer.
IMPACT_KEYS = ("from", "reachable_rooms_before", "reachable_rooms_after", "lost_access_count",
               "lost_access_by_floor", "longer_routes_count", "max_extra_m")
PLACE = {"type": "string", "description": "Space id, room ref, exact room name, or asset name/id; \"here\" = "
         "where the user is (when the app knows it)"}
HERE = {"here", "me", "my location", "my position", "current location", "where i am", "where i am now"}
TOOL_DEFINITIONS: list[dict] = [
    {"name": "building_overview", "description": "Floors, stairs/lifts, entrances, the user's routing profile and "
     "applied changes. Call once at the start.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "search", "description": "Find spaces and assets whose name, ref or type contains every word.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                      "floor_level": {"type": "integer"}}, "required": ["query"]}},
    {"name": "locate", "description": "Where an item is: asset type (plural ok), name or id → rooms and floors.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                      "floor_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "count_assets", "description": "How many assets of a type, on one floor or the whole building.",
     "input_schema": {"type": "object", "properties": {"asset_type": {"type": "string"},
                      "floor_id": {"type": "string"}}, "required": ["asset_type"]}},
    {"name": "room_facts", "description": "Area, centre, shared walls, doors with widths, rooms above/below "
     "(omitted where floors aren't aligned), items in a room.",
     "input_schema": {"type": "object", "properties": {"space": PLACE}, "required": ["space"]}},
    {"name": "find_route", "description": "Shortest walk under the user's profile and current closures: metres, "
     "rooms passed, followable steps (turns, landmarks, rounded metres) and about_m (the rounded total). Routes never pass through production bays (destinations only) or outside "
     "the building; reachable=false + reason means no route under these rules — tell the user so. A destination "
     "that fits several places goes to the nearest; `chosen` lists the next ones.", "input_schema": {"type": "object", "properties": {
         "start": PLACE, "destination": PLACE, "via": {"type": "array", "items": PLACE}},
         "required": ["start", "destination"]}},
    {"name": "find_nearest", "description": "The nearest place with something (\"nearest toilet\", \"closest "
     "kitchen\", \"a meeting room near me\"): ranks every room holding that item kind (or of that room kind/name) by "
     "walking distance under the user's profile, routes to the nearest (the map shows that route only; the result "
     "is a find_route result) and lists the next two with about_m. Use it instead of several find_route calls. "
     "closed: lifts, stairs, rooms, corridors or doors closed for THIS question only (\"the lift is out of order\"); "
     "use propose_change for lasting closures.",
     "input_schema": {"type": "object", "properties": {
         "start": PLACE, "query": {"type": "string", "description": "item or room kind, e.g. toilet, kitchen"},
         "floor_id": {"type": "string", "description": "only when the user restricts the floor"},
         "closed": {"type": "array", "items": {"type": "string"}}},
         "required": ["start", "query"]}},
    {"name": "compute", "description": "Exact building analytics no other tool covers (the smallest / second-largest "
     "room, how many rooms of a kind, the narrowest door on a route, lists by any criterion). Runs Python over a copy "
     "of the building and returns what it prints. In scope: b (the BuildingMap: b.spaces, b.floors, b.openings, "
     "b.connectors, b.assets, dicts by id), spaces(floor=None, room_type=None, type=None), floor_id(name_or_level), "
     "area(space_id) m², polygon(space_id), place(phrase, floor=None, item=False), route(start, destination, "
     "stops=(), step_free=None, forklift=None, min_width=None, closed=()) — routes exactly as find_route (your route "
     "rules, the user's profile) —, solve(kind, **inputs), describe(space_id), "
     "math, Counter, Polygon, Point, nx; importable: " + ", ".join(sorted(ALLOWED_MODULES)) + ". \"Rooms\" = spaces "
     "with type room. Print only what you need; state only numbers it printed.", "input_schema": {
         "type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "tour", "description": "Visit several places in the given order.", "input_schema": {
        "type": "object", "properties": {"stops": {"type": "array", "items": PLACE}}, "required": ["stops"]}},
    {"name": "reachable_rooms", "description": "Rooms the user can reach from a place under their profile.",
     "input_schema": {"type": "object", "properties": {"start": PLACE, "floor_id": {"type": "string"}},
                      "required": ["start"]}},
    {"name": "solve", "description": "Exact building analytics. kind ∈ " + ", ".join(sorted(SOLVERS)) + ". params "
     "use ids: floor_area_total/largest_room {floor_id, room_type}; shared_walls_count {start}; room_stacked "
     "{start, direction: above|below}; straight_line_3d {first, second}; wide_delivery_count {start, floor_id, "
     "min_width}; errand {start, asset_type, floor_id, room_type}; what_if_door {first, second, floor_id}; "
     "step_free_reachable_count {closed, start, floor_id}; nearest_item {start, item} (which asset is nearest by "
     "walking); lift_closed {closed} (rooms that lose step-free access from the entrance); add_door {first, second} "
     "(route between them after a new door on their shared wall).", "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": sorted(SOLVERS)}, "params": {"type": "object"}},
         "required": ["kind", "params"]}},
    {"name": "set_profile", "description": "Remember the user's mobility constraints for every later route. "
     "preset: wheelchair or pram = step-free + doors ≥ 0.8 m (assumed); trolley = step-free, also give "
     "min_door_width_m (ask if unknown); no_lifts; forklift = openings ≥ 3 m, no stairs, no pedestrian walkways; "
     "default = clear all constraints. A preset changes only its own "
     "fields; explicit fields override it. The result lists assumed values: name them to the user.",
     "input_schema": {"type": "object", "properties": {
         "preset": {"type": "string", "enum": list(PRESETS)}, "step_free": {"type": "boolean"},
         "min_door_width_m": {"type": "number"}, "avoid_lifts": {"type": "boolean"},
         "forklift": {"type": "boolean"}}}},
    {"name": "propose_change", "description": "Prepare (not apply) a building change and predict its effect: the "
     "last route before/after and, from that route's start, rooms that lose access and routes that get longer. "
     "Show the summary to the user and apply only after they confirm.", "input_schema": {
         "type": "object", "properties": {"action": {"type": "string", "enum": ["close", "reopen", "add_door"]},
                                          "targets": {"type": "array", "items": {"type": "string"}}},
         "required": ["action", "targets"]}},
    {"name": "apply_change", "description": "Apply a proposed change the user confirmed.", "input_schema": {
        "type": "object", "properties": {"change_id": {"type": "string"}}, "required": ["change_id"]}},
    {"name": "compare_routes", "description": "Before → after a pending or applied change, from a start place "
     "(default: the last route's start, else the main entrance) under the user's profile: rooms that lost access, "
     "routes that got longer and by how many metres.", "input_schema": {"type": "object", "properties": {
         "change_id": {"type": "string"}, "start": PLACE}, "required": ["change_id"]}},
    {"name": "show_on_map", "description": "Highlight rooms and items in the user's map view: the map zooms to "
     "them. search, locate and room_facts already show what they found; call this to show the one(s) you mean.",
     "input_schema": {"type": "object", "properties": {"space_ids": {"type": "array", "items": PLACE},
                                                       "asset_ids": {"type": "array", "items": PLACE}}}},
    {"name": "set_my_location", "description": "The user says where they are now (\"I'm in the lobby\", \"I'm at "
     "Lab 2.17\"): it becomes \"here\" for later routes, and the app puts its you-are-here figure there and zooms to "
     "it.", "input_schema": {"type": "object", "properties": {"place": PLACE}, "required": ["place"]}},
    {"name": "show_route_step", "description": "Move the app's step card to a step of the route the user is "
     "following, numbered as in the [route note]: call it whenever your reply is about a different step than the "
     "one the user is at (they moved on, ask what's next, or ask about a later or earlier step).",
     "input_schema": {"type": "object", "properties": {"step": {"type": "integer", "minimum": 1}},
                      "required": ["step"]}},
    {"name": "open_edit_mode", "description": "Switch the app to its Edit mode, where the Builder changes the "
     "building itself on a copy: rename or re-purpose rooms, move or reshape walls, move or widen doors, add, "
     "move or remove items, save as a new building. Pass the user's request in their words (or nothing when they "
     "just want to edit). Not for closing, reopening or adding a door for routing: that is propose_change.",
     "input_schema": {"type": "object", "properties": {"request": {"type": "string"}}}},
]
# Only for buildings with neighbours (BuildingSession.campus).
CAMPUS_TOOLS = [
    {"name": "search_nearby_buildings", "description": "Search the buildings next to this one (nearest first, with "
     "distances). Use it when something is not in this building before saying it isn't there.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "route_to_building", "description": "Route from a place here to a place in a nearby building: inside "
     "here to the best exit, outside (straight line, rounded), inside there. The app shows the first part and a "
     "Continue button; say which building and place you found, not the route.", "input_schema": {"type": "object", "properties": {
         "start": PLACE, "building": {"type": "string", "description": "nearby building id or name"},
         "destination": {"type": "string", "description": "place in that building"}},
         "required": ["start", "building", "destination"]}},
]

# Access mode only (BuildingSession.preferences_enabled): set_profile with route preferences, and set_preference.
_SET_PROFILE = next(tool for tool in TOOL_DEFINITIONS if tool["name"] == "set_profile")
SCOPE = {"type": "string", "enum": ["global", "building"], "description": "global (default) = everywhere; "
         "building = only in this building, when the user says so (\"here\", \"in this building\")"}
PREFERENCE_SET_PROFILE = {
    "name": "set_profile",
    "description": _SET_PROFILE["description"] + " Route preferences (soft, routes may get a little longer, "
    "say by how much): prefer_lifts, fewer_doors, quiet (avoids noisy rooms like canteens, lobbies, production "
    "halls), avoid_halls (open halls), simple_routes (fewer rooms passed); avoid_room_types = room types never "
    "crossed (start and destination excepted). The app remembers what the user tells you (result `remembered`): "
    "say so in a few words. preset default clears mobility constraints only.",
    "input_schema": {"type": "object", "properties": {
        **_SET_PROFILE["input_schema"]["properties"],
        "avoid_room_types": {"type": "array", "items": {"type": "string"}}, "prefer_lifts": {"type": "boolean"},
        "fewer_doors": {"type": "boolean"}, "quiet": {"type": "boolean"}, "avoid_halls": {"type": "boolean"},
        "simple_routes": {"type": "boolean"}, "scope": SCOPE}},
}
SET_PREFERENCE = {
    "name": "set_preference",
    "description": "Remember how the user wants you to talk (language as an English name, e.g. Turkish; "
    "reply_style brief or detailed; voice true/false) or a favourite place in this building. Call it when the "
    "user states such a wish; the app remembers it (result `remembered`).",
    "input_schema": {"type": "object", "properties": {
        "language": {"type": "string"}, "reply_style": {"type": "string", "enum": ["brief", "detailed"]},
        "voice": {"type": "boolean"}, "favourite": {"type": "string"}, "scope": SCOPE}},
}
SEND_OBJECT = {
    "name": "send_object",
    "description": "Admin only: send a moving object (robot, forklift, AGV — by name) to a place. The route fits the "
    "object's attributes (width, stairs, lifts); the object receives it as machine steps and the map shows it "
    "moving. reachable=false + reason: tell the admin why. An unknown name lists the building's objects.",
    "input_schema": {"type": "object", "properties": {"object": {"type": "string"}, "destination": PLACE},
                     "required": ["object", "destination"]},
}
