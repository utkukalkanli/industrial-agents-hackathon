"""One route question with any mix of constraints — for wording no template matches (agent/llm_parser.py `route`).

Places may be rooms (name, ref or id), room types ("the toilet") or items ("the forklift charging station"); when a
place fits several rooms the nearest one under the question's constraints is taken, leg by leg (as `errand` takes
the nearest item). Stops are visited in order, one leg each. Constraints combine freely: closures (lifts, stairs,
rooms, corridors, doors — names or ids), step-free, forklift (core/route_models.py) and a minimum door width.

Built on core.navigation, which reproduces every warm-up route answer (tests/test_navigation.py), so lengths are
the kit 1.1.0 route model the judges use. The result has the v1 solver shape (core/solvers_v1.py `route`): legs in
the warm-up answer format, the whole `space_path` / `element_path`, `steps` for the reply."""

from core import navigation, route_models
from core.building_map import BuildingMap, MapError
from core.route_models import KIT, RouteRules

LEADING_WORDS = ("the ", "a ", "an ", "nearest ", "closest ", "any ", "room ")
MAX_CANDIDATES = 12  # several rooms for one place: only the 12 nearest by straight line are routed to


def normalise(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").split())


def strip_leading(text: str) -> str:
    phrase = normalise(text)
    changed = True
    while changed:
        changed = False
        for word in LEADING_WORDS:
            if phrase.startswith(word):
                phrase, changed = phrase[len(word):].strip(), True
    return phrase


def resolve_place(bmap: BuildingMap, phrase: str, floor_id: str | None = None, is_item: bool = False) -> list[str]:
    """Space ids a place phrase can mean (optionally on one floor): exact room name/ref, an entrance or dock by name
    or id (the space it opens into), room type, then items (asset id, type, name or words) — items first when
    `is_item` — then a word search. Empty when nothing fits."""
    text = phrase.strip()
    if text in bmap.spaces:
        return [text]
    if text in bmap.assets:
        return [bmap.assets[text]["space_id"]]
    wanted = strip_leading(text)
    forms = {wanted, wanted.removesuffix("s"), wanted.removesuffix("es")}

    def rooms() -> list[str]:
        return [space["id"] for space in bmap.spaces.values()
                if wanted in (normalise(space["name"]), normalise(space.get("ref") or ""))]

    def entrances() -> list[str]:
        return bmap.entrance_spaces(wanted)

    def room_types() -> list[str]:
        return [space["id"] for space in bmap.spaces.values() if normalise(space["room_type"]) in forms]

    def items() -> list[str]:
        return [asset["space_id"] for asset in navigation.match_assets(bmap, wanted)[1]]

    def words() -> list[str]:
        return [hit["id"] if hit["kind"] == "space" else bmap.assets[hit["id"]]["space_id"]
                for hit in bmap.search(wanted)]

    for tier in ((items, rooms, entrances, room_types) if is_item else (rooms, entrances, room_types, items)) + (words,):
        found = sorted({space_id for space_id in tier()
                        if floor_id is None or bmap.spaces[space_id]["floor_id"] == floor_id})
        if found:
            return found
    return []


def nearest(graph, endpoints: frozenset[str], start: str, candidates: list[str]) -> tuple[str, float]:
    """The candidate with the shortest route from `start` (first by id on a tie or when none is reachable)."""
    if start not in graph:
        return candidates[0], float("inf")
    distances = route_models.single_source(graph, endpoints, start)
    return min(((candidate, distances.get(candidate, float("inf"))) for candidate in candidates),
               key=lambda pair: pair[1])


def shortlist(bmap: BuildingMap, anchor: str, candidates: list[str]) -> list[str]:
    """At most MAX_CANDIDATES candidates, nearest to `anchor` by straight line first (floors apart by elevation)."""
    if len(candidates) <= MAX_CANDIDATES:
        return candidates

    def where(space_id: str) -> tuple[float, float, float]:
        x, y = bmap.anchor(space_id)
        return x, y, bmap.floors[bmap.spaces[space_id]["floor_id"]].get("elevation_m", 0.0)

    origin = where(anchor)
    return sorted(candidates, key=lambda space_id: sum((a - b) ** 2 for a, b in zip(where(space_id), origin)))[
        :MAX_CANDIDATES]


def route_query(
    bmap: BuildingMap,
    stops: list[list[str]],
    *,
    step_free: bool = False,
    forklift: bool = False,
    min_width: float | None = None,
    closed: list[str] | tuple[str, ...] = (),
    include_steps: bool = True,
    rules: RouteRules | None = None,
) -> dict:
    """Shortest route through `stops` in order; each stop is a list of candidate space ids (`resolve_place`).

    Returns `reachable: False` with a reason when the constraints leave no route; raises MapError for a stop
    without candidates or a closure that names nothing."""
    if len(stops) < 2:
        raise MapError("A route needs a start and a destination.")
    if not all(stops):
        raise MapError("A stop of the route matches no place in this building.")
    closures = sorted({bmap.find_element(reference) for reference in closed})
    narrow = [opening["id"] for opening in bmap.openings.values()
              if min_width is not None and opening["width_m"] < min_width]
    view = navigation.routing_view(bmap, [*closures, *narrow])
    rules = rules or RouteRules(forklift=forklift)  # the Guide's compute passes its own (agent/tools.py)
    graph = route_models.route_graph(view, step_free, KIT, rules)
    endpoints = route_models.endpoint_only(view, rules)

    first, second = stops[0], stops[1]
    if len(first) == 1:
        chosen = [first[0]]
    else:  # several possible starts: the one closest to its nearest next stop
        starts = shortlist(bmap, second[0], first)
        chosen = [min(starts, key=lambda start: nearest(graph, endpoints, start, shortlist(bmap, start, second))[1])]
    for candidates in stops[1:]:
        if len(candidates) == 1:
            chosen.append(candidates[0])
        else:
            chosen.append(nearest(graph, endpoints, chosen[-1], shortlist(bmap, chosen[-1], candidates))[0])

    legs = [navigation.leg(view, graph, start, end, step_free, include_steps, KIT, rules)
            for start, end in zip(chosen, chosen[1:])]
    constraints = {"step_free": step_free, "forklift": forklift, "min_width": min_width, "closed": closures}
    failed = next((leg for leg in legs if not leg.reachable), None)
    if failed:
        return {"reachable": False, "stops": chosen, "from_space_id": chosen[0], "to_space_id": chosen[-1],
                "reason": f"No route from {bmap.describe_space(failed.from_space_id)} to "
                          f"{bmap.describe_space(failed.to_space_id)}: {failed.reason}.", **constraints}
    steps = [step for index, leg in enumerate(legs) for step in leg.steps or []
             if index == 0 or not step.startswith(("Start in", "Start outside"))]
    return {
        "reachable": True,
        "stops": chosen,
        "from_space_id": chosen[0],
        "to_space_id": chosen[-1],
        "optimal_length_m": round(sum(leg.length_m for leg in legs), 2),
        "space_path": [chosen[0], *(space for leg in legs for space in leg.space_path[1:])],
        "element_path": [element for leg in legs for element in leg.element_path],
        "legs": [{"from_space_id": leg.from_space_id, "to_space_id": leg.to_space_id,
                  "optimal_length_m": leg.length_m, "space_path": leg.space_path, "element_path": leg.element_path}
                 for leg in legs],
        "steps": steps,
        **constraints,
    }
