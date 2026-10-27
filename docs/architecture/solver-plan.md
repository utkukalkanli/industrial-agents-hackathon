---
id: arch-solver-plan
summary: Deterministic algorithm per benchmark question kind — every kind VERIFIED against all train+dev answers (655/655), with the exact rules the data settled and the variants it rejected.
status: verified 2026-10-24
sources: [../kit/questions.md, ../kit/route-model.md, ../challenge/scoring.md, ../../core/solvers/, ../../scripts/validate_solvers.py]
related: [overview.md, ../kit/questions.md, ../../memory-bank/open-questions.md]
---

# Solver plan per question kind — VERIFIED

[Docs index](../README.md) · Definitions: [questions.md](../kit/questions.md#precise-definitions) ·
Tolerances: [scoring.md](../challenge/scoring.md#tolerances-per-kind)

Code: `core/solvers/` — one `@solver(kind)` function per kind, `fn(building, **inputs) -> SolverResult`
(`value`, `unit`, `explanation`, JSON `evidence`, `area_m2`). Solvers never mutate the building (what-ifs work
on a copy). `core/formatter.py` writes the reply + `Answer:` line ([D-003](../../memory-bank/decisions.md#d-003)).

Validation: `uv run python scripts/validate_solvers.py [--kinds …] [-v]` runs each solver on the gold `inputs`
of every train+dev question and scores the formatted reply with the official `benchmark/score.py`.
Per-module tests: `tests/test_solvers_{geometry,walls,reachability,routing}.py`.

| Kind | Test share | Status | train+dev (gold inputs) | Module |
|---|---|---|---|---|
| floor_area_total | 23% | VERIFIED | 181/181 | geometry.py |
| shared_walls_count | 18% | VERIFIED | 143/143 | walls.py |
| largest_room | 14% | VERIFIED | 96/96 | geometry.py |
| errand | 14% | VERIFIED | 93/93 (incl. gold `via`/`target`) | routing.py |
| wide_delivery_count | 12% | VERIFIED | 80/80 | reachability.py |
| straight_line_3d | 10% | VERIFIED | 30/30 | geometry.py |
| room_stacked | 6% | VERIFIED | 26/26 | geometry.py |
| what_if_door | 2% | VERIFIED (4 examples) | 4/4 | routing.py |
| step_free_reachable_count | 0% (Sunday?) | VERIFIED (2 examples, weak) | 2/2 | reachability.py |
| nearest_item | — (not a kit kind) | tested (synthetic + organisers' eval, [below](#post-hackathon-kinds-and-data-rules-2026-10-27)) | — | changes.py |
| lift_closed | — (not a kit kind) | tested (synthetic + organisers' eval) | — | changes.py |
| add_door | — (not a kit kind) | tested (synthetic + organisers' eval) | — | changes.py |

A second implementation, `core/solvers_v1.py` (`solve(bmap, kind, params)` → dict, used by `agent/answer.py` and
the v1 Guide `agent/guide_v1/`), reaches the same 655/655 on gold inputs (`uv run pytest tests/test_solvers.py -q -s`).

End-to-end from question **text** (`agent/benchmark_agent.py`, regex parser): dev **138/138**, train **515/517** —
the 2 misses are inherently ambiguous names ([Q-006](../../memory-bank/open-questions.md#q-006)).

## Room definition per kind

Resolves [Q-003](../../memory-bank/open-questions.md#q-003): "room" means something different per kind.

| Kind | Counted / candidate spaces | Evidence |
|---|---|---|
| shared_walls_count | `type` ∉ {corridor, stair, lift, outdoor} — **halls count**, balconies (`outdoor`) don't | 143 vs 124 (excl. hall) vs 90 (incl. balcony) |
| wide_delivery_count, step_free_reachable_count, what_if_door | `type == "room"` — equals the manifest `rooms` column in all 280 buildings | 80 vs 61 (room+hall) vs 49 |
| room_stacked | any space on the adjacent floor (a lobby→lobby winner exists) | `type == room` only fails osm-way13507441-H06 |
| floor_area_total, largest_room | exact `floor_id` + `room_type` match | 277/277 |

## floor_area_total
Sum of shapely `Polygon.area` over spaces with `floor_id == F` and `room_type == T`. Number, ±5%.

## largest_room
Argmax area among the same set. Answer line: `<ref> (<name>), <area> m²` — the ref is in `accept` for all 122
space answers and disambiguates repeated OSM names.

## straight_line_3d
`Polygon.centroid` (`buffer(0)` if invalid) at floor `elevation_m`; 3D Euclidean. No frame correction.
**Swiss risk checked (2026-10-24):** all 30 train+dev and all 15 test `straight_line_3d` questions are on
procedural/OSM buildings — the generator avoids Swiss here, as the kit README states for stacked questions. The
misalignment is real (84 of 108 multi-floor Swiss buildings have every floor's space-bbox centre within 2 m of
the origin on each axis; 82 with a Euclidean 2 m radius), but a gold answer would be computed from the same raw
coordinates, so no frame correction is the right call either way. The
Guide's `room_facts` omits "above/below" for Swiss buildings (`UNALIGNED_SOURCES` in `agent/tools.py`).

## room_stacked
Next existing `level` up/down (gaps skipped, e.g. swiss-460 levels 0,2,3,4); winner = largest intersection area
with the start room (dividing by the candidate's area fails 2/26). Winner covers ≥ 0.652 of the start room;
runner-up ≤ 0.191.

## shared_walls_count
`Polygon(A).exterior.intersection(Polygon(B).buffer(0.35)).length >= 1.0`, same floor, type filter above.
Direction (A/B/max/min) and `>=`/`>` never change the score; tolerance 0.3–0.5 m and threshold 0.5–1.5 m all
score 143/143 (no borderline cases). Helpers: `shared_wall_neighbours`, `shared_wall_length`,
`shared_wall_segment` (midpoint for doors).

## wide_delivery_count
BFS from `start` over step-free openings/connectors whose opening `width_m >= min_width` — **every opening kind**
(door, leafless opening, entrance) is width-checked; connectors have no width field, so lifts pass. Start
counts if it is a room on the target floor. Rejected: doors only 77, doors+entrances 78, strict `>` 73,
excluding start 38. ([Q-004](../../memory-bank/open-questions.md#q-004))

## step_free_reachable_count
Same BFS, step-free, with the named connector closed. Weak evidence: in both examples the closure doesn't change
the count ([Q-005](../../memory-bank/open-questions.md#q-005)).

## errand
Full graph (stairs allowed: "I can carry it on the stairs" is the only carry phrase in train/dev/test; step-free
scored 34/93). `via` = room holding an asset of that type with the shortest route distance from start, **any
floor** (same-floor only: 90/93); `target` = largest `room_type` room on `floor_id`; total = d(start,via) +
d(via,target). Min nearest-vs-runner-up gap in data 0.62 m. Evidence: per-leg ordered nodes/spaces/elements.

## what_if_door
Copy the building; add a 0.9 m step-free door at the middle of the longest merged shared-wall stretch (halfway
between both rooms' outline midpoints; fallback: nearest points). For each `type == "room"` space on the target
floor: route distance to `outside` (full graph) before/after; count improvements **> 1 m**; rooms with no route
out are skipped. Step-free distance rejected (21 vs 6). Robustness sweep over 1044 random wall-sharing pairs:
midpoint variant changes the count in ≤ 3 pairs; no improvement falls within 0.8–1.2 m.

## Warm-up kinds (questions_basic.jsonl)
In case Sunday asks one-search / one-route questions ([Q-001](../../memory-bank/open-questions.md#q-001)), the
parser has a template per warm-up kind and `solve()` answers them (VERIFIED 2026-10-24, from the question text,
`uv run pytest tests/test_warm_up.py -q -s`):

| Kind | Solver | train+dev |
|---|---|---|
| `locate` | the asset of that type (label → type: exact, plural, start of asset name, end of type) | 553/553 |
| `count` | assets of that type with that `floor_id` | 239/239 |
| `route` / `route_step_free` / `route_with_closure` | `BuildingMap.route()` (closure added to `closed`); `reachable: False` when cut off | 715/720, 239/240, 136/138 |
| `tour` | `route()` with the middle stops as `via`, one leg per stop pair | 238/240 |

All 10 misses are texts naming a room that several rooms share (OSM duplicates such as "Büro"); the parser picks
the first candidate. The LLM parser knows these kinds too: 12/12 on reworded dev questions (live, 2026-10-24).

<a id="sunday-routes"></a>
## Sunday route questions (Q-014) — one route model since kit 1.1.0, rules open
Route answers are scored as an ordered space list, re-measured with the organisers' rule — since kit 1.1.0 that rule
is the route model of every expected answer, ported verbatim into `core/building_map.py`
([D-014](../../memory-bank/decisions.md#d-014), [route-model.md](../kit/route-model.md)). Our route path
(`core/basic_parser.run_parsed` → `core/navigation.find_route` / `tour`) takes `rules`
([route-model.md](../kit/route-model.md#sunday-route-model-and-route-rules-q-014)): none for the kit answers
(train+dev warm-up 1,338/1,338 exact with gold ids), `SUNDAY_RULES` (+ `forklift=True`) for the organisers' bay /
forklift rules, which the kit answers don't use. `outside` is never crossed. No route under the rules →
`reachable: false`, reason starts "no route under these rules"; the answer must say so. Open: Q-014 (3), (4).

## Post-hackathon kinds and data rules (2026-10-27)
Measured on the organisers' internal evaluation set (7 buildings, 252 auto-scored questions; shared by the
organisers after the event, kept outside the repo; harness and scorer runs in the session log,
[log.md](../../memory-bank/log.md)). None of this changes a kit answer: the kit data has no `through` flag and no
entrance a question would name.
- **`through: false`** on a space = destination only: `BuildingMap.route` drops it (node and inside walks) from
  every leg it does not start or end, and `route_models.endpoint_only` adds it, so `navigation`, `route_query`, the
  campus and the Guide's tools obey it too (`tests/test_route_models.py`).
- **Entrances and docks are places**: `BuildingMap.entrance_spaces` matches an entrance by `name` or id ("Dock 1" ↔
  `DOCK01`) → the space it opens into; used by `core/route_query.resolve_place` (after exact room names) and the
  Guide's `agent/places.candidates`; the LLM parser's vocabulary lists them.
- **`nearest_item`** {start, item}: assets matching `item` (`navigation.match_assets`) ranked by route distance from
  `start` (kit graph, stairs allowed, destination-only spaces respected); ties → smaller asset id.
- **`lift_closed`** {closed[, start]}: spaces reachable step-free from `start` (default: where the lowest floor's
  entrances open into) **inside** the building — never round the outside — before vs after the closure; the rooms
  and halls among the lost ones (not corridors, stairs, lifts, outdoor). A first version started from `outside`
  and found 0 rooms on a building with an upper-floor entrance.
- **`add_door`** {first, second}: `routing.with_new_door` (0.9 m, middle of the shared wall, on a copy), route
  before and after.
- **The Guide (UI) uses the same logic**: `find_nearest` for an item ranks the holders with `nearest_item` under
  the session's route model and rules (bays destination-only, no outside, forklift) plus the profile's step-free
  rule and closures, measures the nearest 5 with `find_route` (profile penalties) and routes to the shortest, so
  the named nearest, its length and the drawn route agree; `nearest_item` takes `model`/`rules` (default: kit, no
  rules = the benchmark); `propose_change` closing a lift adds
  `step_free_lost_<lift>` from `lift_closed`; `propose_change add_door` already used `with_new_door`; `solve`
  lists all three kinds.
Scores (parser Sonnet 5.5, solver agent 1 run): 0.464 → 0.673 (`through`) → 0.764 (entrances) → 0.885 (three
solvers).

## Answer formatting (all kinds)
`core/formatter.py`: explanation lines, then `Answer: <number>[ unit]` (integers bare, else 2 decimals) or
`Answer: <ref> (<name>)[, <area> m²]`. Never a ref on a number line
([scoring.md](../challenge/scoring.md#formatting-pitfalls-cost-real-points)).

## Related
- [overview.md](overview.md) · [questions.md](../kit/questions.md) · [route-model.md](../kit/route-model.md) ·
  [ai-agents.md](ai-agents.md#benchmark-pipeline)
