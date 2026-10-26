"""FastAPI app: the Building Guide over HTTP.

  GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765

Endpoints: /health, /buildings, /sessions (create, inspect, switch building), /sessions/{id}/plan (vector floor
plan of the session's current building, gzipped), /chat, /chat/stream (the same turn as NDJSON: live tool steps,
then the reply), /events (polling cursor for the map UI; route events
carry turn-by-turn `legs` and a plan `line`, change events `space_ids`), /dev/* (the dev panel: Guide tools run by
hand, backend/devtools.py), /tts (ElevenLabs audio for the Guide's spoken replies, backend/tts.py), /stt/token (Scribe
Realtime token + keyterms for the user's words, backend/stt.py), the
OpenAI-compatible /v1/chat/completions for ElevenLabs (backend/openai_compat.py), and the Edit mode's /drafts (create, get, plan, ops, undo, save, chat/stream for the Builder agent, proposals/{pid}/apply — backend/drafts.py;
saved buildings appear in /buildings as `user/<slug>`; stored in Postgres with SUPABASE_DB_URL, else under
GUIDE_USER_DIR, default data/user/). A draft change or Builder turn that lost a race to another instance answers 409;
a database error 503. /imports/stream runs the Creator (agent/creator.py) on uploaded floor plans and opens its building
as a draft on a private base `import/<id>`.
Guide turns are blocking (tool loop + LLM calls), so those endpoints are plain `def` and run in FastAPI's
threadpool; each conversation's lock serialises its turns. With persistence on (backend/persistence.py) every turn
is saved when it ends; a turn that lost a save race to another instance answers 409 and must be resent.

On Vercel (vercel.json) the app is the `api` service behind the rewrite `/api/(.*)`, which passes the original path
through, so every route is also reachable under `/api` (StripPrefix). CORS_ORIGINS (comma-separated) restricts
cross-origin callers; the default `*` is for local development, the deployed frontend is same-origin."""

import copy
import json
import os
import queue
import re
import threading
from pathlib import Path

import anthropic
import psycopg
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES
from pydantic import BaseModel

from agent.guide import PHOTO_TYPES, llm_mode, system_blocks
from agent.speech import speakable
from backend import devtools, openai_compat, persistence, service_errors, stt, tts
from backend.fleet import Fleet, fleet_from_env
from backend.fleet import router as fleet_router
from backend.access import Access, AuthError, AuthUnavailable, BuildingAccess, Member, Viewer
from agent.builder import Builder
from agent.campus import Campus, arrive
from core.building_map import MapError
from agent.creator import Creator
from agent.creator_tools import ImportSession
from backend.drafts import Draft, DraftStore, backend_from_env
from backend.sessions import DATA_DIR, DEFAULT_SESSION, Conversation, SessionStore, UnknownBuilding, summary
from core.edits import EditError
from core.plan_import.ingest import load_sources
from core.plan_import.reference import reference_for
from core import osm_lookup
from core.geoplace import Placement, distance_m, location_for, place as place_on_map, placement_ops
from core.plan_import.ingest import median_gps
from shapely.geometry import Point as ShapelyPoint, Polygon as ShapelyPolygon
from core.edits import apply_op

API_PREFIX = "/api"


class StripPrefix:
    """ASGI middleware: serve `/api/x` as `/x`, so the same routes work behind the Vercel rewrite and locally."""

    def __init__(self, app: object, prefix: str = API_PREFIX) -> None:
        self.app, self.prefix = app, prefix

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        path = scope.get("path", "")
        if scope["type"] in ("http", "websocket") and (path == self.prefix or path.startswith(self.prefix + "/")):
            scope = {**scope, "path": path[len(self.prefix):] or "/",
                     "raw_path": scope.get("raw_path", b"")[len(self.prefix):] or b"/"}
        await self.app(scope, receive, send)


origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()]
app = FastAPI(title="Talk to Your Building")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
# the floor plan export is up to ~0.5 MB of JSON; NDJSON streams stay uncompressed: gzip holds a Guide turn's lines
# back until the turn ends (browsers ask for gzip), so steps and spoken sentences arrived all at once on the deployment
app.add_middleware(GZipMiddleware, minimum_size=1000,
                   exclude_content_types=(*DEFAULT_EXCLUDED_CONTENT_TYPES, "application/x-ndjson"))
app.add_middleware(StripPrefix)  # added last = outermost: routes see the path without /api
store = SessionStore()
drafts = DraftStore(backend_from_env(Path(os.environ.get("GUIDE_USER_DIR", DATA_DIR / "user"))), store.catalogue)
store.user_buildings = drafts
access = Access()  # access mode (ACCESS_MODE=on): accounts, restricted spaces — backend/access.py



@app.middleware("http")
async def drafts_admin_only(request: Request, call_next):
    """Access mode: Edit mode (/drafts) hands out a building's full data, and an import (/imports) is a paid Creator
    run that ends in the Edit mode, so only the admin may use them."""
    path = request.url.path.removeprefix(API_PREFIX)
    admin_only = (any(path == root or path.startswith(root + "/") for root in ("/drafts", "/imports"))
                  or (request.method == "DELETE" and path.startswith("/buildings/")))  # deleting a saved building
    if access.enabled and admin_only and request.method != "OPTIONS":
        try:
            viewer = await run_in_threadpool(access.viewer, request.headers.get("authorization"))
        except AuthError:
            return JSONResponse({"detail": "sign-in expired or invalid; sign in again"}, status_code=401)
        except AuthUnavailable as error:
            return JSONResponse({"detail": f"sign-in is unavailable right now ({error})"}, status_code=503)
        if not viewer.admin:
            return JSONResponse({"detail": "only the building admin can edit buildings"}, status_code=403)
    return await call_next(request)


UPDATED_ELSEWHERE = "this draft was updated elsewhere meanwhile; try again"
DB_DOWN = "the database is unavailable right now; try again in a moment"


@app.exception_handler(anthropic.APIError)
def claude_failed(request: Request, error: anthropic.APIError) -> JSONResponse:
    """A Claude call failed on a plain request (/chat, Builder, …): the readable sentence, not a 500 trace."""
    readable = service_errors.friendly(error)
    return JSONResponse({"detail": readable["message"], "code": readable["code"]},
                        status_code=service_errors.STATUS[readable["code"]])


@app.exception_handler(persistence.Conflict)
def conflict_409(request: Request, error: persistence.Conflict) -> JSONResponse:
    return JSONResponse({"detail": UPDATED_ELSEWHERE}, status_code=409)


@app.exception_handler(psycopg.Error)
def database_503(request: Request, error: psycopg.Error) -> JSONResponse:
    return JSONResponse({"detail": DB_DOWN}, status_code=503)


class NewSession(BaseModel):
    building: str | None = None


class SwitchBuilding(BaseModel):
    building: str


class NewDraft(BaseModel):
    base: str


class DraftOps(BaseModel):
    ops: list[dict]


class SaveDraft(BaseModel):
    name: str


class BuilderMessage(BaseModel):
    message: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    channel: str = "text"  # "voice": spoken-style reply, also returned as `spoken` (agent/speech.py)
    photo: str | None = None  # data URL (jpeg/png/webp) from the camera walk mode, shown to the Guide for one turn
    heard: bool = True  # voice channel: the message is a speech transcript; false for a tapped button read aloud
    selected: str | None = None  # the space or asset id tapped on the plan while asking ("how do I get there?")
    route_step: int | None = None  # the step card's step (0-based) while a route is on the map


class LocationRequest(BaseModel):
    space_id: str | None = None  # the room the "you are here" figure stands in; None = taken away
    point: list[float] | None = None  # where in that room (plan metres): the drawn route line starts there


class ArriveRequest(BaseModel):
    entrance: str  # opening id of this building the user comes in through
    destination: str  # space id here
    from_session: str | None = None  # the conversation in the building they came from: its routing profile carries over


class SpeechRequest(BaseModel):
    text: str
    lang: str | None = None  # BCP 47 like "de-DE"; its first two letters keep the voice to that language


class SttTokenRequest(BaseModel):
    session_id: str | None = None  # keyterms come from this session's building


PHOTO_MAX_CHARS = 1_500_000  # base64 of a ~1.1 MB image; the app sends ~1280 px JPEGs well below this


def viewer_or_401(authorization: str | None) -> Viewer:
    try:
        return access.viewer(authorization)
    except AuthError:
        raise HTTPException(401, "sign-in expired or invalid; sign in again") from None
    except AuthUnavailable as error:
        raise HTTPException(503, f"sign-in is unavailable right now ({error})") from None


def conversation_or_404(session_id: str, authorization: str | None = None) -> Conversation:
    """The conversation, on the building copy this request's viewer may see (access mode; a no-op when off)."""
    conversation = store.get(session_id)
    if conversation is None:
        raise HTTPException(404, f"unknown session {session_id!r}")
    return with_campus(with_access(conversation, viewer_or_401(authorization)))


def with_campus(conversation: Conversation) -> Conversation:
    """The session's buildings nearby (agent/campus.py); sessions are rebuilt on restores and switches."""
    campus = conversation.session.campus
    if campus is None or campus.building_id != conversation.building:
        conversation.session.campus = Campus(conversation.building, store.catalogue)
    return conversation


def with_access(conversation: Conversation, viewer: Viewer) -> Conversation:
    if not access.enabled:
        return conversation
    conversation.session.preferences_enabled = True  # remembered preferences come with access mode
    if not access.visible(viewer, conversation.building):
        raise HTTPException(404, f"unknown session {conversation.id!r}")
    restricted = access.restricted_for(viewer, conversation.building, store.base_data(conversation.building))
    conversation = store.ensure_access(conversation, restricted)
    conversation.session.preferences_enabled = True
    building = conversation.building
    conversation.session.object_dispatch = (
        (lambda name, destination: dispatch_by_name(building, name, destination)) if viewer.admin else None)
    return conversation


def dispatch_by_name(building: str, name: str, destination: str) -> dict:
    """The Guide's send_object for the admin: an object of this building by name or id → fleet.dispatch."""
    rows = fleet.store.list(building)
    wanted = name.strip().lower()
    row = next((row for row in rows if wanted in (row["id"].lower(), row["name"].lower())), None)
    if row is None:
        matches = [row for row in rows if wanted in row["name"].lower()]
        row = matches[0] if len(matches) == 1 else None
    if row is None:
        return {"error": f"No object called '{name}'", "objects": [row["name"] for row in rows]}
    return fleet.dispatch(row, destination)


def visible_or_422(viewer: Viewer, building: str | None) -> None:
    if building is not None and access.enabled and not access.visible(viewer, building):
        raise HTTPException(422, f"unknown building {building}; see GET /buildings")


def save_or_409(conversation: Conversation) -> None:
    try:
        store.save(conversation)
    except persistence.Conflict:
        raise HTTPException(409, "this conversation was updated elsewhere meanwhile; send the message again") from None


def turn_payload(conversation: Conversation, turn: object) -> dict:
    return {
        "reply": turn.text,
        "tool_calls": [{"name": call["name"], "input": call["input"]} for call in turn.tool_calls],
        "events": conversation.view.enrich(conversation.session, turn.events),
        "ungrounded": turn.ungrounded,
        "spoken": turn.spoken,
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True, "llm": llm_mode(), "tts": tts.enabled(), "stt": stt.enabled()}


@app.post("/stt/token")
def speech_to_text_token(body: SttTokenRequest, authorization: str | None = Header(None)) -> dict:
    """A single-use ElevenLabs Scribe Realtime token (15 minutes, one connection) and the session building's keyterms
    (backend/stt.py) — from the building copy this viewer may see, so restricted names never reach the browser in
    access mode. 503 when Scribe is off, 502 when ElevenLabs refuses: the app then uses browser recognition."""
    if not stt.enabled():
        raise HTTPException(503, "Scribe speech recognition is not configured (ELEVENLABS_API_KEY, STT_MODE)")
    conversation = conversation_or_404(body.session_id, authorization) if body.session_id else None
    try:
        token = stt.single_use_token()
    except stt.SttError as error:
        raise HTTPException(502, f"ElevenLabs Scribe failed ({error})") from None
    return {"token": token, "keyterms": stt.keyterms(conversation.session.building) if conversation else []}


@app.post("/tts", response_model=None)
def text_to_speech(body: SpeechRequest) -> StreamingResponse:
    """One piece of a spoken reply as ElevenLabs MP3 (backend/tts.py). 503 without a key, 502 when ElevenLabs
    refuses: the app then speaks with the browser's own voice."""
    if not tts.enabled():
        raise HTTPException(503, "the ElevenLabs voice is not configured (ELEVENLABS_API_KEY)")
    text = speakable(body.text)  # the voice replies' safety net: no markup, ids or symbols read out
    if not text:
        raise HTTPException(422, "nothing to say")
    if len(text) > tts.MAX_CHARS:
        raise HTTPException(413, f"text is too long to speak at once (max {tts.MAX_CHARS} characters)")
    try:
        audio = tts.open_stream(text, body.lang)
    except tts.TtsError as error:
        raise HTTPException(502, f"ElevenLabs voice failed ({error})") from None
    return StreamingResponse(audio, media_type="audio/mpeg", headers={"cache-control": "no-store"})


@app.get("/buildings")
def buildings(authorization: str | None = Header(None)) -> list[dict]:
    drafts.refresh(quiet=True)  # buildings saved on other instances; dataset buildings even if the database is down
    hidden = access.hidden_buildings(viewer_or_401(authorization))
    return [{"id": item["id"], "split": item["split"], "name": item["name"],
             "location": None if item.get("superseded") else item.get("location")}  # a newer save stands there
            for item in store.catalogue.values() if item["id"] not in hidden]


@app.post("/sessions")
def create_session(body: NewSession, authorization: str | None = Header(None)) -> dict:
    viewer = viewer_or_401(authorization)
    visible_or_422(viewer, body.building)
    try:
        conversation = with_access(store.create(body.building), viewer)
    except UnknownBuilding as error:
        raise HTTPException(422, f"unknown building {error}; see GET /buildings") from None
    return {"session_id": conversation.id, "building": conversation.building,
            "overview": conversation.session.building.overview()}


@app.get("/sessions/{session_id}")
def get_session(session_id: str, authorization: str | None = Header(None)) -> dict:
    return summary(conversation_or_404(session_id, authorization))


@app.put("/sessions/{session_id}/building")
def switch_building(session_id: str, body: SwitchBuilding, authorization: str | None = Header(None)) -> dict:
    conversation = conversation_or_404(session_id, authorization)
    viewer = viewer_or_401(authorization)
    visible_or_422(viewer, body.building)
    try:
        store.switch_building(conversation, body.building)
    except UnknownBuilding as error:
        raise HTTPException(422, f"unknown building {error}; see GET /buildings") from None
    except persistence.Conflict:
        raise HTTPException(409, "this conversation was updated elsewhere meanwhile; try again") from None
    with_access(conversation, viewer)
    return {**summary(conversation), "overview": conversation.session.building.overview()}


@app.post("/chat")
def chat(body: ChatRequest, authorization: str | None = Header(None)) -> dict:
    conversation = conversation_or_404(body.session_id, authorization)
    with conversation.lock:
        turn = conversation.guide.reply(body.message, channel=channel_or_422(body.channel),
                                        photo=photo_or_422(body.photo), heard=body.heard,
                                        selected=body.selected, route_step=body.route_step)
        save_or_409(conversation)
        return turn_payload(conversation, turn)


def photo_or_422(photo: str | None) -> dict | None:
    if photo is None:
        return None
    header, _, data = photo.partition(",")
    media_type = header.removeprefix("data:").removesuffix(";base64")
    if not header.startswith("data:") or not header.endswith(";base64") or media_type not in PHOTO_TYPES or not data:
        raise HTTPException(422, f"photo must be a base64 data URL of type {', '.join(PHOTO_TYPES)}")
    if len(data) > PHOTO_MAX_CHARS:
        raise HTTPException(413, "photo is too large; send a smaller image")
    return {"media_type": media_type, "data": data}


def channel_or_422(channel: str) -> str:
    if channel not in ("text", "voice"):
        raise HTTPException(422, "channel must be 'text' or 'voice'")
    return channel


@app.post("/chat/stream")
def chat_stream(body: ChatRequest, authorization: str | None = Header(None)) -> StreamingResponse:
    """One turn as NDJSON lines: {"type": "step", …} per tool call or check while the Guide works (the map can
    poll /events on each `tool_done`), then {"type": "reply", …the /chat payload} or {"type": "error", "detail"}.
    Voice turns also send {"type": "say", "text"} per sentence as soon as it may be spoken (agent/speech.py
    SpokenStream), all before the reply line; together they are the whole spoken reply."""
    conversation = conversation_or_404(body.session_id, authorization)
    channel, photo = channel_or_422(body.channel), photo_or_422(body.photo)
    lines: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            with conversation.lock:
                conversation.guide.on_step = lambda step: lines.put({"type": "step", **step})
                conversation.guide.on_say = lambda text: lines.put({"type": "say", "text": text})
                try:
                    turn = conversation.guide.reply(body.message, channel=channel, photo=photo, heard=body.heard,
                                                    selected=body.selected, route_step=body.route_step)
                finally:
                    conversation.guide.on_step = None
                    conversation.guide.on_say = None
                try:
                    store.save(conversation)
                except persistence.Conflict:
                    lines.put({"type": "error", "code": "conflict",
                               "message": "This conversation was updated elsewhere meanwhile. Send the message again.",
                               "detail": "this conversation was updated elsewhere meanwhile; send the message again"})
                    return
                lines.put({"type": "reply", **turn_payload(conversation, turn)})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put(service_errors.error_line(error))
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        while (line := lines.get()) is not None:
            yield json.dumps(line, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.put("/sessions/{session_id}/location")
def put_location(session_id: str, body: LocationRequest, authorization: str | None = Header(None)) -> dict:
    """The app's "you are here" figure: the Guide routes from there and stops asking where the user is."""
    conversation = conversation_or_404(session_id, authorization)
    with conversation.lock:
        if body.space_id is not None and body.space_id not in conversation.session.building.spaces:
            raise HTTPException(422, f"unknown space {body.space_id!r}")
        location = conversation.guide.set_location(body.space_id, body.point)
        save_or_409(conversation)
    return {"location": location}


@app.post("/sessions/{session_id}/arrive")
def post_arrive(session_id: str, body: ArriveRequest, authorization: str | None = Header(None)) -> dict:
    """Coming over from a nearby building (route_to_building → Continue): the user stands at `entrance`; the
    route from there to `destination` comes back as events, like a Guide turn's."""
    conversation = conversation_or_404(session_id, authorization)
    previous = None
    if body.from_session:
        try:  # same access check as the target session; a session this viewer may not see is ignored
            previous = conversation_or_404(body.from_session, authorization)
        except HTTPException:
            previous = None
    with conversation.lock:
        session = conversation.session
        if previous is not None:
            session.profile = copy.deepcopy(previous.session.profile)
        first = len(session.events)
        try:
            route = arrive(session, body.entrance, body.destination)
        except (MapError, KeyError) as error:
            raise HTTPException(422, str(error)) from None
        conversation.guide.set_location(session.user_location["space_id"])
        conversation.guide.location_note += (" They just came over from a nearby building; the map shows the way "
                                             f"to {session.building.spaces[route['to_space_id']]['name']}."
                                             if route.get("reachable") else " They just came over from a nearby building.")
        save_or_409(conversation)
        events = conversation.view.enrich(session, session.events[first:])
    return {"route": {key: route.get(key) for key in ("reachable", "reason", "about_m", "length_m")},
            "location": session.user_location, "events": events}


@app.get("/events")
def events(session_id: str, after: int = Query(0, ge=0), authorization: str | None = Header(None)) -> dict:
    # Read without the lock so the map can update while a turn's tools run.
    conversation = conversation_or_404(session_id, authorization)
    log = conversation.session.events
    end = len(log)  # snapshot: a running turn may append meanwhile
    return {"events": conversation.view.enrich(conversation.session, log[after:end]), "next": end}


@app.get("/sessions/{session_id}/plan")
def plan(session_id: str, authorization: str | None = Header(None)) -> dict:
    conversation = conversation_or_404(session_id, authorization)
    floor_plan = conversation.view.plan(conversation.session)
    if not conversation.restricted_shapes:
        return floor_plan
    index = {floor["id"]: number for number, floor in enumerate(floor_plan["floors"])}
    return {**floor_plan, "restricted": [{"id": shape["id"], "floor": index[shape["floor_id"]],
                                          "polygon": shape["polygon"]}
                                         for shape in conversation.restricted_shapes if shape["floor_id"] in index]}


# ---------- access mode: config, me, admin (backend/access.py) ----------


class SessionPreferences(BaseModel):
    values: dict = {}  # effective preferences for this building (global ← building), see agent/tools.py
    auto_capture: bool = True


class AccessUpdate(BaseModel):
    building: str
    public: bool = True
    room_types: dict[str, list[str]] = {}
    spaces: dict[str, list[str]] = {}


class Invite(BaseModel):
    email: str
    building: str
    groups: list[str]
    redirect_to: str | None = None


class MemberUpdate(BaseModel):
    user_id: str
    email: str
    building: str
    groups: list[str]


@app.get("/config")
def config() -> dict:
    """What the frontend needs to know at start: whether access mode is on and how to sign in (public values)."""
    if not access.enabled:
        return {"access_mode": False}
    return {"access_mode": True, "supabase_url": os.environ.get("SUPABASE_URL", ""),
            "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", "")}


@app.put("/sessions/{session_id}/preferences")
def session_preferences(session_id: str, body: SessionPreferences, authorization: str | None = Header(None)) -> dict:
    """The app's remembered preferences for this conversation (access mode): set on the session's profile without
    events; the Guide's system prompt gets the talking preferences."""
    if not access.enabled:
        raise HTTPException(404, "access mode is off")
    conversation = conversation_or_404(session_id, authorization)
    with conversation.lock:
        session = conversation.session
        try:
            session.apply_preferences(body.values)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, f"bad preferences: {error}") from None
        session.auto_capture = body.auto_capture
        conversation.guide.system = system_blocks(session)
        save_or_409(conversation)
    return summary(conversation)


@app.get("/me/preferences")
def my_preferences(authorization: str | None = Header(None)) -> dict:
    """A signed-in user's stored preferences ({} until saved); anonymous users keep theirs in the browser."""
    viewer = viewer_or_401(authorization)
    if not access.enabled or viewer.anonymous:
        raise HTTPException(404, "sign in to store preferences on the server")
    return access.store.preferences(viewer.user_id)


@app.put("/me/preferences")
def put_my_preferences(body: dict, authorization: str | None = Header(None)) -> dict:
    viewer = viewer_or_401(authorization)
    if not access.enabled or viewer.anonymous:
        raise HTTPException(404, "sign in to store preferences on the server")
    if len(json.dumps(body)) > 50_000:
        raise HTTPException(413, "preferences too large")
    access.store.set_preferences(viewer.user_id, body)
    return body


@app.get("/me")
def me(authorization: str | None = Header(None)) -> dict:
    viewer = viewer_or_401(authorization)
    groups = access.store.member_buildings(viewer.user_id) if access.enabled and viewer.user_id else {}
    return {**viewer.to_dict(), "buildings": groups}


def admin_or_403(authorization: str | None) -> Viewer:
    if not access.enabled:
        raise HTTPException(404, "access mode is off")
    viewer = viewer_or_401(authorization)
    if not viewer.admin:
        raise HTTPException(403, "only the building admin can do this")
    return viewer


def known_or_422(building: str) -> None:
    if not store.known(building):
        raise HTTPException(422, f"unknown building {building}; see GET /buildings")


@app.get("/access/building")
def get_access(building: str, authorization: str | None = Header(None)) -> dict:
    """The building's access settings plus what the editor needs: its room types and spaces."""
    admin_or_403(authorization)
    known_or_422(building)
    data = store.base_data(building)
    spaces = [{"id": space["id"], "name": space["name"], "ref": space.get("ref") or "",
               "room_type": space.get("room_type") or "", "floor_id": space["floor_id"]} for space in data["spaces"]]
    room_types = sorted({space["room_type"] for space in spaces if space["room_type"]})
    return {"building": building, **access.store.building(building).to_dict(), "room_type_options": room_types,
            "space_options": spaces}


@app.put("/access/building")
def put_access(body: AccessUpdate, authorization: str | None = Header(None)) -> dict:
    admin_or_403(authorization)
    known_or_422(body.building)
    space_ids = {space["id"] for space in store.base_data(body.building)["spaces"]}
    unknown = sorted(set(body.spaces) - space_ids)
    if unknown:
        raise HTTPException(422, f"unknown space ids: {', '.join(unknown[:5])}")
    rules = BuildingAccess.from_dict(body.model_dump())
    access.store.set_building(body.building, rules)
    return {"building": body.building, **rules.to_dict()}


@app.get("/access/members")
def get_members(building: str, authorization: str | None = Header(None)) -> list[dict]:
    admin_or_403(authorization)
    return [member.to_dict() for member in access.store.list_members(building)]


@app.post("/access/invite")
def invite(body: Invite, authorization: str | None = Header(None)) -> dict:
    """Create (or find) the account and return a sign-in link for the admin to pass on; no email is sent."""
    admin_or_403(authorization)
    known_or_422(body.building)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "enter an email address")
    try:
        user_id, link = access.auth.invite(email, body.redirect_to)
    except (AuthError, AuthUnavailable) as error:
        raise HTTPException(503, f"could not create the invite ({error})") from None
    member = Member(user_id, email, body.building, sorted({g.strip() for g in body.groups if g.strip()}))
    access.store.set_member(member)
    return {**member.to_dict(), "link": link}


@app.put("/access/members")
def put_member(body: MemberUpdate, authorization: str | None = Header(None)) -> dict:
    """Change a member's groups in a building; no groups removes the membership."""
    admin_or_403(authorization)
    member = Member(body.user_id, body.email.strip().lower(), body.building,
                    sorted({g.strip() for g in body.groups if g.strip()}))
    access.store.set_member(member)
    return member.to_dict()


# ---------- Edit mode: drafts (backend/drafts.py) ----------


def draft_or_404(draft_id: str) -> Draft:
    draft = drafts.get(draft_id)
    if draft is None:
        raise HTTPException(404, f"unknown draft {draft_id!r}")
    return draft


@app.delete("/buildings/{split}/{slug}")
def delete_building(split: str, slug: str) -> dict:
    """Delete a building saved from the Edit mode or an import (user/<slug>); dataset buildings cannot be deleted.
    A version it superseded comes back to the map."""
    if split != "user" or not re.fullmatch(r"[a-z0-9-]+", slug) or not drafts.delete(f"user/{slug}"):
        raise HTTPException(404, f"no saved building {split}/{slug}")
    return {"deleted": f"user/{slug}"}


@app.post("/drafts")
def create_draft(body: NewDraft) -> dict:
    try:
        draft = drafts.create(body.base)
    except KeyError:
        raise HTTPException(422, f"unknown building {body.base!r}; see GET /buildings") from None
    return drafts.state(draft)


@app.get("/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    return drafts.state(draft_or_404(draft_id))


@app.get("/drafts/{draft_id}/plan")
def draft_plan(draft_id: str) -> dict:
    return drafts.plan(draft_or_404(draft_id))


@app.post("/drafts/{draft_id}/ops")
def draft_ops(draft_id: str, body: DraftOps) -> dict:
    draft = draft_or_404(draft_id)
    try:
        drafts.apply(draft, body.ops)
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    tell_builder(draft, "The user changed the draft by hand (dragging on the plan); look again before proposing.")
    return drafts.state(draft)


@app.post("/drafts/{draft_id}/undo")
def draft_undo(draft_id: str) -> dict:
    draft = draft_or_404(draft_id)
    try:
        drafts.undo(draft)
    except EditError as error:
        raise HTTPException(409, str(error)) from None
    tell_builder(draft, "The user undid the last change to the draft; look again before proposing.")
    return drafts.state(draft)


@app.post("/drafts/{draft_id}/save")
def draft_save(draft_id: str, body: SaveDraft) -> dict:
    draft = draft_or_404(draft_id)
    issues = drafts.issues(draft)
    return {"building": drafts.save(draft, body.name), "issues": issues}


# ---------- Edit mode: the Builder agent (agent/builder.py) — prompt edits ----------
# One Builder per draft behind a per-draft turn lock. The dict is only a cache: the conversation is stored with the
# draft after every turn / apply / cancel / hand-edit note (drafts.backend) and restored when the stored version is
# newer than ours — another instance moved it on, or this one never saw it.

builders: dict[str, Builder] = {}
builder_locks: dict[str, threading.Lock] = {}
builders_guard = threading.Lock()


def builder_lock(draft_id: str) -> threading.Lock:
    with builders_guard:
        return builder_locks.setdefault(draft_id, threading.Lock())


def load_builder(draft: Draft) -> Builder:
    """The draft's Builder as last stored. Hold its builder_lock."""
    cached = builders.get(draft.id)
    if cached is not None and cached.draft is draft and cached.version == drafts.backend.builder_version(draft.id):
        return cached
    state, version = drafts.backend.load_builder(draft.id)
    builder = Builder.restore(drafts, draft, state) if state is not None else Builder(drafts, draft)
    builder.version = version
    builders[draft.id] = builder
    return builder


def store_builder(builder: Builder) -> None:
    """Persist after a change; raises persistence.Conflict (and forgets our copy) if another instance stored first."""
    try:
        builder.version = drafts.backend.save_builder(builder.draft.id, builder.dump(), builder.version)
    except persistence.Conflict:
        builders.pop(builder.draft.id, None)
        raise


def tell_builder(draft: Draft, note: str) -> None:
    """A hand edit / undo: tell the draft's Builder (if it has talked yet), closing its open proposal."""
    lock = builder_lock(draft.id)
    if not lock.acquire(blocking=False):  # a turn is running here; it stores the note with its own state
        if (builder := builders.get(draft.id)) is not None:
            builder.drafted_by_hand(note)
        return
    try:
        for attempt in range(2):
            if draft.id not in builders and drafts.backend.builder_version(draft.id) == 0:
                return  # no conversation yet: nothing to tell
            builder = load_builder(draft)
            builder.drafted_by_hand(note)
            try:
                store_builder(builder)
                return
            except persistence.Conflict:
                if attempt:  # the edit itself is stored; the Builder just misses one note
                    return
    finally:
        lock.release()


def proposal_payload(draft: Draft, proposal: object | None) -> dict | None:
    """An open proposal for the UI, with the draft as it would look after it (the plan's ghost overlay). None when
    the draft changed while the Builder worked (a hand edit): the reply still goes out, the outdated proposal not."""
    if proposal is None or proposal.draft_version != draft.version:
        return None
    preview = proposal.preview
    return {"id": proposal.id, "summary": proposal.summary, "ops": proposal.ops,
            "new_problems": [issue["message"] for issue in proposal.new_problems], "effect": proposal.effect,
            "building": preview}


@app.post("/drafts/{draft_id}/chat/stream")
def draft_chat_stream(draft_id: str, body: BuilderMessage) -> StreamingResponse:
    """One Builder turn as NDJSON: {"type": "step", …} while it works, then {"type": "reply", "reply", "tool_calls",
    "proposal" (or null), "applied" (summary when a "yes" applied the open proposal), "state"} or {"type": "error"}."""
    draft = draft_or_404(draft_id)
    lines: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            with builder_lock(draft.id):
                builder = load_builder(draft)
                builder.on_step = lambda step: lines.put({"type": "step", **step})
                try:
                    turn = builder.reply(body.message)
                finally:
                    builder.on_step = None
                try:
                    store_builder(builder)
                except persistence.Conflict:
                    lines.put({"type": "error", "code": "conflict",
                               "message": "This conversation was updated elsewhere meanwhile. Send the message again.",
                               "detail": "this conversation was updated elsewhere meanwhile; send the message again"})
                    return
                lines.put({"type": "reply", "reply": turn.text,
                           "tool_calls": [{"name": call["name"], "input": call["input"]} for call in turn.tool_calls],
                           "proposal": proposal_payload(draft, turn.proposal), "applied": turn.applied,
                           "ungrounded": turn.ungrounded, "state": drafts.state(draft)})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put(service_errors.error_line(error))
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        while (line := lines.get()) is not None:
            yield json.dumps(line, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ---------- Plan import: the Creator (agent/creator.py) — a building from floor plans ----------

MAX_IMPORT_FILES = 20
MAX_IMPORT_BYTES = 25 * 1024 * 1024  # per file


def make_creator(session: ImportSession) -> Creator:
    return Creator(session)


@app.post("/imports/stream")
def import_stream(files: list[UploadFile] = File(...), place: str | None = Form(None),
                  device: str | None = Form(None), draft: str | None = Form(None),
                  levels: str | None = Form(None)) -> StreamingResponse:
    """Floor plans (PDF / images) → the Creator → a draft on a private base `import/<id>`, as NDJSON:
    {"type": "warning", "detail"} per unreadable file, {"type": "step", …} while the Creator works, then one of
    {"type": "done", "draft_id", "base", "name", "issues", "notes"}, {"type": "no_plan", "reason"} or
    {"type": "error", "detail"}. `place` (JSON, optional): where on the map the building stands — {"ring": [[lon, lat],
    …]} (the tapped OSM footprint, fitted onto) or {"point": [lon, lat]}; the `done` line then carries `location`.
    Without a tap the building goes where the photos were taken (EXIF GPS; else `device`, the browser's {"lat",
    "lon"} at upload), fitted onto the OSM building there (core/osm_lookup.py) when one is found; with a tap far from
    that position the `done` line adds `suggestion` ({"ring", "name"}: the building the photos point at).
    `located_by`: "tap" | "photos" | "device" | null. `levels` (JSON list, one int per file, all different): the floor
    each file is, as the user said — the Creator registers each file at that level. `draft` (an open draft's id, Edit
    mode's "Add a floor"): the new floors go into that draft as one undo step (edit op `add_floors`, laid onto the
    building, core/plan_import/merge.py); a level the draft already has → 422; the `done` line names that draft."""
    where = place_or_422(place)
    target = draft_or_404(draft) if draft else None
    given = levels_or_422(levels, len(files))
    if target is not None and given is not None:
        have = {floor["level"] for floor in drafts.building(target)["floors"]}
        if clash := sorted(have & set(given)):
            raise HTTPException(422, f"the building already has floor {', '.join(map(str, clash))}; pick another level")
    browser = device_or_none(device)
    if len(files) > MAX_IMPORT_FILES:
        raise HTTPException(413, f"at most {MAX_IMPORT_FILES} files per import")
    uploads = []
    for upload in files:
        data = upload.file.read(MAX_IMPORT_BYTES + 1)
        if len(data) > MAX_IMPORT_BYTES:
            raise HTTPException(413, f"{upload.filename}: larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB")
        uploads.append((upload.filename or "upload", data))
    lines: queue.Queue[dict | None] = queue.Queue()
    cancel = threading.Event()  # the client went away: the Creator stops and no draft is made

    def work() -> None:
        try:
            sources, warnings = load_sources(uploads, given)
            found = median_gps([data for _, data in uploads])
            gps = (found[0], found[1]) if found else None
            for warning in warnings:
                lines.put({"type": "warning", "detail": warning})
            if not sources:
                lines.put({"type": "error", "detail": "no readable PDF or image among the files"})
                return
            session = ImportSession(sources, warnings)
            creator = make_creator(session)
            creator.cancel = cancel
            creator.on_step = lambda step: lines.put({"type": "step", **step})
            result = creator.run()
            if cancel.is_set() or result.status == "cancelled":
                return
            if result.status == "no_plan":
                lines.put({"type": "no_plan", "reason": result.reason})
            elif result.status != "done" or result.building is None:
                lines.put({"type": "error", "detail": result.reason or "the import did not finish"})
            else:
                notes = result.building["building"]["source_ref"]["import"]["floors"]
                for level, floor in session.floors.items():  # the straightened plans, for Edit mode's reference panel
                    if str(level) in notes and floor.image is not None and floor.transform is not None:
                        notes[str(level)]["reference"] = reference_for(floor)
                if target is not None:  # new floors of the building being edited
                    drafts.apply(target, [{"op": "add_floors", "building_with_floors": result.building}])
                    lines.put({"type": "done", "draft_id": target.id, "base": target.base, "name": target.name,
                               "issues": drafts.issues(target), "notes": strip_import_images(
                                   result.building["building"]["source_ref"].get("import")),
                               "location": None, "located_by": None, "suggestion": None})
                    return
                building, located_by, suggestion = locate_import(result.building, where, gps or browser,
                                                                 "photos" if gps else "device" if browser else None)
                draft = drafts.create_import(building)
                lines.put({"type": "done", "draft_id": draft.id, "base": draft.base, "name": draft.name,
                           "issues": drafts.issues(draft),
                           "notes": strip_import_images(building["building"]["source_ref"].get("import")),
                           "location": building["building"].get("location"), "located_by": located_by,
                           "suggestion": suggestion})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put({"type": "error", "detail": f"{type(error).__name__}: {error}"[:300]})
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        try:
            while (line := lines.get()) is not None:
                yield json.dumps(line, ensure_ascii=False) + "\n"
        finally:  # also on GeneratorExit: the client disconnected or the screen was left
            cancel.set()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


def levels_or_422(levels: str | None, files: int) -> list[int] | None:
    """The floor of each uploaded file (JSON list of ints, one per file, all different), or None when not given."""
    if not levels:
        return None
    try:
        given = json.loads(levels)
        if not isinstance(given, list) or not all(isinstance(level, int) and not isinstance(level, bool) for level in given):
            raise ValueError("a list of whole numbers")
    except ValueError as error:
        raise HTTPException(422, f"levels must be a JSON list of floor numbers ({error})") from None
    if len(given) != files:
        raise HTTPException(422, f"levels: {len(given)} given for {files} files — one floor number per file")
    if len(set(given)) != len(given):
        raise HTTPException(422, "levels: each file must be a different floor")
    return given


def place_or_422(place: str | None) -> dict | None:
    """{"ring": [[lon, lat], ≥ 3 points]} or {"point": [lon, lat]} → keyword arguments of core.geoplace.place."""
    if not place:
        return None
    try:
        data = json.loads(place)
        if "ring" in data:
            ring = [[float(lon), float(lat)] for lon, lat in data["ring"]]
            if len({tuple(point) for point in ring}) < 3:
                raise ValueError("a ring needs at least 3 points")
            return {"ring": ring}
        lon, lat = data["point"]
        return {"point": [float(lon), float(lat)]}
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, f"place must be {{'ring': [[lon, lat], …]}} or {{'point': [lon, lat]}} ({error})") from None


def device_or_none(device: str | None) -> tuple[float, float] | None:
    """The browser's position sent with an import ({"lat", "lon"}); None when absent or malformed (it is optional)."""
    try:
        data = json.loads(device) if device else None
        return (float(data["lat"]), float(data["lon"])) if data else None
    except (ValueError, TypeError, KeyError):
        return None


MISMATCH_M = 50  # the photos' position this far from the tapped building (and outside it) = another building


def locate_import(building: dict, where: dict | None, position: tuple[float, float] | None,
                  source: str | None) -> tuple[dict, str | None, dict | None]:
    """(placed building, how it was located, a suggestion when the tap and the photos disagree)."""
    if where:
        placed = place_on_map(building, **where)
        if position is None:
            return placed, "tap", None
        if "ring" in where:
            ring = ShapelyPolygon(where["ring"])
            near = ring.contains(ShapelyPoint(position[1], position[0])) or distance_m(
                position, (ring.centroid.y, ring.centroid.x)) <= MISMATCH_M
        else:
            near = distance_m(position, (where["point"][1], where["point"][0])) <= MISMATCH_M
        if near:
            return placed, "tap", None
        other = osm_lookup.building_at(*position)
        suggestion = {"ring": other["ring"], "name": other.get("name")} if other else {"point": [position[1], position[0]], "name": None}
        return placed, "tap", suggestion
    if position is None:
        return building, None, None
    found = osm_lookup.building_at(*position)
    if found:
        return place_on_map(building, ring=found["ring"], address=found.get("name")), source, None
    return place_on_map(building, point=[position[1], position[0]]), source, None


class DraftFit(BaseModel):
    ring: list[list[float]]
    name: str | None = None


@app.post("/drafts/{draft_id}/fit")
def draft_fit(draft_id: str, body: DraftFit) -> dict:
    """Fit the draft's building onto another OSM footprint (the "did you mean" building): one undo step."""
    draft = draft_or_404(draft_id)
    where = place_or_422(json.dumps({"ring": body.ring}))
    try:
        drafts.apply(draft, placement_ops(drafts.building(draft), ring=where["ring"], address=body.name))
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    return drafts.state(draft)


def strip_import_images(notes: dict | None) -> dict | None:
    """The import notes without the reference images (they are served by /drafts/{id}/references)."""
    if not notes:
        return notes
    floors = {level: {key: value for key, value in floor.items() if key != "reference"}
              for level, floor in notes.get("floors", {}).items()}
    return {**notes, "floors": floors}


class DraftLocation(BaseModel):
    origin: dict
    bearing_deg: float
    scale: float = 1.0


@app.put("/drafts/{draft_id}/location")
def draft_location(draft_id: str, body: DraftLocation) -> dict:
    """Where the building stands on the map, set by hand (move / rotate / scale over the OSM footprint): one undo
    step of `scale_building` (when the scale changes) + `set_location`. Scale per call within 0.75–1.25."""
    draft = draft_or_404(draft_id)
    if not 0.75 <= body.scale <= 1.25:
        raise HTTPException(422, "scale must be within 0.75–1.25 (the map fit corrects the import's scale by ±25 % at most)")
    try:
        origin = {"lat": float(body.origin["lat"]), "lon": float(body.origin["lon"])}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "origin must be {lat, lon}") from None
    ops = [] if abs(body.scale - 1.0) < 1e-6 else [{"op": "scale_building", "factor": body.scale}]
    building = drafts.building(draft)
    for operation in ops:
        building = apply_op(building, operation)
    previous = building["building"].get("location") or {}
    location = location_for(building, Placement(origin, body.bearing_deg % 360, 1.0, 0.0, False),
                            address=previous.get("address"))
    location["fit"] = {"scale": body.scale, "by_hand": True}
    if previous.get("supersedes"):
        location["supersedes"] = previous["supersedes"]
    try:
        drafts.apply(draft, [*ops, {"op": "set_location", "location": location}])
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    return drafts.state(draft)


@app.get("/drafts/{draft_id}/references")
def draft_references(draft_id: str) -> dict:
    """The import's straightened plan per floor (image data URL + 2×3 px → metres transform) for Edit mode's
    reference panel and trace; empty for buildings that did not come from an import."""
    return {"floors": drafts.references(draft_or_404(draft_id))}


@app.post("/drafts/{draft_id}/proposals/{proposal_id}/cancel")
def cancel_proposal(draft_id: str, proposal_id: str) -> dict:
    draft = draft_or_404(draft_id)
    with builder_lock(draft.id):
        builder = load_builder(draft)
        builder.cancel(proposal_id)
        store_builder(builder)
    return {"cancelled": proposal_id}


@app.post("/drafts/{draft_id}/proposals/{proposal_id}/apply")
def apply_proposal(draft_id: str, proposal_id: str) -> dict:
    draft = draft_or_404(draft_id)
    with builder_lock(draft.id):
        builder = load_builder(draft)
        try:
            builder.apply(proposal_id)
        except EditError as error:
            raise HTTPException(409, str(error)) from None
        store_builder(builder)
    return drafts.state(draft)


@app.post("/v1/chat/completions", response_model=None)
def chat_completions(body: dict, x_session_id: str | None = Header(None)) -> dict | StreamingResponse:
    # The request's `tools` (ElevenLabs system tools) are ignored: UNVERIFIED, not handled yet.
    conversation = store.get_or_create(openai_compat.session_key(body, x_session_id) or DEFAULT_SESSION)
    conversation = with_access(conversation, viewer_or_401(None))  # voice callers are anonymous viewers
    text = openai_compat.last_user_text(body.get("messages") or [])
    model = str(body.get("model") or os.environ.get("GUIDE_MODEL", "building-guide"))

    def reply() -> str:
        if not text:
            return "Sorry, I didn't catch that."
        with conversation.lock:
            turn = conversation.guide.reply(text, channel="voice")  # spoken style for ElevenLabs
            try:
                store.save(conversation)
            except persistence.Conflict:  # mid-stream there is no status code left to send: say it instead
                return "Sorry, I lost track of that. Could you say it again?"
            return turn.spoken or turn.text

    if body.get("stream"):
        return StreamingResponse(openai_compat.stream(reply, model), media_type="text/event-stream")
    return openai_compat.completion(reply(), model)


def viewer_restricted(authorization: str | None, building: str) -> tuple[Viewer, frozenset[str]]:
    viewer = viewer_or_401(authorization)
    known_or_422(building)
    if not access.visible(viewer, building):
        raise HTTPException(422, f"unknown building {building}; see GET /buildings")
    return viewer, access.restricted_for(viewer, building, store.base_data(building))


fleet = Fleet(fleet_from_env(), store.base_data)  # moving objects (access mode): backend/fleet.py
app.include_router(fleet_router(fleet, lambda: access.enabled, admin_or_403, viewer_restricted, known_or_422))
app.include_router(devtools.router(store, conversation_or_404, save_or_409))  # the app's dev panel (backend/devtools.py)
