"""Live check of the Building Guide (agent/guide.py) on scripted conversations (calls the Claude API, costs money).

  uv run --env-file .env python scripts/eval_guide.py                      # every tests/guide_conversations/*.json
  uv run --env-file .env python scripts/eval_guide.py tests/guide_conversations/lift_closure.json
  uv run --env-file .env python scripts/eval_guide.py --model claude-sonnet-5-5 --effort low

Each turn's `expect` is checked against the GuideTurn and the Guide's BuildingSession. Keys: `asked` (reply contains
a question), `tools` ([] = no tool call, otherwise each name was called), `route_to` (the last reachable find_route / find_nearest
of the turn, else of the conversation so far, ends there and its length equals a fresh core route from the session
state after the turn), `no_route` (no reachable route computed this turn), `step_free` (session profile flag),
`space_ids_include` (space ids in the turn's tool results and UI events), `grounded` (no ungrounded number or id
left), `asset_total` (asset type id whose building-wide count a `locate`/`count_assets` result and the reply must
state). Prints PASS/FAIL per turn with seconds and cost, and the totals; exit 1 on any failure."""

import argparse
import json
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.guide import Guide, GuideTurn, Usage, make_client  # noqa: E402
from agent.tools import BuildingSession  # noqa: E402
from core import navigation  # noqa: E402
from scripts.live_guide import cost, delta  # noqa: E402

EXPECT_KEYS = {"asked", "tools", "route_to", "no_route", "step_free", "space_ids_include", "grounded", "asset_total"}
CONVERSATIONS = Path(__file__).resolve().parent.parent / "tests" / "guide_conversations"


def load_conversation(path: Path) -> dict:
    conversation = json.loads(Path(path).read_text())
    for turn in conversation["turns"]:
        unknown = set(turn["expect"]) - EXPECT_KEYS
        if unknown:
            raise ValueError(f"{path}: unknown expect keys {sorted(unknown)}")
    return conversation


def asks(text: str) -> bool:
    """The reply puts a question to the user anywhere ("…, so which one do you want? Makerspace 1.14 …")."""
    return re.search(r"\?(?=\s|$)", text) is not None


def routes(turn: GuideTurn) -> list[dict]:
    """Reachable find_route / find_nearest results of the turn (find_nearest routes to what it finds), in call
    order."""
    return [call["result"] for call in turn.tool_calls
            if call["name"] in ("find_route", "find_nearest") and call["result"].get("reachable") is True]


def space_ids(session: BuildingSession, turn: GuideTurn) -> list[str]:
    """Every space id that appears in the turn's tool results or UI events."""
    found: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value in session.building.spaces and value not in found:
            found.append(value)

    walk([call["result"] for call in turn.tool_calls])
    walk(turn.events)
    return found


def check_route(session: BuildingSession, turn: GuideTurn, destination: str, earlier: dict | None = None) -> list[str]:
    """The last reachable route (this turn's, else `earlier`, the conversation's last one before this turn: the
    Guide may repeat a route it already has) ends at `destination` and matches a fresh core route under the
    session's state after the turn (profile, applied changes, route rules): a route computed before a profile or
    change took effect fails here."""
    computed = routes(turn) or ([earlier] if earlier else [])
    if not computed:
        return [f"route_to {destination}: no reachable route was computed"]
    last = computed[-1]
    if last["to_space_id"] != destination:
        return [f"route_to {destination}: route ends at {last['to_space_id']}"]
    reference = navigation.find_route(
        session.building, last["from_space_id"], destination, step_free=session.profile.step_free,
        closed=session.profile_closures(), via=last.get("via") or (), model=session.route_model,
        rules=session.route_rules()).to_dict()
    if reference.get("reachable") is not True:
        return [f"route_to {destination}: core finds no route under the session state"]
    if last["length_m"] != reference["length_m"]:
        return [f"route_to {destination}: length_m {last['length_m']} != core {reference['length_m']}"]
    return []


def check_asset_total(session: BuildingSession, turn: GuideTurn, asset_type: str) -> list[str]:
    """A locate/count_assets result this turn equals the building's asset count, and the reply states it."""
    expected = sum(a["type"] == asset_type for a in session.building.assets.values())
    totals = [call["result"].get("total" if call["name"] == "locate" else "count") for call in turn.tool_calls
              if call["name"] in ("locate", "count_assets") and "error" not in call["result"]]
    if expected not in totals:
        return [f"asset_total {asset_type}: core counts {expected}, tool totals {totals}"]
    if not re.search(rf"\b{expected}\b", turn.text):
        return [f"asset_total {asset_type}: reply does not state {expected}"]
    return []


def check_turn(session: BuildingSession, turn: GuideTurn, expect: dict, earlier: dict | None = None) -> list[str]:
    failures = []
    if "asked" in expect and asks(turn.text) != expect["asked"]:
        failures.append(f"asked is {asks(turn.text)}, expected {expect['asked']}")
    called = [call["name"] for call in turn.tool_calls]
    if "tools" in expect:
        if not expect["tools"] and called:
            failures.append(f"expected no tool call, got {called}")
        missing = [name for name in expect["tools"] if name not in called]
        if missing:
            failures.append(f"tools not called: {missing} (called {called})")
    if "route_to" in expect:
        failures += check_route(session, turn, expect["route_to"], earlier)
    if expect.get("no_route") and routes(turn):
        failures.append("a route was computed, expected none")
    if "step_free" in expect and session.profile.step_free != expect["step_free"]:
        failures.append(f"session step_free is {session.profile.step_free}, expected {expect['step_free']}")
    if "asset_total" in expect:
        failures += check_asset_total(session, turn, expect["asset_total"])
    seen = space_ids(session, turn)
    missing_ids = [i for i in expect.get("space_ids_include", []) if i not in seen]
    if missing_ids:
        failures.append(f"space_ids missing {missing_ids} (got {seen})")
    if "grounded" in expect and (not turn.ungrounded) != expect["grounded"]:
        failures.append(f"grounded is {not turn.ungrounded} (ungrounded {turn.ungrounded}), "
                        f"expected {expect['grounded']}")
    return failures


def run_conversation(path: Path, model: str | None, effort: str | None) -> tuple[int, int, float, float]:
    conversation = load_conversation(path)
    guide = Guide(BuildingSession.load(Path(conversation["building"])), client=make_client(), model=model,
                  effort=effort)
    passed = 0
    earlier: dict | None = None  # the conversation's last reachable route so far
    started_all = time.perf_counter()
    for number, turn in enumerate(conversation["turns"], 1):
        before, started = Usage(**asdict(guide.usage)), time.perf_counter()
        try:
            result = guide.reply(turn["user"])
        except Exception as error:
            failures, reply = [f"error: {type(error).__name__}: {error}"], ""
        else:
            failures, reply = check_turn(guide.session, result, turn["expect"], earlier), result.text
            earlier = (routes(result) or [earlier])[-1]
        seconds = time.perf_counter() - started
        passed += not failures
        print(f"  {'PASS' if not failures else 'FAIL'} turn {number} ({seconds:.1f}s, "
              f"${cost(delta(guide.usage, before), guide.model):.3f}): {turn['user']}")
        for failure in failures:
            print(f"       - {failure}")
        if failures:
            print(f"       reply: {reply}")
    return passed, len(conversation["turns"]), cost(guide.usage, guide.model), time.perf_counter() - started_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scripted Guide conversations against the live API.")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--model", default=None, help="default: GUIDE_MODEL or agent.guide.DEFAULT_MODEL")
    parser.add_argument("--effort", default=None, help="default: GUIDE_EFFORT or agent.guide.DEFAULT_EFFORT")
    args = parser.parse_args()
    files = args.files or sorted(CONVERSATIONS.glob("*.json"))
    passed = total = 0
    spent = seconds = 0.0
    for path in files:
        print(path.name)
        ok, count, price, took = run_conversation(path, args.model, args.effort)
        passed, total, spent, seconds = passed + ok, total + count, spent + price, seconds + took
    print(f"\n{passed}/{total} turns PASS, {seconds:.1f}s, total cost ~${spent:.4f}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
