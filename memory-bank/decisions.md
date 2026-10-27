---
id: decisions
summary: Decision log (D-###). Status proposed | accepted | rejected | superseded. Never renumber.
related: [open-questions.md, project-state.md, ../docs/architecture/overview.md]
---

# Decisions

[Memory bank](README.md) · Next free id: **D-023**

Template:

```markdown
<a id="d-000"></a>
### D-000 — Title
- **Status:** proposed | accepted | rejected | superseded by D-xxx · **Date:** YYYY-MM-DD · **By:** who
- **Context:** why this came up (link Q-### if it resolves one)
- **Decision:** what we do
- **Consequences:** what this implies / rules out
- **Evidence:** files, commands, messages
```

---

<a id="d-001"></a>
### D-001 — Knowledge structure: CLAUDE.md + docs/ + memory-bank/
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan (request), set up by Claude
- **Context:** Several agents/sessions will work in parallel during a short hackathon; they must share facts
  without re-deriving or hallucinating them.
- **Decision:** `CLAUDE.md` is the entry point; `docs/` holds verified descriptive knowledge (challenge, kit)
  and our design (architecture) with front matter `sources`/`related`; `memory-bank/` holds live state,
  decisions, open questions and a log. All cross-linked with stable anchors.
- **Consequences:** Every session follows the protocol in [CLAUDE.md](../CLAUDE.md#session-protocol-do-this-every-time).
- **Evidence:** files created 2026-10-24 (CLAUDE.md, docs/, memory-bank/).

<a id="d-002"></a>
### D-002 — Build our core on the starter `BuildingMap` route model
- **Status:** proposed · **Date:** 2026-10-24
- **Context:** Expected route lengths come from a specific model; the starter code implements it exactly
  (README §3, `building_map.py:179-212`).
- **Decision:** Reuse/extend `BuildingMap` (add width filter, reachability, geometry) instead of rewriting.
- **Consequences:** Must keep anchor = `representative_point()`, MultiGraph, stair/lift costs unchanged.
- **Evidence:** [route-model.md](../docs/kit/route-model.md). To accept: oracle run on dev matches.
  2026-10-24: acceptance criterion met — all solvers build on `core.building_map` and match 655/655 train+dev
  answers (`tests/test_solvers.py`). Status left for the team to flip.

<a id="d-003"></a>
### D-003 — LLM for language, code for facts; deterministic `Answer:` line
- **Status:** proposed · **Date:** 2026-10-24
- **Context:** Scorer only reads the last `Answer:` line and is strict (exactly one number, ordering of rooms).
- **Decision:** Solvers compute answers; a formatter writes the final `Answer:` line from structured results.
  The LLM may phrase explanations and parse intent, never compute numbers.
- **Consequences:** Needs a reliable question → (kind, params) step ([Q-008](open-questions.md#q-008)).
- **Evidence:** [scoring.md](../docs/challenge/scoring.md#how-a-reply-is-parsed).

<a id="d-004"></a>
### D-004 — Build at the repo root; archive the organiser kit
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan
- **Context:** Resolves [Q-009](open-questions.md#q-009).
- **Decision:** Root repo is where we build. Extracted to root: `data/` (moved), `benchmark/` (moved, official
  scorer — never edit `score.py`), `core/building_map.py` (copied from starter), `ATTRIBUTION.md`,
  `.env.example`. Root `pyproject.toml` (uv, Python ≥3.12). Everything else → `archive/initial-repo/`.
- **Consequences:** Run everything from the root. Starter agent still runnable via
  `PYTHONPATH=archive/initial-repo`. See [archive/README.md](../archive/README.md).
- **Evidence:** after the move, oracle on dev 369/369; `core.building_map` reproduces all 120 dev warm-up routes
  to < 1 cm (2026-10-24).

<a id="d-005"></a>
### D-005 — Commit the dataset to git
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan
- **Context:** Resolves [Q-011](open-questions.md#q-011). The upstream kit repo is public, so redistribution is fine;
  ODbL attribution kept via `ATTRIBUTION.md` at root.
- **Decision:** `data/` (~209 MB) is committed as normal files.
- **Consequences:** Clone size ~200 MB+; keep `ATTRIBUTION.md`; the repo stays ODbL-compliant for OSM-derived parts.

<a id="d-006"></a>
### D-006 — Cloud stack: FastAPI on Vercel's Python runtime + Supabase + own React app (Vercel) + ElevenLabs Custom LLM
- **Status:** accepted (zero-cost revision) · **Date:** 2026-10-24 · **By:** Atahan · **Waiting for:** account sign-ups (Vercel, Supabase)
- **Revision 2026-10-24 (zero cost):** Atahan wants to pay nothing → backend moves from Railway to **Vercel's Python
  runtime** in the same Vercel project as the frontend; fallback Render Free / Modal. See
  [stack-options.md §9](../docs/research/stack-options.md#9-zero-cost-variant-added-2026-10-24).
- **Context:** "Cloud on day one", realtime collaboration, voice. Resolves [Q-007](open-questions.md#q-007).
- **Decision:** Python core + Claude agents in FastAPI on Vercel's Python runtime, in the same Vercel project as the
  frontend (fallback Render Free / Modal); Supabase for Postgres (buildings JSON +
  `building_edits` event log), Realtime broadcast/presence, Auth, Storage; Vite/React/TS/Tailwind/shadcn +
  react-three-fiber in `frontend/` on Vercel; ElevenLabs Agent with Custom LLM → our OpenAI-compatible endpoint;
  GitHub Actions CI. Lovable only for throw-away mock-ups (no monorepo-subfolder sync).
- **Consequences:** backend is the only writer of edits; one agent brain for text + voice.
- **Evidence:** [stack-options.md](../docs/research/stack-options.md), [elevenlabs.md](../docs/research/elevenlabs.md),
  [overview.md](../docs/architecture/overview.md).

<a id="d-007"></a>
### D-007 — Benchmark parsing: deterministic regex templates first, LLM fallback for unknown wording
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan (both, configurable; Claude decides default)
- **Modes:** `PARSER_MODE` = `hybrid` (default) | `regex` | `llm` | `crosscheck` — `agent/parsing.py`;
  LLM parser `agent/llm_parser.py` (structured outputs, Opus 5.5, server-side fallback). Rationale:
  [ai-agents.md](../docs/architecture/ai-agents.md#parser-modes).
- **Context:** [Q-008](open-questions.md#q-008).
- **Decision:** `core/question_parser.py` (one regex per template + name resolver) is primary. If no template
  matches, Claude with a strict tool schema returns `{kind, raw slot text}` — never ids — and the same resolver
  maps them. Ambiguous names: solver runs every candidate and answers if they agree.
- **Evidence:** train+dev 655/655 params match `inputs`; test 145/145 parse, 0 ambiguous (`uv run pytest`,
  2026-10-24); fallback ≈ $0.007/question. [question-parsing.md](../docs/research/question-parsing.md).

<a id="d-008"></a>
### D-008 — Every commit is verified by an independent agent
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan
- **Context:** Many agents write code in parallel; we need to know that what is claimed is what is implemented.
- **Decision:** Worklog of claims (`.claude/worklog/PENDING.md`) → `/ship` → fresh `commit-verifier` agent →
  `commit-fixer` loop (≤ 3 rounds) on FAIL → commit only with a PASS stamp of the staged tree; enforced by a
  PreToolUse hook. Entries + reports archived in `.claude/worklog/history/`.
- **Consequences:** direct `git commit` from Claude is blocked; each commit costs one verifier run per round.
- **Evidence:** hook pipe-tested 2026-10-24 (blocks: no stamp, stale stamp, `--amend`, `-am`, add+commit
  one-liner; allows a fresh stamp); stamp script refuses FAIL and unstaged entries.
  [dev-workflow.md](../docs/guides/dev-workflow.md).

<a id="d-009"></a>
### D-009 — Licensing: MIT for our code; third-party material keeps its own terms
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan (MIT confirmed)
- **Context:** Repo is public. `ATTRIBUTION.md`: data is CC BY 4.0 (Swiss Dwellings, ResPlan), ODbL 1.0 (OSM),
  CC0 (procedural) — all allow redistribution with attribution; ODbL is share-alike. Upstream kit repo
  (`Synera-GmbH/industrial-agents-hackathon-2026`) is public but has **no licence** (GitHub API `license: null`),
  so kit *code* (`benchmark/`, `archive/initial-repo/`, kit parts of `core/building_map.py`) has no explicit grant.
- **Decision:** `LICENSE` (MIT, our code only), `NOTICE.md` (what is third-party, under which terms, removal on
  request), `data/README.md` (per-source licences + obligations), keep `ATTRIBUTION.md` at root. Ask organisers to
  confirm redistribution of kit code ([Q-013](open-questions.md#q-013)).
- **Consequences:** screenshots / video showing OSM buildings must credit "© OpenStreetMap contributors";
  modified OSM buildings we publish stay ODbL.

<a id="d-010"></a>
### D-010 — Guide guardrails live in code: same-turn apply refused, grounding check with one repair round
- **Status:** proposed · **Date:** 2026-10-24 · **By:** Claude (Guide session)
- **Context:** The behaviour contract ([ai-agents.md](../docs/architecture/ai-agents.md#building-guide--behaviour-contract))
  needs propose → confirm → apply and D-003 ("every number and id from a tool"). A prompt alone can't guarantee
  either, and the brief scores "shows what it understood before it changes a plan".
- **Decision:** `agent/guide.py` refuses `apply_change` for a change proposed in the same user turn, and checks
  every reply: numbers/ids must appear in a tool result, the overview or the user's words (rounding allowed);
  one repair round, then report leftovers in `GuideTurn.ungrounded` instead of blocking the reply.
- **Consequences:** one extra request when the model invents a number; a confirmation always costs one user turn.
  Derived numbers (differences, sums) must come from tools → `compare_routes` and `extra_m` exist for that.
- **Evidence:** `tests/test_guide.py` (same-turn apply refused; invented "437 m" repaired; leftovers reported).

<a id="d-011"></a>
### D-011 — Monochrome visual language for the app (black / white, light + dark)
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan ("simplistic look, black or white colour scheme for
  light and dark mode, point clouds with good animations")
- **Context:** [visualization.md](../docs/product/visualization.md#visual-language) had a colour-coded scheme
  (cyan walls, magenta cores, amber doors, gold highlight).
- **Decision:** the app is monochrome: white on black (dark), black on white (light), system default + toggle.
  Point kinds and states are told apart by density, alpha, size and motion (flow, flicker, float, sink), never hue.
- **Consequences:** additive glow in dark mode, normal blending with crisp dots in light mode; the prototype keeps
  its colours as a reference only.

<a id="d-012"></a>
### D-012 — Duplicate room names: core returns candidates, the agent asks; the benchmark runs them all
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Utku
- **Context:** Some buildings repeat a name on the same floor (three "Büro" on the ground floor, OSM rooms
  duplicated with the same ref). The question text then cannot say which room is meant: all 12 train+dev misses
  (2 benchmark, 10 warm-up) are such texts. The floor is usually already in the text, so it does not help.
- **Decision:** `core/` stays deterministic and never guesses: the parser returns every candidate
  (`ParsedQuestion.alternatives`). **Guide (chat):** ~~if the answers differ, ask one short question naming what
  tells them apart~~ — **revised 2026-10-27 (Utku): the Guide decides instead of asking.** `find_route` to a name
  that fits several places routes to the nearest reachable one and returns the next two as `chosen.others`
  (`find_nearest` already did this); the Guide names the one it took in a few words and lists the others only if
  asked. It asks only when nothing tells the places apart and the answer depends on it (e.g. no start known).
  Reason: users found it asked too much. **Benchmark (no user):** as in [D-007](#d-007), run every
  candidate and answer if they agree; otherwise answer with the first and say so in the reply.
- **Consequences:** benchmark misses on such texts are accepted; the Guide needs a candidate-describing tool
  (ref, floor, area, neighbours). Contract: [ai-agents.md](../docs/architecture/ai-agents.md#building-guide--behaviour-contract).

<a id="d-013"></a>
### D-013 — Voice input gets a transcript rewriter before the Guide (Phase 4)
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Utku
- **Context:** Speech-to-text transcripts are messy ("Lab two twenty", filler words, misheard machine names). For
  typed input we rely on the Guide model plus code-side name resolution and add no rewriter (extra latency/cost,
  risk of dropping nuance). The Guide's grounding check covers the model's *output*, not the user's input.
- **Decision:** In the voice path (ElevenLabs STT → Guide), add a transcript rewriter step that only normalises the
  transcript — names and numbers to the building's vocabulary (e.g. "Lab two twenty" → "Lab 2.20"), no
  interpretation, no answering. The building's room/asset names are its vocabulary (same list as the Scribe
  keyterms). The Guide receives both the rewritten and the original transcript so a dropped nuance stays visible.
- **Consequences:** One extra (small, fast) model call per voice turn; text chat stays rewriter-free. Must be
  measured on voice latency in Phase 4.
- **Implemented (2026-10-24):** `agent/rewriter.py` (`claude-haiku-5-5`, effort low, JSON schema output, vocabulary =
  `building_vocabulary` cached as system prompt), hooked into `Guide.reply(..., channel="voice")`. Live: ~1–2 s and
  < $0.001 per voice turn. Falls back to the transcript as heard on API error, refusal, empty answer or a number
  found neither in the transcript nor in the building; ordinal floor words are kept as said.
- **Evidence:** conversation 2026-10-24 (branch `1-agentic-yarag`); voice path in
  [ai-agents.md](../docs/architecture/ai-agents.md#voice-path).

<a id="d-014"></a>
### D-014 — One route model: the kit 1.1.0 graph, ported verbatim into core
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Utku
- **Context:** Kit 1.1.0 recomputed every expected answer (train/dev/test) with the judges' rule — door to door
  15 cm off the walls, 30 cm door landings, stairs 2 m per metre climbed, a lift ride 15 m + 1 m per metre, no
  outdoor link ([Q-014](open-questions.md#q-014)). Our `kit` model no longer matched (errand 10/93, what_if_door
  0/4); our own `geodesic` approximation was within 1 m but exact on only 3 of 161 dev routes.
- **Decision:** Copy the 1.1.0 starter's geometry helpers and `BuildingMap.graph` into `core/building_map.py`
  unchanged (same node/edge order → same Dijkstra tie-breaks) and make it the only route model. `expand` /
  `path_parts` give the 1.1.0 `space_path` / `element_path`. `outside` stays available as a start/end node only.
  Remove `core/geodesic.py` and `scripts/compare_route_models.py`; keep `model=` and `GEODESIC` as aliases so
  callers (Guide, branches) don't break. The bay / forklift rules stay ours (organiser note, not in the answers).
- **Consequences:** Train+dev warm-up routes 1,338/1,338 exact (paths too), solvers 655/655, dev benchmark
  138/138. First graph build is slow on huge OSM corridors (~25 s on osm-way360544293); walks are cached by geometry.
  One gold value disagrees with the starter itself (resplan-12462, 10 cm); validators accept starter-equal lengths.
- **Evidence:** [route-model.md](../docs/kit/route-model.md), `tests/test_routes.py`, `scripts/validate_warmup.py`,
  `scripts/validate_solvers.py`.

<a id="d-015"></a>
### D-015 — Access mode: accounts, restricted spaces, preferences, moving objects behind one switch
- **Status:** accepted · **Date:** 2026-10-25 · **By:** Atahan
- **Context:** Demo add-in (Interaction / Creativity, L5). Utku's access-roles design (claimed roles in
  conversation) replaced in part: Atahan wants real accounts, settings UI, remembered preferences and IoT-style
  moving objects.
- **Decision:** Everything behind `ACCESS_MODE=on` (off by default; off = the app exactly as before). Supabase Auth
  (email + password), one admin (`ADMIN_EMAIL`) over every building, members invited by the admin with groups per
  building. Restricted spaces: no defaults; a viewer who may not enter them gets a session on a filtered building
  copy (`core/access.py`), so every Guide tool — `solve` included — can't see them; plan darkens them. Preferences
  belong to the user (browser for anonymous, `user_preferences` when signed in; global ← building override); the
  Guide captures them (`preference` events). Moving objects: only data-backed attributes (width, step-free, lifts,
  stairs, room types), live positions by device token, missions as deterministic machine steps. Multi-object path
  conflicts and building-wide applied changes are "Later".
- **Consequences:** benchmark untouched (dev 138/138 after the change, regex parser); Guide tool list unchanged
  when off; `/drafts` admin-only when on. Needs the migration `20261025200000_access.sql` applied and an admin
  account before a live demo.
- **Evidence:** [access-profiles-design](../docs/superpowers/specs/2026-10-25-access-profiles-design.md),
  [plan](../docs/superpowers/plans/2026-10-25-access-profiles.md), `tests/test_access.py`, `tests/test_fleet.py`.

<a id="d-016"></a>
### D-016 — The Guide speaks with ElevenLabs TTS through our backend; browser voice as fallback
- **Status:** accepted · **Date:** 2026-10-25 · **By:** Atahan (asked for step 1 "better voice", default voice left to the agent)
- **Context:** The app listened and spoke with the browser's Web Speech APIs: robotic, machine-dependent voices.
  The ElevenLabs Agent plan (D-006, Custom LLM) was never wired up and needs agent setup, a public URL and
  per-minute billing. The account is on the Creator tier (131,000 characters/month, `GET /v1/user/subscription`).
- **Decision:** Step by step. Step 1 keeps the browser's speech recognition and replaces only the voice:
  `POST /tts` (`backend/tts.py`) proxies ElevenLabs streaming TTS with the key server-side; defaults
  `eleven_flash_v2_5` (lowest latency, de/tr too) and the premade voice "River" `SAz9YHcvj6GT2YYXdXww` (calm, neutral,
  conversational), overridable with `TTS_MODEL` / `TTS_VOICE_ID`. The frontend (`voice/tts.ts`) fetches sentence
  pieces ahead while playing and falls back to speechSynthesis (no key, failed request — then 60 s pause, locked audio).
  The D-006 Custom LLM agent stays an option for later; next steps are streaming the reply into speech,
  barge-in / hands-free, and Scribe Realtime with building keyterms.
- **Consequences:** Every spoken reply costs ElevenLabs characters (~100–300 per reply). `/tts` has no auth beyond
  the 1,000-character cap, like the other endpoints before access mode. Units are spelled in English by
  `speakable()` even when the voice speaks German or Turkish.
- **Evidence:** `tests/test_tts.py`; live round trip TTS → Scribe ("Meeting room 3.07 … 124 meters" heard back),
  Chrome: first sound 371 ms after the call, real audio level for the orb, cut-off and fallback paths checked.
- **Amendment (2026-10-25):** a failed piece is now retried once, and only a second failure falls back to the
  browser voice; the ElevenLabs pause after that is 15 s, not 60 s (`voice/tts.ts` `COOL_OFF_MS`, latency pass).

<a id="d-017"></a>
### D-017 — Voice replies are spoken while the Guide works: grounded sentences stream, a short "let me check" first
- **Status:** accepted · **Date:** 2026-10-25 · **By:** Atahan (asked for voice step 2, "start speaking sooner")
- **Context:** After D-016 the voice still waited for the whole turn (rewriter, tool rounds, repair) — 5–10 s of
  silence on routing questions. Speaking text before the end-of-turn grounding check could say a made-up number.
- **Decision:** On voice turns the Guide streams each request and `SpokenStream` (`agent/speech.py`) emits a
  sentence only once it is complete and `ungrounded()` finds nothing in it; an ungrounded sentence, a grounding
  repair or a profile-safety-net redo holds live speech, and `finish` adds only what the final reply says that was
  not said yet. `VOICE_STYLE` asks for one fact-free sentence before the first tool call. `/chat/stream` sends
  `{"type":"say"}` lines; the app queues them into the voice (`openSpeech`).
- **Consequences:** Voice-turn replies (and their chat text) now usually start with a "Let me check …" sentence.
  A sentence said live and then dropped by a repair stays said (it was grounded). The after-tool answer arrives
  from the API in one burst in traced turns, so most of the gain is the first sentence. `/v1/chat/completions`
  still answers at the end (no agent uses it).
- **Evidence:** `tests/test_speech.py`, `tests/test_backend.py`; live traces in
  [ai-agents.md](../docs/architecture/ai-agents.md#voice-path) (first sound 2.35 s vs reply at 10.4 s).

<a id="d-018"></a>
### D-018 — Spoken questions start a hands-free conversation with barge-in; utterances end on a 1.3 s pause
- **Status:** accepted · **Date:** 2026-10-25 · **By:** Atahan (asked for voice step 3: barge-in, hands-free, pauses)
- **Context:** The building screen forced "one question, one answer" (`setHandsFree(false)`), recognition stopped at
  the first pause, and the only way to cut the Guide off was a tap.
- **Decision:** Recognition is continuous with our own end-of-utterance timer (1.3 s). After the reply to a spoken
  question the Guide listens again (quiet end after 6 s). While that reply plays (once complete), a second
  recogniser watches for the user: an echo filter (`voice/bargeIn.ts`, word overlap with what the Guide says) tells
  the user's words from the Guide's; two or more own words interrupt and become the next question, a stop word alone
  stops. Supersedes the "one question, one answer" choice in `BuildingScreen`.
- **Consequences:** Two recognisers never run at once (the watcher is aborted before listening). Text-level echo
  filtering can miss a user who repeats the Guide's words, and loud speakers could still trigger a false barge-in;
  Bluetooth headsets drop to call quality while the mic is open. Words said during the preamble (reply still pending)
  don't interrupt; a tap does.
- **Evidence:** Chrome run with a scripted SpeechRecognition, see [ai-agents.md](../docs/architecture/ai-agents.md#voice-path).
- **Amendment (2026-10-25):** the end-of-utterance pause is now 1.0 s, not 1.3 s (`voice/useVoice.ts`
  `END_PAUSE_MS`, latency pass). `interruption` (`voice/bargeIn.ts`): three or more own words → talk; otherwise a
  stop word → stop; otherwise two own words or one own word of three or more letters → talk; else nothing.
  The watcher runs from the reply's first sound (`onStart` in `voice/useVoice.ts` `stream`), the fact-free preamble
  included, not only once the reply is complete. Words heard while the Guide turn is still pending cut the voice,
  are queued (`queued` in `building/BuildingScreen.tsx`) and sent as the next question when that turn is done; this
  replaces "while that reply plays (once complete)" and "words said during the preamble … don't interrupt" above.

<a id="d-019"></a>
### D-019 — The user's words go to ElevenLabs Scribe Realtime with the building's keyterms; browser recognition as fallback
- **Status:** accepted · **Date:** 2026-10-25 · **By:** Atahan (asked for voice step 4)
- **Context:** Browser SpeechRecognition misheard building names (hence the D-013 rewriter), fails in Brave
  ("network") and Firefox, and differs per browser.
- **Decision:** `POST /stt/token` (`backend/stt.py`) mints a single-use Scribe Realtime token and picks ≤ 50
  keyterms (≤ 20 chars, limits checked live) from the session's building: room / lift / stair / floor names without
  numbers first, then asset names, then types. The browser (`voice/scribe.ts`) streams the mic as 16 kHz PCM straight
  to `wss://api.elevenlabs.io/v1/speech-to-text/realtime` (`commit_strategy=manual`, `keyterms` repeated in the query)
  behind the SpeechRecognition interface, so listening, the pause timer and barge-in (D-018) run unchanged. Any
  Scribe failure → browser recognition for 60 s. `STT_MODE=browser` turns Scribe off.
- **Consequences:** Every listen — and the barge-in watcher while replies play — streams audio to ElevenLabs
  (billed per audio time; the Creator tier's STT allowance is UNVERIFIED). Partials only start after ~2 s of audio
  (ElevenLabs docs), and Scribe repeats unchanged partials through silence (only changes count as results). The
  rewriter may now be redundant: [Q-020](open-questions.md#q-020).
- **Evidence:** live probes (keyterm encoding, 50/20 limits), Chrome end-to-end with ElevenLabs-spoken audio as
  the mic: "Where is the CNC mill?" → committed exactly → sent → answered; token 502 → browser recognition; see
  [ai-agents.md](../docs/architecture/ai-agents.md#voice-path). `tests/test_stt.py`.
- **Amendment (2026-10-25):** `stop()` now waits 0.8 s for the last committed segment, not up to 2 s
  (`COMMIT_WAIT_MS`); the mic is opened via `voice/mic.ts` and kept warm 8 s after a listen (`MIC_WARM_MS`).
  The 60 s Scribe cool-off is unchanged.

<a id="d-020"></a>
### D-020 — Route replies are a summary; the app shows the whole route, then guides step by step
- **Status:** proposed · **Date:** 2026-10-25 · **By:** Atahan (asked: the Guide read the whole route at once while
  the plan showed one floor), built by Claude
- **Context:** Route answers listed every step in text and voice; the plan jumped to the start floor only.
- **Decision:** The Guide's directions are one echo line, the total (about_m), the floors crossed and the first step
  (INSTRUCTIONS + VOICE_STYLE in `agent/guide.py`). The app frames the whole route (all floors stacked when it
  crosses floors); Start (or "start"/"başla") begins the guide: each step is framed, read aloud, and the next one
  comes on "I'm there" / "geldim" / "next" (button, typed or spoken; hands-free voice keeps listening).
- **Consequences:** The interaction eval's "directions" rubric judged full step lists; its scores may drop until the
  judge knows the app does the stepping. The camera walk mode and tracking still use the same steps.
- **Evidence:** headless Chrome run on Hauptgebäude (log 2026-10-25 "Guide highlights, figure, guide, nearby").

<a id="d-021"></a>
### D-021 — Places in nearby buildings: search the neighbours, route with a straight-line outdoor leg
- **Status:** proposed · **Date:** 2026-10-25 · **By:** Atahan (asked: answers in the next building), built by Claude
- **Context:** In a building on the map the Guide said "not here" for things in the building next door.
- **Decision:** Buildings with a real position (backend/locations.json) get `search_nearby_buildings` and
  `route_to_building` (`agent/campus.py`, pins ≤ 600 m apart). A route picks the entrance pair with the shortest
  inside-here + straight-line outside + inside-there total; the route event carries `next_building` and the app's
  Continue opens that building, where `POST /sessions/{id}/arrive` places the user at the entrance and draws the rest
  (routing profile copied from the previous session).
- **Consequences:** No street graph: outdoor metres are a straight-line estimate (labelled so in the tool result).
  The other building's leg ignores this session's closures. Only the 17 located OSM buildings have neighbours.
- **Evidence:** `tests/test_campus.py` (10 tests); Hauptgebäude → Mensa Arcisstraße: ~7 m inside, ~120 m outside,
  ~15 m inside.

<a id="d-022"></a>
### D-022 — Sunday agentic layers: route specs on the canonical core, a solver agent, a committed decision cache
- **Status:** proposed · **Date:** 2026-10-25 · **By:** Utku (asked for "the most advanced agent for this task";
  P1 of the Sunday plan, branch `4-sunday-agent`)
- **Context:** A probe of 14 Sunday-style questions on a factory dev building: `regex` answered 1, `hybrid` 11 without
  an error, but only about 7 correctly — the LLM parser had to squeeze every question into one of 15 templates, so
  combined constraints (closure + step-free), item destinations, forklift and new kinds became near-miss kinds
  (silently wrong). The canonical `core.navigation` already handles closures of any element, item endpoints and
  route rules, and reproduces every warm-up route answer. The organisers may re-run our command, possibly without an
  API key (Utku's question).
- **Decision:** (1) the LLM schema gets one general `route` spec (places = rooms, room types or items, nearest
  taken; stops; step_free, forklift, min_width, closures) plus `asks_for`; a spec that is exactly a warm-up kind
  keeps it, anything richer is `route_query` (`core/route_query.py` on `core.navigation`); (2) kind `other`, an
  `asks_for` the kind cannot answer, unresolvable slots or a solver error go to a solver agent
  (`agent/solver_agent.py`: Python sandbox over the building + `submit_answer`, 2 runs + tie-break, Answer line by
  code); (3) every model decision is stored in `llm_cache/decisions.json` (committed) and replayed first, so re-runs
  reproduce `answers.json` without a key. Regex templates stay first and unchanged.
- **Consequences:** test-set and dev answers unchanged (all template wording); Sunday questions in unseen wording or
  new kinds get answers; the cache file must be committed with `SUBMISSION/answers.json`. Model code runs locally in a
  restricted `exec` (accident guard, not a security boundary). Tests never touch the committed cache
  (`tests/conftest.py`).
- **Evidence:** `tests/test_route_query.py`, `tests/test_llm_route_spec.py`, `tests/test_solver_agent.py`,
  `tests/test_answer_agentic.py`, `scripts/eval_sunday_probe.py` (`tests/sunday_probe/`),
  [ai-agents.md](../docs/architecture/ai-agents.md#sunday-layers-route-specs-solver-agent-decision-cache-2026-10-25).

<a id="d-023"></a>
### D-023 — A building from plans gets a real position: origin + bearing, fitted onto OSM, adjusted by hand
- **Status:** proposed · **Date:** 2026-10-25 · **By:** Utku (brainstorming; branch `7-buildings-from-plans` (started as `6-plan-reference-location`))
- **Context:** Imported buildings had no place on the map, so they could not be found again there, and the user had
  no way to compare the generated building with the plan it came from while correcting it.
- **Decision:** `building.location` = {lat, lon, address, origin, bearing (° CCW from east to the building's x),
  outline, height_m, fit, supersedes}; the building's own coordinates are never rotated (Edit mode keeps the plan's
  orientation, the map applies the bearing). Position from the tapped OSM building, else the photos' EXIF GPS, else
  the browser's position; fit = principal axes + IoU descent, scale clamped 0.75–1.25 (low confidence below IoU 0.5
  or at a bound); the user always confirms by hand. The straightened plan is kept per floor with its px → metres
  transform and scales with the building. Re-saving a placed user building supersedes the older one on the map.
  Floors: the user types each file's floor number; more floors are added only in Edit mode, into the open draft,
  turned only by quarter turns of the angle that keeps their walls parallel to the lowest floor's.
- **Consequences:** only the coordinate goes to Overpass; Overpass outages fall back to the map's tiles. Design:
  [plan-reference-and-location-design.md](../docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md).
