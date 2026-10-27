"""Live check of the Builder agent (prompt edits) against the real API: three edits on a draft of one building.

  uv run --env-file .env python scripts/live_builder.py [building_id] [--model claude-opus-5-5] [--effort medium]

The prompts are built from the building's own rooms and things (a lab to widen, a machine to move, two neighbouring
offices to join with a door), so any building with those works. Each prompt runs in a fresh Builder on the same
draft (nothing is applied). Prints, per prompt: seconds, whether it ended with a proposal, its ops, ungrounded
numbers and an estimated cost (prices in scripts/live_guide.py). The draft goes to a temporary directory."""

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from live_guide import cost  # noqa: E402

from agent import llm_client
from agent.builder import DEFAULT_EFFORT, DEFAULT_MODEL, Builder  # noqa: E402
from agent.builder_tools import BuilderTools  # noqa: E402
from agent.guide import llm_mode  # noqa: E402
from backend.drafts import DraftStore  # noqa: E402
from backend.sessions import load_catalogue  # noqa: E402


def prompts(tools: BuilderTools) -> list[str]:
    building = tools.store.building(tools.draft)
    rooms = [space for space in building["spaces"] if space["type"] == "room" and space.get("ref")]
    out = []
    lab = next((space for space in rooms if "lab" in space["room_type"]), None)
    if lab:
        out.append(f"Make {lab['name']} one metre wider, into the room next to it.")
    machine = next((asset for asset in building["assets"] if asset["category"] == "machine"), None)
    if machine:
        target = next(space for space in rooms if space["id"] != machine["space_id"])
        out.append(f"Move the {machine['name']} to {target['name']}.")
    for space in rooms:
        info = tools.call("space_info", {"space": space["id"]})
        partner = next((n for n in info.get("neighbours", []) if n["id"] in {r["id"] for r in rooms}
                        and not any(o["to"] == n["id"] for o in info["openings"])), None)
        if partner:
            out.append(f"Add a door between {space['name']} and {partner['name']}.")
            break
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("building", nargs="?", default="train/proc-campus-train-000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    args = parser.parse_args()
    if llm_mode() == "offline":
        sys.exit(f"needs {llm_client.key_name()} (uv run --env-file .env …)")
    store = DraftStore(Path(tempfile.mkdtemp()), load_catalogue())
    draft = store.create(args.building)
    total = 0.0
    for prompt in prompts(BuilderTools(store, draft)):
        builder = Builder(store, draft, model=args.model, effort=args.effort)
        started = time.perf_counter()
        turn = builder.reply(prompt)
        seconds = time.perf_counter() - started
        spent = cost(builder.usage, args.model) if args.model in ("claude-opus-5-5", "claude-sonnet-5-5",
                                                                  "claude-haiku-5-5") else 0.0
        total += spent
        ops = [operation["op"] for operation in turn.proposal.ops] if turn.proposal else []
        print(f"\n> {prompt}\n  {seconds:.1f} s · ~${spent:.3f} · proposal: {bool(turn.proposal)} {ops} · "
              f"ungrounded: {turn.ungrounded} · tools: {[call['name'] for call in turn.tool_calls]}")
        print("  " + turn.text.replace("\n", "\n  "))
    print(f"\ntotal ~${total:.3f} ({args.model}, effort {args.effort}); draft steps applied: {len(draft.steps)}")


if __name__ == "__main__":
    main()
