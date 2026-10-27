"""Benchmark entry point: question text → parser → solver → reply ending in a deterministic `Answer:` line.

  uv run python -m benchmark.evaluate data/dev --agent agent.answer:answer

The answer line follows benchmark/score.py (D-003): number kinds carry exactly one number (a room ref such as
"1.02" would count as a second number, so refs stay on the explanation lines); space kinds name the room by its
ref, which every train/dev `accept` list contains, and largest_room adds the area. Warm-up kinds: locate names the
room and floor, count gives the number, routes give the step-by-step directions and the length (or "no route").

Outside `PARSER_MODE=regex`, a question that fails anywhere (no template, slots the LLM parser hands over as kind
`other` or a kind that does not answer what is asked, slots that never resolve, a solver error) goes to the solver
agent (agent/solver_agent.py), unless SOLVER_AGENT=off. Its decisions and the parser's are replayed from the
decision cache (agent/llm_cache.py) when present."""

import os
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path

from agent.parsing import QuestionUnderstanding
from agent.solver_agent import SolverAgent
from core.building_map import BuildingMap
from core.question_parser import ParsedQuestion, ParseError
from core.solvers_v1 import solve


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def room(result: dict) -> str:
    return f"{result['name']} ({result['ref']}, {result['floor']})"


def explain(kind: str, params: dict, result: dict) -> tuple[str, str]:
    """(explanation, answer-line text) for a solver result."""
    if kind == "largest_room":
        return (f"The largest {params['room_type'].replace('_', ' ')} is {room(result)} "
                f"at {result['area_m2']:.2f} m².", f"{result['ref']}, {result['area_m2']:.2f} m²")
    if kind == "room_stacked":
        return (f"The room directly {params['direction']} it is {room(result)} "
                f"({result['overlap_m2']:.2f} m² of overlap).", result["ref"])
    if kind == "floor_area_total":
        return (f"{result['count']} rooms of that type add up to {result['total_m2']:.2f} m².",
                f"{result['total_m2']:.2f} m²")
    if kind == "straight_line_3d":
        return f"Centre to centre, through floors and walls: {result['distance_m']:.2f} m.", f"{result['distance_m']:.2f} m"
    if kind == "errand":
        return (f"Nearest one is in {room(result['via'])}, {result['first_leg_m']:.2f} m away; from there to "
                f"{room(result['target'])} is {result['second_leg_m']:.2f} m.", f"{result['total_m']:.2f} m")
    if kind == "locate":
        return (f"The {result['asset_name']} ({result['asset_id']}) is in {room(result)}.",
                f"{result['name']} ({result['ref']}), {result['floor']}")
    if kind == "count":
        return f"{result['count']} {params['asset_type'].replace('_', ' ')} items on that floor.", str(result["count"])
    if kind in ("route", "route_step_free", "route_with_closure", "tour", "route_query"):
        if not result["reachable"]:
            return result["reason"], "no step-free route" if kind == "route_step_free" else "no route"
        return "\n".join(result["steps"]), f"{result['optimal_length_m']:.2f} m"
    if kind == "nearest_item":
        return "\n".join(result["explanation"]), f"{result['asset_name']} ({result['asset_id']})"
    if kind == "lift_closed":
        return "\n".join(result["explanation"]), str(result["value"])
    if kind == "add_door":
        return "\n".join(result["explanation"]), f"{result['length_after_m']:.2f} m"
    if kind == "shared_walls_count":
        names = ", ".join(room(neighbour) for neighbour in result["rooms"]) or "none"
        return f"Rooms sharing at least 1 m of wall: {names}.", str(result["count"])
    names = ", ".join(result["rooms"]) or "none"
    return f"Rooms counted: {names}.", str(result["count"])


@dataclass
class Response:
    reply: str
    kind: str | None = None
    params: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    parser: str | None = None


def reply(parsed: ParsedQuestion, bmap: BuildingMap, result: dict) -> str:
    explanation, committed = explain(parsed.kind, parsed.params, result)
    lines = [explanation]
    for slot, candidates in parsed.alternatives.items():
        refs = ", ".join(bmap.spaces[candidate]["ref"] for candidate in candidates)
        lines.append(f"Note: several rooms share that name ({refs}); I used {bmap.spaces[candidates[0]]['ref']}.")
    return "\n".join([*lines, f"Answer: {committed}"])


def failure(error: Exception) -> Response:
    if isinstance(error, (ParseError, ValueError, KeyError)):
        return Response(f"I could not answer this: {error}", error=str(error))
    return Response(f"I could not answer this: {error}", error=f"{type(error).__name__}: {error}")


def agent_response(question_text: str, bmap: BuildingMap, cause: Exception) -> Response:
    """The solver agent's answer; `cause` (why the parser path failed) goes along as a hint."""
    try:
        answered = SolverAgent().solve(question_text, bmap, hint=str(cause))
    except Exception as error:  # noqa: BLE001 — no model and no cached answer: the question fails alone
        return failure(error)
    parser = "agent-cache" if answered.cached else "agent"
    if answered.error or answered.submission is None:
        return Response(answered.reply, error=answered.error or "agent gave no answer", parser=parser)
    return Response(answered.reply, "agent", {}, {**asdict(answered.submission), "runs": len(answered.runs),
                                                  "parser_failure": str(cause)[:300]}, parser=parser)


def respond(building_directory: Path, question_text: str) -> Response:
    """The reply plus what produced it (kind, resolved ids, solver result, parser) for structured outputs.

    Never raises: unknown wording, an API error or an unreadable building becomes an error reply without an
    `Answer:` line, so one bad question cannot stop a benchmark run."""
    try:
        bmap = building(Path(building_directory))
    except Exception as error:  # noqa: BLE001
        return failure(error)
    understanding = QuestionUnderstanding()
    try:
        parsed = understanding.parse(question_text, bmap)
        result = solve(bmap, parsed.kind, parsed.params)
        return Response(reply(parsed, bmap, result), parsed.kind, parsed.params, result,
                        parser=parsed.notes.get("parser"))
    except Exception as error:  # noqa: BLE001 — anything else (network, geometry) is still one failed question
        if understanding.mode == "regex" or os.environ.get("SOLVER_AGENT", "on").lower() == "off":
            return failure(error)
        return agent_response(question_text, bmap, error)


def answer(building_directory: Path, question_text: str) -> str:
    """benchmark.evaluate agent signature: (building directory, question text) → reply text."""
    return respond(building_directory, question_text).reply
