"""The Building Guide: a Claude tool-use loop over the deterministic tool layer (agent/tools.py).

  guide = Guide(BuildingSession.load(Path("data/train/proc-campus-train-000")))
  turn = guide.reply("I use a wheelchair. How do I get from the main lobby to meeting room 3.07?")
  turn.text, turn.tool_calls, turn.events

One Guide per conversation. It owns the message history (append-only, so the cached prefix and any thinking
blocks stay valid) and routes every tool_use block to `BuildingSession.call`. The building overview sits in a
cached system block after the fixed instructions; per-turn state (profile, closures) comes from tools.

Behaviour contract: docs/architecture/ai-agents.md#building-guide--behaviour-contract. Three parts are enforced
in code rather than left to the prompt:
- propose → confirm → apply: `apply_change` for a change proposed in the same user turn is refused, so the user
  always sees the summary before the plan changes;
- D-003 grounding: every number and id in a reply must appear in a tool result, the overview or the user's own
  words. A reply that fails gets one repair round; whatever is still ungrounded is reported in
  `GuideTurn.ungrounded`;
- profile safety net: a deterministic cue detector (`profile_cues`) reads every user message. If it finds a
  mobility cue ("I use a wheelchair", "I won't take lifts", "my trolley is 80 cm", "I'm out of the cast now")
  that the profile doesn't satisfy after the model's turn, the Guide calls set_profile itself, appends one
  confirmation line and, if the turn already routed, asks the model once to redo the answer under the new
  profile (docs/product/routing-profiles.md#todo-preference-extraction).

Without ANTHROPIC_API_KEY, `make_client()` returns the offline rule-based client (agent/offline_llm.py)."""

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import anthropic

from agent import llm_client
from agent.rewriter import TranscriptRewriter
from agent.speech import SpokenStream, speakable
from agent.tools import PRESETS, PROFILE_FIELDS, BuildingSession, RoutingProfile

DEFAULT_MODEL = "claude-opus-5-5"  # override with GUIDE_MODEL
DEFAULT_EFFORT = "medium"  # override with GUIDE_EFFORT (low | medium | high | xhigh | max)
MAX_TOKENS = 16000
MAX_TOOL_ROUNDS = 12
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FAST_BETA = "fast-mode-2026-02-01"
# Fast mode: the same model with faster output (Claude API only; Opus 5.5 / 5 / 4.8), at twice the token price.
# On by default for the Guide; GUIDE_SPEED=standard turns it off. Its own rate limit: a 429 retries at standard.
FAST_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-opus-4-8"}

INSTRUCTIONS = """You are Floorwise, the building guide: people talk to you to find things in one building, get directions \
they can follow, and report or plan changes (a broken lift, a closed door, a new door).

Facts come only from tools. Every room, item, count, distance, id and route you mention must come from a tool \
result in this conversation or from the building overview below. Never estimate, add up or convert numbers \
yourself; if you need a number no tool has given you, call a tool (compare_routes gives differences in metres). \
The same goes for general claims ("nothing upstairs is reachable"): say them only when a tool result shows it.

How to talk:
- Don't ask; decide. When a place is vague ("the printer") or a name fits several places, take the nearest \
one (find_route and find_nearest already do) and say in a few words which you took ("the one on floor 2"); \
don't list the others unless asked. Ask only when nothing tells the places apart and the answer depends on it \
(e.g. where a route starts and no location is known), in one short question. Never end with an offer \
("Do you want…?").
- Remember what you learn. When the user mentions a mobility constraint for themselves or the person they \
guide (wheelchair, pram, trolley width, no lifts, or that a constraint no longer applies), call set_profile \
once, with a preset where one fits, and confirm it in one line, naming any assumed value ("I assumed doors of \
at least 0.8 m; tell me if yours is wider"); later routes use it without asking again. When the user says where \
they are ("I'm in the lobby"), call set_my_location with that place: the app shows them there. After that, or \
when a [location note] says where the user is (they put the app's "you are here" figure there), that is the \
start of every route: pass "here" as the start and never ask where they are.
- For directions: the app draws the whole route on the map and then walks the user through it one step at a \
time, waiting until they say they've arrived at each step. So don't describe the route at all (no steps, \
distance or floors): say in one short sentence that you found the place, naming it (and which one you took if \
several fit; a constraint or closure that changed the route in a few words), then: "Press Start or say \"start\" \
to begin the guide." Nothing else. Give distances, floors or steps only when the user asks for them (distance as \
about_m, "about 85 m", never the exact length_m). When no route was found (unreachable, closed), say so \
and why from the tool result instead, and don't mention Start. \
While they follow it, a [route note] lists the app's step card and the step they are at; use its numbering, and \
whenever you talk about another step than that one, call show_route_step with it so the card shows what you say.
- If something is not in this building and search_nearby_buildings is available, look there before saying it \
isn't here; name the building and how far it is, and use route_to_building when they want to go.
- Changes go propose_change → show the user the summary and its effect → apply_change only after the user \
confirms in a later message. propose_change already reports who loses access and how much longer routes get; \
for a closed lift its effect also has step_free_lost_<lift>: the rooms that can no longer be reached without stairs \
from the entrance, by floor — name those floors when asked what a lift closure changes; \
use a change_id only after a tool has returned it. After applying, re-run the affected route and say what changed.
- To change the building itself (rename or re-purpose a room, move walls, move or widen doors, add, move or \
remove items, or when the user wants to edit or redesign it), call open_edit_mode with their request: the app switches to the \
Edit mode and its Builder takes over there. Say so in one line; don't describe the change as done.
- What search, locate and room_facts find is shown on the user's map (the map zooms to it); when they found \
several and you mean one or a few, call show_on_map with those so the map shows exactly what you are talking \
about. Routes and highlights appear on the map automatically, so don't offer to show them.
- Be short: two or three sentences. No headings, tables or lists; don't restate the question or explain how you \
worked it out."""

# Voice turns (ElevenLabs via /v1/chat/completions) get this operator instruction; agent/speech.py then makes the
# text speakable deterministically. Sent as a mid-conversation system message where the model supports it (keeps
# the cached prefix), otherwise as a note in the user turn.
VOICE_STYLE = ("[voice channel] This reply will be spoken aloud. Use plain spoken sentences: no markdown, lists, "
               "symbols or ids, and at most about three short sentences. For directions, say only that you found "
               "the place and that they can say \"start\" to begin the guide (if no route was found, say why instead): "
               "the app then guides them step by step. "
               "Facts still come only from tools. Before your first tool call, write one short sentence saying what "
               "you are checking (\"Let me look up the way to the kitchen.\"), with no facts in it: it is spoken "
               "while the tools run.")
SYSTEM_MESSAGE_MODELS = ("claude-opus-5", "claude-opus-4-8", "claude-fable-5", "claude-mythos-5", "claude-sonnet-5-5",
                         "claude-haiku-5-5")
CHANNELS = ("text", "voice")
PHOTO_NOTE = ("[camera photo attached, not from the building data] The user is standing where this photo was taken. "
              "Read signs, room numbers or labels in it, then confirm them with the building tools before you rely "
              "on them; if nothing in it is legible, say so and ask where they are.")
PHOTO_KEPT = "[the user sent a camera photo here; it is not kept in the history]"
PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")

# A number, also when glued to a unit ("120m", "45m²"); not "3D" or "2nd" (from agent/guide_v1/grounding.py).
UNIT = r"(?:m²|m2|km|cm|mm|min|m|s|%|x)"
NUMBER = re.compile(rf"(?<![\w.])\d+(?:[.,]\d+)?(?={UNIT}?(?!\w))")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
# An id like "proc-campus-dev-001-F0-S014": hyphen-joined parts with a digit somewhere, not "step-by-step".
IDENTIFIER = re.compile(r"\b(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}\b")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)

# ---------- profile safety net: deterministic mobility cues ----------
# Deliberately conservative: a cue must be a statement about the user or the person they guide ("I use a
# wheelchair", "my mother uses a wheelchair"), not a facility name or question ("the wheelchair lift", "is there
# a wheelchair-accessible toilet?"). Negated cues ("I don't use a wheelchair") are ignored. Anything subtler is
# left to the model.
NEGATION = re.compile(r"\b(?:not|no|never|without|nicht|kein\w*)\b|n't\b")
FACILITY = r"(?![\s-]*(?:lifts?|toilets?|wc|bathrooms?|restrooms?|access\w*|ramps?|friendly|spaces?|parking|park|" \
    r"storage|rooms?|users?))"
WHEELCHAIR = re.compile(
    r"\b(?:use[sd]?|using|in|on|push(?:es|ing)?|with|need[s]?|my|her|his|their|our)\s+"
    r"(?:a\s+|an\s+|my\s+|her\s+|his\s+|their\s+|the\s+)?(?:electric\s+|manual\s+|power\s+)?wheel\s?chair"
    + FACILITY + r"|\b(?:i'm|i am|im|is|she's|he's|we're|are)\s+(?:a\s+)?wheel\s?chair\s+users?\b"
    r"|\b(?:im|sitze im|bin im|fahre)\s+rollstuhl\b|\brollstuhlfahrer(?:in)?\b")
PRAM = re.compile(r"\b(?:pram|stroller|buggy|pushchair|baby carriage|kinderwagen)s?\b" + FACILITY)
SCOOTER = re.compile(r"\bmobility scooter\b|\b(?:my|a|on|in)\s+(?:electric\s+)?scooter\b")
TROLLEY = re.compile(
    r"\b(?:push(?:ing)?|pull(?:ing)?|mov(?:e|ing)|wheel(?:ing)?|with|have|got|my|our)\s+"
    r"(?:a\s+|an\s+|the\s+|my\s+|our\s+)?(?:\w+\s+)?(?:trolley|trolly|cart|pallet(?:\s+jack)?|hospital bed|"
    r"hand\s?truck|dolly|rollwagen)s?\b")
VEHICLE = re.compile(r"\b(?:wheel\s?chair|chair|rollstuhl|scooter|pram|stroller|buggy|pushchair|trolley|trolly|cart|"
                     r"pallet|bed|dolly|hand\s?truck)s?\b")
WIDTH_WORD = re.compile(r"\b(?:wide|width|narrow|across|breit)\b")
WIDTH = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(mm|cm|m|metres?|meters?)\b")
NO_STAIRS = re.compile(
    r"\b(?:can't|cannot|can not|unable to|won't|don't|do not|shouldn't|mustn't|not able to)\s+"
    r"(?:use|take|climb|do|manage|walk up|go up)\s+(?:the\s+|any\s+)?(?:stairs|steps|staircases?)\b"
    r"|\bno stairs\b(?!\s+(?:here|in|on|to|between|at)\b)|\bavoid(?:ing)?\s+(?:the\s+|any\s+)?(?:stairs|steps)\b"
    r"|\bneed\s+(?:a\s+)?step[- ]free\b|\bkeine treppen\b")
NO_LIFTS = re.compile(
    r"\b(?:i|we|she|he|they)\s+(?:can't|cannot|won't|will not|don't|do not|never|would rather not|"
    r"prefer not to|am not going to)\s+(?:take|use|ride|get in(?:to)?|go in)\s+(?:the\s+|a\s+|any\s+)?"
    r"(?:lifts?|elevators?)\b|\bavoid(?:ing)?\s+(?:lifts|elevators)\b|\bno lifts\b|\bclaustrophobic\b"
    r"|\bkeine?n? (?:aufzug|aufzüge|fahrstuhl)\b")
CLOSURE_TALK = re.compile(r"\b(?:broken|closed|out of order|out of service|not working|blocked)\b")
RESET = re.compile(
    r"\b(?:not|no longer)\s+(?:in|using|on)\s+(?:the|my|a)\s+(?:wheel\s?)?chair\b|\bout of (?:the|my)\s+"
    r"(?:cast|wheel\s?chair|chair)\b|\b(?:off|done with) (?:the|my) crutches\b|\b(?:reset|clear|forget)\s+"
    r"(?:my\s+|the\s+)?(?:routing\s+)?(?:profile|constraints|preferences|settings)\b|\bi can (?:walk|use the stairs|"
    r"take the stairs|climb stairs)(?: normally)? (?:again|now)\b|\bnicht mehr im rollstuhl\b")
NEGATED_CUES = ("wheelchair", "pram", "scooter", "trolley")
PROFILE_TOOLS = {"find_route", "find_nearest", "tour", "reachable_rooms", "compare_routes", "propose_change"}


SENTENCE_END = r"[.;!?](?=\s|$)"  # not the dot in "0.7 m" or "3.07"


def sentences(text: str) -> list[str]:
    return [part for part in re.split(SENTENCE_END, text.lower().replace("’", "'")) if part.strip()]


def clauses(sentence: str) -> list[str]:
    return [part for part in re.split(r",|\bbut\b", sentence) if part.strip()]


def negated(clause: str, start: int) -> bool:
    """A negation word among the three words before a cue ("I don't use a wheelchair")."""
    return bool(NEGATION.search(" ".join(clause[:start].split()[-3:])))


def cue_width(sentence: str) -> float | None:
    """A width for the user's vehicle: in a sentence that says wide/width/narrow, or within 30 characters after
    the vehicle word ("my trolley is 80 cm wide", "my chair is narrow, 0.7 m"), between 0.4 and 4 m."""
    if WIDTH_WORD.search(sentence):
        candidates = [WIDTH.search(sentence)]
    else:
        candidates = [WIDTH.search(sentence[vehicle.end():vehicle.end() + 30].partition(",")[0])
                      for vehicle in VEHICLE.finditer(sentence)]
    for match in filter(None, candidates):
        value = float(match[1].replace(",", ".")) / {"mm": 1000, "cm": 100}.get(match[2], 1)
        if 0.4 <= value <= 4.0:
            return round(value, 3)
    return None


def profile_cues(text: str) -> dict | None:
    """Mobility cues in one user message → {"cues": [...], "arguments": set_profile arguments}, or None.

    Stricter cues win over a reset in the same message; a width only counts in a sentence that names a vehicle
    (chair, pram, trolley ...) — the clause may end at a comma, so the sentence is checked too."""
    cues: list[str] = []
    arguments: dict = {}
    parts = [(sentence, clause) for sentence in sentences(text) for clause in clauses(sentence)]
    for sentence, clause in parts:
        for name, pattern in (("wheelchair", WHEELCHAIR), ("pram", PRAM), ("scooter", SCOOTER),
                              ("trolley", TROLLEY), ("no_stairs", NO_STAIRS), ("no_lifts", NO_LIFTS),
                              ("reset", RESET)):
            for match in pattern.finditer(clause):
                if (name in NEGATED_CUES or match[0] == "claustrophobic") and negated(clause, match.start()):
                    continue
                if name == "no_lifts" and CLOSURE_TALK.search(sentence):
                    continue  # "I can't take the lift, it's broken" is a closure, not a preference
                if name not in cues:
                    cues.append(name)
    widths = [width for sentence in sentences(text) if VEHICLE.search(sentence)
              for width in [cue_width(sentence)] if width is not None]
    if widths:
        cues.append("width")
        arguments["min_door_width_m"] = widths[0]
    for preset in ("wheelchair", "pram", "trolley"):  # strictest named preset first
        if preset in cues:
            arguments["preset"] = preset
            break
    if "scooter" in cues or "no_stairs" in cues:
        arguments["step_free"] = True  # no scooter width in the data docs: step-free only, the model asks
    if "no_lifts" in cues:
        if "preset" in arguments:
            arguments["avoid_lifts"] = True
        else:
            arguments["preset"] = "no_lifts"
    if "reset" in cues and not set(cues) - {"reset", "no_lifts", "width"}:
        arguments["preset"] = "default"  # "out of the cast, but I won't take lifts" keeps the lift cue
        if "no_lifts" in cues:
            arguments["avoid_lifts"] = True
    return {"cues": cues, "arguments": arguments} if arguments else None


def profile_satisfies(profile: RoutingProfile, arguments: dict) -> bool:
    """Whether the profile already honours what set_profile(**arguments) would set. A preset's assumed value
    (wheelchair door width) is satisfied by any value the model or user chose."""
    preset = arguments.get("preset")
    wanted, assumed = {}, []
    if preset is not None:
        spec = PRESETS[preset]
        wanted = dict(PRESETS["default"]["values"]) if preset == "default" else dict(spec["values"])
        assumed = spec.get("assumed", [])
    wanted.update({name: arguments[name] for name in PROFILE_FIELDS if name in arguments})
    for name, value in wanted.items():
        current = getattr(profile, name)
        if name in assumed and name not in arguments:
            if current is None:
                return False
        elif name == "min_door_width_m" and value is not None and current is not None:
            if abs(current - value) > 1e-9:
                return False
        elif current != value:
            return False
    return True


def confirmation_line(result: dict) -> str:
    if result.get("preset") == "default" and not any(result["profile"][name] for name in PROFILE_FIELDS):
        return "(Noted: no mobility constraints any more; routes may use stairs and lifts again.)"
    line = f"(Noted: {result['summary']}. I'll use that for every route."
    if "min_door_width_m" in result.get("assumed", []) and "min_door_width_m" in result.get("changed", {}):
        line += " Tell me if your doors need to be wider or can be narrower."
    if "min_door_width_m" in result.get("needs", []):
        line += " How wide is it? Then I'll only use doors wide enough."
    return line + ")"


def llm_mode() -> str:
    """The provider GUIDE_LLM names ("openai" or "anthropic"), else the configured one (agent/llm_client.py)
    when its key is set, else "offline" (GUIDE_LLM=offline forces it)."""
    choice = os.environ.get("GUIDE_LLM", "").lower()
    if choice in llm_client.PROVIDERS:
        return choice
    return llm_client.provider() if choice != "offline" and llm_client.has_key() else "offline"


def make_client() -> object:
    """The provider's client (llm_client.make) in a live mode, else the offline rule-based client."""
    if (mode := llm_mode()) != "offline":
        return llm_client.make(name=mode)
    from agent.offline_llm import OfflineClient

    return OfflineClient()


def overview_text(session: BuildingSession) -> str:
    """The static building overview (no profile or closures — those change during the conversation)."""
    return json.dumps(session.building.overview(), ensure_ascii=False, separators=(",", ":"))


RESTRICTED_NOTE = """

Access: some areas of this building are restricted for this user and are not in your tools. When a tool answers \
"restricted", tell the user that area is restricted for them, give no detail about it, and offer a public place \
instead."""


def system_blocks(session: BuildingSession) -> list[dict]:
    note = RESTRICTED_NOTE if session.restricted_names else ""  # access mode only (backend/access.py)
    if session.preferences_enabled and session.guide_preferences:  # remembered by the app (access mode only)
        wishes = ", ".join(f"{name.replace('_', ' ')}: {value}" for name, value in session.guide_preferences.items())
        note += f"\n\nThe user's remembered preferences for how you talk: {wishes}. Follow them."
    return [
        {"type": "text", "text": INSTRUCTIONS},
        {"type": "text", "text": "Building overview:\n" + overview_text(session) + note,
         "cache_control": {"type": "ephemeral"}},
    ]


def ungrounded(text: str, corpus: str) -> list[str]:
    """Numbers and ids in `text` that appear nowhere in `corpus` (tool results, overview, user messages).

    A number counts as grounded when some corpus number rounds to it at the same precision ("about 124 m" for
    124.24), or when it is the length of a list in a JSON tool result ("I found 2 options"). Numbered-list markers
    and clock times are ignored; digits inside ids are checked as part of the id."""
    missing = [token for token in dict.fromkeys(IDENTIFIER.findall(text)) if token not in corpus]
    scrubbed = TIME.sub(" ", LIST_MARKER.sub(" ", IDENTIFIER.sub(" ", text)))
    known = [float(token.replace(",", ".")) for token in NUMBER.findall(IDENTIFIER.sub(" ", corpus))]
    known += list_lengths(corpus)
    for token in dict.fromkeys(NUMBER.findall(scrubbed)):
        value = float(token.replace(",", "."))
        decimals = len(token.replace(",", ".").partition(".")[2])
        if not any(half_up(number, decimals) == value for number in known):
            missing.append(token)
    return missing


def half_up(number: float, decimals: int) -> float:
    """round() rounds halves to even (42.5 → 42); people say 43."""
    return float(Decimal(repr(number)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP))


def list_lengths(corpus: str) -> list[float]:
    """Lengths of the lists of records or names inside the corpus lines that are JSON (tool results)."""
    lengths: list[float] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            if value and all(isinstance(item, (dict, str)) for item in value):
                lengths.append(float(len(value)))
            for item in value:
                walk(item)

    for line in corpus.splitlines():
        if line.startswith(("{", "[")):
            try:
                walk(json.loads(line))
            except ValueError:
                continue
    return lengths


@dataclass
class GuideTurn:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # {"name", "input", "result"}
    events: list[dict] = field(default_factory=list)  # UI events emitted during this turn
    ungrounded: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    spoken: str | None = None  # voice turns: the reply made speakable (agent/speech.py)
    auto_profile: dict | None = None  # {"cues", "arguments", "result"} when the safety net set the profile
    rewritten: str | None = None  # voice turns: the transcript normalised to the building's names (D-013)


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    fast_requests: int = 0


class Guide:
    def __init__(self, session: BuildingSession, client: object | None = None, model: str | None = None,
                 effort: str | None = None) -> None:
        self.session = session
        self.client = client if client is not None else make_client()
        self.model = model or os.environ.get("GUIDE_MODEL", DEFAULT_MODEL)
        self.effort = effort or os.environ.get("GUIDE_EFFORT", DEFAULT_EFFORT)
        self.fast = (os.environ.get("GUIDE_SPEED", "fast").lower() == "fast" and self.model in FAST_MODELS
                     and isinstance(self.client, anthropic.Anthropic))  # fast mode is Claude-only
        self.system = system_blocks(session)
        self.messages: list[dict] = []
        self.corpus: list[str] = [overview_text(session)]
        self.turn = 0
        self.proposed_in_turn: dict[str, int] = {}
        self.usage = Usage()
        self.profile_note: str | None = None  # tells the model next turn what the safety net set
        self.location_note: str | None = None  # where the app's "you are here" figure stands, sent with the next turn
        # Voice transcripts are normalised first (D-013), only when talking to a real API.
        self.rewriter: TranscriptRewriter | None = (
            TranscriptRewriter(session.building, client=self.client) if llm_client.live(self.client)
            and os.environ.get("GUIDE_REWRITER", "on").lower() != "off" else None)
        self.on_step: Callable[[dict], None] | None = None  # live progress for the UI (backend /chat/stream)
        # voice turns: each sentence the moment it may be said (agent/speech.py SpokenStream; backend /chat/stream)
        self.on_say: Callable[[str], None] | None = None
        self.speech: SpokenStream | None = None

    def reply(self, text: str, channel: str = "text", photo: dict | None = None, heard: bool = True,
              selected: str | None = None, route_step: int | None = None) -> GuideTurn:
        """One user turn. channel="voice" asks for a spoken style and fills `GuideTurn.spoken`; `heard=False` marks
        a voice turn whose text was tapped, not transcribed, so it skips the transcript rewrite. `selected`: the
        space or asset id tapped on the app's plan while asking, so "this room" / "there" resolve to it.
        `route_step`: the step (0-based) the app's step card shows while a route is on the map. `photo`
        ({"media_type", "data": base64}) is shown to the model for this turn only, then dropped from the history."""
        if channel not in CHANNELS:
            raise ValueError(f"channel must be one of {CHANNELS}")
        if photo is not None and photo.get("media_type") not in PHOTO_TYPES:
            raise ValueError(f"photo media_type must be one of {PHOTO_TYPES}")
        self.turn += 1
        self.corpus.append(text)
        rewritten = self.rewriter.rewrite(text) if channel == "voice" and heard and self.rewriter is not None else text
        said = text
        if rewritten != text:  # the model sees both: a nuance the rewrite dropped stays visible
            self.corpus.append(rewritten)
            said = f"{rewritten}\n\n[speech transcript as heard: {text}]"
        note, self.profile_note = self.profile_note, None
        where, self.location_note = self.location_note, None
        picked = self.selection_note(selected)
        on_route = self.route_note(route_step)
        note = "\n\n".join(part for part in (where, picked, on_route, note) if part)
        content = f"{note}\n\n{said}" if note else said
        system_role = self.model.startswith(SYSTEM_MESSAGE_MODELS)
        if channel == "voice" and not system_role:
            content = f"{VOICE_STYLE}\n\n{content}"
        if photo is not None:
            content = [{"type": "image", "source": {"type": "base64", "media_type": photo["media_type"],
                                                    "data": photo["data"]}},
                       {"type": "text", "text": f"{PHOTO_NOTE}\n\n{content}"}]
        photo_at = len(self.messages)
        self.messages.append({"role": "user", "content": content})
        if channel == "voice" and system_role:
            self.messages.append({"role": "system", "content": VOICE_STYLE})
        first_event = len(self.session.events)
        self.speech = self.spoken_stream(text) if channel == "voice" else None
        try:
            turn = self.run()
        finally:
            if photo is not None:  # one turn only: never resent, never persisted
                self.messages[photo_at] = {"role": "user", "content": f"{PHOTO_KEPT}\n\n{content[1]['text']}"}
        auto = self.profile_safety_net(text)
        if auto is not None:
            routed = any(call["name"] in PROFILE_TOOLS for call in turn.tool_calls)
            if routed and turn.stop_reason == "end_turn":
                self.step({"kind": "check", "name": "profile"})
                self.messages.append({"role": "user", "content": (
                    f"[profile check, not from the user] From the user's words I set their routing profile to: "
                    f"{auto['result']['summary']}. Redo any route or reachability in your reply under this profile "
                    "and give the user your full reply again.")})
                self.hold_speech()
                redone = self.run()
                redone.tool_calls = turn.tool_calls + redone.tool_calls
                turn = redone
            else:
                self.profile_note = (f"[profile note, not from the user] After your last reply I set the user's "
                                     f"routing profile to: {auto['result']['summary']}.")
        missing = ungrounded(turn.text, "\n".join(self.corpus))
        if missing and turn.stop_reason == "end_turn":
            self.step({"kind": "check", "name": "grounding"})
            self.messages.append({"role": "user", "content": (
                "[grounding check, not from the user] Your last reply states "
                + ", ".join(missing)
                + ", which appear in no tool result. Check them with a tool, or leave them out, and give the "
                "user your full reply again.")})
            self.hold_speech()
            repaired = self.run()
            repaired.tool_calls = turn.tool_calls + repaired.tool_calls
            turn = repaired
        if auto is not None:
            turn.auto_profile = auto
            turn.tool_calls.append({"name": "set_profile", "input": auto["arguments"], "result": auto["result"],
                                    "auto": True})
            turn.text = f"{turn.text}\n\n{confirmation_line(auto['result'])}".strip()
        turn.ungrounded = ungrounded(turn.text, "\n".join(self.corpus))
        turn.events = self.session.events[first_event:]
        turn.rewritten = rewritten if rewritten != text else None
        if channel == "voice":
            turn.spoken = speakable(turn.text)
        if self.speech is not None:
            self.speech.finish(turn.text)  # what of the final reply was not said live
            self.speech = None
        return turn

    def set_location(self, space_id: str | None, point: list[float] | None = None) -> dict | None:
        """The user put the app's "you are here" figure down (or took it away): the session resolves "here" to
        that space, and the next turn tells the model, so it routes from there without asking. Moved within the
        same room, only the point changes (no new note)."""
        same_room = space_id is not None and (self.session.user_location or {}).get("space_id") == space_id
        location = self.session.set_location(space_id, point)
        if same_room and point is not None:
            return location
        if location is None:
            self.location_note = "[location note, from the app] The user removed their position; ask if you need it."
        else:
            ref = f" ({location['ref']})" if location.get("ref") else ""
            self.location_note = (f"[location note, from the app] The user is in {location['name']}{ref} on the "
                                  f"{location['floor']}. Use \"here\" as the start; don't ask where they are.")
        self.corpus.append(self.location_note)
        return location

    def selection_note(self, item_id: str | None) -> str | None:
        """What the user has tapped on the plan, for this turn (unknown ids are ignored)."""
        building = self.session.building
        if item_id in building.spaces:
            space = building.spaces[item_id]
            ref = f" ({space['ref']})" if space.get("ref") else ""
            what = f"the room {space['name']}{ref} on the {building.floor_name(space['floor_id'])}"
        elif item_id in building.assets:
            asset = building.assets[item_id]
            room = building.spaces[asset["space_id"]]
            what = f"{asset['name']} in {room['name']} on the {building.floor_name(room['floor_id'])}"
        else:
            return None
        note = (f"[selection note, from the app] The user has {what} selected on the map (id {item_id}). Words like "
                "\"this\", \"it\" or \"there\" mean it.")
        self.corpus.append(note)
        return note

    def route_note(self, index: int | None) -> str | None:
        """Where the user is on the route on the map, for this turn, with the app's step card (its numbering
        differs from find_route's steps, which add a start line); None when no route is shown."""
        steps = self.session.route_card() if index is not None else []
        if not 0 <= (index or 0) < len(steps):
            return None
        listed = " ".join(f"{number}. {step['text']}" for number, step in enumerate(steps, 1))
        note = (f"[route note, from the app] The route is on the user's map and its step card shows step "
                f"{index + 1} of {len(steps)}, where the user is. The card's steps: {listed}")
        self.corpus.append(note)
        return note

    def spoken_stream(self, text: str) -> SpokenStream | None:
        """A voice turn with a listener (`on_say`): the reply is said while the model writes it, each sentence
        once it passes the grounding check."""
        if self.on_say is None:
            return None
        speech = SpokenStream(self.on_say, lambda sentence: not ungrounded(sentence, "\n".join(self.corpus)))
        found = profile_cues(text)
        if found is not None and not profile_satisfies(self.session.profile, found["arguments"]):
            speech.hold()  # the safety net may redo this reply under a new profile: say only the final one
        return speech

    def hold_speech(self) -> None:
        """A redo is coming: stop saying the reply live; `finish` says what the final reply adds."""
        if self.speech is not None:
            self.speech.hold()

    def profile_safety_net(self, text: str) -> dict | None:
        """Apply a mobility cue from the user's message that the model's turn left unhonoured."""
        found = profile_cues(text)
        if found is None or profile_satisfies(self.session.profile, found["arguments"]):
            return None
        arguments = dict(found["arguments"])
        preset = arguments.get("preset")
        current = self.session.profile.min_door_width_m
        if preset in PRESETS and "min_door_width_m" in PRESETS[preset].get("assumed", []) \
                and current is not None and "min_door_width_m" not in arguments:
            arguments["min_door_width_m"] = current  # keep a width the model already chose
        result = self.session.call("set_profile", arguments)
        if "error" in result:
            return None
        self.corpus.append(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return {"cues": found["cues"], "arguments": arguments, "result": result}

    def run(self) -> GuideTurn:
        """Request → run every tool_use → send all results back, until the model ends its turn."""
        calls: list[dict] = []
        said: list[str] = []  # text from every round, including any written before tool calls
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.request()
            content = llm_client.kept_content(response)
            self.messages.append({"role": "assistant", "content": content})
            if response.stop_reason == "refusal":
                return GuideTurn("Sorry, I can't help with that one.", calls, stop_reason="refusal")
            said += [block.text.strip() for block in response.content if block.type == "text" and block.text.strip()]
            if response.stop_reason == "pause_turn":
                continue
            uses = [block for block in content if getattr(block, "type", None) == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                if response.stop_reason == "max_tokens":
                    said.append("(My answer was cut off — ask me to continue.)")
                return GuideTurn("\n\n".join(said), calls, stop_reason=response.stop_reason)
            results = []
            for use in uses:
                self.step({"kind": "tool", "name": use.name, "input": dict(use.input or {})})
                result = self.execute(use.name, dict(use.input or {}))
                self.step({"kind": "tool_done", "name": use.name, "ok": "error" not in result})
                calls.append({"name": use.name, "input": dict(use.input or {}), "result": result})
                content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                self.corpus.append(content)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content,
                                **({"is_error": True} if "error" in result else {})})
            self.messages.append({"role": "user", "content": results})
        return GuideTurn("I couldn't finish that in a reasonable number of steps. Could you narrow it down?",
                         calls, stop_reason="max_tool_rounds")

    def step(self, step: dict) -> None:
        if self.on_step is not None:
            self.on_step(step)

    def execute(self, name: str, arguments: dict) -> dict:
        if name == "apply_change" and self.proposed_in_turn.get(arguments.get("change_id", "")) == self.turn:
            return {"error": "This change was proposed in the current turn. Show the user its summary and effect, "
                             "and apply it only after they confirm."}
        result = self.session.call(name, arguments)
        if name == "propose_change" and "change_id" in result:
            self.proposed_in_turn[result["change_id"]] = self.turn
        return result

    def request(self) -> object:
        params = dict(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=self.session.tool_definitions(),
            messages=self.messages,
            cache_control={"type": "ephemeral"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if self.fast:
            try:
                response = self.send({**params, "speed": "fast", "betas": [FALLBACK_BETA, FAST_BETA]})
            except anthropic.RateLimitError:  # fast mode's own limit: this request at standard speed
                response = self.send(params)
        else:
            response = self.send(params)
        self.track(response.usage)
        return response

    def send(self, params: dict) -> object:
        if self.speech is not None and llm_client.live(self.client):
            response = self.streamed(params)
        else:
            response = self.client.beta.messages.create(**params)
            if self.speech is not None:  # offline and test clients don't stream: each text block at once
                for block in response.content:
                    if block.type == "text":
                        self.speech.feed(block.text)
                        self.speech.end_block()
        return response

    def streamed(self, params: dict) -> object:
        """The same request, streamed: its text goes to the spoken stream as the model writes it."""
        with self.client.beta.messages.stream(**params) as stream:
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    self.speech.feed(event.delta.text)
                elif event.type == "content_block_stop":
                    self.speech.end_block()
            return stream.get_final_message()

    def track(self, usage: object) -> None:
        self.usage.requests += 1
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cache_read_input_tokens += usage.cache_read_input_tokens or 0
        self.usage.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0
        self.usage.fast_requests += getattr(usage, "speed", None) == "fast"
