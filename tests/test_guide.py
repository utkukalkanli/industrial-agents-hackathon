"""The Building Guide loop, offline: a scripted fake Claude plays a tricky-user conversation.

Each scripted step reads the request it is answering (the tool results the Guide just sent) and replies the way a
good model would, quoting only numbers it was given. The tests check what the Guide does around the model: tool
dispatch, the remembered profile, propose → confirm → apply (enforced in code), the D-003 grounding check, the
cached system prompt and the append-only history."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from agent.guide import Guide, ungrounded
from agent.offline_llm import OfflineClient, message, text_block, tool_use
from agent.tools import TOOL_DEFINITIONS, BuildingSession

BUILDING = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"
LIFT_1 = "proc-campus-train-000-V02"
LIFT_2 = "proc-campus-train-000-V04"

Step = Callable[[dict], object]


class ScriptedClient:
    """Fake Anthropic client: `beta.messages.create` answers with the next scripted step."""

    def __init__(self, steps: list[Step]) -> None:
        self.steps = list(steps)
        self.requests: list[dict] = []
        self.beta = self
        self.messages = self

    def create(self, **request: object) -> object:
        snapshot = {**request, "messages": copy.copy(request["messages"])}
        self.requests.append(snapshot)
        assert self.steps, "the Guide made more requests than scripted"
        return self.steps.pop(0)(snapshot)


def results(request: dict) -> list[dict]:
    """The tool results the Guide sent in this request, parsed."""
    return [json.loads(block["content"]) for block in request["messages"][-1]["content"]]


def say(text: str) -> Step:
    return lambda request: message(text_block(text))


def call(*uses: tuple[str, dict]) -> Step:
    return lambda request: message(*(tool_use(name, arguments) for name, arguments in uses))


@pytest.fixture
def session() -> BuildingSession:
    return BuildingSession.load(BUILDING)


def run(session: BuildingSession, script: list[Step]) -> tuple[Guide, ScriptedClient]:
    client = ScriptedClient(script)
    return Guide(session, client=client), client


# ---------- the tricky user ----------


def ask_which_printer(request: dict) -> object:
    hits = results(request)[0]["assets"]
    options = ", ".join(f"{hit['space_name']} (level {hit['floor_level']})" for hit in hits[:3])
    return message(text_block(f"There are {len(hits)} printers. Nearest options: {options}. Which floor are you on?"))


def name_the_nearest_meeting_room(request: dict) -> object:
    route = results(request)[0]
    return message(text_block(f"Taking you to the nearest one, {route['steps'][-1]}, about {route['about_m']} m."))


def give_directions(request: dict) -> object:
    route = results(request)[0]
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(route["steps"][1:], 1))
    return message(text_block(
        f"Main lobby → Meeting room 3.07, {route['profile']}, about {round(route['length_m'])} m:\n{steps}"))


def propose_and_try_to_apply_at_once(request: dict) -> object:
    change_id = results(request)[0]["change_id"]
    return message(tool_use("apply_change", {"change_id": change_id}))


def ask_to_confirm(request: dict) -> object:
    refused = results(request)[0]
    assert "confirm" in refused["error"]
    proposed = next(block for block in request["messages"] if block["role"] == "user"
                    and not isinstance(block["content"], str) and "change_id" in block["content"][0]["content"])
    effect = json.loads(proposed["content"][0]["content"])["effect"]
    return message(text_block(
        f"I understood: close Lift 1. Your route goes from {round(effect['before_m'])} m to "
        f"{round(effect['after_m'])} m via the other lift. Shall I apply it?"))


def apply_pending(request: dict) -> object:
    return message(tool_use("apply_change", {"change_id": "C1"}))


def reroute_and_compare(request: dict) -> object:
    return message(text_block("Done, Lift 1 is marked closed. Checking your route again."),
                   tool_use("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"}),
                   tool_use("compare_routes", {"change_id": "C1"}))


def explain_new_route(request: dict) -> object:
    route, comparison = results(request)
    return message(text_block(
        f"New route, about {round(route['length_m'])} m, {comparison['last_route']['extra_m']} m longer, via "
        f"Lift 2. {comparison['longer_routes_count']} rooms are now a longer walk; "
        f"{comparison['lost_access_count']} lost access."))


TRICKY_USER = [
    ("Where's the printer?", [call(("locate", {"query": "printer"})), ask_which_printer]),
    ("I use a wheelchair.", [call(("set_profile", {"preset": "wheelchair"})),
                              say("Got it: step-free routes, and I assumed doors of at least 0.8 m.")]),
    ("Take me from the main lobby to the meeting room.", [
        call(("find_route", {"start": "Main lobby", "destination": "Meeting room"})),
        name_the_nearest_meeting_room,
    ]),
    ("3.07 please", [call(("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})),
                     give_directions]),
    ("The lift is broken!", [call(("propose_change", {"action": "close", "targets": ["Lift 1"]})),
                             propose_and_try_to_apply_at_once, ask_to_confirm]),
    ("Yes, go ahead.", [apply_pending, reroute_and_compare, explain_new_route]),
]


def test_tricky_user_conversation(session):
    guide, client = run(session, [step for _, steps in TRICKY_USER for step in steps])
    turns, state = {}, {}
    for text, _ in TRICKY_USER:
        turns[text] = guide.reply(text)
        state[text] = (set(session.pending), set(session.building.closed), len(session.applied))
    assert not client.steps
    for text, turn in turns.items():
        assert turn.ungrounded == [], (text, turn.text, turn.ungrounded)
        assert turn.stop_reason == "end_turn"

    printer = turns["Where's the printer?"]
    assert [c["name"] for c in printer.tool_calls] == ["locate"]
    assert printer.text.count("Print room") == 3  # ≤ 3 options although there are 4 printers

    assert session.profile.step_free
    wheelchair = turns["I use a wheelchair."]
    assert wheelchair.tool_calls[0]["result"]["summary"] == "step-free, doors at least 0.8 m wide (assumed)"
    assert wheelchair.auto_profile is None and len(wheelchair.tool_calls) == 1  # the model did it: no safety net

    vague = turns["Take me from the main lobby to the meeting room."]
    nearest = vague.tool_calls[0]["result"]  # several meeting rooms: the nearest, no question (D-012)
    assert nearest["reachable"] and len(nearest["chosen"]["others"]) == 2
    assert all(other["length_m"] >= nearest["length_m"] for other in nearest["chosen"]["others"])
    assert "?" not in vague.text and [event for event in vague.events if event["type"] == "route"]

    directions = turns["3.07 please"]
    route = directions.tool_calls[0]["result"]
    assert route["step_free"] and route["length_m"] == 61.24 and LIFT_1 in route["element_path"]
    assert "set_profile" not in [c["name"] for c in directions.tool_calls]  # profile remembered, not re-asked
    assert "\n1. " in directions.text and "about 61 m" in directions.text
    assert directions.events[-1] == {"type": "route", "space_path": route["space_path"],
                                     "element_path": route["element_path"], "length_m": 61.24,
                                     "profile": "step-free, doors at least 0.8 m wide (assumed)"}

    broken = turns["The lift is broken!"]
    assert [c["name"] for c in broken.tool_calls] == ["propose_change", "apply_change"]
    assert "error" in broken.tool_calls[1]["result"]  # same-turn apply refused by the Guide
    assert state["The lift is broken!"] == ({"C1"}, set(), 0)  # pending, nothing closed, nothing applied
    assert "Shall I apply" in broken.text

    confirmed = turns["Yes, go ahead."]
    assert [c["name"] for c in confirmed.tool_calls] == ["apply_change", "find_route", "compare_routes"]
    assert state["Yes, go ahead."] == (set(), {LIFT_1}, 1)
    assert [change.summary for change in session.applied] == ["close Lift 1"]
    after = confirmed.tool_calls[1]["result"]
    assert after["length_m"] == 96.46 and LIFT_1 not in after["element_path"] and LIFT_2 in after["element_path"]
    comparison = confirmed.tool_calls[2]["result"]
    assert comparison["status"] == "applied" and comparison["lost_access_count"] == 0
    assert comparison["last_route"]["extra_m"] == 35.22 and "35.22 m longer" in confirmed.text
    assert confirmed.text.startswith("Done, Lift 1 is marked closed.")  # text written before the tool calls
    assert [event["type"] for event in confirmed.events] == ["change", "route"]


def test_requests_cache_the_overview_and_only_append(session, monkeypatch):
    monkeypatch.setenv("GUIDE_MODEL", "claude-sonnet-5-5")
    guide, client = run(session, [step for _, steps in TRICKY_USER for step in steps])
    for text, _ in TRICKY_USER:
        guide.reply(text)
    first = client.requests[0]
    assert first["model"] == "claude-sonnet-5-5"
    assert first["tools"] == TOOL_DEFINITIONS
    assert first["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "Forschungsbau 024" in first["system"][-1]["text"]
    assert all(request["system"] == first["system"] for request in client.requests)  # stable cached prefix
    for earlier, later in zip(client.requests, client.requests[1:]):
        assert later["messages"][: len(earlier["messages"])] == earlier["messages"]  # append-only history
    for request in client.requests:  # every tool_use is answered in the very next message, all at once
        for index, item in enumerate(request["messages"][:-1]):
            if item["role"] == "assistant":
                uses = {block.id for block in item["content"] if block.type == "tool_use"}
                answered = request["messages"][index + 1]["content"]
                if uses:
                    assert {block["tool_use_id"] for block in answered} == uses


# ---------- D-003 grounding ----------


def test_invented_number_triggers_one_repair(session):
    guide, client = run(session, [
        call(("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})),
        say("It's about 437 m, roughly 2 minutes."),
        lambda request: message(text_block(
            f"It's about {round(results_from_history(request)['length_m'])} m.")),
    ])
    turn = guide.reply("How far is meeting room 3.07 from the main lobby?")
    assert "grounding check" in client.requests[-1]["messages"][-1]["content"]
    assert "437" in client.requests[-1]["messages"][-1]["content"]
    assert turn.text == "It's about 58 m." and turn.ungrounded == []  # 57.68 m without a profile
    assert [c["name"] for c in turn.tool_calls] == ["find_route"]


def results_from_history(request: dict) -> dict:
    return next(json.loads(item["content"][0]["content"]) for item in reversed(request["messages"])
                if item["role"] == "user" and not isinstance(item["content"], str))


def test_still_ungrounded_after_repair_is_reported(session):
    guide, client = run(session, [say("Room proc-campus-train-000-F9-S999 is 42 m away."),
                                  say("Room proc-campus-train-000-F9-S999 is 42 m away.")])
    turn = guide.reply("Where is the server room?")
    assert len(client.requests) == 2
    assert turn.ungrounded == ["proc-campus-train-000-F9-S999", "42"]


def test_ungrounded_rules():
    corpus = '{"length_m":124.24,"name":"Meeting room 3.07","id":"x-F3-S007"} user: my trolley is 80 cm'
    assert ungrounded("About 124 m to Meeting room 3.07 (x-F3-S007).", corpus) == []
    assert ungrounded("1. Go.\n2. Turn.\n3. Arrive, 124.2 m.", corpus) == []  # list markers, rounding
    assert ungrounded("Your 80 cm trolley fits.", corpus) == []  # the user's own numbers
    assert ungrounded("About 125 m, 3.4 km, id x-F3-S008.", corpus) == ["x-F3-S008", "125", "3.4"]
    assert ungrounded("Say start for the step-by-step guide, door-to-door.", corpus) == []  # words, not ids


# ---------- loop edges ----------


def test_refusal_and_tool_errors(session):
    guide, _ = run(session, [call(("room_facts", {"space": "Room 9.99"})),
                             lambda request: message(text_block("No room 9.99 here."))])
    turn = guide.reply("Tell me about room 9.99")
    assert "error" in turn.tool_calls[0]["result"]
    assert guide.messages[2]["content"][0]["is_error"] is True
    guide, _ = run(session, [lambda request: message(stop_reason="refusal")])
    assert guide.reply("...").stop_reason == "refusal"


def test_offline_client_runs_the_same_conversation(session):
    guide = Guide(session, client=OfflineClient())
    assert "Which one" in guide.reply("Where is the printer?").text
    assert "step-free" in guide.reply("I use a wheelchair").text and session.profile.step_free
    assert "About 60 m" in guide.reply("from Main lobby to Meeting room 3.07").text
    assert "Shall I apply" in guide.reply("Lift 1 is broken").text and not session.applied
    turn = guide.reply("yes")
    assert session.applied and "About 95 m" in turn.text and turn.ungrounded == []


class FastProbeClient(anthropic.Anthropic):
    """A real Anthropic client type (so the Guide may ask for fast mode) whose requests never leave the test:
    `limited` fast requests raise a 429, every request is recorded and answered with one text block."""

    def __init__(self, limited: int = 0) -> None:
        super().__init__(api_key="test")
        self.calls: list[dict] = []
        self.limited = limited
        probe = self

        class Messages:
            def create(self, **params):
                probe.calls.append(params)
                if params.get("speed") == "fast" and probe.limited:
                    probe.limited -= 1
                    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
                    raise anthropic.RateLimitError("fast limit", response=httpx2.Response(429, request=request),
                                                   body=None)
                reply = message(text_block("Hello."))
                reply.usage.speed = params.get("speed", "standard")
                return reply

        self._probe_messages = Messages()

    @property
    def beta(self):
        return SimpleNamespace(messages=self._probe_messages)


def test_guide_asks_for_fast_mode_and_falls_back_to_standard_on_its_rate_limit(monkeypatch):
    monkeypatch.delenv("GUIDE_SPEED", raising=False)
    client = FastProbeClient(limited=1)
    guide = Guide(BuildingSession.load(BUILDING), client=client)
    guide.reply("Hello")
    assert [call.get("speed") for call in client.calls] == ["fast", None]
    assert "fast-mode-2026-02-01" in client.calls[0]["betas"] and "fast-mode-2026-02-01" not in client.calls[1]["betas"]
    guide.reply("Hello again")
    assert client.calls[-1]["speed"] == "fast" and guide.usage.fast_requests == 1


def test_guide_speed_standard_turns_fast_mode_off(monkeypatch):
    monkeypatch.setenv("GUIDE_SPEED", "standard")
    client = FastProbeClient()
    Guide(BuildingSession.load(BUILDING), client=client).reply("Hello")
    assert "speed" not in client.calls[0]


def test_a_reply_cut_off_mid_tool_call_leaves_no_dangling_call(session):
    """A tool call cut off by the token limit is neither run nor kept: the next request must stay valid (every
    tool_use answered by a tool_result, no empty assistant message)."""
    def cut(request: dict) -> object:
        return message(tool_use("locate", {"query": "prin"}), stop_reason="max_tokens")

    guide, client = run(session, [cut, say("Hello again.")])
    assert "cut off" in guide.reply("Where is the printer?").text
    guide.reply("Hi")
    history = client.requests[1]["messages"]
    assistant = [message for message in history if message["role"] == "assistant"]
    blocks = [block for message in assistant for block in message["content"]]
    assert assistant and all(message["content"] for message in assistant)
    assert not [block for block in blocks if getattr(block, "type", None) == "tool_use"]
