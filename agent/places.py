"""Turn the words a person uses for a place into space ids (ported from the v1 Guide, agent/guide_v1/resolve.py).

`candidates` never guesses: a phrase that fits several spaces returns all of them, and `problem` writes the
MapError text the model repairs from — every candidate with what tells it apart (D-012), or near-miss names
when nothing matched. Candidates are written as `id (name, ref, type, floor[, extra])` so the offline client's
CANDIDATES pattern can read them too."""

import difflib

from core.building_map import BuildingMap
from core.navigation import type_candidates

MAX_OPTIONS = 8
LEADING_WORDS = ("the ", "a ", "an ", "room ")


def strip_leading(text: str) -> str:
    lowered = text.strip().lower()
    changed = True
    while changed:
        changed = False
        for word in LEADING_WORDS:
            if lowered.startswith(word):
                lowered, changed = lowered[len(word):].strip(), True
    return lowered


def unique(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def candidates(building: BuildingMap, reference: str) -> list[str]:
    """Space ids a phrase can mean: id, asset id, exact ref/name, an entrance or dock (the space it opens into),
    asset name, asset type, then word search."""
    phrase = reference.strip()
    if phrase in building.spaces:
        return [phrase]
    if phrase in building.assets:
        return [building.assets[phrase]["space_id"]]
    wanted = strip_leading(phrase)
    exact = [space["id"] for space in building.spaces.values()
             if wanted in ((space.get("ref") or "").lower(), space["name"].lower())]
    if exact:
        return unique(exact)
    entrances = building.entrance_spaces(wanted)
    if entrances:
        return entrances
    named =[asset["space_id"] for asset in building.assets.values() if asset["name"].lower() == wanted]
    if named:
        return unique(named)
    known_types = {asset["type"] for asset in building.assets.values()}
    asset_type = next((name for name in type_candidates(wanted) if name in known_types), None)  # exact type only
    if asset_type is not None:
        return sorted({asset["space_id"] for asset in building.assets.values() if asset["type"] == asset_type})
    hits = building.search(wanted)
    return unique([hit["id"] if hit["kind"] == "space" else building.assets[hit["id"]]["space_id"] for hit in hits])


def nearest_names(building: BuildingMap, reference: str, n: int = 3) -> list[str]:
    names = {space["name"] for space in building.spaces.values()}
    names |= {space["ref"] for space in building.spaces.values() if space.get("ref")}
    names |= {asset["name"] for asset in building.assets.values()}
    return difflib.get_close_matches(reference.strip(), sorted(names), n=n, cutoff=0.6)


def describe(building: BuildingMap, space_id: str, extra: str | None = None) -> str:
    space = building.spaces[space_id]
    parts = [space["name"]]
    if space.get("ref") and space["ref"] not in space["name"]:
        parts.append(f"ref {space['ref']}")
    parts += [space["room_type"].replace("_", " "), building.floor_name(space["floor_id"])]
    if extra:
        parts.append(extra)
    return f"{space_id} ({', '.join(parts)})"


def problem(building: BuildingMap, reference: str, found: list[str], extras: dict[str, str] | None = None) -> str:
    """MapError text for a phrase that matched no space or several."""
    if not found:
        close = nearest_names(building, reference)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        return f"No place matches '{reference}'.{hint} Try search with fewer words."
    shown = found[:MAX_OPTIONS]
    more = f"; and {len(found) - len(shown)} more" if len(found) > len(shown) else ""
    listed = "; ".join(describe(building, space_id, (extras or {}).get(space_id)) for space_id in shown)
    return (f"'{reference}' is ambiguous: {len(found)} places match. Ask the user which one, naming what tells "
            f"them apart — floor, ref, size or a neighbour: {listed}{more}")
