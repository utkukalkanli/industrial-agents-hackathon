---
id: log
summary: Append-only session log, newest first. One entry per session/work chunk.
related: [project-state.md, decisions.md, open-questions.md]
---

# Log

[Memory bank](README.md)

Template: `## YYYY-MM-DD HH:MM — title` then *Did / Learned / Changed docs / Opened-closed Q / Next*.

## 2026-10-25 — CI/CD: first GitHub run of PR #2

- **Did:** pushed `ci-cd`, opened PR #2 (repo now detached from Atahan's fork network). First run 40218266044:
  Python tests and frontend pass (~2.5 min on GitHub), integration failed — `supabase db push` tried TLS against
  the `postgres:17` service ("does not accept TLS"). Fixed: `?sslmode=disable` in the job's URL. CI also ran twice
  per PR commit (push + pull_request) → push now triggers CI only on `dev`.
- **Next:** watch the next run (migrations, live store tests, smoke test have not run on GitHub yet); Utku sets up
  the Supabase/Vercel secrets ([ci-cd.md](../docs/guides/ci-cd.md#one-time-setup)); decide whether to drop `/ship`
  now that CI gates PRs.

## 2026-10-25 — CI/CD: GitHub Actions → our own Supabase + Vercel (branch `ci-cd`, not pushed)

- **Did:** `origin` → utkukalkanli/industrial-agents-hackathon (old one kept as `upstream`; no upstream-only
  commits). Worktree `../iah-ci-cd` on branch `ci-cd` from `origin/main`. Added `.github/workflows/ci.yml`
  (python, integration, frontend, preview), `deploy.yml` (ci → migrate → deploy → promote), `dependabot.yml`,
  `scripts/smoke_test.py`, `.vercelignore`, `pytest-xdist` (dev), `vercel.json` git deploys off;
  [ci-cd.md](../docs/guides/ci-cd.md), [D-024](decisions.md#d-024).
- **Learned:** full suite 1088 passed / 2 skipped, ~6 min serial, ~3.6 min with `-n auto` locally (the
  whole-dataset tests take 2–4 min each); migrations are plain Postgres (no Supabase roles), so CI applies them to
  `postgres:17`; `setup-uv` publishes no major tags (pin full versions). Docker was not running locally: the
  integration job is only checked on GitHub.
- **Next:** push `ci-cd`, open a PR on the fork, fill the secrets ([ci-cd.md](../docs/guides/ci-cd.md#one-time-setup)).


## 2026-10-25 — Map list: "New building from floor plans / Create →" row styled again

- **Did:** `frontend/app/src/map/map.css` `.ml-more` (+ hover, focus-visible) on the HUD tokens (`--hud-line`,
  `--hud-ink`, `--hud-ink-2`, `--hud-fill`, `--hud-route`, `--font-ui`): one row at the bottom of the list panel, name
  left, "Create →" right. **Learned:** the rule was dropped in 3113a99 (map list rework), so the two spans ran
  together ("plansCreate"). **Checked:** headless Chrome, wide dark / light and phone (390 px): row 47 px high, the two
  texts apart; `tsc -b` exit 0, `vite build` OK.
## 2026-10-25 15:00 — Buildings from plans: reference + trace in Edit mode, real map position (branch `7-buildings-from-plans` (started as `6-plan-reference-location`))

- **Did:** design + plan (`docs/superpowers/specs|plans/2026-10-25-plan-reference-and-location*`), executed inline.
  Part 1: the import stores each floor's straightened plan + px → metres transform (`core/plan_import/reference.py`,
  `GET /drafts/{id}/references`, stripped from every other payload); Edit mode shows it right of the editor
  (sized to the image) with a "Trace" overlay. Part 2: right-click card on the map ("Create a building here", at the
  cursor, outline of the building under it); the import is fitted onto the OSM footprint (`core/geoplace.py`), placed
  by hand (`Placement.tsx`, `PUT /drafts/{id}/location`), saved with `building.location` incl. `bearing`, shown on the
  map; re-save supersedes. GPS: EXIF GPS median → Overpass building (`core/osm_lookup.py`) → fit; browser position as
  fallback; "did you mean" when the tap is > 50 m from the photos. "Edit position" in the Edit bar.
- **Learned:** overpass-api.de answered 406 to curl's UA and 502 "at capacity" → the app falls back to the map's own
  vector-tile buildings (`querySourceFeatures`); tiles merge same-look buildings into MultiPolygons, so the part
  holding the point must be picked. A fit at the scale bound (×1.25) moved the trace off the plan: `scale_building`
  now scales the references too (Utku's live test). The kit's TUM main building fits its own OSM outline at IoU 0.86.
- **Changed docs:** visualization.md (new section), commands.md (3 endpoints, import fields), the design's status.
- **Then (Utku's live test):** floors: one per file with a floor number the user types (`levels`), "Add a floor"
  only in Edit mode (into the open draft, walls kept parallel — a free-angle fit had tilted added floors 7–11°),
  "Straighten this floor"; map card: Open / Delete only (`DELETE /buildings/user/{slug}`, file store keeps it in
  `.deleted/`); trace adjustable (`set_reference`); reference window draggable / resizable; problems list over the
  reference; floor picker follows the draft.
- **Fixed before shipping (commit-verifier round 2):** save rebuilt `source_ref.import` from the base, so an adjusted
  trace, a scaled plan, added floors' plans and every plan after a second save were lost; save now keeps the draft's
  own `source_ref.import` (`tests/test_plan_references.py::test_reference_edits_and_added_floors_survive_save_and_a_second_save`).
- **Decisions:** D-023 (proposed). **Next:** ship on a new branch and push (Utku asked); merge into `dev` later.

## 2026-10-25 — Post-commit verifier fixes for d6b07c9 (4466286)

- **Did:** an exhaustive `commit-verifier` run on d6b07c9 (it went in without a PASS): every C / S50 / S22 row MET,
  10 required fixes, all done here. Edit mode: `checking` starts true and stays until GET /config (and a signed-in
  viewer's GET /me) has answered, and `mayChange` is false while it is, so a direct `?building=X&edit=1` shows no Edit
  bar and sends no `/drafts` request before the app knows who is looking (`access/auth.ts`, `BuildingScreen.tsx`).
  `set_my_location("outside")` gets resolve's "No place matches" again (`start_of(…, outside=False)`; it had become
  `{'error': 'outside'}`), test in `tests/test_voice_location.py`. Docs: ai-agents.md `suggest_my_location` row,
  ambiguous start on `set_my_location`, destination shortlist; project-state (session 50 bullet, People tab, last
  updated); "(not committed)" headings → d6b07c9; three stale "next-move card" comments.
- **Session 70's part of d6b07c9, for the record:** Building settings in tabs Access / People / Objects (shield button
  in the admin corner; Objects tab restyled, `access/ObjectsSection.tsx`), the Edit mode's Access tool
  (`AccessCard.tsx`, `useAccessRules.ts`, restricted rooms hatched), a failed draft copy shows "Could not edit" with
  Close, the Edit mode opens flat on one floor and its bar fits on phones.
- **Checks:** see the worklog. Edit-mode gating not tried in a browser.

## 2026-10-25 — The living building (branch `5-living-building`, worktree `.claude/worktrees/5-living-building`)

- Atahan asked for a "living" building: connected things (forklifts, robots, things left behind) that report
  positions, block corridors and change navigation, with trails. Built ([living-building.md](../docs/product/living-building.md)):
  `core/live.py` (obstacles cut door-to-door walks by free-area connectivity with the walker's clearance; waits,
  squeeze, wet floor; `collapse_hops`), `navigation.find_route/tour(live=)` + `live` notes, `backend/live.py`
  (simulated world per building, BLE/telematics report intervals, 50 m trails, wet zones, real-device ingest,
  `GET /live` with reroute / alert / suggestion, `/live/control`, `/live/shorter`), session `live_effects`, `reroute`,
  Guide tool `live_status` + `[live note]` + prompt paragraph; frontend `src/live/` (layer, markers, panel, notice).
- Checked: `tests/test_live.py` 36 passed (edge cases listed in living-building.md "Tested"); full suite 1026 passed;
  `tsc -b`, oxlint, `vite build` clean; stress run over all 280 buildings (world, 150 s simulated, snapshot, live
  routes, blocked-route reroute): 0 errors, every path well-formed; headless Chrome with the live Opus Guide: reroute
  while guiding (step guide goes on), alert + dismiss, "clear again" + Take it, tap to drop, Edit mode hides it; demo
  video + screenshots made. Bugs found and fixed: a door beside the pallets bridged both sides; wet-floor door→door
  hops; a pallet on a door's landing didn't count; narrow spaces let routes hop past a cart; a stopped cleaning
  robot's floor never dried; the cleaning robot stood still on one-corridor floors; reroutes followed an older
  question instead of the route on the map (route events now carry `request`); 11 s ticks (robot planning now off
  the clock on a planner thread, view-based graph filter, caches; huge OSM outlines walked straight).
- Merged into the main checkout as uncommitted changes (3-way per file onto dev `fc58314` + others' WIP).
- Fix round: `/live/control` and `/live/devices` admin-only in access mode (`admin_in_access_mode`), test_live 37;
  a reroute the map can't draw is checked before it is added or saved.

## 2026-10-25 — Submission prep: technical explanation, demo runbook, pitch deck

- **Did:** listed what the submission needs; re-ran `SUBMISSION/BENCHMARK.md` in hybrid (test 145/145 answered,
  identical to the committed `SUBMISSION/answers.json`, all via templates; dev 138/138); picked the demo building
  Thierschbau (`train/osm-way61408163`) and ran the demo lines against the live Guide (API + app in headless Chrome);
  built a 12-slide click-through pitch deck (claude.ai artifact) from real app screenshots.
- **Learned:** Lift 2 closed → step-free route 1373 → Theodor-Fischer-Hörsaal 88.0 m → 223.8 m via Lift 1, 30
  Basement 1 rooms lose step-free access; Guide closures are per session (a reload resets); "OK, how do I get there
  now?" was taken as a yes to apply; `llm_cache/decisions.json` does not exist yet (no LLM decision on the test
  set) — it appears on Sunday if a question needs the LLM and must be committed with `answers.json`. Phone-width
  glitches: route HUD text under its icons, lift callouts overlap.
- **Changed docs:** new `docs/challenge/technical-explanation.md`, `docs/guides/demo-runbook.md`; links in
  `docs/README.md`, `docs/challenge/brief.md`.
- **Next:** record the video, submit the Hack and More form, merge `dev` → `main`; admin screenshots for the deck.

## 2026-10-25 — Phones: Guide voice and stuck turns, home-screen app (merged into dev)

- **Did:** `voice/tts.ts`: unlock on `pointerup`/`touchend`/`click` too, a silent first utterance primes
  speechSynthesis, browser utterances run one at a time with a start timeout (`START_MS` 4 s) and an end timeout
  (`MS_PER_CHAR`), `navigator.audioSession` set to playback; on iOS the warm mic is closed before speaking
  (`mic.ts` `dropMicrophone`) and `useVoice` starts no barge-in watcher; `scribe.ts` resumes its capture context on
  those events. `backend/app.py`: NDJSON excluded from gzip, `ndjson_with_pings` (10 s) for `/chat/stream` and the
  Builder stream; `api.ts` `watchedStream` gives up after 45 s without a byte. `index.html`: `viewport-fit=cover`,
  `maximum-scale=1`, home-screen metas, `manifest.webmanifest`; `styles.css`: 16 px fields on touch (iOS zooms into
  smaller ones and stays zoomed), no overscroll / tap flash; map sheet clear of the home bar, credits start closed.
- **Learned:** the deployment has no `ELEVENLABS_API_KEY` (`/api/health` tts/stt false), so iPhones used the browser
  voice, which iOS drops silently outside a gesture: the orb then stayed on "Working". Through gzip the deployment's
  stream sent nothing for 40 s, then every line at once (curl without `--compressed` looked fine).
- **Changed docs:** [ai-agents.md](../docs/architecture/ai-agents.md), [commands.md](../docs/guides/commands.md#deploy-vercel).
- **Next:** add `ELEVENLABS_API_KEY` on Vercel and redeploy; try it on a real iPhone home-screen app.

## 2026-10-25 12:00 — Floor changes and "where you are" on the plan (session 22)

*Did:* the riser between floors is a cased tube drawn over the slabs (was an invisible 1px line); a stairs/lift step while guiding stacks its two floors; a new position from the Guide shows before the route (1.6 s); with the position unknown, `maybe_here` (Guide's rooms via new `suggest_my_location`, else entrances) → "Here? · room" badges, tap to stand there. *Learned:* vite reads `BACKEND_URL` only when exported in its own shell; without it, it proxies to the shared 8765 backend. *Next:* screenshot the stacked ride step.

## 2026-10-25 — Possible start rooms in the figure's orange (d6b07c9)

- **Did:** "I'm in the kitchen" (several matches) now marks every match as where the user might be (`start_of` →
  `maybe_here`, also for a route's start) instead of a plain search highlight; those rooms are drawn with a dashed
  outline and "Here?" badge in the figure's orange (palette `me`), the destination stays blue; prompt line to use
  set_my_location for such words. Ambiguous-destination error now gives the real match total.
- **Next:** badges of rooms on different stacked floors overlap on a phone.

## 2026-10-25 — Route asking and metres left: merged highlights, nearest options, cross-floor countdown (d6b07c9)

- **Did:** reviewed the Guide's route flow live (both known, start unknown, destination ambiguous, start ambiguous,
  Start on a cross-floor route). Start already goes back to the first step's floor. Fixed: the trip pill's metres
  left dropped on Start (55 → 30 m) because the walking track leaves out stairs/lifts (`tracking.ts` `metresLeft`,
  also the camera walk); highlights within one reply now merge (a later subset narrows), so "which kitchen are you
  in?" shows the kitchens (`dev/story.ts`); `destination_options` highlights its candidates and shortlists big
  matches; the prompt sends a known start + ambiguous destination to `find_route` for the nearest 3 with metres.
- **Learned:** route legs give stairs/lifts 0 m; `length_m` − walking total is their cost.
- **Next:** draw "where you might be" apart from "where you're going" (a highlight role; session 22 works on the
  location flow).

## 2026-10-25 — Verifier fixes for 3113a99..a5f5407 (d6b07c9)

- **Did:** an exhaustive `commit-verifier` run over the three commits that went in without a final PASS (every claim
  MET; 11 required fixes) and fixed all of them. Access mode: `ensure_access` rebuilds the Guide's system prompt
  from the restricted copy again (`refresh_system` after the first turn had kept the unfiltered overview), and
  `Guide.seen_overview` (persisted) makes `refresh_system` send a settings note once per change, not on every call.
  "I'm there" at the exit of a route into a nearby building opens it (same path as `open_nearby_building`) instead
  of saying "Tap Continue". `ARRIVED_SAID` takes "arrived" only first-person or as the first word. One "Spoken
  replies": the Preferences sheet's `voice` field sets the Guide menu's switch, the menu writes it back
  (`setSpokenReplies`). Stale comments (next-move card, `devApi.ts`), docs (visualization, ai-agents), D-021,
  project-state and this log's order / "(not committed)" labels fixed.
- **Also (session 70, same checkout):** Edit mode: bar fits (Done no longer cut off), opens flat on one floor,
  non-admin ?edit=1 no longer stuck; new Access tool in Edit mode (AccessCard + useAccessRules, restricted rooms
  hatched); shield button opens Building settings for the admin.
- **Checks:** pytest (see worklog), `tsc -b --noEmit` exit 0, `vite build` OK, check_links OK. "I'm there" at the
  exit and the spoken-replies link not tried in a browser.
- **Changed docs:** visualization.md, ai-agents.md, decisions.md (D-021), project-state.md.

## 2026-10-25 — Dead route buttons removed from NextMove

- `NextMove.tsx` had its own Start / "I'm there" / Done / Continue buttons (`guiding`, `onStart`, `next`,
  `onContinue`, `onFinish` props), but it is only rendered by `CameraWalk.tsx`, which never passed them: dead code.
  Removed with its `.guide-actions` rules in `hud.css`; the live buttons are `RouteHud.tsx` `RouteBar`. Checked:
  `tsc --noEmit` clean, `vite build` OK; nothing visible changes.

## 2026-10-25 — Directions: overview + "say start", no first step

- Atahan asked: after finding a route the Guide gave the first step and asked whether to start. Now (`agent/guide.py`
  INSTRUCTIONS + VOICE_STYLE, [D-020](decisions.md#d-020) amended) a directions answer is an overview — found it,
  echo line, about_m, floors, a landmark or two — ending in "Say start or press Start when you're ready." in the
  user's language; "no steps" gets the whole route in a few sentences. Step-by-step after Start was already the
  app's (`BuildingScreen.tsx` reads each step, "I'm there" moves on). Offline client's route reply follows it;
  `route_to_building` description asks for an overview too. Test: `test_directions_are_an_overview_that_ends_in_the_start_line`.
- Checked: `uv run pytest -q` 989 passed before the new test; live Opus (scratch script, train campus 000): English
  and Turkish route replies are overviews ending in the Start line, "No steps please" gives the full way.

## 2026-10-25 — Guide opens nearby buildings itself

- Problem: asked to go between buildings, the Guide said it could not open another building — it had no tool for
  it, and `route_to_building`'s result told it the user taps Continue.
- New Guide tool `open_nearby_building(building)` (`agent/tools.py`, only with located neighbours) → UI event
  `open_building`; `BuildingScreen.tsx` opens it once the reply has been said (at least `OPEN_DELAY_MS` 1.5 s, then
  while the voice is `thinking`/`speaking`, at most `OPEN_MAX_MS` 15 s), going
  through `continueTo` (arrival at the entrance + rest of the route) when the route on the map leads there.
  Prompt + `route_to_building` description + campus `app` note point to it. Test:
  `test_the_guide_opens_a_nearby_building_itself`. Checked: `uv run pytest -q` 989 passed, `tsc --noEmit` clean;
  not tried in a browser or with a live LLM. Offline client has no phrasing for it.

## 2026-10-25 — Route step card follows "I'm there"; Guide offers to walk you there

- **Did:** `BuildingScreen.tsx`: `ARRIVED_SAID` catches "I'm there / vardım / geldim / made it …" inside a short
  sentence (≤ 6 words) and moves the step card even when Start was never pressed (it starts the guide); at the last
  step it ends the route with a chat note ("You have arrived at …") instead of only speaking. `/chat` now always gets
  `route_step` while a route is on the map, so the Guide's `[route note]` is there for "I'm at the stairs". A tapped
  question that draws a route keeps listening (for "start"). `NextMove.tsx`: "I'm here — done" button at the last
  step. `agent/guide.py` prompt: directions end with one offer ("Say start and I'll walk you there step by step");
  on an arrival the Guide calls `show_route_step` with the next step.
- **Learned:** before, "I'm there" only worked after Start and in ≤ 3 words; otherwise it went to the Guide without a
  route note, so the card never moved.
- **Next:** try it with a live mic; no live LLM run of the new prompt yet.
- **Then (same chunk), route arrows + step animations:** `dev/StoryLayer.tsx`: route band 12 px, chevrons larger
  (36 px apart) and also on the rest of the way past the step being walked (40 %), the walked part and the step's
  end ease to a new step (`STEP_EASE`), and the "you" puck glides along the route line to the new step
  (`pointAlong`, `You.along`; jumps over 80 m snap). `NextMove.tsx` + `hud.css`: a new step slides in, its arrow
  settles in, the step's segment fills from the left; all off under reduced motion. Checked with headless
  screenshots (Hauptgebäude, dark, 1440×900), including a frame mid-transition; phone width and light mode not checked.
- **Then, navigation variant B** (Atahan compared two mockups and picked B, which pins the step on the map):
  `core/directions.maneuvers` joins straight-on doors (Hauptgebäude 0119 → Toilet 0137 goes from 8 steps to 6). The
  card, the `[route note]` and the spoken steps all use it, and each step carries `legs` (`tracking.ts`
  `routeTrack(..., spans)`). New `building/RouteHud.tsx`: `TripBar` is the top pill and replaces the NextMove card
  outside the camera view; `RouteBar` sits over the dock through Guide's new `routeBar`/`quiet` props. The map gets
  a `move` callout at the step and a "then …" tag at its end. The route shader is now thin: solid only on the current
  step, dotted for walked and coming steps, with a running light instead of chevrons (`routeMaterial(colour, done,
  comet, casing)`; StreetView's call is unchanged, but it now shows a plain line). The talk mode default is tap
  (`useVoice` HOLD default false). Coordinated with -20, who added `focusInsets` so framed answers clear the rail.
  Checked headless on test servers (:8766 / :5182), desktop 1440×900 and phone 390×844, dark theme only. Not checked:
  light theme, a live mic, multi-floor routes (connector steps), Continue into the next building.

- 2026-10-25 — Basement veil removed (user: the darkening over the basement made it hard to look at). `City` in
  `frontend/app/src/plan/PlanView.tsx` no longer draws the ground-colour veil (opacity 0.7) over the biggest basement
  outline; the `ground`/`underground` props and `VEIL_ALPHA` are gone. `docs/product/visualization.md` updated.
  Checked: `tsc --noEmit` clean. Not checked in the browser.

- 2026-10-25 — Route end (user: after cancelling or finishing a route the map kept it and the position stayed
  old). New Guide tool `end_route(arrived?, place?)` → UI event `route_end` (`agent/tools.py`, prompt in
  `agent/guide.py`); `BuildingSession.shown_route` ignores routes ended since, so `route_card`/`show_route_step` see
  none. `DELETE /sessions/{id}/route` for routes the app ends. `BuildingScreen.endRoute` is the one path for Finish,
  End directions, a short "stop"/"cancel the route"/"rotayı iptal et" (`STOP`) and the Guide's event: clears the
  story, tracking, camera walk and step guide, and puts the figure at the destination (arrived), the Guide's room, or
  where the walk got to (tracking position, else the last step reached), telling the session. Checked: pytest 880
  passed (2 new tests), `tsc` and oxlint clean. Not checked in the browser or with a live LLM.
- 2026-10-25 — Guide 400 "Invalid `signature` in `thinking` block … bound to a different conversation" (user, while
  talking to the Guide). Cause: Opus 5.5 binds thinking blocks to the prefix (system, tools, earlier messages) and
  the Guide edited it mid-conversation: preferences (`PUT /sessions/{id}/preferences`) and access switches
  (`SessionStore.ensure_access`) rebuilt `guide.system`; a photo turn's message is replaced after the turn. Fix:
  `Guide.refresh_system()` rebuilds the system prompt only before the first turn, afterwards queues
  `system_note` (persisted) for the next user turn; Guide and Builder requests send `thinking.block_binding.
  prefix_mismatch_behavior: "drop_block"` (beta `thinking-binding-controls-2026-08-01`) so any remaining edit (the
  photo) drops outdated thinking instead of failing. Checked: pytest 881 passed (1 new test); one live request
  with the new fields accepted (`input_transformations: []`). Not replayed against the exact failing conversation.

- 2026-10-25 — Basements you are not on drawn darker (user: "bodrum katlar, o kata bakmıyorsak daha karanlık").
  `FloorModel` in `frontend/app/src/plan/PlanView.tsx` gets `under` (level < 0 and not the current floor): material
  colours (vertex-coloured meshes via `color`, slab, hairlines, edges) times `UNDER_TINT` 0.35; seen through the
  current floor its opacity is `UNDER_FADED_OPACITY` 0.3 instead of `FADED_OPACITY` 0.12. Checked: `tsc -b` clean;
  headless screenshots of Landwirtschaftsbau (osm-way50299720, B1+B2) at 1440×900, light and dark: all floors, G
  (basements dark under it), B1 (B1 normal). Phone width not checked; on the dark theme the effect is subtle.
- 2026-10-25 — Kind filter chips on the landing list (user: "filters … like campus or house or factory").
  `backend/sessions.py` `building_kind` maps the manifest `source` (+ `proc-campus-`/`proc-factory-` in `path`) to
  `kind` campus / factory / home (resplan, swiss_dwellings) / real (osm_indoor); saved Edit-mode buildings are
  `saved` (backend/drafts.py). GET /buildings returns `kind`. `MapLanding.tsx`: chips All · Campus · Factory · Home ·
  Real · Saved (only kinds present), one at a time, combined with the name search; they filter the list, not the map
  pins. Counts: home 214, factory 26, campus 23, real 17. Checked: `tsc --noEmit` clean, backend tests (test_backend,
  test_campus, test_draft_backends, test_access) 63 passed; the UI was not checked in a browser.
- 2026-10-25 — Dev tools removed; the admin button is just Edit (user: "remove dev tools completely and just make
  the button edit button for the admin role"). Deleted `frontend/app/src/dev/DevPanel.tsx` and `devApi.ts`
  (`DevEvent` moved to `dev/story.ts`); `dev/dev.css` cut down to the plan badges as `dev/story.css`, imported by
  `StoryLayer.tsx`. `BuildingScreen.tsx`: no `DEV_TOOLS`/`?dev`/backtick panel; the admin button (shown to
  `mayChange`) toggles the Edit mode directly (`aria-pressed`), no menu. Building settings now open only through the
  Guide (`open_building_settings`); the account hint says so. Backend `/dev/*` kept (tests use it). Checked:
  `tsc -b` clean (after session -20's BuildingSearch.tsx type fix), `vite build` OK; not checked in a browser.

## 2026-10-25 — Map widths per class, one mic stream, admin-only building settings, no reduced motion (3113a99)

- **Did:** `map/style.ts`: road, rail, bridge and walkway widths are zoom-only (one layer per road class, one per
  walkway width) instead of a per-feature `match` inside the zoom curve. `voice/mic.ts`: one shared microphone
  stream for Scribe and the orb (`acquireMicrophone` / `releaseMicrophone`, kept `KEEP_MS` after the last user:
  120 s as a home-screen app, 8 s else; `iOS` detection); `scribe.ts` keeps only its `AudioContext`.
  `access/BuildingSettings.tsx`: My preferences section removed, the panel is admin only. Every
  `prefers-reduced-motion` check removed (CSS blocks incl. the `styles.css` global rule and `import.css`; TS goes
  through `motion.ts` `reducedMotion()`, which returns false).
- **Learned:** a width that reads the feature is a composite expression, baked per tile, so the same street showed
  different widths across tiles in a tilted view; iOS Safari mutes an older capture when a second stream opens.
- **Changed docs:** `docs/product/visualization.md` (fit paragraph for `smallest_inside`, motion sentence, the
  removed city/alone bullet), `memory-bank/project-state.md` (no veil, partial-model fit).
- **Next:** check the mic on a real iPhone; light theme of the road widths.

## 2026-10-25 — Route overview over floors; step frames follow you (3113a99)

- **Did:** a route over several floors is first shown whole: only its floors, stacked (`PlanView` `only`), until
  Start or a floor pick ("All floors" brings every floor back); in a stack the route band draws over the floors
  above it (`StoryLayer` depthTest off when stacked). On a phone the overview is framed again when the Guide's
  sheet grows. Each step now frames where it starts plus `STEP_AHEAD_M` (10 m) ahead, facing the way, instead of
  the whole stretch to its end; the "you are here" figure is hidden while guided (the dot on the route is you).
- **Learned:** the backend sent one complete route event; the "only the destination" view came from all six
  floors stacked over the route and long steps framed up to their end. Checked with Playwright screenshots
  (StudiTUM, Library 0.001 → Library 2.205, 1440×900 and 390×844), all 6 steps walked.

## 2026-10-25 — Guide history arrows; light theme check (3113a99)

- **Did:** `Guide.tsx`: "‹ 2/5 ›" beside the question steps through earlier exchanges one at a time (no list);
  the view is held for the current message count only, so a new message shows the latest again; a past
  exchange's bubble has a dashed edge, never the "Speaking" label, and keeps its numbered steps. `hud.css`:
  `.screen .core:disabled { opacity: 1 }` — the global `.screen button:disabled` (0.4) greyed the ball while it
  worked.
- **Learned:** light theme checked (idle, options, thinking, answer, history) at 1440×900; fine apart from that
  dimming.

## 2026-10-25 — Guide: thinking line, quieter answer header, field in the dock's style, one width (3113a99)

- **Did:** `Guide.tsx`: while working, one line says what it does now (the running step's label, a light
  sweeping across it) with a dot per lookup (running one pulses, no-result ones hollow) and seconds from 3 s on —
  no "Working" label, no mono log, no struck-through red tool names. After the answer: the question in plain small
  type with a quiet "N steps" toggle beside it; open, the steps as a thin timeline ("no match" in grey). `ui/
  guideSteps.ts`: labels for find_nearest, set_my_location, show_route_step, nearby buildings, route_to_building,
  open_edit_mode, open_building_settings, set_preference, send_object (they showed raw tool names). `hud.css`:
  column 360 px (`GUIDE_COL_PX`), everything centred in it so the bubble never runs past the dock; message field
  44 px glass like the dock's buttons, no blue focus ring, send a quiet arrow until there is text; reply preview
  7.2em. Classes `work*` (a global `.thinking` in `styles.css` from the old chat clashed).
- **Learned:** checked with 5 real questions (LLM calls) on wide and phone, dark only.

## 2026-10-25 — Hold to talk (default) or tap, in the Guide's options (3113a99)

- **Did:** `useVoice`: `holdToTalk` / `setHoldToTalk` (default on, `ttyb-guide-hold`) and `hold()` = listen with no
  timers until `finish`; with hold on, no reply listens by itself (no hands-free loop, no barge-in watch, no
  `listenAfter`). `Core.tsx`: `hold` + `onHold` — press listens (pointer captured; pressing while it speaks cuts it
  off), letting go sends; Space/Enter held work the same; tap mode unchanged. `Guide.tsx`: options row "Talk by
  Hold / Tap"; the "Tap or hold to talk" hint under the ball removed (labels/titles carry it); caption "Listening…
  let go to send". `CameraWalk.tsx` passes the same setting to its small ball.
- **Learned:** not tried with a live mic (headless has no recognition); options popover checked by screenshot.

## 2026-10-25 — Layout: Guide bottom-left on wide, actions bottom-right, phone layout (3113a99)

- **Did:** wide: the floating Guide column (440 px) sits bottom-left, left-aligned; the floor rail stays in the
  middle of the right edge (Atahan's correction, via session -70) and the plan's buttons (street view, compass,
  figure, with the admin button on top) form one column in the bottom-right corner under it (`insets` right
  `ACTIONS_RIGHT_PX`, bottom 24, left 16 + `GUIDE_COL_PX` + 24). Guide type scaled to the 44 px buttons (reply
  15 px, greeting 16.5 px) and the bubble only as wide as its text (≤ 360 px). Phone:
  the Guide measures itself (`Guide` `onHeight`, ResizeObserver) and `insets.bottom` follows it, so the plan's
  buttons stand on its top edge; chips are one sideways-scrolling row; smaller greeting and bubble padding.
- **Learned:** `Rig` reads `insets` through a ref, so changing them (the measured height) never refits by itself.
  Checked by screenshot at 1440×900 and 390×844, dark only; the admin button and light theme not seen.

## 2026-10-25 — Guide without a panel: floating bubble + dock, main way in the middle (3113a99)

- **Did:** `Guide.tsx` / `hud.css`: no card any more — the Guide floats at the bottom centre on every screen; the
  caption is a glass bubble, the chips and dock buttons have their own glass. Dock = three places: talking first
  (default) → keyboard left, ball (76 px) middle, options right; the keyboard brings the field into the middle,
  focused (Escape or leaving it empty brings the ball back, unless focus stays in the dock); typing first → small
  ball left, field middle. Options: "Ask by Voice / Text" (`ttyb-guide-first`, replaces the message-field switch),
  Spoken replies, Start over. The dock keeps one height in both arrangements. `BuildingScreen.tsx`: wide insets keep
  answers clear of the bottom centre (`GUIDE_WIDE_PX` 230) instead of a left card (`PANEL_PX` removed).
- **Learned:** Playwright can capture the open building through CDP `Page.captureScreenshot` (the normal
  `page.screenshot` times out); wide and phone checked, dark theme only.

## 2026-10-25 — Guide card: the ball, a message field, voice/typing options, fewer chips (3113a99)

- **Did:** `building/Core.tsx` is now a ball: a WebGL fragment shader (domain-warped noise, light shading, film
  grain) whose palette follows the state in the HUD colours — calm blue at rest, `--hud-live` green listening,
  indigo working, `--hud-route` blue speaking, with rings on the voice level; static CSS gradient without WebGL
  (also used by `CameraWalk`). `building/Guide.tsx`: the "Guide" name is gone from the captions ("Working" /
  "Speaking" only), the dock is ball + message field + options; options = "Message field" (talk only when off),
  "Spoken replies" (text only when off) and Start over, both remembered (`ttyb-guide-typing`,
  `ttyb-guide-speaks`). `voice/useVoice.ts` gains `speaks` / `setSpeaks`: off, `stream`/`speak` say nothing and the
  loop rests. `BuildingScreen.tsx`: the Guide card shows only once plan and session are loaded; `suggest()` chips
  rethought — Toilet / Way out / Lift (multi-floor with a lift) / Canteen (not home kitchens) / This floor, asked
  as "nearest" (find_nearest), max 3; Step-free (a preference) and Help (repeats the greeting) dropped.
- **Learned:** 266 of 280 buildings have a `kitchen`, mostly homes, so a "Food" chip keyed on kitchens was wrong.
  Playwright can't screenshot the open building (the screenshot times out), so the ball was checked on the error
  screen only; the chips, the loading gate and the live states are not checked visually.
- **Next:** try the states with a live mic; Atahan to judge the palette.

## 2026-10-25 — One settings corner top right; map Open button border (3113a99)

- **Did:** `access/AccessLayer.tsx` `Corner`: a settings button top right on every screen (always, not only in
  access mode) with Theme, and in access mode Preferences and the account (sign in / set a password / sign out); a
  pill on the landing, a round 44 px button over a building (on phones the HUD top line stops short of it,
  `hud.css`). Closes on an outside press or Escape. `BuildingScreen`'s "…" menu keeps only the building's own items
  (edit, show it all, city/alone, Building settings, dev tools). The map gains the theme. `map.css` `.ml-enter`:
  `border: 0` (the browser's default button border drew the odd line round "Open").
- **Checked:** `tsc -b` clean; headless Chrome screenshots (wide + phone): Open row, map menu, building menu.

## 2026-10-25 08:55 — Opening a building without the freeze (3113a99)

- **Did:** `plan/geometry.ts` `prepareFloors` builds a plan's floors one per frame during the map's fly-in and
  hands them to the next `buildFloors` of the same plan / palette / look (taken once: the fills get recoloured in
  place). `BuildingScreen` awaits it before showing the model; "Opening the building…" is now a pill with a spinner,
  shown from the tap until the model is there, the fly-in included (faded in 0.35 s late, `screen.css`), replacing the
  2.4 s timer. Its block on the map breathes meanwhile (`bridge.ts` `pulse` drives a `pulse` feature state on the
  `models` source; `MapLanding.tsx` model-blocks / model-footprints ease toward a paler accent; reduced motion: lit).
- **Checked:** production builds (old vs new) with `vite preview` on the local backend, headless Chrome, three
  buildings × 2 runs: `buildFloors` (~245 ms, 146 ms of it `EdgesGeometry`) no longer runs in the frame the model
  appears; the longest task while opening dropped from ~130–240 ms to ~55–80 ms (the rest: MapLibre tiles, first
  three.js draw). Ready time unchanged (~1.9 s, the fly-in). Screenshots: wait pill (wide, phone) and the model.
  `tsc -b` clean. Dev mode still builds twice (StrictMode runs the memo twice; the second call misses the cache).
- **Next:** start the prefetch when a row is picked on the map (in `MapLanding.tsx`, after its pending work lands).

## 2026-10-25 08:30 — Chat Guide gets the Sunday layers; readable Claude API errors; dev c3ab8f0 merged (branch `4-sunday-agent`)

- **Did:** merged `origin/dev` (6fa882e step card / `find_nearest` / route line from the figure, c3ab8f0 landing
  account button). The chat Guide (`agent/tools.py`) gets `compute` (the solver agent's Python sandbox; its
  `route()` routes exactly as `find_route`: the Guide's rules, the user's profile, its closures) and Atahan's
  `find_nearest` gets `closed` (closures for one question) and a 12-candidate straight-line shortlist (a
  `route_to_nearest` tool of ours was dropped in favour of it). Claude API failures become a readable sentence + code
  (`backend/service_errors.py`: credits, auth, busy, unavailable, offline, internal) in the Guide and Builder streams
  and as 503/429 on plain requests; the app shows it (and says it on voice turns) instead of
  `BadRequestError: Error code: 400 - {...}`.
- **Learned (old dev Guide vs new, one run each, ~$2.4):** capability set (5 questions with code-computed answers,
  proc-factory-dev-004) 3/5 → **5/5** (old miscounted rooms as 31 spaces and first routed a wheelchair user through the
  closed lift); `eval_guide` 17/18 → 18/18; interaction judge asks 3.33 → 3.83, shows 4.17 → 4.00, directions 3.67 =
  3.67, remembers 4.17 → 4.33, goal 4/6 → 3/6 (noise level). The judge found one real bug: `compute`'s `route()`
  ignored the bay rule and profile, so it contradicted `find_route` (technician scenario) — fixed, rerun: goal reached.
  Out of API credit, the app used to show a raw error string — now the readable note.
- **Docs:** `docs/architecture/ai-agents.md` updated: `find_nearest(start, query, floor_id?, closed?)` (per-question
  closures, 12-candidate shortlist) and the new `compute(code)` tool in the tool table and the implemented list.
- **Next:** ship, push to PR #2; ElevenLabs key is empty in `.env` (browser voice in use).

## 2026-10-25 — Plan import merged into local dev; builder_imports migration applied

- **Did:** local `dev` fast-forwarded to `3-plan-import` (`99e6203`; not pushed — the main checkout was on another
  session's branch with open work, left untouched). The `builder_imports` migration was applied by Utku (the permission
  classifier blocked it as a production change; `.superpowers/runs/migrate.sh` held the documented command); a
  read-only check shows columns `id, building, created_at` and RLS on.
- **Next:** push `dev` when Utku says so.

## 2026-10-25 — Plan import: final review fixes

- **Did:** whole-branch review (opus) → "with fixes". Fixed with a failing test first: `/imports` admin-only in access
  mode (it let anyone start paid Creator runs; frontend now sends the token and hides the buttons for non-admins);
  merges of cells that don't touch are refused (one was silently dropped); a scale-bar scale is never rescaled by the
  alignment, an aligned one is noted `+aligned`; closing the stream cancels the Creator (and the screen aborts on
  leave); a stream without its last line is an error in the UI; PDF pages render straight at the working size, ≤ 40
  pages / images per import, scanned pages not added twice. End-to-end: the Builder fixed an unreachable kitchen on
  the Urban Colab draft (door proposal → apply → Save → `user/munich-urban-colab`, route F0 → F4 104 m).
- **Deferred minors:** no reachability check without an entrance; carved / coarse rooms not marked per space; imports
  never cleaned up; photos decoded at full size first; `%PDF-` only at byte 0; door scale not recomputed after door changes.

## 2026-10-25 — Plan import: origin/dev (new UI) merged into 3-plan-import

- **Did:** merged `origin/dev` `ed7e974` (voice, Access mode, Sunday agent, Edit mode inside the building view) with
  dev as the base. Conflicts: `backend/app.py` imports (kept both), memory-bank log / project-state (kept both sides).
  The standalone `EditMode` is gone in dev → the import screen now hands the base to `Root` (`?building=import/<id>&
  edit=1`), `BuildingScreen` takes `startEditing`, `SessionStore` opens a private import base (not in the catalogue).
- **Learned:** `npx tsc --noEmit -p .` checks nothing in `frontend/app` (root tsconfig has `files: []` + references) —
  earlier "typecheck clean" claims in this branch were vacuous; the real check is `npx tsc -b --noEmit` (now clean).
  `tests/test_commit_hook.py` fails while a merge has unmerged index entries (`git write-tree`); passes once resolved.
- **Checked:** `uv run pytest -q` 944 passed, 2 skipped; `tsc -b` exit 0; headless Chrome: upload → Creator → Edit mode.

## 2026-10-25 — Creator live results; stable door numbers; what counts as a floor plan

- **Did:** door candidates keep the number they were drawn with ("d<n>"), so merges no longer shift them; the prompt
  defines a floor plan (rooms divided by walls) and forbids made-up rooms; full eval and demo runs.
- **Learned:** eval (8 dataset floors): count ratio 0.97, IoU 0.91, doors 89 %, ≈ $1.09. Urban Colab: off-wall doors
  49 → 13 with stable numbers, errors 69 → 23, ≈ $1.73 (cache fix measured: ≈ $1.24–1.73 vs ≈ $4.80; the "before"
  figures come from the previous run's output, whose log was overwritten — UNVERIFIED from a saved file).
  Projektsteckbrief first turned a landscape plan into "blocks" (`.superpowers/runs/live_projekt.log`) → now `no_plan`
  in 10 s (`live_projekt_after.log`). Rathaus 59 spaces / 0 errors.
- **Next:** merge origin/dev (new UI), show the imports there; final branch review; merge to dev with Utku's go.

## 2026-10-25 — Creator cost: stop rewriting the prompt cache every turn

- **Learned:** cost by run at Opus 5.5 prices (input $4, output $20, cache write ≈ $5, cache read $0.20 per MTok):
  ResPlan floor ≈ $0.08, Residenz ≈ $1.50, Urban Colab ≈ $4.80 — of that ≈ $4.4 was cache *writes* (0.87 M tokens),
  because dropping one old image per turn changed the conversation prefix every turn.
- **Did:** images now stay; only past 40 are all but the newest 8 dropped, in one cut (`agent/creator.py` `prune`).
  Expected Urban Colab ≈ $1.5–2 (estimate, to be measured on the next live run).

## 2026-10-25 — Plan import: stacking fix, API errors, docs; credits ran out

- **Did:** floors registered with a relative-scale search (each photo has its own px/m), stairs / lifts joined by name
  before distance, unconnected consecutive floors get their nearest pair (`synthetic: true`); the Creator ends with
  "Claude API error: …" instead of a traceback; Creator docs in ai-agents.md + commands.md; import screen checked in
  headless Chrome (upload → streamed lines → Edit mode, NO PROBLEMS).
- **Learned:** the Urban Colab run (5 floors, 107 spaces, 329 s, ~0.87 M cache-write tokens) failed on stacking, not
  on reading: 80 rooms unreachable. EditMode's header class `.guide-line` has no CSS any more (pre-existing).
- **Blocked:** the API key's credit balance ran out mid-run → no live runs until topped up.

## 2026-10-25 — Plan import: Creator agent, /imports/stream, import screen

- **Did:** Tasks 8–12 of the [plan](../docs/superpowers/plans/2026-10-25-plan-import.md): private import drafts,
  Creator tools + loop, `/imports/stream`, import screen, HEIC, dataset eval + live runner. Live: resplan-439 render 8/8
  rooms in 23 s; Residenz PDF 2 floors / 56 spaces / 0 errors in 174 s.
- **Learned:** walls segmentation misses rooms open to the outside (foyers) → `add_rooms` with cell 0; the model
  falls back to coarse boxes on busy plans (escape-plan photos, the Residenz brochure) and still names rooms well from
  legends; wall-mask thresholds 190 / 50 lift dataset IoU 0.30 → 0.40; Utku's Photos drag-out gave 768 px previews,
  the originals are HEIC 5712×4284.
- **Next:** Urban Colab re-run, browser check, full eval, docs.

## 2026-10-25 — Plan import (Creator), core stages 1–7

- **Did:** designed Builder project 2 with Utku ([spec](../docs/superpowers/specs/2026-10-25-plan-import-design.md),
  [plan](../docs/superpowers/plans/2026-10-25-plan-import.md)); built the deterministic core `core/plan_import/`
  (ingest, rectify / crop / wall mask, cells, labels, scale, stacking, assembly) on branch `3-plan-import`
  (worktree `.claude/worktrees/3-plan-import`). New deps: numpy, opencv-python-headless, pypdfium2, pypdf, pillow,
  python-multipart.
- **Learned:** door gaps close at 6 × the measured wall thickness (scale-free); "outside" must come from the
  building footprint, not the image border (wide foyers leak); Residenz walls are shades of the fill colour →
  separator mask with straight thin lines (hatching ignored). Urban Colab photos are only 768×1024 px.
- **Next:** draft store import bases, Creator tools + loop, `/imports/stream`, import screen, eval, demo runs.

## 2026-10-25 — Round buttons, one size system (6fa882e)

- **Did:** buttons across `building/hud.css`, `access/access.css` and `edit/edit.css` are round with three heights,
  32 / 36 / 44 px (`--btn-sm` / `--btn-md` / `--btn-lg`), filled with `--hud-fill` / `--hud-fill-2` variants, and share
  one set of press / hover / disabled rules. Floors: a popover on phones, the rail on wide screens.
- **Checked:** `npx tsc -b` clean. Not checked visually in this commit pass.

## 2026-10-25 — `find_nearest`: "nearest toilet" without asking (6fa882e)

- **Did:** new Guide tool `find_nearest(start, query, floor_id?)` (`agent/tools.py`): rooms holding that item kind
  (else rooms of that kind/name), ranked by route length under the profile; routes to the nearest (one `route`
  event) + `highlight`, returns `nearest` and `next_nearest` (next 2, with `about_m`). System prompt
  (`agent/guide.py`): "nearest/closest X" → `find_nearest`, take them there without asking; added to
  `PROFILE_TOOLS`. Also in `Guide.set_location`: moving the figure within the same room only updates the point and
  queues no new location note. The app sends `routeStep` only while the route is being followed (guiding, walking,
  or past step 1; `BuildingScreen.tsx`).
- **Checked:** smoke run on `proc-campus-train-000`, from Main lobby, query "toilet" → Toilet 0.14 at 17.99 m
  (about 20), next Toilet 1.16 about 35 m and Toilet 0.16 about 45 m; events `route`, `highlight`. No unit test yet.

## 2026-10-25 — Step guide: map faces the step, animated route band (6fa882e)

- **Did:** step moves (`BuildingScreen.onMove`) pass a heading (step start → end, `RouteTrack.at`) into `Focus`;
  `PlanView` Rig turns the camera to it (azimuth = atan2(-hx, hy)). Route band shader (`StoryLayer` Route) draws
  flowing chevrons (`ribbon` now carries `across`, and exact along/across in the round joints), greys the walked
  part and keeps chevrons on the current step only (`Story.step`, `RouteTrack.toLine`); a `goal` marker shows the
  next step's TurnIcon at the step's end; without tracking the "you" dot sits at the step start.
- **Learned:** `half` is a reserved word in GLSL ES — a uniform named that silently fails to compile the shader.
  Heading from only the first few metres turned the map by a door kink; start → end keeps the goal straight ahead.
- **Checked:** `tsc -b`, `vite build`, browser run (U-Trakt, N0177 → N0111, steps 1–4 screenshotted).

## 2026-10-25 — Building centred on open; "you are here" figure placement reworked (6fa882e)

- Wide screens framed the building as if the Guide were a full-height left column (480 px) → it sat right of centre.
  `PlanView` `frameInsets` (whole-building fits) now mirror the floor rail; `insets` still used for answer focus.
- Figure: the drag ghost lived inside the dock, whose `backdrop-filter` made it the containing block of the fixed
  ghost (invisible while dragging) → moved over the plan, with a live label of where it would land. A tap on the dock
  no longer drops it mid-screen: it arms placing (next tap on the plan, Esc cancels). Off the building it stays where
  it was put, with a dashed line to the nearest entrance of that floor and an "Entrance" marker (`Me.door`, sent as
  the location point so routes start at the door); on a wall → room within 0.6 m. First version snapped the figure
  onto the door and left the placing ghost frozen while panning (looked like two figures) — both fixed.
- Checks: `tsc -b`, `vite build`; headless Chromium (Playwright) runs of tap-place, dock drag, figure drag in/out,
  pan while placing and after: one figure each time.

## 2026-10-25 — Voice less jumpy: longer end pause, voice gate, steadier barge-in (6fa882e)

- **User report:** voice cuts the user off mid-sentence, the Guide's own reply keeps getting interrupted, and it
  "hears" things in silence.
- **Changes** (`frontend/app/src/voice/useVoice.ts`, `bargeIn.ts`):
  - end-of-utterance pause 1000 → 1700 ms; 2800 ms when the last word leaves the sentence open (`OPEN_ENDINGS`:
    "and", "to the", "ve", "için", "um", …).
  - voice gate: the level meter counts frames above `VOICE_LEVEL` (0.12); words recognised before ~8 voiced frames
    neither show nor extend the listen, and a listen that never heard a voice sends nothing (logged). Ungated when
    the meter could not open, and for words carried over from barge-in.
  - barge-in: grace 1000 → 1500 ms, "talk" needs ≥4 own words (was 3) held over 700 ms of results (was two results
    in a row); carry pause 2000 → 2500 ms.
- **Checks:** `npx tsc -b` clean; oxlint shows only the 3 pre-existing `react(immutability)` warnings.
  Not tried in the running app; `VOICE_LEVEL` may need tuning per mic.

## 2026-10-25 — Step card and Guide in sync (6fa882e)

- **Did:** user report: in route mode the voice Guide talked about step 2 or 3 while the step card stayed put. The
  card only moved on short local commands ("next", "back"); longer turns went to the Guide, which neither knew the
  card's step nor could move it. Now: the app sends `route_step` (the card's 0-based step, while a route is on the
  map) with `/chat` and `/chat/stream`; the Guide gets a `[route note]` listing the card's steps and the current one
  (`Guide.route_note`, `BuildingSession.route_card`); new tool `show_route_step` (1-based, card numbering) emits a
  `route_step` event; the app moves the card/map there, starts the step guide if needed, and doesn't read that step
  aloud again over the reply (`quietStep`). System prompt tells the Guide to call it when it talks about another step.
- **Learned:** find_route's `steps` (core/directions.guidance_steps) add a "Start in …" line before the card's steps,
  so the Guide's "step 2" was the card's step 1 — the route note gives the card's numbering.
- **Checked:** `uv run pytest` 815 passed, 2 skipped (new `tests/test_route_step.py`); `tsc -b` clean; `npm run
  build` ok. Not checked live with the LLM (restart uvicorn to pick it up).

## 2026-10-25 — Route line: starts at the figure, no dip at overlapping-space doors (6fa882e)

- **Did:** user report (CIT building `dev/osm-way27917482`, from Friedrich L. Bauer Hörsaal the line dipped into a
  Regieraum doorway and the route always started at the room's centre). `core/routeline.py`: `route_line(...,
  start=)` starts the line at a given point in the first space; a door whose two landings each lie in the other space
  (`overlap_at`) is dropped with its landings. Backend: `PUT /sessions/{id}/location` takes `point` (kept in
  `user_location` only if inside the room), route events carry `start_point` when the route starts in the figure's
  room (`BuildingSession.start_point`, also `agent/campus.py`); a move within the same room sends no new location
  note. App: `api.setLocation(..., point)`, `placeMe` sends it when the figure moves.
- **Learned:** in that building the hall's OSM outline contains all of Lobby 0.22; their only door `F0-O0008` sits on
  the Regieraum's wall, so both landings fall on the same side. All 392 routes from the hall leave through it. Route
  lengths (anchor-based, kit model) are unchanged; only the drawing moved. Random sample of 1,976 route doors on dev:
  none dropped (the rule only fires on overlaps).
- **Checked:** `uv run pytest` 813 passed, 2 skipped; `tsc -b` clean; TestClient on the CIT building: line starts at
  the figure point and has no point at `O0008`. Not checked in the running app (the local uvicorn on :8765 has no
  `--reload`; restart it).

## 2026-10-25 — Map: whole building clickable, touching buildings told apart (6fa882e)

- **Did:** `map/style.ts`: `MODEL_TONES` + `modelTones` (greedy colouring: kit buildings whose outlines come within
  ~4 m get different shades), `modelColours(dark, tone)` with `hover` and `edge` colours. `map/MapLanding.tsx`: models
  source keyed by id (`promoteId`), blocks and footprints coloured by `tone` and lit on hover (pin and block together,
  `hoverBuilding`), new `model-edges` line layer tracing every footprint; hidden for the open building like the rest.
  `map/bridge.ts`: neighbours around an open building use the same tone; `model-edges` filtered with `model-blocks`.
- **Checked:** `tsc -b` clean, oxlint clean on `src/map`; Chrome (dark): campus around Arcisstraße 21 shows alternating
  shades + outlines, hover lights the whole Hauptgebäude block, a click at the far end of the Thierschbau wing opened
  `train/osm-way61408163`. Light mode not checked visually.

## 2026-10-25 — Calmer barge-in, readable nearby-buildings card, bigger map click target (a9cff16)

- **Did:** Barge-in no longer fires on one stray word: `voice/bargeIn.ts` `interruption` now needs a stop word in a
  phrase of ≤3 words, or ≥3 own words that are at least half of the user's part; `useVoice.ts` ignores results in
  the first 1 s of the voice (`BARGE_GRACE_MS`) and holds "talk" until two results in a row (or a final one) agree.
  Nearby-buildings card (`building/Elsewhere.tsx`): own buttons (Directions in the route blue, Open outlined), names
  ellipsised, rows wrap. Map (`map/MapLanding.tsx`): a building opens from its pin, name, halo or block, with 14 px
  slop; the nearest pin wins when pins overlap.
- **Learned:** the dark-mode buttons were unreadable because `.screen button { color: inherit }`
  (`building/screen.css`, 0,1,1) beat `.hud-pill` (0,1,0): text took the panel ink, same as the solid fill. Fixed by
  scoping `.screen .hud-pill` (also fixes the camera pill in `NextMove`).
- **Checked:** `tsc -b` clean; oxlint warnings only (pre-existing); in Chrome (dark + light): card buttons
  rgb(75,133,255)/white and transparent/ink; a click 15 px off a pin opened the nearest building; interruption cases
  via node ("okay", "hmm", misheard echo → nothing; "stop", "wait please" → stop; "actually where is the cafeteria"
  → talk). Not tested with a live microphone.
- **Changed docs:** `docs/architecture/ai-agents.md` (barge-in rules).

## 2026-10-25 — Voice gaps: tapped questions spoken, selection and "I'm in …" reach the Guide, faster turns (e8de230)

- **Did:** Tapped questions (room card Directions, chips, nearby-building directions, camera "Where am I", Builder
  chips) are answered aloud: `send(text, via)` in `BuildingScreen.tsx`, voice channel with `heard: false` (no
  transcript rewrite, `Guide.reply(heard=)`); one that asks something back listens for the answer. The room or item
  selected on the plan goes with the question (`/chat` `selected` → a `[selection note]`, `Guide.selection_note`).
  New Guide tool `set_my_location` (on `session.set_location`) + event `location`: "I'm in Lobby 0.01" puts the figure
  there and frames the room; the offline Guide understands "I'm in/at …" and "take me to …" from here. "start" also
  inside a short sentence; the step guide keeps listening 45 s for "I'm there" (`waitMs`/`until` in useVoice).
  Latency: end-of-speech pause 1.3 → 1.0 s, Scribe commit wait 2 → 0.8 s, mic + worklet kept warm 8 s, the real mic
  remembered when the default input is virtual (was two opens per listen), barge-in from the reply's first sound and on
  one own word, an utterance during a pending turn is queued. "Mic starting" until audio really flows (`hearing`).
  TTS: a failed piece is retried once; cool-off 60 → 15 s; a short first sentence ("Step 2.") rides with the next.
- **Checked:** `tsc -b`, oxlint (warnings only, none new as errors), full pytest (810 passed, new
  `tests/test_voice_location.py`). In Chrome on the local backend (Arcisstraße 21): "I'm in Lobby 0.01" → figure and
  zoom; route + Start + next step → `/tts` 200 for every step (ElevenLabs); room tap → Directions → voice turn with
  `selected`, spoken, then the mic opened by itself for the answer ("Mic starting" ~0.7 s).
- **Learned:** could not reproduce steps in the browser voice; the likely cause was the 60 s cool-off after any one
  failed piece. Auto-listening also catches room talk (it sent "No. How was-" from background speech).
- **Next:** Atahan to try by voice; consider browser recognition for short step commands to save Scribe minutes.

## 2026-10-25 — Edit mode inside the building view (e8de230)

- **Did:** Edit mode is no longer a separate full-screen editor (`EditMode.tsx`, `PlanEditor.tsx` deleted). "Edit this
  building" (… menu) keeps the building screen — map, model, top line, floor chip — and: the model shows the draft
  (`GET /drafts/{id}/plan`, refetched after every change, one floor); the edit card (`edit/EditPanel.tsx`) takes the
  Guide card's slot (tools Select / Door / Item, problems, undo, Inspector, "Describe a change instead" → Builder chat,
  Save as a new building); handles sit on the model in `edit/EditLayer.tsx`, an SVG whose group PlanView keeps on the
  floor plane (`align` prop + `Align` in `plan/PlanView.tsx`: the camera is orthographic, so the plane maps to the
  screen affinely; 3 projected points per frame). State in `edit/useDraft.ts`. Taps on the model select rooms /
  items (PlanView's own picking) or, with the Door / Item tool, place (`place` ref) — pan / zoom / tilt keep working.
  Inspector: room name / number / use / delete, door kind / width / step-free / delete, item name / size / turn /
  delete. Wall drags (`move_edge`), corner drags, door drags, item drags with a readout. Phone inset `EDIT_PX`.
  Story, focus, figure and next-move are hidden while editing (their state is kept).
- **Learned:** a first version as a restyled separate screen was rejected by Atahan: Edit mode must live in the
  current view. `.screen button` (0,1,1) beats single-class button rules — scope them.
- **Checked:** `tsc --noEmit`, `vite build`. Headless Chromium (playwright-core in the scratchpad) on the local
  backend, Forschungsbau 024, tilted 3D view: tap selects Toilet 0.16, corner / wall handles in register with the
  model, wall drag → 1 change and the model redraws; door tool → door Office 0.15 ↔ Toilet 0.16 (2 changes, 3
  problems listed); item tool → Plant placed + selected, dragged; Stop editing → Guide back; 390 px phone layout.
  Not checked: real touch device, live Builder chat, save → reopen.
- **Then (same day, Atahan: "use the same AI assistant UI"):** the edit card is gone (`EditPanel.tsx`,
  `BuilderChat.tsx` deleted). While editing, the Guide's own card (`building/Guide.tsx`, new optional `persona` +
  `card` props) talks to the Builder: greeting, chips from the building's rooms, typed or spoken requests (voice
  `onUtterance` routes to `draft.ask` while editing, replies spoken), the Builder's tool steps as the work trail
  (`ui/guideSteps.ts` labels for overview / find / space_info / floor_plan / propose_edit). The inspector and the
  Builder's proposal (Apply / Cancel) show in the card's room-card slot (`edit/EditCard.tsx`). Tools, problems, undo,
  Save, Done moved to `edit/EditBar.tsx` (top right; under the top line on phones). Header: "Editing a copy · N
  changes"; "All floors" hidden while editing. Live check (Opus via the local backend): chip "Rename 0.03" → trail →
  proposal card + dashed ghost on the model → Apply → label "Quiet room" on the model.
- **View behaviour (Atahan's list):** PlanView — labels no longer vanish when zoomed out (a room too small for its
  name gets its number, else its name, at 10 px; only overlapping labels are skipped); one tap on the stacked view
  steps onto the floor *and* selects the room; changing floors keeps the camera (Rig no longer refits on a floor
  change, nor when the plan object is replaced by the same building — draft edits used to snap the camera back —
  and keeps the user's tilt); the floor under the mouse lights up in "All floors" (`FloorGlow`); the Edit mode no
  longer forces one floor (handles hidden while stacked, a tap steps in and selects). `hud.css` `.screen
  .hud-primary`: the room card's Directions button text was invisible (`.screen button` won). Checked headless:
  hover glow top / ground floor, one tap → Lecture hall 0.19, zoomed G → 3 same camera, far zoom labels, camera
  unchanged after a wall drag, edit + all floors one tap → Office 3.09 with handles.
- **Improvements + the Guide opens the Edit mode:** new Guide tool `open_edit_mode(request?)` (agent/tools.py) →
  UI event `edit_mode` → the app switches to the Edit mode and hands the request to the Builder (spoken stays spoken;
  access mode: admin only). Prompt rule in agent/guide.py (closing / reopening / adding a door for routing stays
  propose_change); offline intent `EDIT` in agent/offline_llm.py; `tests/test_edit_mode_tool.py`. Edit mode: one
  tap places with Door / Item on "All floors" too (PlanView `onTap` gives the plan point; `edit/place.ts` shared by
  the ghost and the tap); redo (⇧⌘Z / Ctrl+Y) kept in the tab (`useDraft` remembers the ops of its own steps — no
  backend change, lost on reload); "Discard changes" (asks in place, fresh draft of the original); the Builder's own
  words in the proposal card (markdown stripped); a proposal steps onto its floor. **Learned:** `tsc -p .` in
  frontend/app checks nothing (`files: []`) — use `tsc -p tsconfig.app.json`; a local backend with `.env` writes
  drafts and saved buildings to the shared Supabase — run tests with `GUIDE_PERSIST=off`. A test save
  "Forschungsbau 024 quiet test" (`user/forschungsbau-024-quiet-test`) landed in Supabase `saved_buildings` before
  that was noticed; deleted on Atahan's go (that one row only). Checked: pytest 805 passed / 2 skipped; headless live
  run on a separate backend: Guide "rename office 0.03…" → Edit mode, proposal on G with ghost → Apply; Item tool one
  tap on All floors → desk on floor 3; undo → redo; save → reopen as the new building; discard.
- **Next:** commit via `/ship` when Atahan asks.
## 2026-10-25 — Guide highlights, "you are here" figure, step-by-step guide, nearby buildings

- **Did (Atahan's four asks):** (1) clearer answers on the plan: `search` / `locate` / `room_facts` / `show_on_map`
  emit highlights with `asset_ids`; rooms tinted + pulsing + name badges, items ringed; camera frames the answer
  (`PlanView` `focus`, `fitPoints`). (2) Draggable "you are here" figure with a dock (`PlanView`, `StoryLayer`
  `MeFigure`), `PUT /sessions/{id}/location`, `Guide.set_location` → a location note, "here" resolves to it.
  (3) Routes framed whole (stacked across floors), Start → one step framed and read aloud at a time, "I'm there" /
  "geldim" / "next" moves on (`NextMove` actions, `BuildingScreen.routeCommand`); the Guide's route replies are now a
  summary + first step ([D-020](decisions.md#d-020)). (4) `agent/campus.py`: `search_nearby_buildings`,
  `route_to_building` (entrance pair with the shortest total, straight-line outdoor leg), `POST /sessions/{id}/arrive`;
  app: "found nearby" card (`building/Elsewhere.tsx`), dashed outdoor line + Continue that opens the other building and
  draws the rest ([D-021](decisions.md#d-021)).
- **Checked:** `tests/test_campus.py` 10 passed; full suite 801 passed, 2 skipped (offline); `tsc -b` clean; headless
  Chrome (own servers on 8775/5183, real Opus): figure → "Stairwell 0190", "Where are the toilets on the ground
  floor?" answered from the figure ("closest to you") with both toilets tinted and framed; "Take me to the lecture
  hall" routed from the figure without asking (route framed, Start button); "Is there a canteen?" → Mensa
  Arcisstraße found, route to the exit, dashed outdoor line, "Continue in Mensa Arcisstraße · 120 m south-west".
  Not yet seen in a browser: clicking Start / "I'm there", the Continue → arrival in the Mensa. Open bug: the route
  overview did not frame the other building's entrance (the dashed line runs off screen); cause not found yet.
- **Learned:** headless Chrome with SwiftShader takes ~60 s per screenshot of the plan; the "alone" view (no map) is
  faster. Neighbour pins on the TUM main campus are 95–250 m apart, so the campus tools matter there.
- **Not done:** no street graph (outdoor metres are straight lines); the other building's leg ignores this session's
  closures; the interaction eval's directions judge still expects full step lists.

## 2026-10-25 02:50 — Sunday hardening P1: route specs, solver agent, decision cache (branch `4-sunday-agent`)

- **Did:** `core/route_query.py` (one route with any mix of constraints; places = rooms, room types or items, the
  nearest taken via one Dijkstra per leg; on `core.navigation`); LLM schema: general `route` spec + `asks_for`,
  kinds `other` / mismatches → `NeedsAgent`; simple specs keep the warm-up kinds and v1 solvers.
  `agent/solver_agent.py`: Opus 5.5 tool loop with a `python` sandbox (restricted builtins, module whitelist, 30 s,
  deep-copied building) and `submit_answer`; 2 runs, a third on disagreement, majority; Answer line by code.
  `agent/llm_cache.py`: parser slots and agent submissions (with code) keyed by building hash + question + version,
  replayed first. Probe set `tests/sunday_probe/proc-factory-dev-004.json` (expected answers by direct code) +
  `scripts/eval_sunday_probe.py`. Solver agent effort lowered to `medium` (Utku).
- **Learned:** the first live probe was 14/14 but every question went to the agent: the new schema had 21
  union-typed parameters and the API rejects more than 16 (HTTP 400 on every parser call) — the fallback masked it.
  Fixed (flags plain booleans, empty lists, `""` floors; 12 unions) and guarded by a test; agent answers now carry
  `parser_failure`. After the fix: 14/14, parser for 10 reworded routes/locates, agent only for the 3 new kinds
  (smallest room, room count, narrowest door), 76 s (high) / 71 s (medium). Replay with an empty key and an
  unreachable API base URL: 14/14 identical in 0 s. Tests initially wrote to the committed cache → `tests/conftest.py`
  sets `LLM_CACHE=off`. The old pipeline's silent errors confirmed: p09 70.59 m (true 107.02), p12 30.85 m (0.9 m),
  p13 31.24 m (no route).
- **Decisions:** D-022 proposed (numbered D-015 on the branch; renumbered when merging `dev`, which had D-015–D-021).
- **Next:** ship P1, merge `4-sunday-agent` into `dev` (ask before pushing); P2 (bay / forklift rules on Sunday) when
  the question file shows the wording; Sunday run → commit `answers.json` + `llm_cache/decisions.json`.

## 2026-10-25 02:20 — Sunday hardening P0: crash-safe runner, hybrid by default (branch `4-sunday-agent`)

- **Did:** probed the v1 pipeline with 14 Sunday-style questions on `proc-factory-dev-004` (paraphrases, no floor
  name, item as destination, blocked aisle, forklift, step-free + closure, new analytics). `regex` answered 1/14;
  `hybrid` 11/14 without an error, but at least 4 of those answer a different question (wheelchair route → `locate`,
  forklift → plain step-free route, closure + step-free → closure only, "narrowest door" → route length), 3 errors
  (space closure, "smallest office", "how many rooms" → `unsupported`). Then P0: `respond` never raises (API /
  geometry / unreadable building → `error` entry), the runner rewrites the answers file after every question (via a
  `.partial` file), reads `.env` itself, records `parser` and the PDF's top-level ids (`item_id`, `space_id`, whole
  `space_path`, `element_path`, `length_m`, `reachable`), `--layout dict`; LLM parser `max_retries=4`.
  `SUBMISSION/answers.json` regenerated: 145 replies, results and routes unchanged, new keys only. BENCHMARK.md,
  commands.md and the state say `hybrid` for Sunday.
- **Learned:** the LLM parser must squeeze every question into one of 15 fixed templates, so combined constraints
  and new kinds become near-miss kinds — silently wrong answers, worse than errors. `core.navigation.find_route`
  already handles space/door closures, item endpoints, step-free + closures and `RouteRules` (forklift, bays).
  Rehearsal of the Sunday command on one dev building: 27 questions in 73 s (14 template, 13 LLM at ~5 s each).
- **Next:** P1 — compositional route spec into `find_route`, agentic tool-use fallback for unsupported kinds,
  answer-type check, nearest-of-many items.

## 2026-10-25 — City view: wireframe, flicker, cut-away, ground level, return flight

- **Did:** open building's OSM blocks → wireframe in the model's scene (`PlanView` `City`); OSM blocks under the blue
  model blocks left out; blocks in front of the model cut away to ghost layers; ground-floor line + underground
  veil over basements; Back flies the map to the camera it had on opening (`src/map/*`, `PlanView`, `BuildingScreen`).
- **Learned:** OpenMapTiles merges same-looking blocks into one MultiPolygon feature; matching only its first
  polygon missed Arcisstraße 21 entirely (the old shell never showed there). At the 1° field of view, 0.4–0.6 m
  offsets still z-fight, so coplanar blocks have to be removed, not nudged. `osmHeights` still tests only the first
  polygon of a merged feature (not changed).
- **Changed docs:** [visualization.md](../docs/product/visualization.md#current-vector-plan-view-2026-10-24).
- **Fix (same day):** hiding a merged feature by id made whole districts of buildings vanish from the map (one
  feature held 1,797 polygons); now its other polygons are put back from a `rest` GeoJSON source.
- **Perf pass (same day):** cut-away moved from `setFilter` ghosts to feature-state flattening; block gathering and
  OSM heights only after new tiles (not every idle), with box prefilters; `osmHeights` now per polygon too.
  Measured: `applyBlocks` 183 → 16 ms, `osmHeights` 68 → 7 ms, filter changes per rotation 54 → 2. The model renders
  in ~0.6 ms and the frame times did not change with the pixel ratio, so render size is not the bottleneck.
- **X-ray (same day):** Atahan found whole blocks popping in and out too abrupt and asked for an x-ray (only the part
  in front, dithered edge). Now a MapLibre custom layer draws the blocks within 500 m with MapLibre's own lighting
  and cuts per pixel in a rounded box over the building, dissolving in a Bayer dither. Checked in dark and light
  themes; frame times unchanged (p50 8 ms, p90 17 ms).
- **Footprints + road widths (same day):** cut blocks leave their footprint on the ground; roads drawn at estimated
  real widths per class (the tiles have no width attribute).
- **Walkways (same day):** the dashed path line replaced by solid walkway / cycle-path lines and tread-dashed steps.
- **Next:** tune the x-ray size/softness with Atahan; ask which issues still remain.

## 2026-10-25 02:00–05:00 — Access mode: accounts, restricted spaces, preferences, moving objects

- **Did:** reviewed Utku's access-roles spec with Atahan; wrote the replacing design
  ([access-profiles-design](../docs/superpowers/specs/2026-10-25-access-profiles-design.md), D-015) and plan.
  Backend: `core/access.py` (filtered building copy), `backend/access.py` (switch, Supabase token check, rules,
  members, invites), `core/preferences.py` (soft penalties / avoided room types, true metres reported),
  RoutingProfile preference fields + `set_preference` + `preference` events (gated: only with access mode),
  `core/fleet.py` + `backend/fleet.py` (objects, positions, missions, forklift import, Guide `send_object` for the
  admin), `scripts/sim_object.py`, migration `20261025200000_access.sql` (applied; Postgres stores round-trip
  verified live, test rows removed). Frontend (subagent): sign-in, darkened restricted spaces, Preferences,
  Building settings (My preferences, Access, Members, Objects), object markers / trails / mission lines.
  Committed without a parallel session's unfinished `src/map/` work, which stays in the working tree.
- **Learned:** openings have no height and lifts no cabin size → height/weight attributes left out; 107 forklifts in
  `equipment.csv` with position + footprint; route_line passes exactly through door positions (mission split points).
- **Checks:** `uv run pytest` 770 passed, 2 skipped; dev benchmark 138/138 (regex); `tests/test_access.py` 12,
  `tests/test_fleet.py` 5.
- **Next:** create the admin account (Atahan's email), live sign-in check, demo run with the simulator.

## 2026-10-25 — Voice step 4: ElevenLabs Scribe Realtime with building keyterms (branch `voice-improvements`)

- **Did:** `backend/stt.py` (single-use token, `keyterms(building)`), `POST /stt/token`, `/health` `stt`,
  `STT_MODE`; `frontend/app/src/voice/scribe.ts` `ScribeRecognition` (SpeechRecognition shape, AudioWorklet 16 kHz
  PCM, token fetched ahead, 60 s cool-off on failure); `useVoice` prefers it and retries with browser recognition on
  `scribe-unavailable`; `BuildingScreen` sets the Scribe session. `tests/test_stt.py`; suite 773 passed, 2 skipped.
- **Learned:** live probes — `keyterms` repeated in the query; > 50 terms or > 20 chars → `invalid_request`. Scribe
  repeats the same partial every ~1 s through silence, which kept the pause timer from firing (fixed: only changed
  partials count). With ElevenLabs-spoken audio as the mic, "Where is the CNC mill?" came back exactly.
- **Decisions / questions:** D-019 accepted; Q-020 opened (keep the rewriter for Scribe transcripts?).
- **Next:** real-mic run of the whole voice loop; Q-020; commit via `/ship`.

## 2026-10-25 — Voice step 3: hands-free conversation, barge-in, pause tolerance (branch `voice-improvements`)

- **Did:** `useVoice`: continuous recognition with a 1.3 s end-of-utterance timer (8 s / 6 s with no words),
  conversation mode for spoken questions (listen again after the reply, quiet end), barge-in watcher while the
  complete reply plays; `voice/bargeIn.ts` echo filter (`userWords`, `interruption`, `userPart`); `stream`/`speak`
  take `{ conversation }`; `BuildingScreen` no longer forces one question, one answer; orb hint "Talk to interrupt".
- **Learned:** verified with a scripted SpeechRecognition in the real UI. First run carried the echo ("About 60 m,
  stairs allowed.") into the next question because the stray "m" counted as the user's → single letters ignored,
  carry starts at the first result that is mostly the user's. Automation re-sends pointer events at the last click
  position, which looked like spurious orb taps (not app behaviour; a traced run was clean).
- **Decisions:** D-018 accepted.
- **Next:** try it with a real mic/speakers; voice step 4 — Scribe Realtime with building keyterms.

## 2026-10-25 — Voice step 2: speak while the Guide works (branch `voice-improvements`)

- **Did:** `SpokenStream` (`agent/speech.py`) + `Guide.on_say` / streamed requests (`agent/guide.py`): grounded
  sentences go out as `say` lines on `/chat/stream` voice turns; repairs / profile redos hold live speech and
  `finish` adds only what is new. `VOICE_STYLE` asks for one fact-free sentence before tools. Frontend
  `openSpeech` queue (`voice/tts.ts`), `voice.stream()`, `BuildingScreen` feeds `onSay`. Suite 769 passed, 2 skipped.
- **Learned:** raw API text streams smoothly (84 deltas over ~4 s), but in Guide turns the answer after tool results
  arrived in one burst every time (with or without the fallback beta) — the win is the early first sentence:
  first sound 2.35 s vs answer at 10.4 s (6 tool calls). The voice rewriter costs ~1.1 s before the first request.
- **Decisions:** D-017 accepted.
- **Next:** voice step 3 — barge-in (stop the voice when the user speaks) and hands-free listening.

## 2026-10-25 — Voice step 1: the Guide speaks with ElevenLabs (branch `voice-improvements`)

- **Did:** Reviewed the voice path: the app used only browser Web Speech; the ElevenLabs Custom LLM endpoint was
  never connected. Added `POST /tts` (`backend/tts.py`, stdlib urllib proxy, key server-side), `/health` `tts` flag,
  `frontend/app/src/voice/tts.ts` (sentence pieces fetched ahead, Web Audio playback with real orb level, browser
  voice fallback, one voice app-wide); `useVoice` / `CameraGuide` use it. Sentence splitter no longer breaks
  "Room 2.03". `tests/test_tts.py`; full suite 762 passed, 2 skipped; frontend build OK.
- **Learned:** account tier Creator, 131,000 chars/month. Flash v2.5 + River: 0.3–1.3 s per sentence server-side;
  Scribe heard "Meeting room 3.07 … 124 meters" back exactly. `speakable()` spells units in English for every language.
- **Decisions:** D-016 accepted.
- **Next:** voice step 2 — stream the reply sentence by sentence into speech, filler while tools run.

## 2026-10-25 — `SUBMISSION/` folder for the graded benchmark (v1 pipeline)

- **Did:** organisers announced the graded folder `SUBMISSION/` with exactly `BENCHMARK.md` + `answers.json`.
  Moved `BENCHMARK.md` there (rewritten around `agent.run_benchmark_v1`) and generated `SUBMISSION/answers.json`
  from the public test set (`PARSER_MODE=regex`, 145 answers, 0 errors; byte-identical to
  `submissions/test_answers.json`). Links updated (README, commands, overview, ai-agents, scoring, Q-001, state).
- **Learned:** the canonical runner (`agent.run_benchmark` → `core/solvers/`) has no solvers for the warm-up kinds:
  all 1,338 train+dev route questions (route, step-free, closure, tour) → `No solver for question kind`. On the
  test set both runners give the same rooms and numbers. v1 answers routes via `BuildingMap.route`
  (1,338/1,338 exact) → v1 is the submission pipeline. Dev 138/138 with v1 (regex).
- **Next:** Sunday building → rerun the one command into `SUBMISSION/answers.json`; video + tech explanation.

## 2026-10-25 00:14 — Plan images vs `building.json`; submission folder; Level 4 question

- **Learned:** floor PNG/SVGs are Matplotlib renders of `building.json` (floor 0 of `osm-way27917482`: polygons
  match at ~9.98 px/m, per-type counts match) — no extra information; nothing in our code reads them. No kit
  source defines Level 4's input or check. Organisers' Discord note: benchmark graded only from `SUBMISSION/`
  with exactly `BENCHMARK.md` + `answers.json` — already there from 8537ca0 (145 test answers, ids match
  `data/test/questions.csv`, 0 errors).
- **Did:** removed the old lowercase `submissions/` (superseded by `SUBMISSION/`; the README/commands CSV commands
  still work, they create their output folder).
- **Opened Q:** [Q-018](open-questions.md#q-018) (Level 4 input/scoring), [Q-019](open-questions.md#q-019)
  (`SUBMISSION/answers.json` scope/format vs the Discord image).
- **Next:** confirm Q-019 against the Discord image; video + form ([project-state](project-state.md#next-priorities)).

## 2026-10-25 — Open building's map block as a see-through shell

- **Did:** the tile blocks over the open building (same overlap test as the blue blocks' heights, now one `overlaps`
  helper in `src/map/bridge.ts`) leave `buildings-3d` for a new see-through `buildings-3d-shell` layer instead of
  being hidden only when their centre is inside: campus wings drawn as one block with their neighbours no longer box
  the model in. Checked in headless Chrome (Wirtschaftswissenschaften light/dark, N8, Hauptgebäude).

## 2026-10-25 — Map and model back in register (field of view, tilt cap, double mount)

- **Did:** measured model vs map in px (dev-only `window.__plan` + `window.__map`): 4° map field of view was up to
  40 px apart at the corners once the stacked view zoomed in and tilted; now 1° (≤ 10 px corners, ≤ 1 px centre).
  Below 1°, and above 60° tilt at 1°, MapLibre drew no buildings at z15–18, so the model's tilt is capped at 60° over
  the map (`MAX_MAP_PITCH`). React's dev double mount created a second map that kept the first one's "already flown"
  state and ended with the default 36.87° field of view (600 px off): refs reset per map, `follow` enforces the flat
  field of view, FOV eases cancel each other.
- **Learned:** an orthographic model over a perspective map only lines up when the map's field of view is tiny;
  MapLibre's high-pitch tile selection sets the floor (1°) and the tilt limit (60°).

## 2026-10-25 — Map: buildings fitted onto OSM, open with all floors, transition with reduce motion

- **Did:** `scripts/fit_locations.py` refits `origin` per building against its OSM way (translation; rotation adds
  nothing) where the kit footprint is ≥ 75 % of the way: 12 buildings, up to 18 m (U-Trakt), N8 IoU 0.58 → 0.99.
  Partial models (Wolf-Ferrari-Haus, Mensa Arcisstraße, Terminal 2, Haus der Weiterbildung, Pasing Arcaden) kept. Model blocks also take
  their height from blocks with most corners inside (U-shaped U-Trakt). Buildings open stacked. Transition plays with
  "reduce motion" on; the loading status uses a timer instead of a CSS delay.
- **Learned:** Atahan's Mac has Reduce motion on, and dev's `styles.css` turns every CSS animation/transition off under
  it: the transition looked missing because my code skipped it there too.
- **Next:** partial models cannot match their OSM outline; marking them (or drawing only the modelled part) is open.

## 2026-10-25 — Map → building transition, city / alone views (branch `map-transition`)

- **Did:** the landing map stays mounted under the building screen and follows the model's camera
  (`src/map/bridge.ts`); fly-in on tap with the plan preloaded meanwhile (`src/building/opening.ts`), camera hand-off
  from the map and a rise-out-of-the-ground reveal (`PlanView` `Reveal`, `Follow`, Rig intro); fade-out + fly-out on
  back. Menu toggle: building in its city (neighbour pins tappable) or alone. `location.origin` (kit (0, 0)) added
  to `backend/locations.json` from the archived georef.json; the building's own OSM blocks hidden by outline.
- **Learned:** backend session + plan is ~0.4 s; the rest of the old wait was React's dev double mount (two
  sessions) and building the plan geometry (~0.3 s for N3). OpenFreeMap tile building ids are not way ids (N3 is
  drawn as its parts). `setVerticalFieldOfView` fires moveend on each call, so "flight done" waits for `!isMoving()`.
- **Checked:** `tsc -b`, oxlint (no new warnings), `pytest tests/test_backend.py` 22 passed; headless Chrome flows
  (city, alone, pin switch, direct URL, building with no position, back).
- **Next:** decide whether the view toggle deserves a visible control instead of the menu.
- **Then (same branch):** buildings with a model drawn as blue blocks on the map (kit footprint + height into
  `backend/locations.json`, height matched to the OSM block); new light map palette. Tile building ids/polygons do
  not match kit buildings (campus wings are one tile polygon), so we draw our own blocks instead of tinting theirs.

## 2026-10-25 — Pulled `origin/dev` twice (kit 1.1.0 route model, Builder Edit mode) into the uncommitted HUD work

- **Did:** stash → fast-forward → stash apply, twice (26b908f, then b352e83). Text conflicts: `log.md` (all entries
  kept, by time), `backend/app.py` (docstring, imports: Builder/drafts + `devtools`; `/buildings` keeps
  `drafts.refresh` and `location`), `Root.tsx` (`go(…, landing)` + `onOpen`), `BuildingScreen.tsx` ("Edit this
  building" moved into the "…" menu; the old round Fit/Theme buttons stay replaced by the menu), `commands.md`.
  Semantic conflicts: `core/routeline.py` used the deleted `core/geodesic.py` → its in-space walk now uses
  `core/building_map.py`'s `outline` / `door_landing` / `visibility_matrix` (same 15 cm clearance as the route
  model); `EditMode` renders `PlanView` without the now-required `story` → passes `EMPTY_STORY`; the Builder's
  `GET /drafts/{id}/points` (+ `api.draftPoints`, `test_points_endpoint`) dropped: `core/pointcloud.py` is removed
  here and the endpoint was unused by the UI.
- **Checked:** `uv run pytest` 753 passed, 2 skipped; `npm run build` passes; check_links OK. Edit mode not looked at
  in the browser.
- **Changed docs:** commands.md (drafts rows, no `/points`), visualization.md (route line walk).

## 2026-10-25 01:30 — Building screen HUD, step 5: live tracking (no positioning hardware)

- **Did:** `building/tracking.ts` maps metres walked to a point on the route line (walking legs spread over the line
  by their metres, rides take none) plus the direction ahead and the step. `building/useTracking.ts` does dead
  reckoning between fixes: a step = an acceleration peak (DeviceMotion; iOS asks from the Track tap), 0.7 m stride
  (UNVERIFIED, not calibrated), never counted past a ride (stairs or lift are confirmed with "next"). Fixes are the
  start, a door you confirm (›, "next", a tapped segment), or a room of the route the Guide highlights (e.g. "Where
  am I?" from the camera: the route stays, you are where it enters that room). Past 30 counted metres since a fix
  the position is "unsure" (amber, asks for a sign). `?walk=sim` walks at a steady pace for demos and checks.
  On the plan: a "you" marker (dot, accuracy ring, cone towards the route ahead) in `dev/StoryLayer.tsx`'s DOM
  markers via `story.you` (set by BuildingScreen, `PlanView.tsx` untouched). The card counts the metres down and
  says where the position comes from and how old it is; Track toggle on the card. Prev/next chevrons now show only
  in the camera view (on the plan: tap the card, or a segment).
- **Checked:** `tsc` + oxlint clean for src/building; screenshots of a simulated walk: start (green, 4 s ago),
  after 40 s (step 3 by counting, amber "Unsure: 50 m counted"), and a tapped step 4 (green, door fix, just now).
  Not checked on a real phone; the camera fix path needs the real Claude Guide (offline can't read photos).
- **Next:** the plan doesn't follow the dot yet (needs PlanView's camera rig); calibrate the stride.

## 2026-10-25 00:50 — Building screen HUD, step 4: walking with the camera

- **Did:** `building/CameraWalk.tsx` (full-screen rear camera, floor chevrons that bend with the step's turn, the
  next room + metres floating ahead, the next-move card inline at the bottom, the Core, "Where am I?"). It shares
  the step index with the plan's card, so card, camera and voice can't disagree. In camera mode `BuildingScreen`'s
  voice handler takes "next / back / repeat" (EN/DE/TR words, as in the old CameraGuide) and sends anything else to
  the Guide with the current frame (`building/frame.ts`, `chatStream` `photo`); each step is read aloud unless muted.
  A "Camera view checked · N s ago" chip appears after a frame was sent. Entry: the "Camera" button on the card.
  The old `ui/CameraGuide.tsx` (not wired in, and it uses the anchor-based leg turns) is left unused.
- **Checked:** `tsc` + oxlint clean for src/building; screenshots with a stand-in camera feed (a canvas stream of
  the corridor drawing) on a phone (step 1, step 5 turn left) and desktop. The offline Guide can't read photos
  ("Where am I?" answers "Sorry, I can only repeat…"); that needs the real Claude Guide.
- **Next:** step 5 (live tracking) needs a positioning plan; highlight the current step on the plan (StoryLayer).

## 2026-10-25 00:20 — Building screen HUD, step 3: the next-move card

- **Did:** Found that a route event's `legs` turn at the room anchor (`route_legs`) while the Guide's text turns
  where a person makes the turn (`guidance_steps`): leg "Corridor 0130" says right, the Guide says "Turn left …
  into Corridor 0110C". So the card uses the Guide's steps: `core/directions.guidance()` now returns them as data
  ({kind, turn, metres, to, floor, door, landmark, via, via_kind, up, floors, text}), `guidance_steps` formats from
  it, and `backend/sessions.enrich` adds `steps` to every route event. Frontend: `GuideStep` type, `StoryRoute.steps`
  and `profile`, `building/NextMove.tsx` (arrow, metres, "Turn left into Corridor 0110C · by the fire
  extinguisher", one segment per step; tap / ‹ › / segment to move; ✕ ends the directions; the floor follows the
  step). The caption leaves out the numbered lines of the answer that drew the route.
- **Checked:** full pytest 328 passed (new: `test_guidance_is_the_same_steps_as_data`,
  `test_route_event_has_the_guides_steps`); `tsc` clean; screenshots of step 1, 5 (turn left) and 7 (arrived) on
  a phone and the desktop layout.
- **Changed docs:** `docs/guides/commands.md` (`/events` route fields).
- **Next:** highlight the current step's stretch on the plan (StoryLayer); step 4, camera wayfinding restyle.

## 2026-10-24 23:50 — Building screen HUD, step 2: the Guide's work trail

- **Did:** The live Guide message now keeps the streamed tool steps (`addStep`/`settle` from `ui/guideSteps.ts`,
  the labels from `stepLabel`) instead of only the latest label. While it works, `Guide.tsx` shows them as a mono
  trail: ✓ done, ✕ "no result" (crossed out), a spinner plus seconds on the running one. After the answer the
  trail folds into one "✓ N checks" button that opens it again.
- **Checked:** `tsc` clean; screenshots of a slowed, replayed 4-step stream (dark + light; the offline Guide is too
  fast to catch mid-run) and the folded trail after a real offline answer.
- **Next:** step 3, the next-move card for routes.

## 2026-10-24 23:50 — Merge `origin/dev` (kit 1.1.0 route model) into `2-builder-edit`

- **Did:** merged `origin/dev` at `26b908f` (kit 1.1.0 answers + route-model port) into `2-builder-edit`. Only
  conflict: this log (both sides prepended entries; kept both, dev's first). Everything else merged automatically,
  incl. `docs/guides/commands.md` and `project-state.md`. Merged tree: pytest 742 passed, 2 skipped; frontend build
  ok; links ok. Builder M3 pushed earlier; its branch preview is behind Vercel Authentication (bypass secret pending).
- **Next:** push to `origin/dev` (fast-forward) when Utku says so; then Builder project 2.


## 2026-10-24 — Kit 1.1.0 route model ported (D-014)

- **Did:** `core/building_map.py` now carries the 1.1.0 starter's geometry helpers and `graph` unchanged (+ `outside`
  endpoint option, geometry-keyed walk cache `_WALKS`, `expand` / `path_parts` for the 1.1.0 paths);
  `core/route_models.py` has one model (`GEODESIC` alias), outside always endpoint-only, bay/forklift filters fixed
  for door-to-door edges (a bay was unreachable as a destination, forklift could cross a walkway door to door);
  `navigation.path_length`, errand/what_if_door, `solvers_v1`, `validate_warmup.py` (unreachable tours, starter-equal
  lengths) updated; removed `core/geodesic.py`, `tests/test_geodesic.py`, `scripts/compare_route_models.py`; tests
  moved to the new metres (Guide scenario: 124.24 → 61.24 m step-free, 132.2 → 96.46 m after Lift 1 closes).
  Regenerated `submissions/` (regex parser): 21 of 145 answers changed (20 errand, 1 what_if_door).
- **Learned:** the official starter reproduces all 189 dev routes exactly; one gold value disagrees with it
  (resplan-12462, 7.57 vs 7.67 m). First build of a huge OSM corridor (~1,000 corners) takes ~13 s; the whole building osm-way360544293 ~25 s.
- **Numbers:** warm-up routes 1,338/1,338 exact (paths too), `validate_warmup` 99.53 % from text, same as before 1.1.0 (misses = duplicate
  names), solvers 655/655, dev benchmark 138/138, `uv run pytest` green.
- **Next:** push `dev`, merge into the feature branches; Q-014 (3), (4).

## 2026-10-24 23:30 — Building screen HUD, step 1: voice-first Guide ("Quiet HUD")

- **Did:** Showed Atahan two rounds of UI mockups (local galleries, not in the repo). He rejected the Apple-Maps-style
  chrome and approved round 2: an AI-centric, dark "Quiet HUD". Step 1 of 5 is now in the app: `building/Core.tsx`
  (the voice control: a ring with ticks that follow `useVoice().level`; tap or hold to talk, tap to stop speaking),
  `building/Guide.tsx` (captions instead of a chat thread: live transcript, the current Guide step, the reply; a
  greeting plus 3 intents; typing as a fallback; the room card), and `building/hud.css` (glass tokens, light + dark).
  `BuildingScreen` has a new top line (back, name, floor chip popover, "…" menu with fit / theme / dev tools) and uses
  `useVoice` (hands-free off) instead of `hearOnce`/`say`. `Conversation.tsx` was removed. Geist font is loaded in
  `index.html`. The theme defaults to dark when nothing is stored. `PlanView.tsx` was not touched.
- **Checked:** `tsc` clean; oxlint clean for the changed files; screenshots of idle, typed route answer, floor popover,
  menu (phone) and desktop.
- **Next:** step 2, the agent's work trail (live steps as "Found … ✓" lines); step 3, the next-move card for routes;
  step 4, camera wayfinding restyle; step 5 (live tracking) needs a positioning plan first.

## 2026-10-24 23:00 — No paper-thin walls where OSM rooms almost touch

- **Did:** `core/floorplan.py` `wall_solids`: rooms closer than `TOUCH_M` (3 cm) now get the 10 cm partition too.
  Before, the wall fell from 10 cm to the gap's few mm wherever the gap exceeded the 1 cm merge (FMI Bistro /
  MI Magistrale in `dev/osm-way27917482`, 0–0.9 cm over ~5 m). Test: `test_rooms_that_almost_touch_keep_a_full_partition`.
- **Learned:** gaps under 10 cm: OSM almost all drift ≤ 2.5 cm; Swiss Dwellings has real 3–9 cm drawn walls, so the
  threshold stays at 3 cm (a 10 cm one made Swiss walls cover bathrooms).
- **Next:** nothing open.

## 2026-10-24 22:30 — Furniture laid out from the real width

- **Did:** Scanned all assets: the kit has no heights; `generated` types have one fixed size each, `dataset` (Swiss)
  fixtures vary. `furniture.ts` now draws lecture seating rows as one seat per 0.50 m and kitchen counters /
  wardrobes / built-in wardrobes with a seam per 0.60 m module, from the placed width.
- **Learned:** kitchen sinks are almost absent (8) — counters carry them implicitly, position unknown, so not drawn.
  `internal_stairs` sizes include junk (0.17×0.06 m) and no ascent direction. SVG/PNG floor files add nothing.
- **Next:** check the look in the app (browser extension was not connected).

## 2026-10-24 — Kit 1.1.0: corrected answers (new route model)

- **Did:** Organisers published a patch (`Synera-GmbH/industrial-agents-hackathon-2026`, branch
  `patch/fix-answers-ruleset`, commit 6a2cdec; same content merged to their `main` as dc03c44). Copied the 334 changed
  `questions*.jsonl` (train + dev) into `data/` (`diff -rq` vs the kit: identical, `data/test` unchanged) and
  updated `archive/initial-repo/` to 1.1.0 (README, CHANGELOG, pyproject, starter_agent). Work on `dev` directly.
- **Learned:** in `data/` only expected answers changed (questions, buildings, manifest, test questions,
  `benchmark/` are identical). Their 1.1.0 `README.md` was rewritten from an older text and drops the cb51a6f
  alignment sections (story, personas, Sunday benchmark, submission process; judging row "Submission demo" →
  "Pitch and demo, 3–5 min live") — kept the old text as `archive/initial-repo/README-cb51a6f.md`, repointed
  personas/scoring/brief sources, opened [Q-017](open-questions.md#q-017). The graded rule = the organisers' route note, now precise in README §3 (see
  [Q-014](open-questions.md#q-014)). With the new answers: `validate_solvers` **568/655** (errand 10/93,
  what_if_door 0/4; all non-routing kinds still 100 %); `validate_warmup.py` crashes on the new unreachable-tour
  shape. Our `geodesic` model is close (dev routes: reachability all right, 158/161 within 1 m, 3 exact).
- **Changed docs:** [route-model.md](../docs/kit/route-model.md) marked outdated; Q-014 updated; Q-017 opened;
  sources in personas.md, scoring.md, brief.md (+ judging-row warning).
- **Next:** port the 1.1.0 route model into `core/` as the default, rewire errand / what_if_door / navigation,
  fix `validate_warmup.py`, regenerate test answers.

## 2026-10-24 22:40 — Commit hook works in git worktrees

- **Did:** the M3 commit was blocked as "stale" although verified: settings.json runs
  `$CLAUDE_PROJECT_DIR/.claude/hooks/require-verification.py` (the main checkout's copy), which compared the stamp
  with the *main checkout's* index. The hook now resolves the repository the commit runs in (`cwd` from the hook
  payload, then `cd <dir>` / `git -C <dir>`, quoted paths ok) and checks that repo's stamp and staged tree. Tests:
  two new cases with a temp repository in `tests/test_commit_hook.py`. The fixed file was also copied into the main
  checkout (branch `1-agentic-yarag`, uncommitted there) so it is the one Claude Code runs.
- **Learned:** the hook's regex also fires on commit-like text inside a heredoc (pre-existing; documented).
- **Next:** commit the hook on `1-agentic-yarag` too (or let it arrive by merge).

## 2026-10-24 22:30 — Builder M3: drafts, saved buildings and Builder history in Supabase

- **Did:** Utku took M3 back from Atahan (not started) and decided with Claude: public-URL demo + real persistent
  multi-user system; own draft per person, no live co-editing; saved buildings visible to everyone. Built plan Tasks
  1–5: `DraftBackend` (`FileDraftBackend` / `MemoryDraftBackend` / `PostgresDraftBackend`) in `backend/drafts.py`,
  `PostgresConnection` + `db_url()` shared in `backend/persistence.py`, migration
  `20261025120000_builder_drafts.sql` (applied to Supabase), `SessionStore.user_buildings` / `known` /
  `load_session`, `Builder.dump` / `Builder.restore` (proposal numbers stored as `BuilderTools.next_id`), app:
  Builder loaded / stored per request, 409 / 503 handlers, `/buildings` refreshes quietly; Edit mode reloads the
  draft after a 409. Tests: `tests/test_draft_backends.py` (17 + 1 live).
- **Learned:** one retry is not enough when two instances hammer one draft → `SAVE_ATTEMPTS = 3`, and a request
  that still loses gets 409 (never a silent loss). Supabase also has an empty `building_edits` table from the early
  architecture docs — unused, left alone.
- **Changed docs:** M3 plan (status, as-built), spec (M3 decisions, table names), ai-agents.md, commands.md,
  docs/README.md, project-state.
- **Next:** Task 6 — deploy, public smoke test.

## 2026-10-24 22:10 — No phantom walls around nested open spaces

- **Did:** `core/floorplan.py` `open_zones`: an open space (`hall`/`corridor`) mapped inside a bigger space gets no
  wall where its outline runs through that space (wall solids and `walls` segments); nested stairwells, lifts and
  rooms keep theirs. Frontend lifts a nested space's floor fill 2 mm (`NESTED_LIFT_M`) so coplanar fills don't
  z-fight. Tests in `tests/test_floorplan.py`.
- **Then:** overlaps are striped: `export_plan` → `overlaps` per floor (`core/floorplan.py` `overlaps`: each pairwise
  overlap ≥ 0.5 m² as 0.5 m diagonal stripes, owners alternating; stairwells/lifts left out as shafts). Frontend
  draws them in the fill geometry; `ranges` is now a list per space so selection recolours a space's stripes too.
- **Then:** open stairs: a stair with no door, only doorless openings (`is_open`), counts as open like a lobby (no
  wall through the space holding it). Nested stairs in corridors/lobbies are all linked by one *synthetic* 0.9 m
  opening (OSM maps no door there); walled stairwells (e.g. in Festsaal, osm-way13507441) have a door. Lifts always
  keep their walls.
- **Learned:** OSM maps Lobby 0.22 (osm-way27917482, G) as a zone inside the Friedrich L. Bauer Hörsaal; its curved
  edge drew a wall through a seating row. Nesting is common in the data (stairs/lifts in corridors: real walls);
  only 3 open-in-bigger cases (that lobby, Lobby 0.12/0.13 in Corridor 0.09 of osm-way360544293).

## 2026-10-24 21:45 — Dev panel merged into the app

- **Did:** moved the dev tool into `frontend/app/src/dev/` (hooks in `PlanView` + `BuildingScreen`; shown in the
  Vite dev server or with `?dev`) and its endpoints into `backend/devtools.py` (mounted in `backend/app.py`);
  route events now carry `line` from `MapView.enrich`. Removed `frontend/devtool/` and `backend/dev_app.py` (no
  more :5190 / :8766). `tests/test_devtools.py`. Coordinated file ownership with the parallel map-landing session.
- **Changed docs:** [commands.md](../docs/guides/commands.md#dev-endpoints),
  [visualization.md](../docs/product/visualization.md#answers-on-the-plan).

## 2026-10-24 21:38 — Edit mode restyled in the new UI's design

- **Did:** pushed `2-builder-edit` to origin (Utku). Restyled the Edit mode to Atahan's building-screen design
  (Utku: option A): header = round back button + `where` card ("Editing … · Draft copy · N changes · floor") + round
  undo + accent Save; `floor-tabs` (G / 1 / 2 …) on the left; plan rooms filled with `plan/geometry.fillOf` and walls /
  labels / furniture / selection from the PlanView palette (light / dark); preview, Builder chat, problems and the
  save sheet as `--surface` cards with `--shadow-float`; user bubbles in the accent; `--danger` for problems.
  `edit.css` rewritten on the screen tokens. Headless Chrome flow unchanged (0 → 1 → 2 → 3 changes, no errors).
- **Next:** push this commit too if Utku wants; then project 2 (build from PDF / image) or polish.

## 2026-10-24 21:25 — Dev tool only (concepts dropped)

- **Did:** Atahan didn't want the less colourful plan: dropped all visual concepts. `frontend/concepts/` →
  `frontend/devtool/`, re-synced from the app (map landing included); the dev panel rewritten for ease of use
  (place pickers, use-selected, plain-language results and impact, lifts/stairs list, examples, log with re-run);
  answer overlays kept but drawn on top of the plan's own colours (`src/dev/StoryLayer.tsx`).
- **Learned:** `compare_routes` defaults to the last route's start, which can be `outside` and then fails; the
  panel measures impact from the entrance room (`/dev/.../state` `entrance_space`).
- **Changed docs:** commands.md, visualization.md (later replaced by the merged dev panel, see the entry above).

## 2026-10-24 21:22 — Builder M2 review fixes; M3 plan for Atahan

- **Did:** whole-branch review of M2 (opus): 1 critical, 3 important, 6 minor. Fixed test-first: (critical) an open
  proposal stayed applicable after the UI dropped it — now any non-confirm turn, Cancel (`POST
  /drafts/{id}/proposals/{pid}/cancel`, wired to the card) or a hand edit closes it, and the Apply button's 409 says
  why; (important) only a message that is nothing but "yes"/"ok"/… skips the model (`CONFIRM_ONLY`), so "yes, but
  call it Library" reaches it; name / ref / type / category fields in ops are coerced to strings (numbers) or refused
  (a float ref broke `find`); the stream drops a proposal whose draft changed during the turn instead of erroring, and
  the ghost uses the dry-run building kept on the `Proposal`. 8 new tests; `uv run pytest` 729 passed, 1 skipped;
  headless Chrome re-run clean. Minors deferred (non-finite coordinates, two `/ops` 500s, Apply clickable while a
  turn runs, revision bump on "yes", richer `find` candidates). Wrote the
  [M3 plan](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m3.md) (Supabase store) for Atahan.
- **Next:** Utku's call — merge / push `2-builder-edit`, or project 2 (build from PDF / image).

## 2026-10-24 — Design: access roles (demo feature, not built)

- **Did:** brainstormed with Utku and wrote [access-roles design](../docs/superpowers/specs/2026-10-24-access-roles-design.md):
  the facility manager sets roles (room-type access + editable physical limits: stairs, lifts, opening width) by
  talking to the Guide; rules and building changes are building-wide and reach open conversations on their next
  turn; only a conversation that claimed `manager` may edit (a claim, not a credential); no role = today's
  behaviour; benchmark untouched. Builder check (subagent) raised 5 questions: 3 answered by Utku, 2 settled as my
  calls in the doc.
- **Also (same session):** factory bay rule — 26/26 factory buildings lose office ↔ hall routes under bays
  destination-only + no outside (the rule comes only from our summary of the organisers' Discord note, not from the
  PDF or kit README; the zone list beyond `production` and applying it to pedestrians are our interpretation).
  Pending Utku's decision; see Q-015.
- **Next:** implementation plan for access roles when Utku asks; bay rule decision + organiser question.

## 2026-10-24 21:08 — Builder M2 Task 5: Edit-mode chat, proposal ghost, live check

- **Did:** `frontend/app/src/edit/BuilderChat.tsx` (NDJSON stream with step lines, proposal card with areas / new
  problems, Apply / Cancel), `api.builderStream` / `applyProposal`, `PlanEditor` `ghost` (changed / new elements
  dashed blue, removed ones red), EditMode right column = PlanView inset + chat, issues bottom-left; a hand edit or
  undo drops the open proposal. `scripts/live_builder.py`. Headless Chrome (offline client): widen → 2 ghost rooms +
  card (33.6 → 39.6, 24.6 → 18.6 m², 3 assets left outside) → Apply → 1 change; rename proposal dropped by a door drag;
  "yes" applies; no console errors.
- **Live (Opus 5.5 medium, train/proc-campus-train-000):** "make Lab 0.13 one metre wider, into the room next to it" →
  asked which side (Main lobby east / Toilet 0.14 west), 5.4 s, ~$0.018; "Into the toilet." → `move_edge` 1 m west,
  39.06 → 45.06 / 38.46 → 32.46 m², flagged Sink 0.14 left outside and offered to move it, 6.9 s; "yes" applied.
  Move 3D printer → `move_asset` 7.6 s ~$0.022; door between Office 0.02 / 0.03 → `add_opening` 13.1 s ~$0.039.
  0 ungrounded replies.
- **Learned:** `.builder` (panel) also matched the chat line's role class `builder` — class names in the Edit mode
  need prefixes; same story as `.plan` / `.primary`.
- **Next:** M2 whole-branch review; M3 plan for Atahan (not implemented by us).

## 2026-10-24 20:56 — Builder M2 Tasks 3–4: Builder agent loop, offline client, backend routes

- **Did:** `agent/builder.py` (`Builder`, `BuilderTurn`, `make_builder_client`; request shape from the Guide;
  `DraftStore.apply(expected_version=…)` checks staleness inside the draft lock), `agent/builder_offline.py`,
  `/drafts/{id}/chat/stream` and `/drafts/{id}/proposals/{pid}/apply` with one in-memory Builder per draft; hand
  edits and undo leave a note for the Builder's next turn. `tests/test_builder.py` 11, `tests/test_drafts.py` 19.
- **Learned:** example numbers in an offline help text trip the grounding check — keep canned text digit-free.
- **Decided (Utku):** M3 goes to Atahan; we write its plan only.
- **Next:** Task 5 — Builder chat, ghost overlay, Apply / Cancel in the Edit mode; live check.

## 2026-10-24 20:55 — Concepts port :5190 + dev panel

- **Did:** `frontend/concepts/` (copy of the app on :5190) with four visual concepts behind `?c=` flags — answer
  on the plan (focus + rest, route band with floor-change badges, closure hatch, lost access), corridors as
  streets, semantic zoom, quiet furniture — and a dev panel that runs every Guide tool by hand. `backend/dev_app.py`
  (:8766, offline LLM, no persistence) adds `/dev/*` and route `line`s; `core/routeline.py` + `tests/test_routeline.py`.
  Nothing in `frontend/app/` or the existing backend files changed.
- **Learned:** the route model's anchor walk detours to each corridor's centre; drawing door to door where the
  segment stays inside the space reads right. Fit zoom ranges ~20–37 px/m across buildings, so LOD tiers at 8 / 50.
  Another session was editing `frontend/app/` at the same time: the concepts copy is a snapshot (~20:35).
- **Changed docs:** commands.md, visualization.md (sections replaced by the dev tool, see the entry above).

## 2026-10-24 20:42 — Builder M2 Tasks 1–2: move_edge, Builder tools

- **Did:** `move_edge` (moves one wall along its outward normal in every room that has its corners, then `settle`),
  `edge_sides`; `apply_op` turns ValueError/IndexError/KeyError from malformed arguments into EditError (M1 review
  minor). `agent/builder_tools.py` with `BuilderTools`, `Proposal`, `BUILDER_TOOLS`; `tests/test_builder_tools.py`
  13 passed, `tests/test_edits.py` 30 passed; full suite green.
- **Next:** Task 3 — Builder loop (`agent/builder.py`) + offline client.

## 2026-10-24 20:32 — Edit mode re-homed in the new UI

- **Did:** Edit button (ruler-pencil) in `BuildingScreen`'s controls opens `EditMode` full screen; its 3D inset is now
  Atahan's `PlanView` fed by the new `GET /drafts/{id}/plan` (`DraftStore.plan`, `core/floorplan.export_plan`,
  centred on the base building so the preview doesn't jump); **Done** goes back; **Save** opens `user/<slug>` through
  `Root` with a one-time note. `App.tsx` / `Scene.tsx` back to dev's versions. Editor CSS class `.plan` →
  `.plan-editor` and `.primary` → `.edit-primary` (dev's globals). Fixed a StrictMode double-open that created two
  drafts and resumed the wrong one (`openDraft` dedupes per base). Headless Chrome: edit → drag → Done → Edit again
  resumes "1 change" → Save → `user/forschungsbau-v2` with the note; no console errors.
- **Next:** M2 Task 1 (`move_edge`).

## 2026-10-24 20:25 — Merge `origin/dev` (Atahan's new UI) into `2-builder-edit`

- **Did:** merged `origin/dev` (92f063a new app UI, 508a1ba directions, 26df725 interaction eval). Conflicts:
  `.gitignore` (both kept), `backend/app.py` (`/sessions/{id}/plan` and `/drafts` both kept), `memory-bank/log.md`
  (both kept), `frontend/app/src/scene/Scene.tsx` (took dev's placeholder; kept an ignored `inset?` prop so the
  Edit mode still compiles until it moves to `PlanView`). `uv run pytest` 685 passed, 1 skipped; `npm run build` ok.
- **Next:** Edit entry in `BuildingScreen`, 3D inset → `PlanView` via `/drafts/{id}/plan`.

## 2026-10-24 20:17 — Builder Edit mode M1 final review fixes; M2 plan; dev merge analysis

- **Did:** whole-branch review (opus): 0 critical, 3 important, 7 minor. Fixed the important ones test-first:
  `settle` skipped neighbours it had already fitted (overlap left with the second room sharing a corner); mid-edge
  neighbours never grew (hole when a room shrank) → the vacated area now goes to the neighbour it borders most;
  overlapping requests lost changes (concurrency test: 10 of 80 assets survived) → per-draft lock in `DraftStore`,
  and the Edit UI no longer sends while an op is in flight and keeps the dropped preview until the answer.
  Minors deferred (plan ledger). Wrote the [M2 plan](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m2.md)
  (Builder agent, `move_edge` op). `uv run pytest` 673 passed, 1 skipped.
- **Learned:** `origin/dev` has Atahan's new UI (92f063a): entry is `Root` → `BuildingSearch` / `BuildingScreen`,
  `App.tsx` no longer rendered, point-cloud `Scene` replaced by a placeholder, vector `PlanView` +
  `/sessions/{id}/plan` (`core/floorplan.py`). Dry-run merge: conflicts only in `.gitignore`, `backend/app.py`,
  `scene/Scene.tsx`, `memory-bank/log.md`.
- **Next:** merge `origin/dev`, re-home the Edit mode in `BuildingScreen`, inset → `PlanView`.

## 2026-10-24 19:58 — Builder Edit mode M1 Tasks 5–7: frontend Edit mode, save → Guide

- **Did:** `frontend/app/src/edit/` (`EditMode.tsx`, `PlanEditor.tsx`, `geometry.ts`, `edit.css`), draft API in
  `api.ts`, `Scene` `inset` prop, View/Edit switch + save flow in `App.tsx`. Verified with playwright-core driving
  headless Chrome against backend :8775 / Vite :5191 (offline Guide): plan + inset render, corner drag moves the
  shared corner in both rooms and the validator flags assets left outside, door slide, asset drag + R, 4× ⌘Z back to
  0 changes, save "Forschungsbau edited" → View on `user/forschungsbau-edited`, note in chat, Guide route Main lobby →
  Meeting room 3.07 99 m. No console errors. `npm run build` clean.
- **Learned:** `.opening.opening` in CSS matches every `.opening` — kind classes need a prefix (`kind-door`); the
  3D inset needs `density` ≈ 0.3 or the small canvas turns black.
- **Next:** final review of the branch; milestone 2 plan (Builder agent).

## 2026-10-24 19:47 — Builder Edit mode M1 Task 4: drafts store + API

- **Did:** `backend/drafts.py` — drafts as base + steps persisted in `data/user/.drafts/<id>.json`, saved buildings in
  `data/user/<slug>/` registered as `user/<slug>`; `/drafts` endpoints in `backend/app.py`; endpoints table in
  [commands.md](../docs/guides/commands.md#backend-guide-api). `.gitignore`: `data/user/`, `.superpowers/`.
  `uv run pytest` 670 passed, 1 skipped.
- **Next:** Task 5 — frontend View/Edit switch, plan view, 3D inset.

## 2026-10-24 19:40 — Builder Edit mode M1 Tasks 2–3: wall moves, validator

- **Did:** `core/edits.py` gained `move_vertex` (moves a corner in every room that has it) and `set_polygon`; both
  shrink overlapped neighbours (`difference`), refuse when a neighbour would vanish, and put doors that were on a wall
  back on it. Opening snapping now buffers by wall thickness (gap ≤ 2.5 m). `core/validate.py` + calibration script.
  `uv run pytest` 658 passed, 1 skipped (280-building validator parametrisation included).
- **Learned:** with thickness-aware snapping, off-wall doors in the dataset drop to osm 61 / swiss 46 / resplan 1;
  overlaps osm 281 / resplan 13 / swiss 38 pairs → validator compares against the base building.
- **Next:** Task 4 — drafts store (`data/user/`) + `/drafts` API.

## 2026-10-24 19:40 — Builder Edit mode: design, M1 plan, core edit ops (branch `2-builder-edit`)

- **Did:** brainstormed Level 4 with Utku → three Builder projects in order: Edit mode, build from scratch
  (PDF/image/conversation), scan ingest. Design of Edit mode
  ([spec](../docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md), status proposed, approved by Utku) and
  milestone-1 plan ([plan](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md), 7 tasks). Work happens on
  branch `2-builder-edit` in the worktree `.claude/worktrees/2-builder-edit`. Task 1 done: `core/edits.py`
  (11 JSON ops, deterministic ids, opening snapping, `apply_steps` replay), `tests/test_edits.py` 16 passed;
  full suite 320 passed, 1 skipped.
- **Learned:** Blueprint-Bench 2 (Andon Labs): models get room counts right but mostly miss which rooms connect →
  validator-first Builder. Dataset scan: all 280 buildings have an entrance and every space is reachable; OSM /
  Swiss / ResPlan have pre-existing overlaps and doors off the shared wall, Swiss walls up to ~2 m thick → the
  validator must separate pre-existing from newly introduced issues, and snapping must tolerate thick walls.
- **Next:** M1 Task 2 (`move_vertex`, `set_polygon` with neighbour fitting).

## 2026-10-24 — Map landing + list view; stacked floors at real height; outside view tried and dropped

- **Did:** "All floors" stacks floors at their real `elevation_m` (was a fixed 5.5 m gap). Built and then, on
  Atahan's call, removed an outside "shell" view of the closed building (glass ribbon, roofs, gallery storeys).
  New landing: `frontend/app/src/map/MapLanding.tsx` (MapLibre `maplibre-gl` 5.24, OpenFreeMap positron/dark,
  pins as map layers, panel list) for the 17 buildings with a position; `?view=list` = the search, now with a "No
  location" filter and "on map" tags; back pill returns to map or list. `GET /buildings` gains `location` from new
  `backend/locations.json` (from `.viz-archive/app-public/map/twins.json`). `export_plan` gains `outlines` (per
  floor, for the stacked view's floor-name signs, whose author is not this session). Tests: `test_backend.py`
  (location), `test_floorplan.py` (outlines). Then 3D: the map is tilted and extrudes every OSM building from the
  OpenFreeMap tiles' `render_height` (no download, no key).
- **Learned:** the kit has no windows anywhere (openings are door / opening / entrance). Swiss Dwellings and
  ResPlan sources do have windows, but Atahan does not want downloads. Only the 17 OSM buildings can be placed on a
  map. The data gives every floor one storey height; a double-height hall shows only as a gallery floor (StudiTUM
  floor 1 covers ~200 of ~450 m²). MapLibre's `isStyleLoaded()` stays false while tiles load, after `style.load`
  has fired: add layers with try/retry on `idle`.
- **Changed docs:** [visualization.md](../docs/product/visualization.md), NOTICE.md (locations.json, ODbL).
- **Next:** none planned for the map; possible: show a building's outline on the map, mobile check of the panel.

## 2026-10-24 — Plan view: models for every machine type

- **Learned:** 13 of the 96 asset types in `data/` had no model in `frontend/app/src/plan/furniture.ts` and fell
  back to one generic grey block: all production machines (drill_press 78, industrial_3d_printer 71, cnc_mill 57,
  injection_moulding_machine 50, cnc_lathe 47, milling_machine 46, press_brake 41, coordinate_measuring_machine 26,
  laser_cutter 23, robot_cell 16, waterjet_cutter 12, curing_oven 8) plus powder_station 6.
- **Did:** rough box/prism models for all 13 (front = -z: glass doors, control pendants with screens; robot cell =
  waist-high glass fence on yellow posts around an orange arm and work table). Plain cubes got detail:
  tool_cabinet (drawers, casters), filing_cabinet (drawers), locker (door split, vents), forklift_charging_station
  (screen, cable). Checked in headless Chromium on `dev/proc-factory-dev-005` and `-008`; `npm run build` passes.
- **Did (openings):** doorless `kind == "opening"` (2,155 in `data/`, median 2.5 m; mostly kitchen↔living room,
  corridor↔living room, stairwell↔stairwell, corridor↔corridor) no longer get the blue threshold strip that made
  corridors look outlined: cut into a wall (a wall within `WALL_M` past either end) → dashed hairline across the
  gap; an open-plan split → nothing; closed → red strip as before (`frontend/app/src/plan/geometry.ts`).
- **Next:** the user reviews the look; cnc_mill still reads as a big box from its back side.

## 2026-10-24 — Plan view: doors as threshold strips, no leaves

- **Learned:** `building.json` has no swing or hinge data (openings carry only `id, floor_id, space_ids, kind,
  position, width_m, step_free, synthetic`). The old swing went into `space_ids[0]`, whose order is arbitrary
  (Swiss room→corridor 3,714 vs corridor→room 3,381). A convention-based swing was tried and rejected by Atahan:
  invented swings mean nothing.
- **Did:** door leaves and swing arcs removed. Every opening is a flat threshold strip across the wall gap, as wide
  as the door: soft blue (`palette.door`), entrances accent blue (`palette.entrance`), doors in `plan.closed` red.
  `core/floorplan.py` `door_geometry` returns only `angle` + `space` (no `side`); `wall_edge` helper shared with the
  wall cuts.
- **Changed docs:** visualization.md, project-state.md.

## 2026-10-24 — Point cloud removed entirely

- **Learned:** opening a building was slow because `MapView.plan` ran `export_points` (~180 k sampled points,
  0.1–1.3 s) only to read its `center`, on every new session; the plan itself took 0.01–0.05 s then.
- **Did:** deleted `core/pointcloud.py`, `tests/test_pointcloud.py`, `GET /sessions/{id}/points`, route `vertices`
  in `/chat` and `/events` (nothing read them), the unused `frontend/app/src/App.tsx` and the `src/scene/`
  placeholder, `PointCloud` / `api.points` in `api.ts`. `door_gaps`, `sorted_floors`, `floor_indices`,
  `SKIPPED_TYPES` moved into `core/floorplan.py`; `export_plan(building_map)` computes `center` from the space bounds
  (optional argument kept). `MapView` caches only the plan; `enrich` adds `legs` + `space_ids`. Tests rewritten on
  `/plan` (`test_plan_export`, `test_plan_is_gzipped`, `test_route_event_has_legs`,
  `test_change_event_has_space_ids_and_plan_update`). /plan now 0.02–0.21 s (wall solids dominate).
- **Changed docs:** visualization.md, commands.md (+ /plan row), docs/README.md, CLAUDE.md doc map, project-state.md.
- **Next:** a route line on the plan needs a plan-frame polyline (`legs` has none).

## 2026-10-24 — Plan view: solid walls at their real thickness

- **Learned:** `building.json` has no walls, only room outlines. The gap between facing edges of neighbouring rooms
  is the wall: procedural 0.00 m (100% of facing edge length), OSM 0.00 m (96%), ResPlan mostly 0.15–0.20 m, Swiss
  0.10–0.50 m. Swiss gaps: same apartment median 0.14 m, between apartments 0.22 m, to corridor/stair 0.20 m. The
  plan drew a 0.16 m box on every room edge, so drawn sources showed two parallel walls.
- **Did:** `core/floorplan.py` `wall_solids` → plan field `wall_solids` (per floor, `{kind, rings}`): gaps between
  rooms (closed up to 0.6 m) + a 0.10 m partition where rooms touch (0.20 m round stairs/lifts) + a 0.25 m exterior
  shell outside the outline, doorways cut out, snapped to the mm grid (all 280 buildings valid, slowest 1.8 s,
  cached per session). Kind by morphological opening: `structural` ≥ 0.18 m, else `partition`; `exterior` shell.
  `frontend/app/src/plan/geometry.ts` extrudes them (tone per kind, `WALL_TONE`); room outlines still drive ghost
  lines and contact shadows. Tests: `tests/test_floorplan.py` (3). Checked in headless Chrome on swiss-1075 and
  proc-campus-dev-001. Display only — solvers and route model unchanged.
- **Next:** OSM/procedural thickness is synthetic; exterior thickness of drawn sources is unknown (0.25 m guess).

## 2026-10-24 — Directions: turns, landmarks, rounded metres

- **Did:** `core/directions.py`: `about_m` (whole metres < 10, steps of 5 < 100, then 10, half up), `landmark` (the
  most recognisable item of `LANDMARK_TYPES` within 4 m of an opening, in a space it joins; no chairs/desks),
  `guidance_steps` (start line, "Turn left and walk about 15 m through the door (by the vending machine) into X",
  one "Take Staircase 2 up two floors to Floor 2." per ride, arrival; no ids). The turn is the heading change at the
  door you came through (previous room's anchor → that door → next door); `route_legs` (camera mode) still turns at
  the room anchor, which read "turn around" next to the entry door. `BuildingSession.guide_steps` replaces the kit
  step text in `find_route` and each `tour` leg and adds `about_m`; prompt: use the route's steps, total as about_m.
  Offline client says about_m. Tests: `tests/test_directions.py` (+4), expectations in `test_guide.py` /
  `test_speech.py` moved from exact to rounded metres (124 → 120, 132 → 130, 27 → 25).
- **Live (Opus 5.5, single runs):** eval_guide 18/18 (~$0.22). Interaction eval: asks 4.67 · shows 4.83 ·
  directions **4.17** (was 3.33) · remembers 5.00 · goal 5/6 (~$0.56). Three scenarios score directions 5.
- **Learned:** remaining judge issues — step distances (straight segments) don't add up to about_m (route cost incl.
  lift/stairs cost), a landmark can sit at the destination door itself, the factory technician still has no route
  (bay rule, see the entry below). Left/right comes from plan geometry and is **UNVERIFIED** on site.
- **Next:** say step distances are approximate or derive the total from them for display; factory bay rule (Q-015).

## 2026-10-24 — Interaction eval: simulated tricky users + LLM judge

- **Did:** `scripts/interaction_eval.py`: a simulated user (Claude, structured JSON `message/done/goal_reached`,
  roles flipped) plays a scenario (persona, goal, facts it shares only when asked) against the Guide, text or voice;
  a judge (Claude, JSON schema) scores asks_only_needed / shows_understanding / followable_directions /
  remembers_context 1–5 + goal_reached + issues, seeing the transcript with each tool call's result (route steps,
  search hits; cut at 1,500 chars). `--repeat`, `--model/--effort`, `--user-model/--judge-model`; transcripts in
  `agent_output/interaction_eval/`. 6 scenarios in `tests/interaction_scenarios/`; offline tests with a fake client
  and the offline Guide (`tests/test_interaction_eval.py`).
- **Live (all Opus 5.5, single runs):** run 1 (judge saw only a few result keys → many "unsupported value" false
  alarms) asks 4.33 · shows 4.17 · directions 3.50 · remembers 5.00 · goal 6/6. Run 2 (full results): asks 4.17 ·
  shows 4.17 · directions 3.33 · remembers 4.83 · goal 5/6, guide $0.31 + eval $0.31, ~4 min.
- **Learned (judge issues, run 2):** directions are the weak spot — no left/right or landmarks, unrounded
  metres ("148.38 m"), distance placed on the wrong leg; voice reads codes aloud ("H-A2"); internal ids leak
  ("change C1"); a few claims beyond tool results (entrances with steps, outside doors). Factory
  `proc-factory-dev-004`: with the Guide's route rules (bays destination-only) the Locker room → Production zone
  H-A2 (press brakes) has **no route** (kit model without rules: 61.56 m via Assembly zone H-A1), so the voice
  technician scenario fails — ties to Q-014/Q-015.
- **Next:** better step text (landmarks/turns, rounding) in `core/directions.py`/prompt; check the factory bay
  rule against Q-015; judge variance with `--repeat 3`.

## 2026-10-24 — Guide eval ported to the canonical Guide

- **Did:** `scripts/eval_guide.py` and `tests/test_guide_conversations.py` now test `agent/guide.py` (they tested
  `agent/guide_v1` before, so the 16/16 below was v1's score). Same expect keys; `route_to` compares the turn's last
  reachable `find_route` with a fresh `core.navigation.find_route` under the session's profile, applied changes and
  route rules after the turn. Per-turn seconds + cost, `--model` / `--effort`. `lift_closure.json` gained two
  "Yes, go ahead." turns (propose → confirm → apply), `update_session` → `set_profile`/`propose_change`.
- **First live run (Opus 5.5 medium):** 14/18 PASS, 95 s, ~$0.24. Failures: `lift_closure` t6 repeated the earlier
  route without calling `find_route` (reply correct); `printers_two_rooms` t1 ended with an offer question; t2 routed
  to the nearer printer instead of asking (against the prompt and D-012), so t3 had no route.
- **Fixes:** `route_to` falls back to the conversation's last route (still checked against the current state, so a
  stale route fails); `asked` = a question anywhere in the reply; Guide prompt: ask which room when items of the
  kind sit in several rooms, even if one is nearer, and no closing offers; `lift_closure` user now uses a wheelchair
  (step-free route goes via Lift 1 at 101.64 m, via Lift 2 at 109.63 m once Lift 1 is closed — the scenario now
  tests something).
- **Second live run:** 17/18, 89 s, ~$0.22; the miss asked mid-reply (checker bug, fixed); `printers_two_rooms`
  re-run 3/3, ~$0.03.
- **Learned:** Level 3 "several buildings" is unsupported in data and code → [Q-016](open-questions.md#q-016).
- **Next:** LLM judge + simulated tricky user on top of this suite; Q-016.

## 2026-10-24 — Merge `origin/dev` into `1-agentic-yarag` (Utku's session)

- **Did:** merged dev's 3 commits (Sunday geodesic route model + route rules, handoff, AI layer: live steps, cards,
  voice orb, camera photo turns). Code conflicts: `Guide.__init__` keeps the rewriter and `on_step`; `agent/tools.py`
  imports both `places` and `route_models`, `tool_tour` resolves stops and passes `model`/`rules`. Not flagged by
  git: `destination_options` (route fan-out) now also passes `model`/`rules`, so option lengths obey the route
  rules. `Guide.reply` auto-merged in the right order (rewrite → note → voice style → photo).
- **Docs:** solver-plan keeps both the warm-up-kinds and the Sunday-routes sections; Q-014 takes dev's progress
  (it implemented the branch's open details) plus a Q-015 link.
- **Checks:** `uv run pytest -q` 301 passed, 1 skipped; live `scripts/live_guide.py` (Sonnet 5.5 low) 7 turns, all
  end_turn, 0 ungrounded, $0.057.

## 2026-10-24 — Voice transcript rewriter (D-013) (Utku's session)

- **Did:** `agent/rewriter.py`: `TranscriptRewriter` (claude-haiku-5-5, effort low, JSON schema, building vocabulary
  cached); `Guide.reply(..., channel="voice")` sends rewritten + "[speech transcript as heard: …]", both grounded,
  `GuideTurn.rewritten`. Only with the real API client; `GUIDE_REWRITER=off`. `tests/test_rewriter.py` (7).
- **Learned:** live, Haiku normalises "lab two seventeen" → "Lab 2.17", "office zero oh two" → "Office 0.02", "defib"
  → "defibrillator", keeps "the kitchen"; ~1–2 s, < $0.001 per call. A prompt example "the second floor → Floor 2"
  made it interpret ordinals (US vs UK floors), so ordinal floor words are now kept as said. End to end (Sonnet low
  Guide): voice turn 4.7 s, one `find_route`, 0 ungrounded.
- **Remote:** `origin/dev` has 3 commits ahead of main (Sunday geodesic route model + rules, live Guide steps,
  camera photo turns, browser voice orb) touching `agent/guide.py` / `agent/tools.py`; not merged here yet.

## 2026-10-24 — v1 Guide strengths ported into `agent/guide.py` (Utku's session)

- **Did:** `agent/places.py` + `BuildingSession.resolve`: articles dropped, exact asset type → its room, repeated
  names → `MapError` listing `id (name, ref, type, floor)` per candidate ([D-012](decisions.md#d-012)), typos → "Did
  you mean"; `find_route` / `tour` pre-resolve stops; an ambiguous destination returns each option with its route
  length. Grounding: unit-glued numbers, list lengths, clock times, half-up rounding. `tests/test_places.py` (10).
- **Learned:** `Resolver.asset_type` / `navigation.resolve_asset_type` are fuzzy ("office" → `office_chair`), so
  places.py accepts only an exact type (plural ok). Python `round()` is half-even: the old check flagged "about
  43 m" for 42.5 m. Live (Sonnet 5.5 low): 7-turn script 0 ungrounded, $0.06; the model already fixed "Ofice" and
  picked the nearest printer itself, so the new paths are a safety net rather than the common path.
- **Next:** voice transcript rewriter (D-013); measure the Vercel preview (protected by Vercel Authentication).

## 2026-10-24 — Merge `origin/main` into `1-agentic-yarag` (Utku's session)

- **Why:** Vercel build failed on the branch (no `vercel.json`, `frontend/app/`, `backend/`). Main and the branch had
  built two parallel stacks; main's is broader (edits, profiles, voice, backend + UI), benchmark scores are equal.
- **Did:** main's stack stays canonical (`agent/guide.py`, `agent/tools.py`, `core/solvers/`, `agent/run_benchmark.py`,
  backend, frontend, `vercel.json`). The branch's modules moved beside it: `agent/guide/` → `agent/guide_v1/`,
  `core/solvers.py` → `core/solvers_v1.py`, `agent/run_benchmark.py` → `agent/run_benchmark_v1.py` (the same names
  would have shadowed each other: a package wins over a module). Text conflicts: main's text kept, branch content
  added as "v1" sections.
- **Decisions / questions:** branch D-010 / D-011 renumbered to [D-012](decisions.md#d-012) /
  [D-013](decisions.md#d-013) (main's D-010 guardrails, D-011 monochrome keep their ids). Both sides opened Q-014 for
  the same organiser note: merged into main's entry; branch Q-015 (factory schema) keeps its id; next free Q-016.
- **Next:** port v1 strengths (name resolution / candidate fan-out, grounding fallback, voice transcript rewriter)
  into `agent/guide.py`; then retire one stack.

## 2026-10-24 — Commit of the new UI work; lost pieces rebuilt

- **Did:** before `/ship`, found parts of the UI work missing from the tree after the fast-forward to `508a1ba`
  (`MapView.plan`, the `Scene.tsx` placeholder, `lucide-react` in package.json, the project-state handoff, the
  visualization map-view section). Rebuilt the first three (plan cached with the export, same `center`), added a
  short handoff to project-state. `uv run pytest` 316 passed, 1 skipped; `npm run build` OK.
- **Learned:** keep UI work committed in small chunks; a dirty tree around merges lost files with no stash to recover.

## 2026-10-24 — UI handoff: clay cutaway, spread floors, floating chat (uncommitted)

- **Did:** iterated with Atahan on the scene: fixed 3D↔2D freeze (frame-delta cap) and stuck gestures (no React
  update mid-drag); furniture orientation from data convention (+ nearest wall / nearest table); doors, stair
  flights, edges, contact shadows; ground-plane grid; single-floor 3D view spreads floors so none overlaps;
  "all floors" kept as plain stack; floor textures and Lab panel removed at his request.
- **Learned:** he judges by eye and rejects cosmetic toggles; wants floor relationships visible without overlap.
- **Next:** see project-state handoff (commit via /ship after his OK; later Guide events on the model).

## 2026-10-24 — Clay cutaway look, furniture models, stacked floors, floating chat

- **Did:** From Atahan's reference screenshot: clay isometric cutaway (walls cut at 0.85 m, contact shadows, one
  soft sun), grainy warm/cool stage with iso grid; ~90 furniture types as rough coloured models
  (`src/plan/furniture.ts`, merged per floor, tap → name card); `/plan` now carries assets (only in drawn spaces).
  Camera tilts freely 2D↔3D by gesture (right/Ctrl/Shift-drag, two fingers), buttons snap; stacked "all floors"
  view (tap a floor to enter); theme switch (system/light/dark); chat is a floating ask bar showing only the latest
  exchange (mic via browser speech). Checked headless phone + desktop.
- **Next:** step 2 = Guide events on the model (focus, route, closures, lost access).

## 2026-10-24 — New UI direction "Drawing Set" + step 1: 2D building screen

- **Did:** With Atahan via Impeccable: `PRODUCT.md` (roles visitor/maintainer, QR/map/search arrival, Apple Maps
  colours, calm), direction **Drawing Set** chosen (contract in `.impeccable/surfaces/frontend-app.md`). Built step 1:
  `core/floorplan.py` + `GET /sessions/{id}/plan` (walls with door gaps, door swing side, label points, same `center`
  as /points), `frontend/app/src/plan/*` (orthographic r3f plan, render on demand, canvas labels that only show when
  they fit, tap a room → place card), `src/building/*` (guide line, floor tabs, Guide sheet with chips, wide-screen
  side panel). `Root.tsx` now opens `BuildingScreen`; old `App.tsx`/`ui/*` unused, kept as reference for porting.
  Added `lucide-react` (ISC). Checked headless at 390×844 and 1440×900, light + dark, campus + OSM building.
- **Next:** step 2: Guide events on the plan (focus + dim, route line, closures, lost access), then 3D, arrival, voice,
  camera, maintainer edit.

## 2026-10-24 — Scene scrapped for a from-scratch rebuild

- **Did:** Atahan's call: scrap the scene/visualization (not the rest of the app). Moved `frontend/app/src/scene/*`,
  `src/map/`, `public/map/`, `scripts/build_map_assets.py` and `frontend/prototypes/` (pointcloud + twin-lab) to the
  gitignored `.viz-archive/`. `src/scene/` is now a placeholder (same `Scene` props, empty backdrop) so chat, Guide
  and search keep working; `?view=map` route removed from `Root.tsx`; `maplibre-gl` uninstalled; back pill CSS moved
  to `src/search/backPill.css`. `npm run build` OK, `check_links.py` OK.
- **Next:** design the new scene from scratch with Atahan, step by step.

## 2026-10-24 — Landing = building search; map parked

- **Did:** Atahan: only 17 OSM buildings have a real position (Swiss/ResPlan/procedural have none), so put the map
  aside. New landing `frontend/app/src/search/` (search over all 280 from `GET /buildings`, type chips derived
  from the id, keyboard nav), `Root.tsx` search ↔ twin, map behind `?view=map`. Root `.gitignore` now ignores
  `node_modules/` + `dist/` (twin-lab's 3,037 files showed as unversioned). WebStorm: heavy folders excluded in
  `.idea` (its JSON-schema index loop was the machine-wide slowdown).
- **Next:** step 2 — mesh twin replaces the point-cloud scene.

## 2026-10-24 — Step 1: map view in the app

- **Did:** research notes → gitignored `.notes/twin-visual-research.md`. `scripts/build_map_assets.py` →
  `frontend/app/public/map/` (twins.json + per-twin compact geometry, 864 KB). `frontend/app/src/map/` (MapView,
  style, geo, liftBuilding, twinLayer, map.css), `src/Root.tsx` (map landing ↔ `?building=` twin, "← Map" pill),
  `maplibre-gl` dependency. App.tsx untouched (other session's files).
- **Learned:** the prototype's lag came from an always-on `triggerRepaint` in the custom layer and per-frame GeoJSON
  `setData`; fixed → ~60 fps headless through the whole flow.
- **Changed docs:** [visualization.md](../docs/product/visualization.md) (map-view section did not survive; map parked).
- **Next:** Atahan reviews the map; step 2 = mesh twin replaces the point cloud scene.

## 2026-10-24 — Twin-lab round 2: map → walkable mesh twin (Atahan's feedback)

- **Did:** Feedback: glow too bright, point cloud unnecessary, auto-rotation tiring; keep the map, mesh buildings,
  cursor highlight; walk inside. Built `twin.html` (`src/mesh.js`, `src/furniture.js`, `src/twin.js`): chunked
  wall boxes with door gaps + lintels, room-tinted floors, N8AO, cursor lens (walls sink, floor ring), furniture
  as point archetypes (97 asset types → 11 shapes), first-person walk with collisions, stairs/lifts Q/E, minimap,
  ceilings; `?entry=1` walks in through the entrance. Map: no drift/rotation, mesh twin rises floor by floor,
  "Walk inside" → twin. Screenshot-verified (overview, lens, walk, entry, map arrival).
- **Learned:** N8AO + OutputPass double-applies gamma unless `gammaCorrection = false`.
- **Changed docs:** twin-lab README, [Q-015](open-questions.md#q-015) partial answer.
- **Next:** decide accent vs D-011; port map + mesh twin into `frontend/app` (coordinate with the AI-layer session).

## 2026-10-24 — Twin-lab: four visual concepts + georeferenced OSM twins

- **Did:** new standalone `frontend/prototypes/twin-lab/` (Vite `:5190`, no backend): browser-side sampler
  (`src/sample.js`: jittered-stratified surfaces with normals, façade detection, door frames, stair treads, edge
  lines; ~1–1.7M points at 60 fps), shared engine (HDR bloom, fly-to, picking, hover tags), concepts Scan / Hologram
  / Morph / Arrival. `scripts/georef.py` pins the 17 `osm-way*` buildings to lat/lon (`public/georef.json`).
  Arrival: MapLibre + OpenFreeMap dark style, OSRM walking route, building lifted out of the map, twin constructs
  in place via a three.js custom layer. Verified by headless-Chrome screenshots (puppeteer-core in scratchpad).
- **Learned:** the kit frame of an OSM building is the way's outline in metres (x east, y north) around ~its bbox
  centre (fit median 0.05–6.6 m). OpenFreeMap z14 building features merge neighbours into MultiPolygons, so hiding
  one building = hide the merged feature + re-extrude its other polygons. Additive blending of ~1M points blows out
  to white; normal blending or very low per-point gain is needed. Chromatic aberration fringes 1-px point lines.
- **Changed docs:** twin-lab README, [project-state.md](project-state.md).
- **Opened Q:** [Q-015](open-questions.md#q-015) visual direction / D-011.
- **Next:** Atahan picks a direction → port into `frontend/app` (coordinate with the AI-layer session).

## 2026-10-24 — AI layer of the app: live steps, cards, voice orb, camera walk mode

- **Did:** (parallel to another session's visual concepts in `frontend/prototypes/twin-lab/`; file split agreed by
  message: this session owns `src/ui/Chat.tsx`, `src/ui/cards/`, `src/voice/`, the orb, the camera view, `chat.css`,
  `/chat/stream`.) Backend: `Guide.on_step` callback + `POST /chat/stream` (NDJSON steps → reply), `channel` and
  `photo` on `/chat`, photo shown for one turn then replaced by a text placeholder, `core/directions.py` turn-by-turn
  legs on route events. Frontend: live tool checklist, route card (steps, show on map, walk with camera), pending
  change card (Apply / Keep as is → plain messages to the Guide), applied note, profile chip, follow-up chips,
  voice mode (browser SpeechRecognition + speechSynthesis, canvas point-cloud orb, EN/DE/TR, hands-free), camera
  walk mode (rear camera, floor arrow, spoken steps, "Where am I?" sends a frame, mic for next/back/repeat or a
  question).
- **Learned:** Starlette GZip flushes streamed chunks (Z_SYNC_FLUSH), so NDJSON is live behind it; `.chat` has
  `backdrop-filter`, so the full-screen camera view must be portalled to `body`. Live Opus 5.5 photo turn: read the
  sign "3.07 Meeting room", confirmed it with `search`, highlighted it; 5.2 s, 0 ungrounded.
- **Changed docs:** [commands.md](../docs/guides/commands.md#backend-guide-api), [project-state.md](project-state.md).
- **Then (Atahan: "no feedback, looks cheap"):** orb rebuilt in WebGL (three.js points, simplex-noise shader, rim +
  depth fade, CSS glow driven by the level); always visible (large in the empty chat, small in the composer); voice
  mode became a stage (orb, live transcript, Guide steps, spoken reply as captions); recognition never fails
  silently (per-error messages, "didn't catch that"); the mic meter starts only on `audiostart`, and an
  `audio-capture` error retries once without it (a parallel mic stream cost recognition the device in Chrome with a
  fake device). Optional `--accent` (fallback `--ink`) for the other session's HUD tokens.
- **Next:** test voice + camera on a phone over HTTPS (deployed URL); ElevenLabs can replace `useVoice` later.

## 2026-10-24 — Vercel deploy config

- **Did:** `vercel.json` (services `web` = Vite `frontend/app/` and `api` = FastAPI `backend.app:app`, `/api/(.*)`
  rewrite, `excludeFiles`, `maxDuration` 300); `StripPrefix` ASGI middleware and `CORS_ORIGINS` in `backend/app.py`;
  `tests/test_deploy.py`; deploy section in [commands.md](../docs/guides/commands.md#deploy-vercel).
- **Learned:** the Vercel rewrite keeps the `/api` prefix, so the backend strips it; the backend reads only
  `building.json` + `manifest.csv` from `data/` (bundle about 49 MB of code+data).
- **Changed docs:** [commands.md](../docs/guides/commands.md#deploy-vercel), [project-state.md](project-state.md#next-priorities).
- **Next:** Atahan imports the repo into Vercel and sets the env vars; pushing `dev` needs Atahan's OK.

## 2026-10-24 — Handoff: app deployed, frontend polish next

- **Did:** Recorded that Atahan has deployed the app; reordered project-state "Do next": frontend polish first
  (next session), Q-014 organiser follow-up and Q-001 output format parked by Atahan's choice; listed the small
  gaps (numpy undeclared, `route_model` not persisted, no live smoke test yet).
- **Next:** frontend polish ([project-state](project-state.md#-start-here-handoff-for-the-next-session-2026-10-24-evening)).

## 2026-10-24 — Q-014: second route model (geodesic) + route rules

- **Did:** `core/geodesic.py` (in-space door-to-door distance, polygon shrunk 0.15 m, visibility graph; subagent),
  `core/route_models.py` (`kit` | `geodesic` per call, height-based stair/lift costs, `RouteRules`: production bays
  destination-only, no outside shortcut, forklift; `sequence_length` = organiser-style re-measure), wired into
  `core/navigation.py`, `core/basic_parser.run_parsed` and `agent/tools.py` (rules always on, `forklift` preset,
  `route_model` attribute). `scripts/compare_route_models.py`; tests `tests/test_geodesic.py`,
  `tests/test_route_models.py`. Gave Atahan the 5 organiser questions as a Discord message.
- **Learned:** on 1,457 warm-up legs the models pick different sequences in 115 (7.9 %); kit answers would score
  0.930 mean (0.984 with the rules), worst legs = kit lift vs new-rule stairs (score 0.36). 202 kit legs pass
  `outside`; 127 have no route without it (Swiss stair blocks) — the outside question decides a lot. No warm-up
  route crosses a production bay. Kit default unchanged: warm-up 2120/2130, solvers 655/655.
- **Changed docs:** route-model.md (new section), solver-plan.md (Sunday routes), routing-profiles.md (forklift
  preset), Q-014 progress, project-state.
- **Next:** organiser answers → switch Sunday route questions to geodesic + rules.

## 2026-10-24 — Organiser route-scoring rules (Discord) → Q-014; session handoff

- **Did:** Analysed the organisers' Discord note on how route answers are scored and compared it with our model
  and the data → [Q-014](open-questions.md#q-014) (door-to-door geodesic distance, height-based stair/lift costs,
  production bays destination-only, forklift ≥ 3 m, likely no `outside` shortcut, score = best ÷ ours). Warning added
  to [route-model.md](../docs/kit/route-model.md). Wrote the handoff in
  [project-state.md](project-state.md#-start-here-handoff-for-the-next-session-2026-10-24-evening).
- **Learned:** under the new costs the stairs-vs-lift choice can flip; any route through a production bay would
  score 0; whether `errand` distances change too is the key question for the organisers.
- **Next:** Q-014 implementation (see project-state).

## 2026-10-24 — Conversation persistence on Supabase

- **Did:** `backend/persistence.py`: conversation ⇄ JSON (profile, applied changes replayed from the base building,
  pending, events, Guide history + system blocks), Memory and Postgres backends with optimistic `version` saves.
  `SessionStore` uses it when `SUPABASE_DB_URL` is set; `/chat` and switch-building save, conflict → 409. Migration
  `supabase/migrations/20261024120000_conversations.sql` applied (RLS on, no policies). `tests/test_persistence.py`.
- **Learned:** the Supabase direct host is IPv6-only (doesn't resolve on our network; Vercel is IPv4) → use the
  Transaction pooler (6543, no prepared statements). Restored history is accepted by the real API (Sonnet, two
  stores, wheelchair profile honoured on the second; cache reads hit). Anon key on `/rest/v1/conversations` → 0 rows.
- **Changed docs:** [commands.md](../docs/guides/commands.md#conversation-persistence-supabase-postgres), `.env.example`.
- **Next:** Vercel config ([project-state.md](project-state.md#next-priorities)).

## 2026-10-24 — Sunday hardening: paraphrases, Swiss frames, end-to-end checks

- **Did:** Live paraphrase eval of the parser (31 dev questions, all kinds): regex 0/31, llm 31/31, hybrid 31/31.
  Checked the Swiss `straight_line_3d` risk: every train/dev/test question of that kind is procedural/OSM; 84 of 108
  multi-floor Swiss buildings have every floor's space-bbox centre within 2 m of the origin on each axis (82 with a
  Euclidean 2 m radius) → `room_facts` no longer reports above/below on Swiss buildings. Full train run 515/517 (unchanged, the 2 known Q-006 cases). Real-Claude conversation through
  the app proxy (`/api/chat`): preset, route with 15 vertices, closure → change event with 4 lift-shaft spaces,
  re-route via Lift 2; all grounded. Browser re-check not possible (Chrome extension disconnected).
- **Budget:** parser eval ≈ $0.59 + paraphrasing + 3 app turns on Opus ≈ $0.8 → ≈ $1.4 total.
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Voice-ready replies

- **Did:** `agent/speech.py` (`speakable`: markdown, list markers, ids, symbols → plain sentences, units spelled
  out, never adds numbers); `Guide.reply(channel="voice")` with `VOICE_STYLE` as a mid-conversation system message
  (models that support it) or a user-turn note; `/v1/chat/completions` speaks; `live_guide.py --channel voice`;
  prompt: don't offer to show the map. Doc nits from the last review fixed.
- **Learned:** Sonnet 5.5 low in voice mode answers in ~3 s with natural spoken steps; only nit was offering to
  "put it on the map" (fixed in the prompt).
- **Budget:** +$0.054 → ≈ $0.63 total.
- **Next:** Sunday hardening (parser paraphrases, Swiss `straight_line_3d`, full train run).

## 2026-10-24 — Frontend app (monochrome point cloud) + point-cloud API + profile presets

- **Did:** Reviewed the teammate's gap check (routing-profiles TODO, personas P19–P26): accurate; fixed P21's Q-004
  link. Built `frontend/app/` (Vite/React/r3f): monochrome cloud with emergence + scan plane, route comets,
  highlight/closure/lost-access per-space states, floor solo + separation, camera rig, chat panel, light/dark.
  Subagents: `core/pointcloud.py` + `GET /sessions/{id}/points` + enriched route/change events; `set_profile`
  presets + cue safety net. Route events now carry `element_path`, `length_m`, `profile`.
- **Learned:** the route only reads well when off-route rooms step back; overlapping event polls replayed events
  (now chained); port 5173 is taken by another local project (we use 5181).
- **Decisions:** D-011 accepted (monochrome, Atahan).
- **Budget:** +$0.058 (one live Sonnet regression run) → ≈ $0.58 total.
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Preference-extraction gap check + new personas

- **Did:** Compared the profile plan in routing-profiles.md with `agent/tools.py`; wrote the gap list as a TODO.
  Added personas P19–P26.
- **Learned:** `RoutingProfile` has only `step_free`, `min_door_width_m`, `avoid_lifts`; it is session-only; it
  depends on the model calling `set_profile` (no presets, no safety net).
- **Changed docs:** [routing-profiles.md](../docs/product/routing-profiles.md#todo-preference-extraction),
  [personas.md](../docs/product/personas.md#added-personas-2026-10-24), project-state priority 4.
- **Next:** [project-state.md](project-state.md#next-priorities).


## 2026-10-24 — Live Guide check (API key set)

- **Did:** `scripts/live_guide.py` (7-turn tricky user against the real API: tools, replies, ungrounded, cache,
  seconds, $). Runs: Opus 5.5 medium ×2, Opus 5.5 low, Sonnet 5.5 low ×2. Fixed what the runs exposed:
  `compare_routes` capped lost rooms at 15 → `lost_access_by_floor` with counts, uncapped; `propose_change` now
  includes the impact (Sonnet had called `compare_routes` in parallel with a guessed id); id errors list valid
  ids; two prompt sentences (no unsupported general claims; change ids only from tool results).
- **Learned:** all models handled the conversation correctly with 0 ungrounded replies and working caching;
  Sonnet 5.5 low is ~1.5–2.2× faster (3.3–3.9 vs 5.9–7.3 s/turn) and ~2.5× cheaper than Opus 5.5 medium;
  Opus low gave no clear speed gain (6.8 s/turn, one pre-fix run; not directly comparable). The first Opus medium
  run had one failed `find_route` (invalid via id `proc-campus-train-000-V04`, "No place matches") that the
  model recovered from.
  Replies use markdown (bad for TTS).
- **Budget:** ≈ $0.52 API spent (5 live runs: 0.157 + 0.055 + 0.118 + 0.061 + 0.129).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Building Guide loop + backend skeleton (offline)

- **Did:** `agent/guide.py` (manual Claude tool-use loop over `agent/tools.py`, cached overview, model via
  `GUIDE_MODEL`), `agent/offline_llm.py` (rule-based client when no key), `compare_routes` tool (pending or applied
  change: lost access, longer routes, `extra_m`), `tests/test_guide.py` (scripted tricky user). A subagent built
  `backend/` (FastAPI: sessions, `/chat`, `/events`, OpenAI-compatible SSE `/v1/chat/completions`) +
  `tests/test_backend.py`; fixed after its review: predictions no longer touch `session.events` (a poll could see
  phantom routes), `llm_mode()` shared with `/health`. Fixed the `run_benchmark` usage in the
  `agent/benchmark_agent.py` docstring.
- **Learned:** with a step-free profile Main lobby → Meeting room 3.07 (train campus 000) is 124.24 m via Lift 1,
  132.2 m via Lift 2 after closing Lift 1; closing both lifts cuts every upper-floor room for a wheelchair user.
  Grounding by rounding is strict enough to catch invented numbers but accepts "about 124 m".
- **Decisions:** D-010 proposed (guardrails in code).
- **Budget:** $0 API (no key yet; all tests offline).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Deterministic core: all solvers verified, benchmark runner, navigation, agent tools

- **Did:** Scaffolding (`core/solvers` registry + `SolverResult`, `core/formatter.py`, `scripts/validate_solvers.py`),
  then 5 parallel subagents: geometry (4 kinds), shared walls, reachability, routing (errand, what_if_door),
  warm-up navigation + parser. I wrote the pipeline (`agent/benchmark_agent.py`, `agent/run_benchmark.py`,
  `BENCHMARK.md`) and the Guide tool layer (`agent/tools.py`).
- **Learned:** "room" differs per kind (walls: not corridor/stair/lift/outdoor, halls count; counts: `type ==
  room` = manifest `rooms`); every opening kind is width-checked; errand via is on any floor with stairs;
  what-if uses full graph + `type == room`; formatter labels spaces `<ref> (<name>)` (repeated OSM names);
  Dijkstra tie-breaking matches gold only while `BuildingMap.graph()` order is unchanged.
- **Scores:** solvers 655/655; text pipeline dev 138/138, train 515/517; warm-up 2120/2130.
- **Questions:** Q-003, Q-004 resolved; Q-005, Q-006 progressed. Spend: $0 API.
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — D-013 (was D-011 on the branch): transcript rewriter for voice input (Utku)

- **Decided:** Phase 4 voice path gets a transcript rewriter (STT → rewriter → Guide) that only normalises names and
  numbers to the building vocabulary; the original transcript is passed along; typed chat stays rewriter-free.
  [D-013](decisions.md#d-013).

## 2026-10-24 — Guide: final review fixes (branch `1-agentic-yarag`)

- **Did:** Grounding now checks numbers glued to a unit ("999m", "45m²", "37.4m"; "3D", "2nd" still ignored);
  `building_fact` / `route` not_found and ambiguous summaries name the slot that failed or varies (not always
  `place` / `to`); a failed `update_session` says "Nothing was saved; call update_session again with all fields…"
  and the prompt only acknowledges a constraint after an ok result; any tool exception becomes an `error`
  tool_result, any turn exception rolls the turn back and re-raises, the REPL and `scripts/eval_guide.py` survive
  any exception; the code fallback strips raw `[id]` tags from steps and ends an ambiguous result with the options
  and "Which one do you mean?"; prompt: closures by name only for lifts/stairs, clarifying questions list ≤ 3
  options. New conversation `compact_units.json`. +10 tests; full suite 117 passed.
- **Live run:** `scripts/eval_guide.py`, 9 conversations: 16/16 turns PASS, ~$0.32 (single run).
- **Changed docs:** project-state.md, ai-agents.md (live run count).
- **Next:** deferred review items: plural closures ("both lifts"), raw opening ids in route summaries.

## 2026-10-24 — Guide Task 6: scripted conversations, live runner, docs (branch `1-agentic-yarag`)

- **Did:** 8 scripted conversations (`tests/guide_conversations/*.json`: two-room and same-room printers, unknown
  room, follow-up "there", wheelchair stated once, lift closed and reopened, Turkish, out of scope),
  `scripts/eval_guide.py` (`check_turn` recomputes `route_to` lengths with `core.solvers.route` from the session
  state; PASS/FAIL per turn + cost) and 7 offline tests in `tests/test_guide_conversations.py`; full suite 107 passed.
- **Live run (dev campus + factory):** first run 12/15 turns; failures were prompt behaviour (closing offer "Would
  you like directions?" counted as a question; route reused from memory instead of calling `route` after a
  clarifying answer and after a lift reopened). Three RULES lines in `agent/guide/prompt.py` fixed it: 15/15 PASS
  (a single run, not a stability measure), ~$0.27 per full run; after the review-round checker fixes the three changed
  conversations re-ran 9/9 PASS (~$0.19).
- **Changed docs:** commands.md (Guide section), ai-agents.md (Guide v1 status), project-state.md.
- **Next:** UI / voice on top of `TurnResult`; Guide edit tools (Builder).

## 2026-10-24 — Organisers' note on Sunday route scoring (Utku's session)

- **Learned:** Sunday routes are scored as a space sequence, re-measured with the organisers' own model
  (door-to-door geodesic ~15 cm off walls; stairs 2 m per metre climbed; lift 15 m + 1 m per metre); score =
  best ÷ ours, full marks within 1%, invalid = 0. New factory rules (forklift aisles, openings ≥ 3 m, no
  pass-through production bays). Current `data/` has no aisle/walkway/bay space types.
- **Changed docs:** [route-model.md](../docs/kit/route-model.md#sunday-scoring-model-organisers-note-2026-10-24)
  (new section).
- **Questions:** Q-001 progress (format partly answered, tolerance answered); opened Q-014 (scoring distance
  model / router), Q-015 (factory schema).
- **Next:** decide on a second cost profile for the router (Q-014).

## 2026-10-24 — Guide Task 5: loop, prompt and REPL (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/prompt.py` (cached RULES + building overview, no per-room facts), `agent/guide/guide.py`
  (`Guide.turn` tool loop, one grounding repair then `fallback_text`, API errors roll the turn back, `TurnResult`
  with ids/routes/options for the UI) and `agent/guide/__main__.py` (REPL with `--show-tools` and a cost line);
  15 tests in `tests/test_guide_loop.py` (+1 empty-list test in `tests/test_guide_route.py`); full suite 100 passed.
- **Learned (live smoke):** the API rejects strict tool sets with more than 16 nullable/union parameters, so
  `via` / `close` / `reopen` are now plain arrays (`[]` = none). The model split "the 3D printer" into one route per
  room until a prompt rule said to pass the user's own words; `locate` now ignores a leading "the".
- **Review fix:** a refusal / cut-off response with tool calls now gets `is_error` tool results (append-only), so the
  next turn's history stays valid.
- **Next:** Task 6+ (UI / voice on top of `TurnResult`).

## 2026-10-24 — Guide Task 4: grounding checker (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/grounding.py` (`grounded_tokens`, `ungrounded`, `fallback_text`); numbers in a reply must
  appear in tool results, rounded to 0/1/2 dp, or be a list length; 14 tests in `tests/test_guide_grounding.py`.
- **Next:** Task 5 wires it into the Guide loop (one repair round, then `fallback_text`).

## 2026-10-24 — Guide Task 3: route + update_session tools (branch `1-agentic-yarag`)

- **Did:** Added `route` and `update_session` to `agent/guide/tools.py`; session closures are fan-out slots
  (ambiguous "the lift" only asks when routes differ), `bmap.closed` restored after each call;
  `tests/test_guide_route.py` (13 tests); full suite 69 passed.
- **Next:** Task 4+ (agent loop / fallback reading `result.space_path`, `steps`, `options`).

## 2026-10-24 — Guide Task 2: lookup tools (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/tools.py` (`Session`, `TOOLS`, `run_tool`; tools locate, find_places, place_info,
  building_fact via a name -> handler dict) and `tests/test_guide_tools.py` (12 tests); `building_fact` equals
  `core.solvers.solve` on gold inputs for every dev question of its kinds; full suite 56 passed.
- **Next:** Task 3 adds `route` and `update_session` to `HANDLERS` / `TOOLS`.

## 2026-10-24 — Guide Task 1: place resolution + candidate fan-out (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/resolve.py` (`resolve_places`, `resolve_elements`, `nearest_names`, `describe`,
  `fan_out`) and `tests/test_guide_resolve.py` (11 tests); full suite 47 passed.
- **Next:** plan Tasks 2-6 ([plan](../docs/superpowers/plans/2026-10-24-guide-agent.md)).

## 2026-10-24 — Phase 3 Guide agent: design + plan (Utku's session, branch `1-agentic-yarag`)

- **Did:** Brainstormed the Phase 3 "brain" with Utku: terminal-first, multi-turn Q&A + directions, no building
  edits, no UI/voice yet. Wrote and got approval for the
  [design](../docs/superpowers/specs/2026-10-24-guide-agent-design.md) and wrote the
  [implementation plan](../docs/superpowers/plans/2026-10-24-guide-agent.md) (6 tasks, subagent-driven).
- **Decided (in conversation):** Anthropic SDK directly, no LangChain; code (not the model) runs every candidate and
  compares answers; grounding check on numbers + refs; closures last for the session; default model
  `claude-opus-5-5` via `GUIDE_MODEL`.
- **Learned:** `locate` silently picks the first of several matching assets (e.g. two 3D printers) — the Guide must
  list or ask instead.
- **Next:** execute the plan task by task.

## 2026-10-24 — Warm-up kinds in parser + solvers (Utku's session)

- **Did:** 6 warm-up templates in `core/question_parser.py` (+ `destination`, tour `stops`, asset label → type
  fallbacks); solvers `locate`, `count_assets`, `route` (step-free / closure / unreachable), tour via `solve()`;
  replies in `agent/answer.py`; LLM parser schema + prompt; `run_benchmark` `route` = `{reachable: false}` when cut off.
- **Result:** `tests/test_warm_up.py` 2,120/2,130 from text (count 239/239, locate 553/553, route 715/720,
  step-free 239/240, closure 136/138, tour 238/240); all 10 misses are duplicate-name texts. Live LLM on 12 reworded
  dev warm-up questions: 12/12 (≈ $0.33, mostly cache writes). Benchmark unchanged: dev 138/138, test CSV identical.
- **Learned:** warm-up `locate`/`count` name assets by a label that is sometimes not the type ("seating row" →
  `lecture_seating_row`, "air compressor" → `compressor`).

## 2026-10-24 — Route paths in the warm-up format (Utku's session)

- **Did:** cloned the organisers' repo to `upstream-challenge/` (read-only, push disabled, ignored via
  `.git/info/exclude`) — identical to our kit copy. Read README §3–4: warm-up answers hold `space_path` and
  `element_path`. Added `RouteResult.legs` / `.element_path` and `BuildingMap.leg()`; errand returns `legs`;
  `run_benchmark` .json gets `route`. Submission renamed to `submissions/team_jaRAG.csv` (team name jaRAG).
- **Result:** `tests/test_routes.py`: 1,338 / 1,338 warm-up route questions exact (length, both paths,
  unreachable cases). `uv run pytest -q` → 30 passed. Test CSV unchanged; JSON has `route` for 20 errands.
- **Open:** Q-001 — question for the organisers drafted there; Utku will ask. Warm-up kinds (route, tour,
  locate…) have no parser templates/solvers yet in case Sunday asks them.

## 2026-10-24 — run_benchmark, BENCHMARK.md, test submission (Utku's session)

- **Did:** `agent/run_benchmark.py` (+ `run_benchmark` script in pyproject); `agent/answer.py` now exposes
  `respond()` (reply + kind + ids + solver result); `BENCHMARK.md`; `submissions/test_submission.csv` and
  `submissions/test_answers.json` generated by the agent (hybrid mode); commands.md uses `agent.answer:answer`.
- **Result:** 145/145 test questions answered, 0 errors; CSV ids == `submission_template.csv`; replies identical
  to `benchmark.evaluate --submission-csv`. `uv run pytest -q` → 28 passed.
- **Open:** Sunday route node ids (Q-001); team name for the `team_<name>.csv` file.

## 2026-10-24 — Live LLM parser accuracy (Utku's session)

- **Did:** `ANTHROPIC_API_KEY` added to `.env` (git-ignored); ran `scripts/eval_llm_parser.py --per-kind 3`
  with and without `--paraphrase` (24 dev questions, 3 per kind; step_free 1, what_if 2).
- **Result:** original wording: regex, llm, hybrid all 24/24. Reworded questions: regex 0/24 (no template
  matches), llm 24/24, hybrid 24/24 → hybrid is the right default for unseen wording (D-007).
- **Cost:** parser tokens at evaluate.py prices ≈ $0.42 first run (66.9k cache-write tokens), ≈ $0.19 second
  (331.7k cache reads); paraphrase calls not included in that count.
- **Caveat:** small sample (24 questions, one paraphrase each); the paraphrases keep names exactly.

## 2026-10-24 — Answer formatter + first official dev score (Utku's session)

- **Did:** `agent/answer.py`: `answer()` for `benchmark.evaluate`, formatter writes the `Answer:` line from solver
  results (refs only for space kinds, a single number for number kinds); `tests/test_answer.py` scores every
  train/dev reply with `benchmark/score.py`.
- **Result:** `benchmark.evaluate data/dev --agent agent.answer:answer` (PARSER_MODE=regex) → **138/138**; train
  515/517; test 145/145 replies, none fail. API spend: $0.
- **Learned:** every space has a `ref` and every train/dev `accept` list holds it. The solver test's "655/655 via
  text" skipped the 7 ambiguous texts; real text → answer is 653/655 (H02 and H04 of osm-way37850565, where
  the text names a duplicate "Büro" and H02/H03 have identical text with different answers).
- **Next:** test CSV, `run_benchmark` + `BENCHMARK.md`; measure LLM parser once `.env` has a key.

## 2026-10-24 — Solvers for every benchmark kind (Utku's session)

- **Did:** `core/solvers.py` with one solver per kind + `solve(bmap, kind, params)`; `tests/test_solvers.py`
  (gold `inputs` and text → parser → solver). Written first in a scratch package before the foundation commit
  landed, then moved into `core/`. Root `README.md` added (setup + how to run the kit from `archive/`).
- **Learned:** shared walls count `type` ∈ {room, hall} (Q-003 resolved); width rule on all opening kinds
  matches 80/80; parser's `step_free` slot for errands is now honoured by the solver.
- **Result:** 655/655 train+dev both ways; 145/145 test questions solve without error. API spend: $0.
- **Next:** formatter + `answer()` + dev evaluation + test CSV ([project-state.md](project-state.md#next-priorities)).

## 2026-10-24 — Zero-cost cloud stack

- **Did:** Re-checked free tiers (Vercel Python runtime, Supabase, Render, Modal, HF Spaces, Koyeb); wrote
  [stack-options.md §9](../docs/research/stack-options.md#9-zero-cost-variant-added-2026-10-24); rewrote the setup
  checklist; `.env.example` now lists `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `PARSER_MODE`.
- **Learned:** HF Docker Spaces now need a paid plan; Koyeb needs a card; Vercel runs FastAPI natively (500 MB bundle,
  streaming, no WebSockets) → frontend + backend in one free project.
- **Decisions:** D-006 accepted (zero-cost revision); Q-007 resolved.
- **Next:** Atahan signs up for Vercel + Supabase; Claude configures; solvers in parallel.

## 2026-10-24 — Licensing, configurable parsing, point-cloud prototype

- **Did:** Checked licences: data CC BY 4.0 / ODbL / CC0 (redistributable with attribution; ODbL share-alike);
  upstream kit repo has no licence → kit code flagged (Q-013). Added `LICENSE` (MIT; Atahan confirmed MIT), `NOTICE.md`,
  `data/README.md`. Added parser modes (`agent/parsing.py`) + LLM parser (`agent/llm_parser.py`) + offline tests
  + live eval script. Point-cloud 3D prototype (three.js) built and verified in Chrome by a background agent;
  viewer shows building attribution (ODbL credit for OSM).
- **Learned:** Opus 5.5 rejects forced `tool_choice` → structured outputs (`output_config.format`) for extraction.
- **Decisions:** D-007 accepted (configurable, hybrid default); D-009 accepted (MIT, Atahan confirmed).

## 2026-10-24 — Verified-commit workflow (.claude/)

- **Did:** Added `commit-verifier` + `commit-fixer` agents, `/ship` skill, worklog template/history, commit-gate
  hook + stamp script, `.claude/settings.json`; documented in [dev-workflow.md](../docs/guides/dev-workflow.md).
- **Learned:** the hook went live immediately and blocked a test command containing a `git commit --amend` string —
  test hook inputs via a script file, not inline.
- **Decisions:** D-008 accepted.
- **Next:** first commit via `/ship` once the GitHub repo question is answered.

## 2026-10-24 — Restructure, setup, research (4 parallel agents)

- **Did:** `uv sync` + oracle on dev (369/369). Moved data + scorer to root, copied `building_map.py` to `core/`,
  archived the kit, root `pyproject.toml`. Research agents wrote ElevenLabs, cloud-stack, question-parsing docs and
  personas + routing profiles; I wrote [overview.md](../docs/architecture/overview.md) and
  [ai-agents.md](../docs/architecture/ai-agents.md) (renamed from agents.md: macOS case-insensitivity made it match
  `AGENTS.md`).
- **Learned:** one template per benchmark kind → regex parser 100%; Lovable can't sync a monorepo subfolder;
  ElevenLabs Custom LLM lets one Claude brain serve voice + text; only 30/23,748 openings have steps (all
  entrances) — lifts and door widths are the real accessibility constraints; 77 multi-floor buildings have no lift.
- **Decisions:** D-004, D-005 accepted (Atahan); D-006, D-007 proposed.
- **Budget:** $150 Claude credits announced (Q-012). Spend so far: $0 API (all deterministic).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Foundation: docs + memory bank

- **Did:** Read the PDF brief, kit README, ATTRIBUTION, starter agent and benchmark code; scanned all 280
  buildings and all question files for schemas and counts. Created `CLAUDE.md`, `docs/` (challenge, kit,
  architecture, guides) and `memory-bank/`.
- **Learned:**
  - Test set = 145 questions in 8 kinds; floor_area_total + shared_walls_count = 41%.
  - Route model fully specified and implemented in `starter_agent/building_map.py`.
  - Scorer: units like `m2` are safe; room refs / extra numbers on a number answer line are fatal.
  - PDF and README disagree on Sunday output format (Q-001).
  - System `python3` is 3.9; the kit needs ≥3.12 → use `uv`.
- **Decisions:** D-001 accepted; D-002, D-003 proposed.
- **Questions opened:** Q-001 … Q-012.
- **Next:** see [project-state.md](project-state.md#next-priorities).
