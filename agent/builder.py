"""The Builder: an agent that edits a draft copy of a building from what the user types (Edit mode, milestone 2).

Design: docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §4. Same shape as the Guide (agent/guide.py):
a Claude tool-use loop with a cached system prompt (instructions + the draft's overview), append-only history, and
the Guide's grounding check (numbers / ids in a reply must come from a tool result, the overview or the user).
The tools (agent/builder_tools.py) can only look and *propose*; a proposal enters the draft when the user applies
it — the Apply button (`Builder.apply`, via the backend) or a plain "yes" while exactly one proposal is open, which
is applied here without a model call. A proposal is open for one exchange only: the next message (or Apply);
any other turn, a Cancel, or a hand edit closes it. Proposals made against an older draft are refused ("changed since").
Offline (no key or GUIDE_LLM=offline) the rule-based agent/builder_offline.py stands in for the model.
`dump` / `Builder.restore` carry the conversation through the draft store (milestone 3), so any backend instance can
continue it; the system blocks are kept, like Guide conversations (backend/persistence.py), for the cache prefix."""

import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from agent import llm_client
from agent.builder_tools import BUILDER_TOOLS, BuilderTools, Proposal
from agent.guide import FALLBACK_BETA, MAX_TOKENS, Usage, llm_mode, ungrounded
from backend.drafts import Draft, DraftStore
from backend.persistence import StateError, plain_messages
from core.edits import EditError

DEFAULT_MODEL = "claude-opus-5-5"  # override with BUILDER_MODEL
DEFAULT_EFFORT = "medium"  # override with BUILDER_EFFORT
MAX_TOOL_ROUNDS = 10
STATE_FORMAT = 1  # Builder.dump layout
MAX_REPAIRS = 2  # failed propose_edit calls per turn before the loop is told to stop proposing
# Only a message that is nothing but a confirmation applies the open proposal without the model ("yes, but call it
# Library" must reach the model).
CONFIRM_ONLY = re.compile(r"^\s*(yes|yep|yeah|ok|okay|sure|confirm|apply|apply it|do it|go ahead|please do|yes please)"
                          r"\s*[.!]*\s*$", re.IGNORECASE)
STOP_PROPOSING = ("stop proposing: your last proposals failed. Tell the user in one or two sentences what you tried "
                  "and what went wrong, and ask how to continue.")

INSTRUCTIONS = """You are the Builder: the user edits a building by telling you what to change. You work on a DRAFT \
COPY of the building; the original is never touched. You can only look and propose — the user applies.

Coordinates are metres, x grows to the east, y to the north. Spaces have outlines (polygons), doors (openings) sit on \
the wall two spaces share, and things (assets) sit inside a space.

How to work:
- Find places with find / space_info; never invent ids or coordinates. If a name matches several places, or the \
wall / direction is unclear, ask ONE short question instead of guessing.
- Make a room wider or narrower = move_edge with an edge taken from space_info.edges (positive offset_m = outward, \
negative = inward); the neighbour on that side shrinks or grows automatically.
- Move a thing = move_asset (position inside the target room — pick a point inside its bbox, away from walls).
- Doors: add_opening between two spaces that share a wall (position near that wall; it is snapped onto it), \
move_opening, set_opening (width_m, step_free), delete_opening.
- Rooms: add_space, set_space (rename / retype), set_polygon, delete_space.
- Always finish a change with ONE propose_edit (all ops of the change in one list), then tell the user in a short \
reply: what you understood, the effect (areas before → after from the tool result) and any new problems it would \
add, and ask them to apply it. Never say a change is done or applied — only the user applies.
- Use only numbers that appear in tool results or the user's words.

Ops (each {"op": name, ...arguments}):
add_space(floor_id, polygon, type, room_type, name, ref) · delete_space(space_id) · \
set_space(space_id, name?, ref?, type?, room_type?) · set_polygon(space_id, polygon) · \
move_vertex(floor_id, from_xy, to_xy) · move_edge(space_id, edge=[[x1,y1],[x2,y2]], offset_m) · \
add_opening(space_ids=[a, b] or [a, "outside"], position, kind=door|opening|entrance, width_m, step_free) · \
move_opening(opening_id, position) · set_opening(opening_id, width_m?, step_free?, kind?) · \
delete_opening(opening_id) · add_asset(space_id, name, category, type, position, footprint?) · \
move_asset(asset_id, position, rotation_deg?, space_id?) · set_asset(asset_id, name?, type?, category?, footprint?) · \
delete_asset(asset_id)"""


@dataclass
class BuilderTurn:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # {"name", "input", "result"}
    proposal: Proposal | None = None  # the proposal this turn made (still open)
    applied: str | None = None  # summary of the proposal a "yes" applied
    ungrounded: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def make_builder_client() -> object:
    if (mode := llm_mode()) != "offline":
        return llm_client.make(name=mode)
    from agent.builder_offline import BuilderOfflineClient

    return BuilderOfflineClient()


class Builder:
    def __init__(self, store: DraftStore, draft: Draft, client: object | None = None, model: str | None = None,
                 effort: str | None = None) -> None:
        self.store = store
        self.draft = draft
        self.tools = BuilderTools(store, draft)
        self.client = client if client is not None else make_builder_client()
        self.model = model or os.environ.get("BUILDER_MODEL", DEFAULT_MODEL)
        self.effort = effort or os.environ.get("BUILDER_EFFORT", DEFAULT_EFFORT)
        overview = json.dumps(self.tools.call("overview", {}), ensure_ascii=False, separators=(",", ":"))
        self.system = [{"type": "text", "text": INSTRUCTIONS},
                       {"type": "text", "text": "Draft overview when this conversation started:\n" + overview,
                        "cache_control": {"type": "ephemeral"}}]
        self.messages: list[dict] = []
        self.corpus: list[str] = [overview]
        self.notes: list[str] = []  # told to the model with the next user message (Apply button, hand edits)
        self.closed: dict[str, str] = {}  # proposal id → why it can no longer be applied (for the Apply button's 409)
        self.usage = Usage()
        self.on_step: Callable[[dict], None] | None = None
        self.version = 0  # stored version this object reflects (0 = never stored); kept by the backend app

    # ---------- storing ----------

    def dump(self) -> dict:
        """Everything another instance needs to continue this conversation, as JSON. Open proposals keep their ops
        and draft version; their preview (a whole building, only shown with the turn that made it) is dropped."""
        state = {
            "format": STATE_FORMAT,
            "system": self.system,
            "messages": plain_messages(self.messages),
            "corpus": self.corpus,
            "notes": self.notes,
            "closed": self.closed,
            "pending": [{**asdict(proposal), "preview": None} for proposal in self.tools.pending.values()],
            "next_id": self.tools.next_id,
            "usage": asdict(self.usage),
        }
        return json.loads(json.dumps(state, ensure_ascii=False))

    @classmethod
    def restore(cls, store: DraftStore, draft: Draft, state: dict, client: object | None = None) -> "Builder":
        if state.get("format") != STATE_FORMAT:
            raise StateError(f"stored Builder format {state.get('format')!r}, expected {STATE_FORMAT}")
        builder = cls(store, draft, client=client)
        builder.system = state["system"]
        builder.messages = state["messages"]
        builder.corpus = state["corpus"]
        builder.notes = state["notes"]
        builder.closed = state["closed"]
        builder.tools.pending = {item["id"]: Proposal(**item) for item in state["pending"]}
        builder.tools.next_id = state["next_id"]
        builder.usage = Usage(**state["usage"])
        return builder

    # ---------- applying ----------

    def cancel(self, proposal_id: str) -> None:
        """The user dismissed the proposal (Cancel): it can no longer be applied."""
        if self.tools.pending.pop(proposal_id, None) is not None:
            self.closed[proposal_id] = "this proposal was cancelled"
            self.notes.append(f"[note, not from the user] The user cancelled {proposal_id}.")

    def drafted_by_hand(self, note: str) -> None:
        """A hand edit / undo changed the draft: tell the model next turn, and drop the open proposal."""
        self.close_all("the draft changed since this proposal; ask again")
        self.notes.append(f"[note, not from the user] {note}")

    def close_all(self, reason: str) -> None:
        self.closed.update({proposal_id: reason for proposal_id in self.tools.pending})
        self.tools.pending.clear()

    def apply(self, proposal_id: str) -> str:
        """Apply an open proposal to the draft (the user's decision). Raises EditError if it is unknown or stale."""
        proposal = self.tools.pending.get(proposal_id)
        if proposal is None:
            raise EditError(self.closed.get(proposal_id, f"no open proposal {proposal_id!r}; ask again"))
        self.store.apply(self.draft, proposal.ops, expected_version=proposal.draft_version)
        self.tools.pending.pop(proposal_id, None)
        self.notes.append(f"[note, not from the user] The user applied {proposal.id} ({proposal.summary}) with the "
                          "Apply button.")
        return proposal.summary

    # ---------- a user turn ----------

    def reply(self, text: str) -> BuilderTurn:
        if CONFIRM_ONLY.match(text) and len(self.tools.pending) == 1:
            proposal_id = next(iter(self.tools.pending))
            try:
                summary = self.apply(proposal_id)
            except EditError as error:
                self.tools.pending.clear()
                reply = f"I couldn't apply it: {error}"
                self.remember(text, reply)
                return BuilderTurn(reply)
            self.notes.pop()  # the exchange below already says so
            reply = f"Applied: {summary}."
            self.remember(text, reply)
            return BuilderTurn(reply, applied=summary)
        # A proposal is only confirmable by the very next message: any other turn closes it (the UI drops its card).
        self.close_all("a newer message replaced this proposal; ask again")
        self.corpus.append(text)
        notes, self.notes = self.notes, []
        self.messages.append({"role": "user", "content": "\n\n".join([*notes, text])})
        turn = self.run()
        missing = ungrounded(turn.text, "\n".join(self.corpus))
        if missing and turn.stop_reason == "end_turn":
            self.step({"kind": "check", "name": "grounding"})
            self.messages.append({"role": "user", "content": (
                "[grounding check, not from the user] Your last reply states " + ", ".join(missing)
                + ", which appear in no tool result. Check them with a tool, or leave them out, and give the user "
                "your full reply again.")})
            repaired = self.run()
            repaired.tool_calls = turn.tool_calls + repaired.tool_calls
            turn = repaired
        turn.ungrounded = ungrounded(turn.text, "\n".join(self.corpus))
        turn.proposal = next(iter(self.tools.pending.values()), None)
        return turn

    def remember(self, said: str, reply: str) -> None:
        self.messages += [{"role": "user", "content": said}, {"role": "assistant", "content": reply}]

    def run(self) -> BuilderTurn:
        calls: list[dict] = []
        said: list[str] = []
        failures = 0
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.request()
            content = llm_client.kept_content(response)
            self.messages.append({"role": "assistant", "content": content})
            if response.stop_reason == "refusal":
                return BuilderTurn("Sorry, I can't help with that one.", calls, stop_reason="refusal")
            said += [block.text.strip() for block in response.content if block.type == "text" and block.text.strip()]
            if response.stop_reason == "pause_turn":
                continue
            uses = [block for block in content if getattr(block, "type", None) == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                if response.stop_reason == "max_tokens":
                    said.append("(My answer was cut off — ask me to continue.)")
                return BuilderTurn("\n\n".join(said), calls, stop_reason=response.stop_reason)
            results = []
            for use in uses:
                arguments = dict(use.input or {})
                self.step({"kind": "tool", "name": use.name, "input": arguments})
                if use.name == "propose_edit" and failures >= MAX_REPAIRS:
                    result = {"error": STOP_PROPOSING}
                else:
                    result = self.tools.call(use.name, arguments)
                    if use.name == "propose_edit" and "error" in result:
                        failures += 1
                self.step({"kind": "tool_done", "name": use.name, "ok": "error" not in result})
                calls.append({"name": use.name, "input": arguments, "result": result})
                content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                self.corpus.append(content)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content,
                                **({"is_error": True} if "error" in result else {})})
            self.messages.append({"role": "user", "content": results})
        return BuilderTurn("I couldn't finish that in a reasonable number of steps. Could you narrow it down?",
                           calls, stop_reason="max_tool_rounds")

    def step(self, step: dict) -> None:
        if self.on_step is not None:
            self.on_step(step)

    def request(self) -> object:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=BUILDER_TOOLS,
            messages=self.messages,
            cache_control={"type": "ephemeral"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.usage.requests += 1
            self.usage.input_tokens += usage.input_tokens
            self.usage.output_tokens += usage.output_tokens
            self.usage.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
            self.usage.cache_creation_input_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        return response
