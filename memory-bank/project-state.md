---
id: project-state
summary: Current phase, what exists, what works, next priorities, blockers. Read first every session.
updated: 2026-10-25
related: [decisions.md, open-questions.md, log.md, ../docs/architecture/solver-plan.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-27** (Guide on Opus fast mode by default, `GUIDE_SPEED`; shared solvers nearest_item / lift_closed / add_door, destination-only spaces and docks — organisers' eval 0.885; before that, 2026-10-25: buildings from plans get a reference panel + trace in Edit mode and a real map position — right-click "Create a building here", OSM fit, EXIF GPS / browser position, Edit position, supersede on re-save; branch `7-buildings-from-plans` (started as `6-plan-reference-location`), [D-023](decisions.md#d-023); before that: step guide faces the step + animated route band, step card and Guide in sync via `route_step` / `show_route_step`, `find_nearest` tool, route line from the figure, calmer voice, map building tones, round-button system — shipped on `dev`; before that: building screen "Quiet HUD" steps 1–5 with the pulls of `origin/dev` 26b908f + b352e83)

## Phase

**Phase 1 ✅ · Phase 2 ✅ (dev 138/138) · Phase 3 ✅ · Phase 4 — UI ✅ first version (`frontend/app/`), voice next**

Planned phases (proposal, see [overview.md](../docs/architecture/overview.md)):

| Phase | Goal | Done when |
|---|---|---|
| 0 Foundation | docs, memory bank, CLAUDE.md | ✅ 2026-10-24 |
| 1 Core + solvers | per-kind solvers verified on train+dev `inputs` | ✅ 2026-10-24 — 655/655 |
| 2 Benchmark runner | question text → solver → `Answer:` reply; dev score via `benchmark.evaluate`; test CSV | ✅ 2026-10-24 — dev 138/138, `agent.run_benchmark`, [BENCHMARK.md](../SUBMISSION/BENCHMARK.md) |
| 3 Agent + interaction | conversational agent with clarifications, directions, closures, edits | scripted tricky-user conversation works — ✅ 2026-10-24 offline (`tests/test_guide.py`) + live (`scripts/live_guide.py`) |
| 4 App/UI + voice | 2D view with route, then stacked floors; voice | demoable |
| 5 Build + extend | plan → building (L4), one add-in (L5) | demoable |
| 6 Submission | `SUBMISSION/` (`BENCHMARK.md` + `answers.json`, v1), Sunday run, video, tech explanation | submitted before code freeze — `SUBMISSION/` ✅ 2026-10-25 with test-set answers; Sunday run pending |

## What exists

- Repo root is the build root ([D-004](decisions.md#d-004)): `core/` (building_map from the kit + question_parser),
  `benchmark/` (official scorer), `data/` (committed, [D-005](decisions.md#d-005)), `tests/`, `pyproject.toml` (uv,
  pytest dev dep). Kit remainder in `archive/initial-repo/`.
- Knowledge base: [docs/](../docs/README.md) incl. architecture, agents, personas, routing profiles, research.
- App visuals: landing = map of the 17 buildings with a real position (`frontend/app/src/map/`, positions in
  `backend/locations.json`) + list view for all 280 (`src/search/`); building = vector plan view
  (`frontend/app/src/plan/`, `core/floorplan.py`); the point-cloud prototype and
  scene moved to the gitignored `.viz-archive/`, see [visualization.md](../docs/product/visualization.md).
- Buildings from plans on the map (2026-10-25, [D-023](decisions.md#d-023),
  [design](../docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md)): right-click card on the map
  starts an import at a building / spot; one floor per file at the floor number the user types; the result is fitted
  onto the OSM footprint (`core/geoplace.py`, `core/osm_lookup.py`, tile fallback), placed by EXIF GPS / browser
  position without a tap, adjusted by hand (`src/map/Placement.tsx`) and saved with `building.location`; re-saving
  supersedes, the card deletes saved buildings. Edit mode: the kept plan beside the editor (movable window) and as an
  adjustable trace; "Add a floor" (walls kept parallel), "Straighten this floor", "Edit position". Not done: Postgres
  delete / supersede tests, merging tile-cut OSM pieces, a final whole-branch review.
- Map → building (2026-10-25): the map stays under the building screen, flies in, then follows the model's camera
  (`src/map/bridge.ts`); plan preloaded on the tap (`src/building/opening.ts`), model rises in; menu toggle "in the
  city" (default, neighbour pins tappable) / "alone"; buildings with a model drawn as blue blocks on the map; new
  light map palette ([visualization.md](../docs/product/visualization.md#current-vector-plan-view-2026-10-24)).
  Since: buildings refitted onto their OSM ways (`scripts/fit_locations.py`, 12 shifted, 5 partial models kept),
  open with all floors, transition plays with "reduce motion" on, map field of view 1° + model tilt ≤ 60° over the map
  (≤ 10 px apart). City view refinements: open building's map blocks drawn as a wireframe in the model's scene,
  no z-fighting under the blue blocks, an x-ray cut-away of blocks in front (`src/map/neighbours.ts`), roads at estimated real widths, a ground line plus an underground veil
  over basements, and Back flies the map to where it was when the building was opened.
- Building screen, 2026-10-25 later chunk ([log](log.md)): new Guide tools `find_nearest(start, query, floor_id?)`
  (nearest room with an item kind / room kind by route length under the profile, one route + highlight, `nearest` +
  `next_nearest`; in `PROFILE_TOOLS`, the prompt sends "nearest/closest X" to it without asking) and
  `show_route_step(step)` (1-based card numbering, `route_step` event). `/chat` and `/chat/stream` take `route_step`
  (the card's 0-based step) and the Guide gets a `[route note]` with the card's steps
  ([ai-agents.md](../docs/architecture/ai-agents.md)). `PUT /sessions/{id}/location` takes the figure's `point`
  (kept only inside the room; a move within the same room queues no new location note) and route events carry
  `start_point`; `core/routeline.py` `route_line(..., start=)` starts the drawn line there and drops doors between
  overlapping spaces (route lengths unchanged). Step moves turn the map to the step; the route band animates.
  Voice: voice gate on the level meter, end pause 1700 ms (2800 ms after an open ending), steadier barge-in. Map:
  touching kit buildings in different tones, hover lights pin + block, `model-edges` outline layer. Buttons: one
  round system, heights `--btn-sm/md/lg` (32/36/44 px) across `hud.css`, `access.css`, `edit.css`. Not tried with a
  live mic; button restyle and light-mode map tones not checked visually.
- Licensing: `LICENSE` (MIT, our code only), `NOTICE.md` (third-party paths + terms), `data/README.md`
  (per-source data licences) — [D-009](decisions.md#d-009) accepted.
- Verified-commit workflow in `.claude/` (verifier + fixer agents, `/ship` skill, commit-gate hook, worklog) —
  [D-008](decisions.md#d-008), [dev-workflow.md](../docs/guides/dev-workflow.md).
- Git: `origin` = https://github.com/utkukalkanli/industrial-agents-hackathon.git, the only remote (2026-10-27:
  fork detached on GitHub, `upstream` = atahankilc/industrial-agents-hackathon removed locally; first commit
  `3300e6c` was pushed there). Working branch: `7-buildings-from-plans` (tracks `origin/7-buildings-from-plans`).

## What works (verified 2026-10-24)

- **Chat Guide + Sunday layers (2026-10-25, branch `4-sunday-agent`, after merging dev c3ab8f0):** `compute` tool
  (Python sandbox; its `route()` = `find_route`'s rules and profile), `find_nearest` with `closed` + shortlist,
  readable Claude API errors (`backend/service_errors.py`, app note + voice). New vs old dev Guide: capability set 5/5
  vs 3/5, eval_guide 18/18 vs 17/18, interaction judge mixed within noise (log 08:30).

- **Plan import / Creator (branch `3-plan-import`, worktree `.claude/worktrees/3-plan-import`, in progress,
  2026-10-25):** create a building from floor-plan PDFs / photos —
  [spec](../docs/superpowers/specs/2026-10-25-plan-import-design.md) (approved by Utku),
  [plan](../docs/superpowers/plans/2026-10-25-plan-import.md). Built: deterministic core `core/plan_import/` (ingest
  incl. HEIC, rectify / crop / wall mask, cells by walls / colours / boxes, labels with stable door numbers, scale,
  stacking with scale search + name joins, assembly + autofix + validate); the Creator (`agent/creator.py` +
  `agent/creator_tools.py`, 11 tools); private import drafts (`import/<id>`; migration
  `20261025180000_builder_imports.sql` applied to Supabase 2026-10-25 by Utku, table + RLS checked); `POST /imports/stream`; the "Create from floor plans" screen
  (`frontend/app/src/import/`, checked in headless Chrome); `scripts/eval_import.py`, `scripts/live_creator.py`.
  New deps: numpy, opencv-python-headless, pypdfium2, pypdf, pillow, pillow-heif, python-multipart (no PyMuPDF, D-009).
  Measured live (Opus 5.5, logs in the worktree's `.superpowers/runs/`): dataset eval (8 floors) count ratio 0.97,
  IoU 0.91, doors 89 %, ≈ $1.09; Urban Colab photos 5 floors / 104 spaces / 23 errors, all floors joined by stairs +
  lift, ≈ $1.73 (≈ $4.80 before the prompt-cache fix); Residenz 2 floors / 56 spaces / 0 errors; Rathaus 59 spaces /
  0 errors, ≈ $0.35; Projektsteckbrief → no_plan in 10 s. origin/dev (`ed7e974`, new UI) merged into the branch
  (dev as the base, Utku 2026-10-25): the import now opens the building screen on `import/<id>` straight into the new
  Edit mode (`?edit=1`, `BuildingScreen` `startEditing`); sessions open private import bases; checked in headless
  Chrome (upload → Creator → Edit mode "No problems"; Urban Colab draft with "23 problems"). Plan done (Tasks 1–14): cross-floor
  routes on the Urban Colab result (stairs; step-free via lift), Builder fix → Save → `user/munich-urban-colab` with a
  route F0 → F4; final review (opus) fixes in (imports admin-only in access mode, no silent merges, bar scales kept,
  cancel on leave, PDF limits); spec status built; Q-018 note. Local `dev` fast-forwarded to the branch
  (`99e6203`, not pushed); migration applied. **Next:** push `dev` to origin when Utku says so; deferred minors. Deferred minors in the log. Demo inputs in the main checkout's
  `building_plans/` (not committed).

- **Sunday agentic layers (2026-10-25, branch `4-sunday-agent`, [D-022](decisions.md#d-022) proposed):** P0 committed
  (`b1805d4`: crash-safe runner, hybrid Sunday command, top-level ids in `answers.json`). P1: LLM route spec →
  `core/route_query.py` (closures of any element, item / room-type endpoints with the nearest taken, stops,
  step-free + forklift + min width combined), `asks_for` check, kind `other` → solver agent
  (`agent/solver_agent.py`, Python sandbox, 2 runs + tie-break, effort `medium`), decision cache
  `llm_cache/decisions.json` (`agent/llm_cache.py`). Probe `scripts/eval_sunday_probe.py`: **14/14** (old pipeline
  ~7/14; agent only for the 3 new kinds), and 14/14 identical when replayed with no API access. Test-set answers
  byte-identical. `origin/dev` merged into the branch (PR #2 into `dev`, pushed 2026-10-25).
- **Guide on the plan, figure, step guide, nearby buildings (2026-10-25, D-020/D-021, not committed yet):** answers
  tint + label + frame their rooms and items; draggable "you are here" figure (the Guide routes from "here"); routes
  framed whole, then Start → step by step with "I'm there"; `search_nearby_buildings` / `route_to_building` for the 17
  located buildings with Continue into the next building (`agent/campus.py`, `building/Elsewhere.tsx`).
  `tests/test_campus.py`; headless Chrome check of figure + highlight (log 2026-10-25).

- **Access mode (2026-10-25, D-015, `ACCESS_MODE=on`, off by default):** design
  [access-profiles-design](../docs/superpowers/specs/2026-10-25-access-profiles-design.md), plan
  [access-profiles](../docs/superpowers/plans/2026-10-25-access-profiles.md). Backend all four phases built and
  tested offline (`tests/test_access.py`, `tests/test_fleet.py`; full suite 770 passed, 2 skipped; dev benchmark 138/138):
  accounts (Supabase Auth, admin = `ADMIN_EMAIL`, invite links), restricted spaces (filtered building copy,
  `solve` included, plan `restricted`), remembered preferences (soft penalties, `set_preference`, `preference`
  events), moving objects (`/objects`, device tokens, missions, `scripts/sim_object.py`, Guide `send_object`).
  Frontend done (`frontend/app/src/access/`, `plan/ObjectsLayer.tsx`): sign-in, darkened spaces, Preferences,
  Building settings (My preferences / Access / Members / Objects), live object markers — checked headless with a
  fake sign-in. Migration `20261025200000_access.sql` applied 2026-10-25 (Postgres stores round-trip verified live).
  2026-10-26: admin account ✅ (one Auth user = `ADMIN_EMAIL` in the new Supabase project); `ADMIN_EMAIL` set in Vercel
  production/preview; `ACCESS_MODE` was on there briefly and removed again (23:43): production runs with access mode
  off so the demo shows create / edit to everyone.
  **Not yet:** a real Supabase sign-in on the app (untested), invite redirect URLs in Supabase, `/events`
  polling (voice turns' preferences are not captured).

- **Builder Edit mode (branch `2-builder-edit`, in progress):** design
  [builder-edit-mode-design](../docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md) (proposed, approved by
  Utku 2026-10-24), plan [M1](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md). Done: Task 1
  `core/edits.py` — ops add/delete/set space, add/move/set/delete opening, add/move/set/delete asset, replay via
  `apply_steps` (`tests/test_edits.py`). Task 2: `move_vertex` / `set_polygon` keep shared walls (overlapped
  neighbours shrink, refused if one would vanish; doors re-projected; thick Swiss walls handled). Task 3:
  `core/validate.py` — `validate(building, base)`, issues already in the base are warnings
  (`scripts/validate_dataset.py`, `tests/test_validate.py` over all 280 buildings). Task 4: `backend/drafts.py`
  (`DraftStore`, local `data/user/`, gitignored) + `/drafts` endpoints (create, get, points, ops, undo, save →
  `user/<slug>` in `/buildings`, Guide routes in it; `tests/test_drafts.py`). Tasks 5–7: frontend Edit mode
  (`frontend/app/src/edit/`: View/Edit switch, SVG plan editor, 3D inset, issues, undo, save → View + Guide);
  verified in headless Chrome (offline Guide): corner / door / asset drags, rotate, 4× undo, save → route 99 m in
  `user/forschungsbau-edited`. **M1 done**; final review (opus) fixes: shared corner into a corridor, neighbours
  grow when a room shrinks, per-draft lock + client gating. M2 plan written
  ([m2](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m2.md)). `origin/dev` merged (`ebcdb3d`, Atahan's new
  UI); Edit mode re-homed: "Edit this building" in `BuildingScreen`'s "…" menu (2026-10-25, was a round button) → `EditMode` full screen, 3D inset = `PlanView`
  of `GET /drafts/{id}/plan`, Save opens `user/<slug>` via `Root`; verified in headless Chrome.
- **Builder M2 (prompt edits), in progress:** Task 1 `move_edge` op + `edge_sides` (walls with compass sides),
  malformed op arguments → EditError (422); Task 2 `agent/builder_tools.py` (overview, find, space_info,
  floor_plan, propose_edit — dry run + effect + new problems, never applies). Task 3 `agent/builder.py` (tool
  loop, "yes" applies the one open proposal without a model call, Apply-button / hand-edit notes, grounding repair,
  stop after 2 failed proposals) + `agent/builder_offline.py` (rename / resize / door rules); Task 4
  `/drafts/{id}/chat/stream` + `/drafts/{id}/proposals/{pid}/apply` (stale → 409). Task 5 frontend
  (`edit/BuilderChat.tsx`, ghost overlay in `PlanEditor`, Apply / Cancel, examples from the building's rooms);
  headless Chrome offline + live Opus check (`scripts/live_builder.py`, ~$0.08 for 3 prompts + $0.03 follow-up).
  **M2 done**; review (opus) fixes: a proposal is confirmable only by the very next message (another turn,
  Cancel — new `/proposals/{pid}/cancel` — or a hand edit closes it), only a bare "yes"/"ok" skips the model, text
  fields in ops are coerced to strings, a proposal made against a draft that changed meanwhile is not sent.
  Edit mode restyled to the building screen's design (clay palette, cards, floor tabs). **2026-10-25 (not
  committed):** Edit mode now lives inside the building view — the model shows the draft, handles sit on it
  (`edit/EditLayer.tsx` + PlanView `align`), the edit card replaces the Guide card (tools, Inspector, Builder, save)
  ([log](log.md#2026-10-25--edit-mode-inside-the-building-view-not-committed)).
- **M3 (deployed store) built by us** (Utku took it back from Atahan 2026-10-24, not started;
  [m3 plan](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m3.md), decisions in the spec's "Milestone 3
  decisions"): drafts, saved buildings (shared with everyone) and the Builder's conversation in Supabase
  (`builder_drafts`, `saved_buildings`, migration applied), version-checked (409), DB down → `/drafts` 503. Verified:
  pytest 746 passed, live Supabase tests, two local instances on Supabase end to end. **Next: Task 6 — deploy and the
  public smoke test** (commands.md Deploy section): the branch preview builds, but Vercel Authentication protects it
  — waiting for a Protection Bypass secret from Atahan (`VERCEL_AUTOMATION_BYPASS_SECRET` in `.env`).
- **Order (Utku, 2026-10-24):** `2-builder-edit` merged with `origin/dev` (kit 1.1.0 route model) → to `dev`;
  Builder project 2 (build from plan images) only after that merge; frontend polish is Atahan's.

- **Solvers** `core/solvers/` (geometry, walls, reachability, routing): **655/655** train+dev on gold inputs
  (`scripts/validate_solvers.py`); rules + rejected variants in [solver-plan.md](../docs/architecture/solver-plan.md).
- **Benchmark pipeline** `agent/benchmark_agent.py` + `agent/run_benchmark.py`: from question text dev **138/138**,
  train **515/517** (2 inherently ambiguous names, Q-006); all 145 test questions answered without errors.
- **Navigation** `core/navigation.py` + `core/basic_parser.py`: warm-up 2120/2130 from text, 100% with gold ids,
  exact `space_path`/`element_path` (`scripts/validate_warmup.py`).
- **Agent tool layer** `agent/tools.py`: `BuildingSession` + Anthropic tool definitions (profile, propose/apply
  changes, `compare_routes`, UI events).
- **Building Guide** `agent/guide.py`: Claude tool-use loop (`GUIDE_MODEL`, cached overview system prompt,
  append-only history); same-turn `apply_change` refused and D-003 grounding check in code
  ([D-010](decisions.md#d-010) proposed). Offline client `agent/offline_llm.py` when no key.
  Since 2026-10-27 every request uses Opus **fast mode** by default (`speed: "fast"`, beta `fast-mode-2026-02-01`;
  `GUIDE_SPEED=standard` turns it off; a 429 on fast mode's limit retries at standard speed; 2× token price).
  dev-004, 3 turns, live: 12.1–15.8 s → 7.2–7.4 s. Haiku 5.5 / Sonnet 5.5 at low effort were not faster
  (10.4–12.8 s) — the time is per-call latency, not output length.
  `tests/test_guide.py`: scripted tricky-user conversation passes offline.
- **Backend** `backend/` (FastAPI): sessions per conversation + building choice, `POST /chat`, `GET /events`,
  OpenAI-compatible streaming `/v1/chat/completions`; runs with `GUIDE_LLM=offline uv run uvicorn backend.app:app`
  ([commands.md](../docs/guides/commands.md#backend-guide-api)).
- **Frontend app** `frontend/app/` (Vite + React + r3f): monochrome point cloud ([D-011](decisions.md#d-011)) with
  emergence + scan, route flow, highlight / closure / lost-access states, floor solo + separation, camera fly-to,
  chat panel; light/dark. Backend enriched route /
  change events. (Point-cloud scene and `core/pointcloud.py` removed 2026-10-24.) Verified in Chrome with the offline Guide ([commands.md](../docs/guides/commands.md#frontend-app)).
- **Building screen "Quiet HUD"** (2026-10-24/25, approved mockup round 2): voice-first Guide (`building/Core.tsx`,
  `Guide.tsx`, `hud.css`), the Guide's work trail, the next-move card from `core/directions.guidance()` steps
  (`NextMove.tsx`, route events carry `steps`), camera walk (`CameraWalk.tsx`), live tracking by dead reckoning
  (`tracking.ts`, `useTracking.ts`; 0.7 m stride UNVERIFIED, `?walk=sim`). Checked with `tsc` + screenshots; not on a
  real phone, camera "Where am I?" needs the real Claude Guide. Next: the plan follows the dot; calibrate the stride.
- **Dev panel** (2026-10-24): in the app (`frontend/app/src/dev/`, backend `/dev/*`) — try every
  Guide capability by hand (find, directions, profiles, closures with impact, display switches, log), answers
  drawn over the plan; route events carry a plan `line` ([visualization.md](../docs/product/visualization.md#dev-panel)).
- **Guide voice = ElevenLabs** (2026-10-25, [D-016](decisions.md#d-016)): `POST /tts` (`backend/tts.py`, Flash v2.5,
  voice "River") played by `frontend/app/src/voice/tts.ts`, browser voice as fallback. Voice replies are spoken while the Guide works ([D-017](decisions.md#d-017)): grounded sentences
  stream as `say` lines from `/chat/stream`, a fact-free "let me check" sentence comes first (first sound ~2.3 s).
  Spoken questions start a hands-free conversation with barge-in from the reply's first sound (preamble included);
  an utterance spoken while a Guide turn is pending is sent once that turn is done (`BuildingScreen.tsx` `queued`);
  utterances end on a 1.0 s pause
  ([D-018](decisions.md#d-018), amended 2026-10-25; not yet tried with a real mic). The user's words go to ElevenLabs Scribe Realtime
  with the building's keyterms (`POST /stt/token`, `voice/scribe.ts`, browser recognition as fallback,
  [D-019](decisions.md#d-019)). Open: drop the ~1 s rewriter for Scribe transcripts? ([Q-020](open-questions.md#q-020)).
- **AI layer of the app** (2026-10-24): `POST /chat/stream` live tool steps, route/change cards, follow-up chips,
  voice mode with the orb (browser speech, `frontend/app/src/voice/useVoice.ts`), camera walk mode with turn-by-turn
  legs (`core/directions.py`) and "Where am I?" photo turns (`Guide.reply(photo=…)`, one turn only). Verified
  headless in Chrome (offline Guide, fake camera) and one live Opus photo turn; WebGL orb + voice stage with
  explicit recognition errors. Real-mic recognition and phone camera not yet confirmed (automation can't feed
  Chrome's speech service).
- **Profiles:** `set_profile` presets (wheelchair, pram, trolley, no_lifts, default) + deterministic cue safety net
  in the Guide (`tests/test_profiles.py`); live Sonnet run uses the preset itself.
- **Voice replies:** `Guide.reply(…, channel="voice")` (used by `/v1/chat/completions`): spoken-style system
  message + deterministic `agent/speech.py`; live Sonnet low 7 turns ~3 s/turn, $0.054, clean speech.
  `uv run pytest` **146 passed**.
- **Live Guide** (API key set 2026-10-24): 7-turn tricky-user conversation correct on Opus 5.5 medium (~5.9–7.3 s/turn,
  ~$0.15) and Sonnet 5.5 low (~3.3–3.9 s/turn, ~$0.06), 0 ungrounded replies — table in
  [ai-agents.md](../docs/architecture/ai-agents.md#implementation--agentguidepy-2026-10-24).

- `uv sync` at root; starter oracle on dev **369/369** (kit 1.0.0); since kit 1.1.0 `core.building_map` reproduces 1,338/1,338 train+dev warm-up routes < 1 cm (D-014).
- `core/question_parser.py`: 655/655 train+dev params match `inputs`; 145/145 test questions parse (`uv run pytest`).
- `agent/parsing.py` modes + `agent/llm_parser.py`: offline tests pass; live (2026-10-24, `scripts/eval_llm_parser.py --per-kind 3`, 24 dev
  questions): original text regex/llm/hybrid 24/24 each; `--paraphrase` regex **0/24**, llm 24/24, hybrid 24/24.
  Parser-only cost ≈ $0.42 (cold cache) and ≈ $0.19 (warm) per 24-question run. `.env` now has `ANTHROPIC_API_KEY`.
- **Second stack (v1)** from branch `1-agentic-yarag`, merged beside the canonical one on 2026-10-24 under `_v1`
  names (the backend, UI and `agent.run_benchmark` use the canonical stack above):
  - `core/solvers_v1.py` (`solve(bmap, kind, params)` → dict): every benchmark kind + warm-up kinds; 655/655
    train+dev on gold `inputs` (`uv run pytest tests/test_solvers.py -q -s`).
  - `agent/answer.py` (`benchmark.evaluate --agent agent.answer:answer`): dev **138/138**, train 515/517
    (`tests/test_answer.py`); `agent/run_benchmark_v1.py`: .csv or .json (reply, ids, solver result, `route`
    with per-leg `space_path`/`element_path`) out; produced `submissions/team_jaRAG.csv` (145 rows).
  - `BuildingMap.route()` per-leg paths exact on all 1,338 train+dev warm-up routes (`tests/test_routes.py`);
    warm-up kinds from text 2,120/2,130 (`tests/test_warm_up.py`; 10 misses = duplicate names, [D-012](decisions.md#d-012)).
  - 2026-10-27, organisers' internal evaluation set (after the event, not in the repo): `through: false` spaces are
    destinations only, entrances/docks are places, new shared solvers `nearest_item` / `lift_closed` / `add_door`
    (`core/solvers/changes.py`, also in the Guide's `solve` tool). Score 0.464 → 0.885 on its 252 auto-scored
    questions (parser Sonnet 5.5, 1 solver-agent run); weakest: `tour` (most go to the solver agent, no answer).
    Details: [solver-plan.md](../docs/architecture/solver-plan.md#post-hackathon-kinds-and-data-rules-2026-10-27).
  - v1 Guide `agent/guide_v1/` (plan: [guide-agent](../docs/superpowers/plans/2026-10-24-guide-agent.md)): 6 tools
    (locate, find_places, place_info, building_fact, route, update_session), candidate fan-out for ambiguous names,
    grounding check with one repair then a code fallback; REPL `uv run --env-file .env python -m agent.guide_v1
    <building_dir> [--show-tools]`. 9 scripted conversations (`tests/guide_conversations/`, `scripts/eval_guide.py`):
    16/16 turns PASS live (single run, ~$0.32).
  - 2026-10-24: `scripts/eval_guide.py` + `tests/test_guide_conversations.py` ported to the canonical Guide
    (`agent/guide.py`; `route_to` checked with `core.navigation.find_route` under the session's state after the
    turn). Conversations updated to its tools (`set_profile`; closures as `propose_change` → "Yes" → `apply_change`).
    First live run 14/18; after the fixes (log 2026-10-24) Opus 5.5 medium **17/18** (89 s, ~$0.22), the one miss
    was the checker's `asked` rule, fixed and re-run 3/3 (~$0.03).
  - 2026-10-24: **Interaction eval** `scripts/interaction_eval.py` — Claude plays a tricky user from
    `tests/interaction_scenarios/*.json` (6: first day/coffee, wheelchair two trips, facility manager + lift, voice
    technician in the factory, typo + change of mind, Turkish trolley), an LLM judge scores the brief's rubric 1–5.
    All Opus 5.5: asks 4.17 · shows 4.17 · **directions 3.33** · remembers 4.83 · goal 5/6, ~$0.62 per run (log).
  - 2026-10-24: **Guidance steps** `core/directions.py` `guidance_steps` / `about_m` / `landmark`: the Guide's
    `find_route` / `tour` steps now carry turns (taken at the door you came through), a landmark item within 4 m of
    each door, rounded metres, one line per ride, no ids; `about_m` = rounded total (`length_m` stays exact).
    Interaction eval: directions **3.33 → 4.17**, asks 4.67, shows 4.83, remembers 5.00, goal 5/6; eval_guide 18/18.
  - Ported into the canonical Guide (2026-10-24): place resolution + described candidates + typo suggestions +
    route fan-out over an ambiguous destination (`agent/places.py`, `BuildingSession.resolve`), and grounding
    (unit-glued numbers, list lengths, clock times, half-up rounding) in `agent/guide.py`; `tests/test_places.py`.
    Not ported: the v1 code fallback reply (main's tools have no uniform `summary`).
  - Voice transcript rewriter ([D-013](decisions.md#d-013)) built 2026-10-24: `agent/rewriter.py` (Haiku 5.5),
    hooked into `Guide.reply(..., channel="voice")`; `tests/test_rewriter.py`.
- `benchmark/score.py` parsing behaviour checked ([scoring.md](../docs/challenge/scoring.md#formatting-pitfalls-cost-real-points)).

## Pending decisions (Atahan)

- none (D-006 zero-cost stack accepted 2026-10-24).
- [Q-002](open-questions.md#q-002) times — Atahan will provide.

## ▶ Start here (handoff for the next session, 2026-10-24 evening)

**Git (`dev`, not pushed — ask Atahan before pushing; never commit on `main`):** latest commits — the Q-014 route
model commit (this session) · `ec1b33e` Vercel deploy config (+ the Q-014 handoff) · `188abd3` conversation
persistence · `dc058f8` Sunday hardening · `46321b5` voice-ready replies. All via `/ship` (verifier PASS).

**Deployment work:** committed (`188abd3` Supabase persistence, `ec1b33e` Vercel config: `vercel.json`,
`StripPrefix` / `CORS_ORIGINS` in `backend/app.py`, `tests/test_deploy.py`, commands.md deploy section). **The app
is deployed** (Atahan, 2026-10-24; public URL not recorded here, no smoke test by Claude yet).

**What works:** benchmark dev 138/138, train 515/517 (2 irreducible Q-006); parser hybrid 31/31 on paraphrases;
Guide live on Opus 5.5 / Sonnet 5.5; FastAPI backend; React app `frontend/app/` (D-011). **New (kit 1.1.0, D-014):** one route model —
the organisers' door-to-door graph, ported verbatim; route rules (production bays destination-only, forklift
preset) per call ([route-model.md](../docs/kit/route-model.md#sunday-route-model-and-route-rules-q-014)). Guide routes always obey
the rules. `uv run pytest` 182 passed, 1 skipped (dev); 301 passed, 1 skipped after merging into `1-agentic-yarag`. API spend ≈ $1.4 of $150.

**Running locally (may still be up):** backend `uvicorn backend.app:app --port 8765` (real Claude), Vite on
`:5181` (port 5173 is another local project). Restart commands: [commands.md](../docs/guides/commands.md#frontend-app).

**Frontend (new UI, committed 2026-10-24):** landing = building search (`src/search/`), `Root.tsx` → `BuildingScreen`
(`src/building/`) over a vector plan view (`src/plan/*`, data from `core/floorplan.py` via
`GET /sessions/{id}/plan`; `center` from the plan bounds). Direction "Drawing Set": `PRODUCT.md`,
`.impeccable/surfaces/frontend-app.md`. Point cloud removed entirely (2026-10-24): code in gitignored `.viz-archive/`, and
`core/pointcloud.py`, `/points`, route `vertices`, old `App.tsx` + `src/scene/` deleted (old events → scene logic is
in git history, e.g. 92f063a:frontend/app/src/App.tsx). /plan no longer samples ~180 k points first (was 0.1–1.3 s
per building open). Doors (2026-10-24) are flat threshold strips (blue, entrances accent, closed red), no leaves: the kit
has no swing info. Next: Guide events on the plan
(focus + dim, route line, closures, lost access), then 3D, voice, camera, maintainer edit.

**▶ Do next, in order (Atahan's call 2026-10-24: frontend polish next session; Q-014 and Q-001 parked):**
1. **Frontend polish** (`frontend/app/`): phone-layout check, demo GIF (needs the Chrome extension), bundle split,
   closure ripple for edits, narrow doors for the active profile, draw in-space walk polylines
   (the visibility-graph walk of `core/building_map.walking_lengths`; `core/geodesic.py` was removed, D-014)
   instead of straight door-to-door lines.
2. Parked until Atahan picks them up: [Q-014](open-questions.md#q-014) (3), (4) — aisle/walkway/bay markers,
   whether Sunday route questions use `rules=SUNDAY_RULES` (the kit 1.1.0 answers use none); Sunday output format ([Q-001](open-questions.md#q-001)) incl. the "no route under these rules" wording.
3. Small gaps: `numpy` used by `core/building_map.py` but not declared in `pyproject.toml` (transitive via shapely;
   Atahan's file); `BuildingSession.route_model` is not saved by `backend/persistence.py` (irrelevant while the app
   stays on the kit model); live smoke test of the deployed app (needs the URL).
4. ElevenLabs Custom LLM on the deployed `/v1/chat/completions` — ask before creating anything in any account.
5. Open for Atahan: model per channel (Q-012), team name for the test CSV, push `dev`.

**Ways of working:** session protocol in CLAUDE.md; keep `.claude/worklog/PENDING.md` current; commit only via
`/ship`, staging/stamp/commit as separate commands; subagents get disjoint files.

## Next priorities

0. **2026-10-27:** deploy the fast-mode Guide (the local `.vercelignore` now excludes `*.zip`); decide on fast mode
   for the Builder / Creator / LLM parser; optionally delete the two deployments whose source holds the organisers'
   zips (`dpl_CxMW5axbcPZr53mdTBu8fLGpQK8v` and its preview).
00. **Submission (2026-10-25):** `SUBMISSION/BENCHMARK.md` + `SUBMISSION/answers.json` (v1, test set) exist. When the
   Sunday building is released: `uv run python -m agent.run_benchmark_v1 <building_dir> <questions>
   SUBMISSION/answers.json` (hybrid, `.env` read automatically — **not** `PARSER_MODE=regex`, which answered 1 of 14
   reworded questions), check errors (the summary line shows the parser mix; agent answers carry
   `parser_failure`), then commit `SUBMISSION/answers.json` **together with `llm_cache/decisions.json`** (re-runs
   without a key replay it) and ship. Keep `SUBMISSION/` to exactly those two files.

‼ **Submission (organisers' Discord note, 2026-10-25 00:10, ~14 h to the deadline) — before anything else:**
- [x] `SUBMISSION/` with exactly `BENCHMARK.md` + `answers.json` (8537ca0, v1 pipeline, 145 test answers, ids match
  `data/test/questions.csv`, 0 errors). Still to confirm against the Discord image: scope and schema
  ([Q-019](open-questions.md#q-019)). Old `submissions/` (lowercase) removed 2026-10-25.
- [ ] Hack and More form: repo link, **strictly 2-minute** demo video (YouTube/Luma; start early), short technical
  explanation.
- [ ] Ask organisers about Level 4 input/scoring ([Q-018](open-questions.md#q-018)); Builder is not a priority.

0. ✅ **Kit 1.1.0 route model ported** (2026-10-24, [D-014](decisions.md#d-014)): `core/building_map.py` = the
   1.1.0 starter graph; warm-up routes 1,338/1,338 exact, solvers 655/655, dev benchmark 138/138, test submission
   regenerated (20 errand + 1 what_if_door answers changed). Open: push `dev` (2 local commits), merge into
   `1-agentic-yarag` / `2-builder-edit`; slow first build on huge OSM corridors (~25 s, cached afterwards).

1. Frontend polish (next session): phone layout check, closure ripple for edits, narrow doors for the active profile, run against
   the real Guide (key set) and record a demo GIF/video.
2. Voice: ElevenLabs Custom LLM on the deployed `/v1/chat/completions` (replies are voice-ready); ask before
   creating anything in any account. Decide model per channel (Q-012).
3. Deploy ✅. **Current (2026-10-26, [log](log.md)):** Supabase = Utku's own project `nsncgtwjallfkqtxhmpd`
   (eu-west-1), all four `supabase/migrations/*.sql` applied, local `.env` and Vercel point at it. Vercel project
   `love-sport/industrial-agents-hackathon` has its env vars set (production/preview/development). Production is
   deployed from the CLI (local working tree) only: git-triggered deployments are disabled; the git link's
   production branch is `7-buildings-from-plans`. Production runs `7-buildings-from-plans`
   (`dpl_F8wfKMwVTZZ1WjjbEZ5ESLFkduRH`, promoted from a smoke-tested preview), functions in `dub1` next to the
   database (`vercel.json` `regions`), access mode off. Voice in the browser not yet re-tested on it.
   *Superseded history:* deployed by Atahan 2026-10-24: Supabase ✅ (old project created, `conversations` table applied, sessions persisted via
   `backend/persistence.py`, live round trip incl. real Claude verified 2026-10-24). Vercel config ✅ (`vercel.json`
   with services `web` + `api`, `/api` rewrite, `excludeFiles`, `maxDuration` 300; `StripPrefix` and `CORS_ORIGINS`
   in `backend/app.py`; `tests/test_deploy.py`). Remaining: smoke-test the live URL; the first-deploy UNVERIFIED
   items are listed in [commands.md](../docs/guides/commands.md#deploy-vercel).
4. Preference extraction, remaining TODO: group composition (P20), profile lifetime/reset scope, persistence,
   soft penalties → [TODO](../docs/product/routing-profiles.md#todo-preference-extraction).
5. Sunday hardening: wording robustness ✅ (hybrid 31/31 on paraphrases), Swiss `straight_line_3d` ✅ (generator
   avoids Swiss; no correction needed); still open: output format once Q-001 is announced, new kinds.

## Blockers

- None hard. Sunday output format unknown ([Q-001](open-questions.md#q-001)) — solvers return structured results + prose.
