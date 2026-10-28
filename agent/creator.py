"""The Creator: an agent that turns uploaded floor plans (PDF pages, photos, scans) into a draft building
(docs/superpowers/specs/2026-10-25-plan-import-design.md). A Claude tool loop over agent/creator_tools.py: the model
looks at the pages and its own intermediate results (tool results carry PNGs) and decides which page is which floor,
which segmentation fits, and what every cell is; code does all geometry and checks every answer. It never asks the
user anything — corrections come afterwards, in Edit mode, from the Builder.

The model's short sentences before each tool call are the progress the user sees (`on_step` "say" events). Images
stay in the conversation (the cached prefix keeps growing, so earlier turns are cheap cache reads); only past
MAX_IMAGES are the old ones dropped, all at once."""

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import anthropic

from agent import llm_client
from agent.creator_tools import CREATOR_TOOLS, CreatorTools, ImportSession
from agent.guide import FALLBACK_BETA, MAX_TOKENS, Usage, llm_mode

DEFAULT_MODEL = "claude-opus-5-5"  # override with CREATOR_MODEL
DEFAULT_EFFORT = "medium"  # override with CREATOR_EFFORT
MAX_TOOL_ROUNDS = 60
MAX_IMAGES = 40  # images in the conversation before old ones are dropped (each ~1.5–2.5k tokens)
KEEP_IMAGES = 8  # how many of the newest stay when that happens
DROPPED = {"type": "text", "text": "[image dropped to save space — call the tool again to see it]"}
NUDGE = ("[not from the user] You stopped without ending the import. Call finish (or no_plan if no file shows a floor "
         "plan).")
CUT = ("[not from the user] Your last reply was cut off by the token limit, so its tool call was not run. Make the "
       "call again, shorter if it was long.")

INSTRUCTIONS = """You are the Creator: you turn uploaded files (PDF pages, photos of plans on a wall, scans) into a \
building model, with no help from the user. Code does all geometry; you read the drawings and decide.

Work in this order:
1. list_sources. Find every floor plan. A floor plan shows the inside of a building: rooms divided by walls, usually \
with room names or numbers, doors, stairs. Site plans, landscape or garden plans, maps, and building outlines whose \
rooms you cannot read are not floor plans — ignore them, like text pages and photos. If no file shows a floor plan, \
call no_plan; never fill an outline with made-up rooms ("Block 1", "Room A").
2. For each floor: decide its level from the name on the plan — EG / Erdgeschoss / ground floor / Parterre / rez-de-\
chaussée / ground → 0; "1. OG" / "1. Obergeschoss" / "Floor 1" / "first floor" / an only "upper floor" → 1 (and n for \
n); UG / Untergeschoss / basement / Keller → −1. One plan per level: if a floor appears twice, use the sharpest, \
most complete view. Pages that name rooms (legends, numbered room lists, signs) are label sources for that floor. \
Use view_source to read a plan's box off the grid: the bbox must hold the whole drawing of the floor but not the \
legend, the title block or text columns. photo=true for photographs of a sheet.
3. register_plan, then look hard at the numbered cells against the drawing. Cells that cross clear walls, or far \
fewer cells than the rooms you can read, mean the segmentation failed: try segment with method=colours (rooms drawn \
as coloured fills) or method=walls with another gap_px; if rooms are still merged, cut them out with add_rooms; rooms \
that got no cell because they are open to the outside (a foyer without a front wall) are added with add_rooms cell=0; \
only if nothing works, coarse_rooms for the whole floor.
4. label_cells for every kept cell: merge cells that are one room, mark as outside what is not inside the building \
(margins, sheet border, legend bits, open courtyards may be outdoor spaces or outside — your call), and for each room \
give type (room / corridor / stair / lift / hall / outdoor), room_type from: bedroom, living_room, kitchen, \
bathroom, toilet, storage, corridor, balcony, stairwell, lift, office, meeting_room, seminar_room, lecture_hall, lab, \
makerspace, library, server_room, technical_room, lobby, canteen, shop, print_room, locker_room, production_zone, \
additive_zone, assembly_zone, warehouse_zone, logistics_zone, quality_lab, generic_room — and the name written in \
the room (translate nothing; use the legend's name for a number, e.g. "74 Nibelungen Hall"; ref = the room number \
if there is one). Stairs and lifts must be labelled on every floor they serve, with the same name on every floor for the same \
stair or lift (e.g. "Treppe West" on all floors) — that is how floors connect. Doors: \
keep the red candidates that are real doors, add [cell, cell] for openings you see that have none. Mark entrances \
(arrows, "Eingang", exit signs on the outer wall). Then look at the labelled plan it returns and fix what is wrong — \
at most two review rounds per floor.
5. set_scale with method=bar if a scale bar or a written dimension is visible; otherwise leave it (door gaps are \
used).
6. stack_floors when there is more than one floor; check that stairs / lifts were joined.
7. finish with the building's name (from the plans or file names). If it returns errors, fix them once, then finish \
again.

Before each tool call write one short sentence for the user saying what you are doing ("Reading the ground floor \
photo.", "The upper floor is page 2."). Never ask the user anything; never invent rooms you cannot see."""


@dataclass
class CreatorResult:
    status: str  # "done" | "no_plan" | "failed" | "cancelled"
    building: dict | None = None
    issues: list[dict] = field(default_factory=list)
    reason: str = ""
    usage: Usage = field(default_factory=Usage)


class Creator:
    def __init__(self, session: ImportSession, client: object | None = None, model: str | None = None,
                 effort: str | None = None) -> None:
        self.session = session
        self.tools = CreatorTools(session)
        self.client = client
        if client is None and (mode := llm_mode()) != "offline":
            self.client = llm_client.make(name=mode)
        self.model = model or os.environ.get("CREATOR_MODEL", DEFAULT_MODEL)
        self.effort = effort or os.environ.get("CREATOR_EFFORT", DEFAULT_EFFORT)
        self.system = [{"type": "text", "text": INSTRUCTIONS, "cache_control": {"type": "ephemeral"}}]
        self.messages: list[dict] = []
        self.usage = Usage()
        self.max_rounds = MAX_TOOL_ROUNDS
        self.on_step: Callable[[dict], None] | None = None
        self.cancel = threading.Event()  # set when the user leaves (the backend stream closed): stop before the next call

    def step(self, step: dict) -> None:
        if self.on_step is not None:
            self.on_step(step)

    def opening(self) -> str:
        lines = [f"- {source.id}: {source.origin}" + (f" — floor {source.level}" if source.level is not None else "")
                 for source in self.session.sources]
        warnings = [f"- {warning}" for warning in self.session.warnings]
        given = any(source.level is not None for source in self.session.sources)
        told = (["The user said which floor each file is (\"— floor n\"): each such source is the plan of that level; "
                 "register every one of them at that level, whatever the drawing is titled."] if given else [])
        return "\n".join(["Uploaded sources:", *lines, *(["Files that could not be read:", *warnings] if warnings
                                                          else []), "", *told, "Build the building from these files."])

    def result(self) -> CreatorResult | None:
        if self.session.finished is not None:
            return CreatorResult("done", self.session.finished["building"], self.session.finished["issues"],
                                 usage=self.usage)
        if self.session.no_plan is not None:
            return CreatorResult("no_plan", reason=self.session.no_plan, usage=self.usage)
        return None

    def run(self) -> CreatorResult:
        if self.client is None:
            return CreatorResult("failed", reason=f"the Creator needs an LLM key (set {llm_client.key_name()})")
        self.messages = [{"role": "user", "content": self.opening()}]
        nudged = False
        for _ in range(self.max_rounds):
            if self.cancel.is_set():
                return CreatorResult("cancelled", reason="the import was cancelled", usage=self.usage)
            self.prune()
            try:
                response = self.request()
            except anthropic.APIError as error:  # credits, limits, network: end with the reason, not a traceback
                return CreatorResult("failed", reason=f"LLM API error: {error}"[:300], usage=self.usage)
            content = llm_client.kept_content(response)
            self.messages.append({"role": "assistant", "content": content})
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self.step({"kind": "say", "text": block.text.strip()})
            if response.stop_reason == "refusal":
                return CreatorResult("failed", reason="the model declined this import", usage=self.usage)
            if response.stop_reason == "pause_turn":
                continue
            uses = [block for block in content if getattr(block, "type", None) == "tool_use"]
            if not uses and response.stop_reason == "max_tokens":  # cut off: not a stop, so the nudge stays unused
                self.messages.append({"role": "user", "content": CUT})
                continue
            if not uses:
                if nudged:
                    return CreatorResult("failed", reason="the Creator stopped without finishing", usage=self.usage)
                nudged = True
                self.messages.append({"role": "user", "content": NUDGE})
                continue
            results = []
            for use in uses:
                arguments = dict(use.input or {})
                self.step({"kind": "tool", "name": use.name,
                           **({"level": arguments["level"]} if "level" in arguments else {})})
                content = self.tools.call(use.name, arguments)
                failed = content[0]["type"] == "text" and content[0]["text"].startswith('{"error"')
                self.step({"kind": "tool_done", "name": use.name, "ok": not failed})
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content,
                                **({"is_error": True} if failed else {})})
            self.messages.append({"role": "user", "content": results})
            if (done := self.result()) is not None:
                return done
        return CreatorResult("failed", reason=f"the import did not finish within {self.max_rounds} steps",
                             usage=self.usage)

    def prune(self) -> None:
        """Past MAX_IMAGES images, replace all but the newest KEEP_IMAGES with a note — in one go. Dropping one image
        per turn would change the conversation's prefix every turn and turn every cache read into a cache write
        (measured: ~0.87 M cache-write tokens for one 5-floor import), so the prefix only changes on these rare cuts."""
        images = [(block["content"], index) for turn in self.messages
                  if turn["role"] == "user" and isinstance(turn["content"], list)
                  for block in turn["content"]
                  if block.get("type") == "tool_result" and isinstance(block.get("content"), list)
                  for index, part in enumerate(block["content"]) if part.get("type") == "image"]
        if len(images) <= MAX_IMAGES:
            return
        for content, index in images[:-KEEP_IMAGES]:
            content[index] = DROPPED

    def request(self) -> object:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=CREATOR_TOOLS,
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
