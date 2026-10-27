"""Agentic fallback for benchmark questions that no template and no slot schema can express (new kinds on Sunday).

Claude gets a summary of the building and two tools: `python`, which runs code against the loaded building (the
BuildingMap, the canonical route and solver functions, shapely, networkx) and returns what it prints, and
`submit_answer`. Every number comes from code the model ran, and the `Answer:` line is written by code from the
submitted value (D-003), never by the model. Self-consistency: two independent runs; when they disagree a third
decides by majority, so one bad trajectory does not decide a question alone.

  agent.answer.respond → regex templates → LLM slots (agent/llm_parser.py) → this agent (kind `other`, a
  question/kind mismatch, or slots that never resolve)

The sandbox (restricted builtins, a module whitelist, a time limit, a deep copy of the building per run) guards
against accidents, not against a hostile model."""

import builtins
import copy
import io
import json
import math
import os
import signal
import threading
import traceback
from collections import Counter
from dataclasses import asdict, dataclass, field

from agent import llm_client
from agent.llm_cache import DecisionCache, decision_key
from core import solvers_v1
from core.building_map import BuildingMap
from core.route_query import resolve_place, route_query

MODEL = os.environ.get("SOLVER_AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("SOLVER_AGENT_EFFORT", "medium")  # medium: 14/14 on the probe at lower cost (Utku, 2026-10-25)
RUNS = int(os.environ.get("SOLVER_AGENT_RUNS", "2"))
MAX_TOKENS = 16000
MAX_ROUNDS = 14
API_RETRIES = 4
FALLBACK_BETA = "server-side-fallback-2026-07-01"
VERSION = "1"  # bump when the tools or instructions change: cached answers of another version are not reused
CODE_TIME_LIMIT_S = 30
MAX_OUTPUT_CHARS = 6000
ALLOWED_MODULES = {"math", "statistics", "collections", "itertools", "functools", "json", "re", "heapq",
                   "shapely", "networkx"}
SAFE_BUILTINS = {name: getattr(builtins, name)
                 for name in ("abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
                              "frozenset", "getattr", "hasattr", "int", "isinstance", "iter", "len", "list", "map",
                              "max", "min", "next", "pow", "range", "repr", "reversed", "round", "set", "slice",
                              "sorted", "str", "sum", "tuple", "type", "zip", "Exception", "ValueError",
                              "KeyError", "TypeError", "IndexError", "ZeroDivisionError", "StopIteration")}
ANSWER_TYPES = ("number", "space", "no_route", "text")

TOOLS = [
    {
        "name": "python",
        "description": (
            "Run Python against the loaded building and get back what it prints (stdout, cut at 6000 characters) "
            "or the error. Variables persist between calls. Available without import: `b` (the BuildingMap: "
            "b.spaces, b.floors, b.openings, b.connectors, b.assets — dicts by id), `spaces(floor=None, "
            "room_type=None, type=None)`, `floor_id(name_or_level)`, `area(space_id)` (m²), `polygon(space_id)`, "
            "`place(phrase, floor=None, item=False)` (space ids a name / room type / item phrase can mean), "
            "`route(start, destination, stops=(), step_free=False, forklift=False, min_width=None, closed=())` "
            "(places as ids or phrases; the nearest match is taken; returns reachable, optimal_length_m, "
            "space_path, element_path, legs), `solve(kind, **inputs)` (exact solvers: largest_room, "
            "floor_area_total, shared_walls_count, room_stacked, straight_line_3d, errand, what_if_door, locate, "
            "count, wide_delivery_count, step_free_reachable_count — ids as inputs), `describe(space_id)`, "
            "math, Counter, Polygon, Point, nx. You may also import: " + ", ".join(sorted(ALLOWED_MODULES)) + "."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python source; print what you need."}},
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_answer",
        "description": (
            "Submit the final answer once, after computing it with python. answer_type: number (a count, area, "
            "distance, width …: give `number` and `unit`), space (a room: give its `space_id`, plus `number` and "
            "`unit` when the question also asks a size), no_route (no route exists under the question's rules), "
            "text (only for yes/no or a name that is not a space). `explanation`: one or two sentences on how "
            "it was computed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "answer_type": {"type": "string", "enum": list(ANSWER_TYPES)},
                "number": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "unit": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "space_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "explanation": {"type": "string"},
            },
            "required": ["answer_type", "number", "unit", "space_id", "text", "explanation"],
            "additionalProperties": False,
        },
    },
]

INSTRUCTIONS = """You answer one question about a building exactly, by computing the answer with the python tool,
then calling submit_answer once. Never state a number you did not compute; never guess a name.

Conventions the graders use (follow them unless the question says otherwise):
- A space has `type` (room, hall, corridor, stair, lift, outdoor …) and `room_type` (office, kitchen, toilet,
  production_zone …). "Rooms" means spaces with type == "room"; halls are type "hall"; corridors, stairs and lifts
  are not rooms.
- Areas are the shapely area of the space polygon in m² (area(space_id)); report 2 decimals.
- Walking distances and routes always come from route() — the judges' route model in metres (door to door 15 cm
  off the walls, stairs 2 m per metre climbed, a lift ride 15 m + 1 m per metre). Never measure walking yourself.
  step_free=True avoids stairs and stepped doors; forklift=True keeps to openings at least 3 m wide; closed=[...]
  takes lift, stair, room, corridor or door names or ids; min_width closes narrower doors.
- "Straight-line" distance: solve("straight_line_3d", first=..., second=...) (centroids, floor elevations).
- Shared walls: solve("shared_walls_count", start=...) (at least 1 m of outline within 0.35 m, same floor).
- The room directly above/below: solve("room_stacked", start=..., direction="above"|"below").
- An item is in the space of its asset record (`space_id`); "the nearest X" means the shortest route().
- Counts are integers. If the question names a place that does not exist, look for the closest real name with
  place() or by scanning b.spaces before giving up.
- If no route exists under the question's rules, submit answer_type "no_route"."""


@dataclass
class Submission:
    answer_type: str
    number: float | None = None
    unit: str | None = None
    space_id: str | None = None
    text: str | None = None
    explanation: str = ""

    def agrees(self, other: "Submission") -> bool:
        if self.answer_type != other.answer_type:
            return False
        if self.answer_type == "space" and self.space_id != other.space_id:
            return False
        if self.number is not None or other.number is not None:
            if self.number is None or other.number is None:
                return False
            if abs(self.number - other.number) > max(abs(other.number) * 0.01, 0.01):
                return False
        if self.answer_type == "text":
            return " ".join((self.text or "").lower().split()) == " ".join((other.text or "").lower().split())
        return True


@dataclass
class AgentAnswer:
    reply: str
    submission: Submission | None
    runs: list[Submission | None] = field(default_factory=list)
    error: str | None = None
    cached: bool = False


def namespace(bmap: BuildingMap) -> dict:
    """What the model's code can see: the building, helpers over the canonical functions, a few modules."""
    from shapely.geometry import Point, Polygon
    import networkx as nx

    def floor_id(floor: str | int) -> str:
        for identifier, item in bmap.floors.items():
            if floor in (identifier, item["level"]) or str(floor).strip().lower() == item["name"].lower():
                return identifier
        raise KeyError(f"No floor '{floor}'. Floors: {[item['name'] for item in bmap.floors.values()]}")

    def spaces(floor: str | int | None = None, room_type: str | None = None, type: str | None = None) -> list[dict]:
        wanted_floor = floor_id(floor) if floor is not None else None
        return [space for space in bmap.spaces.values()
                if (wanted_floor is None or space["floor_id"] == wanted_floor)
                and (room_type is None or space["room_type"] == room_type)
                and (type is None or space["type"] == type)]

    def place(phrase: str, floor: str | int | None = None, item: bool = False) -> list[str]:
        return resolve_place(bmap, phrase, floor_id(floor) if floor is not None else None, is_item=item)

    def stop(reference: str) -> list[str]:
        found = place(reference)
        if not found:
            raise KeyError(f"No place matches '{reference}'")
        return found

    def route(start: str, destination: str, stops: list[str] | tuple[str, ...] = (), step_free: bool = False,
              forklift: bool = False, min_width: float | None = None, closed: list[str] | tuple[str, ...] = ()) -> dict:
        return route_query(bmap, [stop(start), *[stop(item) for item in stops], stop(destination)],
                           step_free=step_free, forklift=forklift, min_width=min_width, closed=closed,
                           include_steps=False)

    def solve(kind: str, **inputs: object) -> dict:
        return solvers_v1.solve(bmap, kind, inputs)

    def polygon(space_id: str) -> Polygon:
        return Polygon(bmap.spaces[space_id]["polygon"])

    def describe(space_id: str) -> str:
        space = bmap.spaces[space_id]
        return f"{space['name']} ({space['type']}, {space['room_type']}, {bmap.floor_name(space['floor_id'])})"

    def safe_import(name: str, *args: object, **kwargs: object):
        if name.split(".")[0] not in ALLOWED_MODULES:
            raise ImportError(f"Module '{name}' is not available here; allowed: {sorted(ALLOWED_MODULES)}")
        return __import__(name, *args, **kwargs)

    return {
        "__builtins__": {**SAFE_BUILTINS, "__import__": safe_import},
        "b": bmap, "spaces": spaces, "floor_id": floor_id, "area": lambda space_id: polygon(space_id).area,
        "polygon": polygon, "place": place, "route": route, "solve": solve, "describe": describe,
        "math": math, "Counter": Counter, "Polygon": Polygon, "Point": Point, "nx": nx,
    }


def run_code(code: str, scope: dict) -> dict:
    """Execute model code in `scope`; stdout and the error (if any), under a time limit on the main thread."""
    output = io.StringIO()
    scope["print"] = lambda *values, sep=" ", end="\n": output.write(sep.join(str(value) for value in values) + end)
    timed = threading.current_thread() is threading.main_thread()
    previous = None
    if timed:
        def expire(signum, frame):
            raise TimeoutError(f"code ran longer than {CODE_TIME_LIMIT_S} s")

        previous = signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, CODE_TIME_LIMIT_S)
    error = None
    try:
        exec(compile(code, "<python tool>", "exec"), scope)  # noqa: S102 — the sandbox is the point of this tool
    except BaseException as caught:  # noqa: BLE001 — every failure goes back to the model
        if isinstance(caught, KeyboardInterrupt):
            raise
        error = "".join(traceback.format_exception_only(type(caught), caught)).strip()
        frames = [line for line in traceback.format_tb(caught.__traceback__) if "<python tool>" in line]
        if frames:
            error = frames[-1].strip() + "\n" + error
    finally:
        if timed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    text = output.getvalue()
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n… cut ({len(text)} characters in all; print less)"
    return {"output": text, **({"error": error} if error else {})}


def number_text(value: float, unit: str | None) -> str:
    """One number for the answer line: integers stay integers, the rest 2 decimals; the unit after a space."""
    shown = str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:.2f}"
    return f"{shown} {unit}".rstrip() if unit else shown


def answer_line(submission: Submission, bmap: BuildingMap) -> str:
    """The committed answer (benchmark/score.py): one number for numbers, the room's name (and ref) for spaces."""
    if submission.answer_type == "no_route":
        return "no route"
    if submission.answer_type == "text":
        return (submission.text or "").strip()
    if submission.answer_type == "space":
        space = bmap.spaces[submission.space_id]
        ref = space.get("ref")
        label = space["name"] if not ref or ref in space["name"] else f"{space['name']} ({ref})"
        return label if submission.number is None else f"{label}, {number_text(submission.number, submission.unit)}"
    return number_text(submission.number, submission.unit)


def validate(arguments: dict, bmap: BuildingMap) -> tuple[Submission | None, str | None]:
    try:
        submission = Submission(**{key: arguments.get(key) for key in
                                   ("answer_type", "number", "unit", "space_id", "text")},
                                explanation=str(arguments.get("explanation") or ""))
    except TypeError as error:
        return None, f"Malformed answer: {error}"
    if submission.answer_type not in ANSWER_TYPES:
        return None, f"answer_type must be one of {ANSWER_TYPES}"
    if submission.answer_type == "number" and submission.number is None:
        return None, "A number answer needs `number`."
    if submission.answer_type == "space" and submission.space_id not in bmap.spaces:
        return None, f"space_id '{submission.space_id}' is not a space id of this building."
    if submission.answer_type == "text" and not (submission.text or "").strip():
        return None, "A text answer needs `text`."
    return submission, None


def building_summary(bmap: BuildingMap) -> str:
    floors = sorted(bmap.floors.values(), key=lambda floor: floor["level"])
    lines = [f"Building: {bmap.data['building'].get('name', '')} ({len(bmap.spaces)} spaces, "
             f"{len(bmap.openings)} openings, {len(bmap.assets)} assets)"]
    for floor in floors:
        on_floor = [space for space in bmap.spaces.values() if space["floor_id"] == floor["id"]]
        kinds = Counter(f"{space['type']}/{space['room_type']}" for space in on_floor)
        lines.append(f"- {floor['name']} (id {floor['id']}, level {floor['level']}, elevation "
                     f"{floor.get('elevation_m')} m): " + ", ".join(f"{kind} ×{n}" for kind, n in sorted(kinds.items())))
    lines.append("Lifts and stairs: " + "; ".join(
        f"{connector['name']} ({connector['kind']}, {len(connector['floor_ids'])} floors)"
        for connector in bmap.connectors.values()) or "none")
    entrances = [opening for opening in bmap.openings.values() if opening["kind"] == "entrance"]
    lines.append(f"Entrances: {len(entrances)}")
    lines.append("Asset types: " + ", ".join(f"{kind} ×{n}" for kind, n in
                                             sorted(Counter(asset["type"] for asset in bmap.assets.values()).items())))
    return "\n".join(lines)


def make_client() -> object:
    return llm_client.make(max_retries=API_RETRIES)  # Anthropic or OpenAI (agent/llm_client.py)


class SolverAgent:
    def __init__(self, client: object | None = None, runs: int | None = None, model: str | None = None,
                 effort: str | None = None, cache: DecisionCache | None = None) -> None:
        self._client = client  # created on the first model call, so cached answers need no API key
        self.runs = RUNS if runs is None else runs
        self.model, self.effort = model or MODEL, effort or EFFORT
        self.cache = cache if cache is not None else DecisionCache.configured()

    @property
    def client(self) -> object:
        if self._client is None:
            self._client = make_client()
        return self._client

    def solve(self, question: str, bmap: BuildingMap, hint: str | None = None) -> AgentAnswer:
        """A cached decision for this building and question, else independent runs until two agree (at most
        runs + 1); the majority answer is the reply and goes into the cache with the code that produced it."""
        key = decision_key("agent", VERSION, bmap, question)
        cached = self.cache.get(key)
        if isinstance(cached, dict) and cached.get("submission"):
            best = Submission(**cached["submission"])
            if validate(asdict(best), bmap)[1] is None:
                return self.answer(best, bmap, [best], cached=True)
        runs: list[tuple[Submission | None, list[str]]] = []
        for _ in range(max(1, self.runs)):
            runs.append(self.run_once(question, bmap, hint))
        if len(runs) >= 2 and not (runs[0][0] and runs[1][0] and runs[0][0].agrees(runs[1][0])):
            runs.append(self.run_once(question, bmap, hint))
        done = [(submission, code) for submission, code in runs if submission is not None]
        if not done:
            return AgentAnswer("I could not answer this: the agent did not submit an answer.", None,
                               [submission for submission, _ in runs], error="agent did not submit an answer")
        best, code = max(done, key=lambda run: sum(run[0].agrees(other) for other, _ in done))  # first largest group
        self.cache.put(key, {"submission": asdict(best), "code": code,
                             "runs": [asdict(submission) if submission else None for submission, _ in runs]})
        return self.answer(best, bmap, [submission for submission, _ in runs])

    @staticmethod
    def answer(best: Submission, bmap: BuildingMap, runs: list[Submission | None], cached: bool = False) -> AgentAnswer:
        explanation = " ".join(line for line in best.explanation.splitlines()
                               if not line.strip().lower().startswith("answer"))
        return AgentAnswer(f"{explanation.strip()}\nAnswer: {answer_line(best, bmap)}", best, runs, cached=cached)

    def run_once(self, question: str, bmap: BuildingMap, hint: str | None) -> tuple[Submission | None, list[str]]:
        """One trajectory: (the accepted submission or None, the code cells it ran)."""
        view = copy.deepcopy(bmap)  # the model's code may change the map; the cached building must not change
        scope = namespace(view)
        system = [{"type": "text", "text": INSTRUCTIONS},
                  {"type": "text", "text": building_summary(view)}]
        prompt = question if not hint else f"{question}\n\n(Note from the question parser: {hint})"
        messages: list[dict] = [{"role": "user", "content": prompt}]
        code: list[str] = []
        for _ in range(MAX_ROUNDS):
            response = self.request(system, messages)
            content = llm_client.kept_content(response)
            messages.append({"role": "assistant", "content": content})
            if response.stop_reason == "pause_turn":
                continue
            uses = [block for block in content if getattr(block, "type", None) == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                messages.append({"role": "user", "content": "Call submit_answer with your final answer."})
                continue
            results, submitted = [], None
            for use in uses:
                arguments = dict(use.input or {})
                if use.name == "python":
                    code.append(str(arguments.get("code", "")))
                    result = run_code(code[-1], scope)
                elif use.name == "submit_answer":
                    submitted, problem = validate(arguments, view)
                    result = {"error": problem} if problem else {"ok": True}
                else:
                    result = {"error": f"Unknown tool {use.name}"}
                results.append({"type": "tool_result", "tool_use_id": use.id,
                                "content": json.dumps(result, ensure_ascii=False),
                                **({"is_error": True} if "error" in result and use.name != "python" else {})})
            if submitted is not None:
                return submitted, code
            messages.append({"role": "user", "content": results})
        return None, code

    def request(self, system: list[dict], messages: list[dict]) -> object:
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=TOOLS,
            messages=messages,
            cache_control={"type": "ephemeral"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
