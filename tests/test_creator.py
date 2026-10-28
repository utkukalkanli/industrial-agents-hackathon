"""agent/creator.py: the Creator's tool loop over a scripted client (no API calls)."""

import json

from agent.creator import Creator
from agent.creator_tools import ImportSession
from agent.offline_llm import message, text_block, tool_use
from core.plan_import.ingest import load_sources
from tests.plan_fixtures import FIXTURE_LABELS, TWO_ROOMS_AND_CORRIDOR, draw_plan, to_png


class ScriptedClient:
    """Returns the given responses in order and records every request's messages."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.requests: list[list] = []
        self.beta = self
        self.messages = self

    def create(self, **request) -> object:
        self.requests.append(json.loads(json.dumps(request["messages"], default=lambda block: block.model_dump()
                                                   if hasattr(block, "model_dump") else str(block))))
        if not self.responses:
            return message(tool_use("list_sources", {}))
        return self.responses.pop(0)


def plan_session() -> ImportSession:
    sources, warnings = load_sources([("plan.png", to_png(draw_plan(*TWO_ROOMS_AND_CORRIDOR)))])
    return ImportSession(sources, warnings)


SCRIPT = [
    message(text_block("Looking at the files."), tool_use("list_sources", {})),
    message(text_block("s1 is a ground floor plan."),
            tool_use("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", "bbox": [0, 0, 1, 1],
                                       "photo": False})),
    message(tool_use("label_cells", {"level": 0, "cells": FIXTURE_LABELS, "entrances": [3]})),
    message(text_block("Building it."), tool_use("finish", {"name": "Fixture house"})),
]


def run(session, script):
    steps = []
    creator = Creator(session, client=ScriptedClient(script))
    creator.on_step = steps.append
    return creator, creator.run(), steps


def test_scripted_import_finishes():
    _, result, steps = run(plan_session(), SCRIPT)
    assert result.status == "done" and result.building["building"]["name"] == "Fixture house"
    assert len(result.building["spaces"]) == 3
    assert steps[0] == {"kind": "say", "text": "Looking at the files."}
    assert {"kind": "tool", "name": "register_plan", "level": 0} in steps
    assert {"kind": "tool_done", "name": "finish", "ok": True} in steps


def test_no_plan_ends_without_building():  # Review Focus 1
    script = [message(tool_use("list_sources", {})), message(tool_use("no_plan", {"reason": "only project text"}))]
    _, result, _ = run(plan_session(), script)
    assert result.status == "no_plan" and result.building is None and result.reason == "only project text"


def images_per_request(creator) -> list[int]:
    return [sum(part.get("type") == "image" for turn in request if turn["role"] == "user"
                and isinstance(turn["content"], list) for block in turn["content"] if block.get("type") == "tool_result"
                and isinstance(block.get("content"), list) for part in block["content"])
            for request in creator.client.requests]


def test_images_are_kept_so_the_cached_prefix_stays_the_same():
    script = [message(tool_use("view_source", {"source_id": "s1"})) for _ in range(8)]
    script.append(message(tool_use("no_plan", {"reason": "x"})))
    creator, _, _ = run(plan_session(), script)
    assert images_per_request(creator) == list(range(9))  # nothing dropped: every request extends the last one
    first, second = creator.client.requests[3], creator.client.requests[4]
    assert second[:len(first)] == first


def test_past_the_limit_old_images_are_dropped_in_one_go(monkeypatch):
    import agent.creator as module

    monkeypatch.setattr(module, "MAX_IMAGES", 6)
    monkeypatch.setattr(module, "KEEP_IMAGES", 2)
    script = [message(tool_use("view_source", {"source_id": "s1"})) for _ in range(8)]
    script.append(message(tool_use("no_plan", {"reason": "x"})))
    creator, _, _ = run(plan_session(), script)
    assert images_per_request(creator) == [0, 1, 2, 3, 4, 5, 6, 2, 3]  # one cut, then the prefix grows again


def test_stops_after_max_rounds():
    creator = Creator(plan_session(), client=ScriptedClient([]))
    creator.max_rounds = 3
    result = creator.run()
    assert result.status == "failed" and "steps" in result.reason


def test_stopping_without_finish_is_nudged_once_then_fails():
    script = [message(text_block("I think I'm done.")), message(text_block("Really done."))]
    creator, result, _ = run(plan_session(), script)
    assert result.status == "failed"
    assert "finish" in json.dumps(creator.client.requests[1][-1])


def test_without_a_key_it_says_so(monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    result = Creator(plan_session()).run()
    assert result.status == "failed" and "OPENAI_API_KEY" in result.reason
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert "ANTHROPIC_API_KEY" in Creator(plan_session()).run().reason


def test_an_api_error_ends_the_import_with_its_message():
    import anthropic
    import httpx2

    class Broke(ScriptedClient):
        def create(self, **request):
            response = httpx2.Response(400, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
            raise anthropic.BadRequestError("Your credit balance is too low", response=response, body=None)

    result = Creator(plan_session(), client=Broke([])).run()
    assert result.status == "failed" and "credit balance is too low" in result.reason


def test_a_cancelled_import_stops_before_the_next_request():
    script = [message(tool_use("list_sources", {})) for _ in range(5)]
    creator = Creator(plan_session(), client=ScriptedClient(script))
    creator.on_step = lambda step: creator.cancel.set() if step["kind"] == "tool_done" else None
    result = creator.run()
    assert result.status == "cancelled" and len(creator.client.requests) == 1


def test_a_tool_call_cut_off_by_the_token_limit_is_not_run():
    cut = message(tool_use("finish", {"name": "Half"}), stop_reason="max_tokens")
    client = ScriptedClient([cut, *SCRIPT])
    steps: list[dict] = []
    creator = Creator(plan_session(), client=client)
    creator.on_step = steps.append
    creator.run()
    assert {"kind": "tool", "name": "finish"} != steps[0]
    assert not [block for block in client.requests[1][1]["content"] if block.get("type") == "tool_use"]
