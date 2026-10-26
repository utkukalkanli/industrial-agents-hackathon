"""The HTTP backend in offline mode (GUIDE_LLM=offline): sessions, chat, event cursor, OpenAI-compatible SSE."""

import json
import math

import pytest
from fastapi.testclient import TestClient

from backend.app import app, store

BUILDING = "train/proc-campus-train-000"
ROUTE = "from Main lobby to Meeting room 3.07"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    return TestClient(app)


def new_session(client: TestClient) -> str:
    response = client.post("/sessions", json={"building": BUILDING})
    assert response.status_code == 200
    return response.json()["session_id"]


def say(client: TestClient, session_id: str, message: str) -> dict:
    response = client.post("/chat", json={"session_id": session_id, "message": message})
    assert response.status_code == 200
    return response.json()


def sse_deltas(response) -> tuple[list[dict], list[str]]:
    lines = [line for line in response.text.split("\n") if line.startswith("data: ")]
    chunks = [json.loads(line[6:]) for line in lines if line != "data: [DONE]"]
    return chunks, lines


def test_health_and_buildings(client, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert client.get("/health").json() == {"ok": True, "llm": "offline", "tts": False, "stt": False}
    ids = [item["id"] for item in client.get("/buildings").json()]
    assert BUILDING in ids and all(item.count("/") == 1 for item in ids)


def test_buildings_carry_a_location_only_where_one_is_known(client):
    items = {item["id"]: item for item in client.get("/buildings").json()}
    # kit buildings only: a building made from plans (user/…) is placed on the map by its import
    located = {building_id for building_id, item in items.items() if item["location"] and not building_id.startswith("user/")}
    assert located and all("/osm-way" in building_id for building_id in located)  # only OSM buildings have one
    main = items["train/osm-way10053349"]["location"]  # TUM main building, Arcisstraße 21
    assert abs(main["lat"] - 48.1489) < 0.001 and abs(main["lon"] - 11.5680) < 0.001
    # where the kit's metres start, which puts the model on the map: within 20 m of the outline's centre
    for b in located:
        loc = items[b]["location"]
        north = (loc["origin"]["lat"] - loc["lat"]) * 111320
        east = (loc["origin"]["lon"] - loc["lon"]) * 111320 * math.cos(math.radians(loc["lat"]))
        assert math.hypot(north, east) < 20, b


@pytest.mark.parametrize("building", ["train/nope", "../pyproject.toml", "/etc", "train/../dev/x"])
def test_invalid_building_is_rejected(client, building):
    assert client.post("/sessions", json={"building": building}).status_code == 422
    session_id = new_session(client)
    assert client.put(f"/sessions/{session_id}/building", json={"building": building}).status_code == 422


def test_unknown_session_is_404(client):
    assert client.post("/chat", json={"session_id": "missing", "message": "hi"}).status_code == 404
    assert client.get("/sessions/missing").status_code == 404
    assert client.get("/events", params={"session_id": "missing"}).status_code == 404


def test_session_overview_and_find(client):
    created = client.post("/sessions", json={"building": BUILDING}).json()
    assert created["building"] == BUILDING and created["overview"]["floors"]
    turn = say(client, created["session_id"], "Where is the printer?")
    assert "print room" in turn["reply"].lower()
    assert turn["tool_calls"][0]["name"] == "locate" and turn["ungrounded"] == []


def test_route_event_via_cursor(client):
    session_id = new_session(client)
    say(client, session_id, "Where is the printer?")
    cursor = client.get("/events", params={"session_id": session_id}).json()["next"]
    turn = say(client, session_id, ROUTE)
    assert [event["type"] for event in turn["events"]] == ["route"]
    polled = client.get("/events", params={"session_id": session_id, "after": cursor}).json()
    assert [event["type"] for event in polled["events"]] == ["route"]
    assert client.get("/events", params={"session_id": session_id, "after": polled["next"]}).json()["events"] == []


def test_profile_and_confirmed_change(client):
    session_id = new_session(client)
    say(client, session_id, "I use a wheelchair")
    state = client.get(f"/sessions/{session_id}").json()
    assert state["profile"]["step_free"] is True and state["profile"]["summary"] == "step-free, doors at least 0.8 m wide (assumed)"
    say(client, session_id, ROUTE)
    say(client, session_id, "Lift 1 is broken")
    assert client.get(f"/sessions/{session_id}").json()["pending"] and not state["applied"]
    say(client, session_id, "yes")
    state = client.get(f"/sessions/{session_id}").json()
    assert [change["summary"] for change in state["applied"]] == ["close Lift 1"] and state["pending"] == []


def test_switch_building_keeps_id_and_resets_state(client):
    session_id = new_session(client)
    say(client, session_id, "I use a wheelchair")
    other = next(item["id"] for item in client.get("/buildings").json() if item["id"] != BUILDING)
    switched = client.put(f"/sessions/{session_id}/building", json={"building": other}).json()
    assert switched["session_id"] == session_id and switched["building"] == other
    assert switched["profile"]["step_free"] is False


def test_completions_non_stream(client):
    body = {"model": "guide", "user": "openai-plain", "messages": [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": [{"type": "text", "text": "Where is the printer?"}]}]}
    result = client.post("/v1/chat/completions", json=body).json()
    assert result["object"] == "chat.completion" and result["model"] == "guide"
    choice = result["choices"][0]
    assert choice["message"]["role"] == "assistant" and choice["finish_reason"] == "stop"
    assert "print room" in choice["message"]["content"].lower()


def test_completions_stream(client):
    body = {"stream": True, "session_id": "stream-test",
            "messages": [{"role": "user", "content": "Where is the printer?"}]}
    with client.stream("POST", "/v1/chat/completions", json=body) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        response.read()
    chunks, lines = sse_deltas(response)
    assert lines[-1] == "data: [DONE]"
    assert chunks[0]["object"] == "chat.completion.chunk"
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant", "content": "... "}
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    spoken = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks[1:])
    assert "print room" in spoken.lower()


def test_session_header_persists_across_completions(client):
    headers = {"X-Session-Id": "voice-call-1"}
    first = {"messages": [{"role": "user", "content": "I use a wheelchair"}]}
    client.post("/v1/chat/completions", json=first, headers=headers)
    second = {"messages": [{"role": "user", "content": "I use a wheelchair"},
                           {"role": "user", "content": ROUTE}]}
    reply = client.post("/v1/chat/completions", json=second, headers=headers).json()
    assert "step-free" in reply["choices"][0]["message"]["content"]
    assert client.get("/sessions/voice-call-1").json()["profile"]["step_free"] is True


def test_plan_export(client):
    session_id = new_session(client)
    plan = client.get(f"/sessions/{session_id}/plan").json()
    x0, y0, x1, y1 = plan["bounds"]
    assert plan["center"] == [round((x0 + x1) / 2, 2), round(-(y0 + y1) / 2, 2)]  # the scene is centred on it
    assert len(plan["walls"]) == len(plan["floors"]) and all(plan["walls"])
    assert plan["spaces"] and all(len(space["polygon"]) >= 3 for space in plan["spaces"])
    door = next(opening for opening in plan["openings"] if opening["kind"] == "door")
    assert door["space"] in door["spaces"] and isinstance(door["angle"], float)
    assert plan["assets"] and all(len(asset["size"]) == 2 for asset in plan["assets"])
    assert client.get("/sessions/missing/plan").status_code == 404


def test_plan_is_gzipped(client):
    session_id = new_session(client)
    response = client.get(f"/sessions/{session_id}/plan", headers={"Accept-Encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"


def test_chat_stream_is_not_gzipped(client):
    session_id = new_session(client)
    response = client.post("/chat/stream", json={"session_id": session_id, "message": ROUTE},
                           headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert "content-encoding" not in response.headers


def test_route_event_has_legs(client):
    session_id = new_session(client)
    turn = say(client, session_id, ROUTE)
    route = next(event for event in turn["events"] if event["type"] == "route")
    assert route["legs"] and route["legs"][-1]["kind"] == "arrive"
    polled = client.get("/events", params={"session_id": session_id}).json()["events"]
    assert next(event for event in polled if event["type"] == "route")["legs"] == route["legs"]


def test_route_event_has_the_guides_steps(client):
    session_id = new_session(client)
    turn = say(client, session_id, ROUTE)
    route = next(event for event in turn["events"] if event["type"] == "route")
    steps = route["steps"]
    assert len(steps) == len(route["legs"]) and steps[-1]["kind"] == "arrive"
    assert all(step["text"] and "[" not in step["text"] for step in steps)


def test_change_event_has_space_ids_and_plan_update(client):
    session_id = new_session(client)
    before = client.get(f"/sessions/{session_id}/plan").json()
    say(client, session_id, ROUTE)
    say(client, session_id, "Lift 1 is broken")
    turn = say(client, session_id, "yes")
    change = next(event for event in turn["events"] if event["type"] == "change")
    lift = next(item for item in before["connectors"] if item["name"] == "Lift 1")
    assert change["space_ids"] == lift["spaces"]
    assert client.get(f"/sessions/{session_id}/plan").json()["closed"] == [lift["id"]]
    polled = client.get("/events", params={"session_id": session_id}).json()["events"]
    assert next(event for event in polled if event["type"] == "change")["space_ids"] == change["space_ids"]
    raw = store.get(session_id).session.events  # the enrichment works on copies
    assert all("legs" not in event and "space_ids" not in event for event in raw if event["type"] != "highlight")


def test_chat_stream_steps_then_reply(client):
    session_id = new_session(client)
    response = client.post("/chat/stream", json={"session_id": session_id, "message": ROUTE})
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    steps = [line for line in lines if line["type"] == "step"]
    assert lines[-1]["type"] == "reply" and lines[-1]["reply"]
    assert any(step["kind"] == "tool" and step["name"] == "find_route" for step in steps)
    assert [step["kind"] for step in steps if step["name"] == "find_route"][:2] == ["tool", "tool_done"]
    assert any(event["type"] == "route" for event in lines[-1]["events"])


def test_chat_stream_voice_says_sentences_before_the_reply(client):
    session_id = new_session(client)
    response = client.post("/chat/stream", json={"session_id": session_id, "message": ROUTE, "channel": "voice"})
    lines = [json.loads(line) for line in response.text.splitlines() if line]
    said = [line["text"] for line in lines if line["type"] == "say"]
    assert said and lines[-1]["type"] == "reply"
    assert all(line["type"] != "say" for line in lines[lines.index(lines[-1]):])  # every say precedes the reply
    assert " ".join(said) == lines[-1]["spoken"]  # together they are the whole spoken reply
    text = client.post("/chat/stream", json={"session_id": session_id, "message": ROUTE}).text
    assert '"say"' not in text  # text turns are not spoken


def test_chat_voice_channel_and_bad_channel(client):
    session_id = new_session(client)
    turn = client.post("/chat", json={"session_id": session_id, "message": ROUTE, "channel": "voice"}).json()
    assert turn["spoken"] and "**" not in turn["spoken"]
    tapped = client.post("/chat", json={"session_id": session_id, "message": ROUTE, "channel": "voice", "heard": False})
    assert tapped.status_code == 200 and tapped.json()["spoken"]  # a tapped button, answered aloud
    assert client.post("/chat", json={"session_id": session_id, "message": "hi", "channel": "fax"}).status_code == 422
    assert client.post("/chat/stream", json={"session_id": session_id, "message": "hi", "channel": "fax"}).status_code == 422


TINY_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5E"
            "rkJggg==")


def test_photo_turn_is_answered_and_not_kept(client):
    session_id = new_session(client)
    turn = client.post("/chat", json={"session_id": session_id, "message": "Where is the printer?",
                                      "photo": TINY_PNG})
    assert turn.status_code == 200 and turn.json()["reply"]
    history = store.get(session_id).guide.messages
    assert any(isinstance(m["content"], str) and m["content"].startswith("[the user sent a camera photo") for m in history)
    assert not any(isinstance(m["content"], list) and any(
        (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "image" for b in m["content"])
        for m in history)
    bad = {"session_id": session_id, "message": "hi"}
    assert client.post("/chat", json={**bad, "photo": "data:text/plain;base64,aGk="}).status_code == 422
    assert client.post("/chat", json={**bad, "photo": "not a data url"}).status_code == 422
    assert client.post("/chat", json={**bad, "photo": "data:image/jpeg;base64," + "A" * 1_500_001}).status_code == 413
