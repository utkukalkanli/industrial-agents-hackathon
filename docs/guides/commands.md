---
id: guide-commands
summary: Setup and every command for chatting, evaluating on dev, scoring and producing the test submission.
sources: [archive/initial-repo/README.md §5-6, archive/initial-repo/starter_agent/README.md, benchmark/evaluate.py, backend/app.py, agent/run_benchmark.py, agent/run_benchmark_v1.py, agent/guide_v1/__main__.py, SUBMISSION/BENCHMARK.md]
related: [../kit/starter-agent.md, ../challenge/scoring.md]
---

# Commands

[Docs index](../README.md)

All commands run from the **repo root**. Outputs go to `agent_output/` (git-ignored).

## Setup

```bash
uv sync                      # creates .venv with python ≥3.12 (system python3 is 3.9 — too old)
cp .env.example .env         # add ANTHROPIC_API_KEY
```

Without syncing, one-off scripts can run with `uv run --no-project --python 3.12 python …` (stdlib only).

## Starter agent (archived, still runnable)

```bash
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m starter_agent data/dev/proc-factory-dev-003
```

## Evaluate on dev (do this before touching test)

```bash
# warm-up questions, tools only, free (verified 369/369 on 2026-10-24 with kit 1.0.0 answers; not re-run on 1.1.0):
PYTHONPATH=archive/initial-repo uv run python -m starter_agent.evaluate data/dev --oracle
# benchmark questions with the starter agent (~$0.10–0.25/question):
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m benchmark.evaluate data/dev --per-kind 3
# our agent, agent/answer.py (verified 138/138 on 2026-10-24):
uv run --env-file .env python -m benchmark.evaluate data/dev --agent agent.answer:answer
# only some kinds:
uv run --env-file .env python -m benchmark.evaluate data/dev --agent agent.answer:answer --kinds errand what_if_door
```

Results: `agent_output/benchmark/<--name, default results>.jsonl` (question, expected answer, reply, correct).

## Produce the test submission

The graded submission is `SUBMISSION/` (exactly `BENCHMARK.md` + `answers.json`):

```bash
PARSER_MODE=regex uv run python -m agent.run_benchmark_v1 data/test data/test/questions.csv SUBMISSION/answers.json
uv run --env-file .env python -m agent.run_benchmark_v1 data/test data/test/questions.csv submissions/team_jaRAG.csv
# same replies via the kit evaluator (checked identical on 2026-10-24):
uv run --env-file .env python -m benchmark.evaluate data/test --agent agent.answer:answer --submission-csv submissions/team_jaRAG.csv
```

Format rules: [scoring.md](../challenge/scoring.md#submission-format).

## Our deterministic pipeline

```bash
uv run python scripts/validate_solvers.py [--kinds errand] [-v]          # solvers on gold inputs, train+dev
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name dev
PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv agent_output/test_answers.json --csv team_<name>.csv
```

## Backend (Guide API)

FastAPI app in `backend/` wrapping the Building Guide ([ai-agents.md](../architecture/ai-agents.md#implementation--agentguidepy-2026-10-24)).
Without the provider's key (`OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` with `LLM_PROVIDER=anthropic`) it runs the
offline rule-based client; `GUIDE_LLM=offline|openai|anthropic` forces one.

```bash
GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765          # no key needed
uv run --env-file .env uvicorn backend.app:app --port 8765            # real Claude once the key is set
# GUIDE_MODEL (default claude-opus-5-5), GUIDE_EFFORT (default medium), GUIDE_SPEED (default fast; standard = off), GUIDE_BUILDING (default train/proc-campus-train-000)
# voice turns: GUIDE_REWRITER=off disables the transcript rewriter (D-013), GUIDE_REWRITER_MODEL (default claude-haiku-5-5)
curl -s localhost:8765/health
curl -s -X POST localhost:8765/sessions -H 'content-type: application/json' -d '{"building":"train/proc-campus-train-000"}'
curl -s -X POST localhost:8765/chat -H 'content-type: application/json' -d '{"session_id":"<id>","message":"Where is the printer?"}'
curl -sN -X POST localhost:8765/v1/chat/completions -H 'content-type: application/json' -H 'X-Session-Id: demo' \
     -d '{"stream":true,"messages":[{"role":"user","content":"I use a wheelchair"}]}'
uv run pytest -q tests/test_guide.py tests/test_backend.py                      # offline tests
uv run --env-file .env python scripts/live_guide.py [--model claude-sonnet-5-5] [--effort low] [--channel voice]   # live, ~$0.05–0.16
```

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | – | `{"ok", "llm": "anthropic"\|"offline", "tts", "stt"}` — `tts` / `stt`: ElevenLabs voice / Scribe recognition available (see `/tts`, `/stt/token`) |
| GET | `/buildings` | – | `[{"id": "train/proc-campus-train-000", "split", "name"}]` |
| POST | `/sessions` | `{"building"?}` | `{"session_id", "building", "overview"}` (unknown building → 422) |
| GET | `/sessions/{id}` | – | building, profile, applied/pending changes, event count |
| PUT | `/sessions/{id}/building` | `{"building"}` | fresh session on another building, same id |
| PUT | `/sessions/{id}/location` | `{"space_id"}` (or `null` = figure taken away) | `{"location"}` — the app's "you are here" figure; the Guide routes from there ("here") and stops asking where the user is; unknown space → 422 |
| POST | `/sessions/{id}/arrive` | `{"entrance", "destination", "from_session"?}` | `{"route": {reachable, reason, about_m, length_m}, "location", "events"}` — coming over from a nearby building (`route_to_building` → Continue): the user stands at opening `entrance`, the route to space `destination` comes back as events; bad entrance / destination → 422; `from_session`'s routing profile carries over only if this viewer may see that session (same access check), else it is ignored |
| GET | `/sessions/{id}/plan` | – | vector floor plan of the current building (`core/floorplan.py`, gzip) |
| POST | `/chat` | `{"session_id", "message", "channel"?, "photo"?, "heard"?, "selected"?}` | `{"reply", "tool_calls", "events", "ungrounded", "spoken"}` — `channel: "voice"` fills `spoken`; `heard: false` = a tapped button's text on the voice channel: spoken, not rewritten as a transcript (default true); `selected` = the space or asset id tapped on the plan while asking → a selection note for the Guide; `photo` = base64 data URL (jpeg/png/webp, ≤1.5 M chars), shown to the Guide for this turn only |
| POST | `/chat/stream` | same as `/chat` | NDJSON: `{"type":"step","kind":"tool"\|"tool_done"\|"check",…}` while the Guide works, then `{"type":"reply",…/chat payload}` or `{"type":"error","code","message","detail"}` (`message`: a sentence to show — e.g. the Claude API credit ran out; `code` ∈ credits, auth, busy, unavailable, offline, internal, conflict; `backend/service_errors.py`; plain `/chat` answers 503/429 with `{"detail": message, "code"}`); voice turns also send `{"type":"say","text"}` per sentence as soon as it may be spoken (grounding-checked, all before `reply`, together the whole spoken reply — `agent/speech.py` `SpokenStream`) |
| GET | `/events` | `?session_id=&after=N` | `{"events": [...since N], "next"}` — UI highlights, routes (with turn-by-turn `legs` and the Guide's followable `steps` — turn, rounded metres, door, landmark, text — both `core/directions.py`), changes |
| POST | `/drafts` | `{"base"}` (catalogue id) | Edit mode: new draft copy → `{"draft": {id, base, name, steps}, "building", "issues"}` (unknown base → 422) |
| GET | `/drafts/{id}` | – | same shape (unknown / malformed id → 404) |
| GET | `/drafts/{id}/plan` | – | vector plan of the draft (`core/floorplan.py`, what `PlanView` draws), centred on the base building |
| POST | `/drafts/{id}/ops` | `{"ops": [{"op": …}]}` (`core/edits.py`) | applied as one undo step → same shape; bad op → 422 with the reason |
| POST | `/drafts/{id}/chat/stream` | `{"message"}` | Builder agent turn (prompt edits) as NDJSON: `step` lines, then `{"type":"reply","reply","tool_calls","proposal" (id, summary, ops, new_problems, effect, `building` = draft after the ops) or null,"applied","state"}`; a plain "yes" applies the one open proposal; offline (`GUIDE_LLM=offline` / no key) a rule-based client understands rename / "make X N m wider to the east" / "add a door between X and Y"; model `BUILDER_MODEL` (default `claude-opus-5-5`), `BUILDER_EFFORT` |
| POST | `/drafts/{id}/proposals/{pid}/apply` | – | apply an open proposal → draft state; unknown or made against an older draft → 409 |
| POST | `/drafts/{id}/undo` | – | drops the last step (nothing to undo → 409) |
| POST | `/drafts/{id}/save` | `{"name"}` | `{"building": "user/<slug>", "issues"}` — written to `GUIDE_USER_DIR` (default `data/user/`, gitignored), listed in `/buildings`; name clash → `-2` |
| POST | `/imports/stream` | multipart `files` (PDF / images incl. HEIC; ≤ 20 files, ≤ 25 MB each, else 413; at most 40 pages / images read, the rest named in a `warning`; access mode: admin only, like `/drafts`; closing the stream stops the Creator; optional form fields `place` = JSON `{"ring": [[lon, lat], …]}` (the tapped OSM building) or `{"point": [lon, lat]}`, `device` = JSON `{"lat", "lon"}` (the browser's position, used when no photo carries EXIF GPS), `levels` = JSON list, the floor of each file as the user typed it (one per file, all different; a PDF's later pages count up; else 422) and `draft` = an open draft's id (Edit mode's "Add a floor": the new floors go into it as one undo step, edit op `add_floors`, walls kept parallel; a level it already has → 422 before the Creator runs)) | the Creator (`agent/creator.py`, `CREATOR_MODEL` default `claude-opus-5-5`, `CREATOR_EFFORT`) builds a building from floor plans, as NDJSON: `warning` per unreadable file, `step` lines (`say` / `tool` / `tool_done`), then `{"type":"done","draft_id","base":"import/<id>","name","issues","notes","location","located_by" ("tap" / "photos" / "device" / null),"suggestion" (the photos point > 50 m from the tapped building: `{ring?, name, point?}`)}` / `no_plan` / `error`; the draft opens in the Edit mode, the base is private until saved |
| DELETE | `/buildings/user/{slug}` | – | delete a saved building (access mode: admin only); the file store moves it to `GUIDE_USER_DIR/.deleted/`; a version it superseded comes back to the map; dataset buildings / unknown → 404 |
| GET | `/drafts/{id}/references` | – | the import's straightened plan per floor for Edit mode's reference panel / trace: `{"floors": [{"floor_id","level","image" (JPEG data URL ≤ 1600 px),"transform" (2×3 px → building metres, y up)}]}` (`[]` for kit buildings); never inside other payloads |
| PUT | `/drafts/{id}/location` | `{"origin": {"lat","lon"},"bearing_deg","scale"}` (scale 0.75–1.25, else 422) | the building's map position by hand (`core/geoplace.py`): `scale_building` (if ≠ 1) + `set_location` as one undo step → draft state; `fit = {"scale","by_hand": true}` |
| POST | `/drafts/{id}/fit` | `{"ring": [[lon, lat], …],"name"}` | fit the draft onto an OSM footprint (principal axes + IoU descent, scale clamped 0.75–1.25, `low_confidence` when IoU < 0.5 or at a bound) → draft state |
| POST | `/v1/chat/completions` | OpenAI body, `stream` | OpenAI-compatible (SSE: `"... "` first, then sentences, `data: [DONE]`) for an ElevenLabs Custom LLM |
| POST | `/tts` | `{"text", "lang"?}` (≤ 1,000 chars after `speakable()`) | the Guide's voice: ElevenLabs MP3 (`audio/mpeg`, `backend/tts.py`); no `ELEVENLABS_API_KEY` → 503, ElevenLabs refused → 502, empty → 422, too long → 413 — the app then uses the browser voice. `/health` says `"tts": true` when the key is set. `TTS_VOICE_ID` / `TTS_MODEL` override voice "River" / `eleven_flash_v2_5` |
| POST | `/stt/token` | `{"session_id"?}` | `{"token", "keyterms"}`: a single-use ElevenLabs Scribe Realtime token (15 min, one connection) and ≤ 50 keyterms (≤ 20 chars) from the session's building (`backend/stt.py`); the browser then streams the mic to Scribe itself (`voice/scribe.ts`). Scribe off (`STT_MODE=browser` or no key) → 503, ElevenLabs refused → 502, unknown session → 404 — the app then uses browser recognition. `/health` says `"stt": true` when it is on |

`/v1/chat/completions` uses only the last user message (the Guide keeps its own history). Session id, first
match wins: body `session_id`, `elevenlabs_extra_body.session_id`, header `X-Session-Id`, body `user`; none → a
shared `default` session. How ElevenLabs actually sends it, and its system `tools`, are UNVERIFIED
([elevenlabs.md](../research/elevenlabs.md)). Sessions are in memory unless
`SUPABASE_DB_URL` is set (see below).

### Conversation persistence (Supabase Postgres)

With `SUPABASE_DB_URL` in `.env` (the **Transaction pooler** URI, port 6543; the direct `db.<project>.supabase.co`
host is IPv6-only and doesn't resolve here) every conversation is stored in the `conversations` table and every turn
is saved, so any backend instance can continue it ([backend/persistence.py](../../backend/persistence.py)).
`GUIDE_PERSIST=off` forces in-memory sessions. A save that loses a race to another instance → HTTP 409.

```bash
uv run --env-file .env uvicorn backend.app:app --port 8765                     # persisted sessions
uv run pytest -q tests/test_persistence.py                                     # offline (two stores, one fake DB)
PERSIST_LIVE_TEST=1 uv run --env-file .env pytest -q tests/test_persistence.py  # + live round trip on Supabase
```

Schema changes go in `supabase/migrations/` (idempotent SQL). Apply one with:

```bash
uv run --env-file .env python -c "import os,sys,psycopg; psycopg.connect(os.environ['SUPABASE_DB_URL'], autocommit=True, prepare_threshold=None).execute(open(sys.argv[1]).read())" supabase/migrations/<file>.sql
```

### Access mode (demo: accounts, restricted spaces, preferences, moving objects)

Off unless `ACCESS_MODE=on`; off = every endpoint as above. Design:
[access-profiles-design](../superpowers/specs/2026-10-25-access-profiles-design.md). Needs `SUPABASE_URL`,
`SUPABASE_ANON_KEY` (sign-in), `SUPABASE_SERVICE_ROLE_KEY` (invite links) and `ADMIN_EMAIL` (admin emails, comma-separated);
tables in `supabase/migrations/20261025200000_access.sql` (in memory without `SUPABASE_DB_URL`). Requests carry
the Supabase access token as `Authorization: Bearer …`.

```bash
ACCESS_MODE=on uv run --env-file .env uvicorn backend.app:app --port 8765
uv run pytest -q tests/test_access.py tests/test_fleet.py                     # offline, fake sign-in
uv run python scripts/sim_object.py --api http://localhost:8765 --object <id> --token <device token>
```

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/config` | all | `{"access_mode"}` (+ Supabase URL / anon key when on) |
| GET | `/me` | all | viewer (`admin`, `anonymous`) + member groups per building |
| GET/PUT | `/me/preferences` | signed in | stored preferences (anonymous users keep theirs in the browser) |
| PUT | `/sessions/{id}/preferences` | all | `{"values", "auto_capture"}` → the session's profile + talking preferences |
| GET/PUT | `/access/building` | admin | public flag, room-type / space rules (groups; `public` = exception) |
| GET/PUT | `/access/members`, POST `/access/invite` | admin | members' groups; invite → sign-in link, no email sent |
| GET | `/objects?building=` | all | moving objects: position, trail, mission + its `line` (objects in spaces the viewer may not enter left out) |
| POST/PUT/DELETE | `/objects`, `/objects/{id}`, POST `/objects/import-forklifts` | admin | create (returns the device `token` once), edit, delete, forklifts from `equipment.csv` |
| POST/DELETE | `/objects/{id}/mission` | admin | dispatch `{"destination"}` / cancel |
| POST | `/objects/{id}/position`, GET `/objects/{id}/mission`, POST `.../mission/done` | device (`X-Object-Token`) | report position, fetch machine steps, finish |

`/drafts` (Edit mode) answers 403 for anyone but the admin while access mode is on.

## Frontend app

```bash
GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765    # or: uv run --env-file .env uvicorn … (real Claude)
cd frontend/app && npm install && npx vite --port 5181          # open http://localhost:5181 (?building=<id>)
cd frontend/app && npm run build                                # type-check + production bundle in dist/
```

**Edit mode** (ruler-pencil button in the building screen's right-hand controls): edits a draft copy of the current
building on a 2D plan, with the building's 3D model (`PlanView` fed by `GET /drafts/{id}/plan`) as a live preview —
click a room and drag its corners, drag doors along walls, drag things (R / Shift+R rotates), ⌘Z undoes; problems
are listed bottom-left; **Done** goes back (the draft is kept); **Save** writes `user/<slug>` (local `data/user/`,
or `GUIDE_USER_DIR`) and opens it as a new building (fresh Guide session, a note says it is the edited building).
The chat on the right edits by prompt (the Builder agent): it proposes, the plan shows the proposal dashed in
blue with its area changes and new problems, **Apply** (or typing "yes") applies, **Cancel** drops it. Live check of
the agent: `uv run --env-file .env python scripts/live_builder.py [building_id] [--model …] [--effort …]`.
The draft id is kept in `localStorage` per building. Without `SUPABASE_DB_URL` drafts and saved buildings are files
under `data/user/`; with it (`uv run --env-file .env uvicorn …`, and on Vercel) they live in Postgres — tables from
`supabase/migrations/20261025120000_builder_drafts.sql`, applied with the command in
[Conversation persistence](#conversation-persistence-supabase-postgres) (milestone 3). Tests:
`uv run pytest -q tests/test_draft_backends.py` (two instances, one fake DB); live:
`PERSIST_LIVE_TEST=1 uv run --env-file .env pytest -q tests/test_draft_backends.py -k live`.

Vite proxies `/api/*` to the backend (`BACKEND_URL`, default `http://127.0.0.1:8765`). Design and data path:
[visualization.md](../product/visualization.md#app-and-data-path).

### Plan import (Creator)

```bash
uv run --env-file .env python scripts/live_creator.py <file|folder>... [--out building.json] [--images DIR]  # live run, steps + tokens
uv run python scripts/eval_import.py --segment-only [--n 30] [--method walls|colours]   # free: segmentation vs dataset renders
uv run --env-file .env python scripts/eval_import.py --full [--n 10]                    # the Creator on dataset renders
```

In the app: "New building from floor plans" on the map, or "New from floor plans" in the list (`?view=import`) →
`POST /imports/stream` → the building screen on the private base, opened in the Edit mode (`?building=import/<id>&edit=1`). Locally without the database: `GUIDE_PERSIST=off` (the `builder_imports` table
from `supabase/migrations/20261025180000_builder_imports.sql` must be applied before imports work with
`SUPABASE_DB_URL`). Tests: `uv run pytest -q tests/test_plan_import_*.py tests/test_creator*.py tests/test_import*.py`.

## Dev panel

Part of the app (`frontend/app/src/dev/`, backend `/dev/*` in `backend/devtools.py`): try every Guide capability
by hand, without an LLM — find places and items, directions, routing profiles, closures and new doors with their
impact, plan display switches, a log of every call. Shown in the Vite dev server (`npx vite`), or in a build with
`?dev` in the URL; open it with ` (backtick) or the wrench. No extra server or port. What it shows:
[visualization.md](../product/visualization.md#dev-panel).

## Deploy (Vercel)

One Vercel project, two [Services](https://vercel.com/docs/services) in [`vercel.json`](../../vercel.json) (D-006):
`web` = the Vite app in `frontend/app/`, `api` = FastAPI `backend.app:app` from the repo root. The rewrite
`/api/(.*)` → `api` keeps the `/api` prefix in the path, so `backend/app.py` strips it (`StripPrefix`); everything
else goes to `web`. The function excludes everything the backend doesn't read (kept: code, `data/**/building.json`,
`data/manifest.csv`, about 49 MB plus packages). `maxDuration` is 300 s, the Hobby maximum.

Atahan (once): Vercel → *Add New → Project* → import the GitHub repo. Leave Root Directory at the repo root
(`vercel.json` defines the services). Add the env vars below under *Settings → Environment Variables*. Deploy.

| Var | Value |
|---|---|
| `ANTHROPIC_API_KEY` | the Claude key when the provider is `anthropic` (without the provider's key the Guide runs the offline rules) |
| `SUPABASE_DB_URL` | Transaction pooler URI (port 6543), same as `.env` |
| `GUIDE_MODEL` / `GUIDE_EFFORT` | optional (defaults `claude-opus-5-5` / `medium`; Sonnet + `low` is cheaper and faster) |
| `LLM_PROVIDER` | optional: `openai` or `anthropic` (unset → `anthropic` only when `ANTHROPIC_API_KEY` is the only key set, else `openai`); every LLM part uses it ([D-024](../../memory-bank/decisions.md#d-024)) |
| `OPENAI_API_KEY` | the OpenAI key when the provider is `openai` (the default); without it requests fail with the readable `auth` error unless the Guide is offline |
| `OPENAI_MODEL` / `OPENAI_MID_MODEL` / `OPENAI_SMALL_MODEL` | optional: the OpenAI models for Claude opus / sonnet / haiku ids (defaults `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-luna`) |
| `OPENAI_SERVICE_TIER` | optional: the tier of the big (opus-mapped) model's calls; default `ultrafast` on `gpt-6.1-sol` / `gpt-6-astra` (same model, faster output), `default` turns it off |
| `GUIDE_SPEED` | optional: `fast` (default — Opus fast mode, same model, ~2× faster turns, 2× token price) or `standard` |
| `CORS_ORIGINS` | optional; the frontend is same-origin, so it isn't needed |
| `ELEVENLABS_API_KEY` | the Guide's ElevenLabs voice (`/tts`); without it the app speaks with the browser voice |
| `TTS_VOICE_ID` / `TTS_MODEL` | optional (defaults "River" `SAz9YHcvj6GT2YYXdXww` / `eleven_flash_v2_5`) |
| `STT_MODE` | optional: `scribe` (default with the key) or `browser` (keep the browser's speech recognition) |

Smoke test after a deploy: `curl -s https://<deployment>/api/health` → `{"ok":true,"llm":"anthropic","tts":true,"stt":true}`. Then
in the app, say "I use a wheelchair" and ask for a route in the next message: the route must be step-free (proof
that persistence works across instances). Edit mode: open a building → Edit → drag a corner → reload (the draft
resumes) → prompt "make <room> 1 m wider to the <side>" → Apply → Save → the saved building opens and the Guide
routes in it; `/drafts` needs the database on Vercel (read-only filesystem). `uv run pytest -q tests/test_deploy.py`
checks the config locally.
UNVERIFIED until the first deploy: Services (beta) with a service root of `./` next to `frontend/app/`, the
exclude globs as Vercel applies them, cold-start time.

## v1 Guide and pipeline (terminal)

Scripted conversations (`tests/guide_conversations/*.json`) run against the canonical Guide (`agent/guide.py`):

```bash
# live API: PASS/FAIL per turn + seconds + cost, exit 1 on a failure; --model / --effort override GUIDE_MODEL / GUIDE_EFFORT
uv run --env-file .env python scripts/eval_guide.py [tests/guide_conversations/lift_closure.json ...] [--model claude-sonnet-5-5 --effort low]
# offline checks of the conversation files and of the checker (no API)
uv run pytest tests/test_guide_conversations.py -q
```

Interaction eval: a simulated tricky user (Claude, playing a scenario from `tests/interaction_scenarios/*.json`) talks
to the Guide, then an LLM judge scores the conversation 1–5 with the brief's Interaction rubric (asks only what it
needs, shows what it understood, followable directions, remembers context) plus goal reached. Live API, ~$0.1–0.3
per scenario; transcripts + verdicts in `agent_output/interaction_eval/`.

```bash
uv run --env-file .env python scripts/interaction_eval.py [tests/interaction_scenarios/first_day_coffee.json ...] \
    [--repeat 3] [--model claude-sonnet-5-5 --effort low] [--user-model …] [--judge-model …]
uv run pytest tests/test_interaction_eval.py -q   # offline (fake client + offline Guide)
```

The second Guide (`agent/guide_v1/`, branch `1-agentic-yarag`) and its benchmark pipeline (`agent/answer.py` →
`core/solvers_v1.py`) sit beside the canonical ones; the backend and UI use `agent/guide.py`.

```bash
# terminal REPL (multi-turn, remembers position / step-free / closures); --show-tools prints each tool call
uv run --env-file .env python -m agent.guide_v1 data/dev/proc-campus-dev-001 --show-tools
# v1 benchmark run: .csv (submission) or .json (reply + ids + solver result + route) out
uv run --env-file .env python -m agent.run_benchmark_v1 <building_dir> <questions> <answers.csv|answers.json>
```

Design: [guide-agent spec](../superpowers/specs/2026-10-24-guide-agent-design.md). A full eval run costs about $0.27.

## Sunday benchmark

`uv run python -m agent.run_benchmark_v1 <building_dir> <questions file> SUBMISSION/answers.json` (default `hybrid`:
templates first, the LLM only for unseen wording; `.env` is read automatically; `--layout dict` keys the .json by
question id) — documented in [`SUBMISSION/BENCHMARK.md`](../../SUBMISSION/BENCHMARK.md) (v1 is the submission
pipeline: it also answers the warm-up kinds, routes included; `agent.run_benchmark` has no solvers for them). Do not
use `PARSER_MODE=regex` on Sunday: on 14 reworded questions it answered 1 (2026-10-25). A failing question becomes an
`error` entry and the run goes on; the file is rewritten after every question. Model decisions go to
`llm_cache/decisions.json` (keyed per provider: OpenAI keys carry `@openai`) — **commit it together with
`SUBMISSION/answers.json`**, so a re-run without a key (provider defaults to OpenAI) reproduces the answers ([ai-agents.md](../architecture/ai-agents.md#sunday-layers-route-specs-solver-agent-decision-cache-2026-10-25)).
Probe of the agentic layers: `uv run python scripts/eval_sunday_probe.py` (`tests/sunday_probe/`, calls Claude). Output format still unannounced →
[Q-001](../../memory-bank/open-questions.md#q-001).

## Related
- [starter-agent.md](../kit/starter-agent.md#evaluation) · [scoring.md](../challenge/scoring.md) · [ai-agents.md](../architecture/ai-agents.md)
