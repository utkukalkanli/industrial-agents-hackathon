"""Deterministic solvers: one function per question kind, building + resolved params → SolverResult.

Every solver is a pure function of the building's current state (closures and added doors included) and never
mutates it; what-if solvers work on a copy. Results carry structured evidence (ids, route node paths, metres)
so the same call can back the benchmark Answer line, the Guide agent's tools and map highlights in the UI.

Plan and verification status per kind: docs/architecture/solver-plan.md."""

from collections.abc import Callable
from dataclasses import dataclass, field

from core.building_map import BuildingMap


@dataclass
class SolverResult:
    kind: str
    # Number answers: the number. Space answers (largest_room, room_stacked): the space id.
    value: float | int | str
    unit: str | None = None
    # 1–3 short human-readable lines explaining how the value was obtained (go before the Answer line).
    explanation: list[str] = field(default_factory=list)
    # Structured facts for UI/agents/Sunday output: space ids, route node ids, per-room numbers, ...
    evidence: dict = field(default_factory=dict)
    # largest_room only: the winning room's area in m².
    area_m2: float | None = None


Solver = Callable[..., SolverResult]
SOLVERS: dict[str, Solver] = {}


def solver(kind: str) -> Callable[[Solver], Solver]:
    def register(function: Solver) -> Solver:
        SOLVERS[kind] = function
        return function

    return register


def solve(building: BuildingMap, kind: str, params: dict) -> SolverResult:
    if kind not in SOLVERS:
        raise KeyError(f"No solver for question kind '{kind}'")
    return SOLVERS[kind](building, **params)


# Solver modules register themselves on import.
from core.solvers import changes, geometry, reachability, routing, walls  # noqa: E402,F401
