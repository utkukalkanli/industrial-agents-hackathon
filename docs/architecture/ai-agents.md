---
id: arch-agents
summary: PROPOSED design of every AI agent in the system — Building Guide (chat + voice), benchmark pipeline, Builder (plan → building), and how they share one deterministic tool layer.
status: proposed
sources: [../research/elevenlabs.md, ../kit/starter-agent.md, ../challenge/brief.md, ../challenge/scoring.md, ../../agent/tools.py, ../../agent/guide.py, ../../agent/offline_llm.py, ../../agent/llm_parser.py, ../../agent/solver_agent.py, ../../agent/llm_cache.py, ../../core/route_query.py]
related: [overview.md, solver-plan.md, ../product/routing-profiles.md, ../product/personas.md, ../research/question-parsing.md]
---

# AI agents — PROPOSED

[Docs index](../README.md) · System view: [overview.md](overview.md)

**One rule for every agent:** the LLM understands and explains; tools compute. No agent ever states a room,
distance, count or route that did not come from a tool result ([D-003](../../memory-bank/decisions.md#d-003)).

## The agents

| Agent | Job | Model (start) | Channel | Points |
|---|---|---|---|---|
| **Building Guide** | conversation: find, route, react, edit; clarifies; remembers user profile. **v1 implemented** (terminal, `agent/guide_v1/`: 6 tools, grounding check, session; live scripted run 16/16 turns, 9 conversations, [spec](../superpowers/specs/2026-10-24-guide-agent-design.md), [plan](../superpowers/plans/2026-10-24-guide-agent.md)); the v1 Guide has no edit tools, UI or voice — those are in the canonical `agent/guide.py` (below) | Opus 5.5 default (`GUIDE_MODEL`), medium effort | terminal REPL; text chat + voice (via ElevenLabs) planned | Interaction 25, L1–L3 |
| **Benchmark pipeline** | question text → parse → solver → `Answer:` line; no free-form LLM | none; Haiku/Sonnet only as parse fallback | CLI `run_benchmark`, `benchmark.evaluate --agent` | Does it work 55 |
| **Builder** | floor-plan image → draft `building.json` → validate → user confirms; drafting from plans is the **Creator** ([design](../superpowers/specs/2026-10-25-plan-import-design.md), [plan](../superpowers/plans/2026-10-25-plan-import.md), in progress) | Opus 5.5 (vision) | UI upload + chat | L4 |
| (dev) **Claude Code subagents** | build the product: research, solvers, tests | — | this repo | — |

Model ids: [claude-api skill / docs]; switch by env var, compare cost/quality with `benchmark.evaluate`.

## Shared tool layer

Every agent calls the same Python functions in `core/` (exposed as Anthropic tools, as HTTP for ElevenLabs
webhooks if ever needed, and optionally as one MCP server). Proposed tool set for the Guide:

| Tool | Returns | Mutates shared building? |
|---|---|---|
| `building_overview` | floors, cores, entrances, closures | no |
| `search(query, floor?)` | ranked spaces/assets with ids | no |
| `room_facts(space)` | area, centre, floor, neighbours (shared walls), above/below (omitted on Swiss Dwellings buildings, floors not aligned — [solver-plan](solver-plan.md#straight_line_3d)), doors + widths | no |
| `find_route(from, to, via?, profile)` | node path, metres, steps with landmarks, profile used | no |
| `find_nearest(start, query, floor_id?, closed?)` | the nearest room holding that item kind (or matching room kind/name) by route length under the profile: a `find_route` result plus `nearest` and `next_nearest` (the next 2, with `about_m`); emits one route (to the nearest) + a highlight. `closed`: closures for this question only, used for the ranking and the final route; for an item (no floor filter) the shared `nearest_item` solver ranks every holder under the session's model and rules (profile step-free + closures), the nearest 5 are measured with `find_route` (penalties) and the shortest wins; [solver-plan.md](solver-plan.md#post-hackathon-kinds-and-data-rules-2026-10-27)), otherwise only the 12 candidates nearest in a straight line are routed to (`core/route_query.shortlist`) | no |
| `compute(code)` | what the Python prints: code over a copy of the building in the solver agent's sandbox (`agent/solver_agent.py`: restricted builtins, module whitelist, 30 s limit); its `route()` routes as `find_route` does (the Guide's route rules, the user's profile and closures, "here"), so code and tools never disagree; access-mode preference penalties are not applied ([D-022](../../memory-bank/decisions.md#d-022)) | no (works on a copy) |
| `compare_routes(before/after change)` | diff: rooms that lost access, extra metres | no |
| `set_profile(...)` | the active [routing profile](../product/routing-profiles.md) for this user | user state only |
| `propose_change(kind, …)` | a **pending** change (close lift, add door, move asset) + its predicted effect | no — needs confirm |
| `apply_change(change_id)` | committed edit event, broadcast to all clients | **yes** |
| `show_on_map(space_ids?, asset_ids?)` | UI event (highlight rooms and items / fly to / switch floor) | no |
| `set_my_location(place)` | the user's position ("here" from now on) + UI event `location` (the "you are here" figure) | user state only |
| `show_route_step(step)` | moves the app's step card to `step` (1-based, the card's numbering from the `[route note]`); UI event `route_step` | no |
| `open_edit_mode(request?)` | UI event `edit_mode`: the app opens its Edit mode, the Builder takes the request | no |
| `search_nearby_buildings(query)` / `route_to_building(start, building, destination)` | matches / a route in the buildings next to this one (only offered when the building has located neighbours) | no |

**Implemented (2026-10-24):** `agent/tools.py` — `BuildingSession` (private building copy, routing profile,
pending/applied changes, UI events) + `TOOL_DEFINITIONS` (Anthropic tool schemas) for building_overview, search,
locate, count_assets, room_facts, find_route, tour, reachable_rooms, solve (every benchmark kind), set_profile,
propose_change, apply_change, compare_routes, show_on_map (`space_ids` and `asset_ids`), set_my_location,
open_edit_mode, find_nearest, show_route_step, compute. Since 2026-10-25: `set_my_location(place)` makes that space the user's position and emits a
`location` event (the app moves its "you are here" figure there); every place argument then also accepts "here"
(`HERE` in `agent/tools.py`: "here", "me", "my location", …; unknown position → an error telling the model to ask).
`open_edit_mode(request?)` emits an `edit_mode` event and the app switches to its Edit mode, where the Builder
takes the request. `search_nearby_buildings(query)` and `route_to_building(start, building, destination)`
(`agent/campus.py`, [D-021](../../memory-bank/decisions.md#d-021)) are added to the tool list only when the building
has located neighbours (`BuildingSession.campus`). Errors come back as `{"error": …}` so the model can
search or ask. Profile → constraints: `min_door_width_m` and `avoid_lifts` act as closures of narrow openings /
lifts. Built on `core/navigation.py` (locate, count, find_route, tour; gold path format) and `core/solvers/`.
Tests: `tests/test_agent_tools.py`.

**Nearest place and the step card (2026-10-25):** `find_nearest(start, query, floor_id?, closed?)` takes the rooms
holding an item of kind `query` (via `locate`), else the rooms whose kind/name matches, keeps only the 12 nearest
in a straight line (`core/route_query.shortlist`), ranks the reachable ones by route length under the user's profile
plus `closed` (closures for this question only, e.g. "the lift is out of order"; also applied to the final route), routes to the nearest (one `route` event, so the map shows only that route) and
highlights it; the result is a `find_route` result with `nearest` and `next_nearest` (the next 2, each with
`about_m`). The system prompt sends "nearest/closest X" to it without asking which; it is in `PROFILE_TOOLS`
(`agent/guide.py`). While a route is followed the app sends `route_step` (the card's 0-based step) with `/chat`
and `/chat/stream` (`backend/app.py`); `Guide.route_note` turns it into a `[route note]` listing the card's steps
(`BuildingSession.route_card`) and the current one. `show_route_step(step)` (1-based, card numbering) emits a
`route_step` event `{index: step - 1}` and the app moves the card there; the prompt tells the Guide to call it
whenever it talks about another step. Test: `tests/test_route_step.py`.

`compare_routes(change_id, start?)` works on a **pending** change (current building vs the building with the
change) or an **applied** one (snapshot before vs after `apply_change`). From `start` (default: the last route's
start, else the main step-free entrance) under the user's profile it returns rooms reachable before/after, the
rooms that **lost access** as `lost_access_by_floor` (`{floor: {count, rooms}}`, uncapped; also emitted as a
`highlight` event with `style: "lost_access"`), the routes that got longer with `before_m`/`after_m`/`extra_m`
(route-model metres, longest first) and the last route's before/after. `propose_change`'s effect carries the same
impact (lost access by floor, longer routes, `max_extra_m`) plus the last route's `extra_m`, without emitting
events — so one call answers "what happens if…", and the model never counts or subtracts itself.

`propose_change` → user sees an "I understood: close *Office lift*; 3 routes get 40 m longer. Apply?" card →
`apply_change`. That is the brief's "show what it understood before it changes a plan"
([brief.md](../challenge/brief.md#directions-from-the-organisers)).

## Building Guide — behaviour contract

- **Decide, don't ask** (revised 2026-10-27). A name that fits several places goes to the nearest:
  `find_route` routes there and returns the next two as `chosen.others`, `find_nearest` ranks by walking
  distance. The Guide names the one it took in a few words and lists the others only if asked; it asks one short
  question only when nothing tells the places apart and the answer depends on it
  ([D-012](../../memory-bank/decisions.md#d-012)). Never ask where the user is if the question doesn't need it;
  once known, remember it for the session.
- **Short replies:** two or three sentences, no headings, tables or lists, no restating the question.
- **Profile once, remember always.** Infer constraints (wheelchair, trolley width, no lifts, quiet) from the
  conversation, confirm once in one line, store in the session/user profile → used by every later route
  without asking twice ([routing-profiles.md](../product/routing-profiles.md)).
- **Echo understanding in one line** (from → to, constraints, closures), then the total, the floors crossed and the
  first step only: the app shows the whole route and guides step by step
  ([D-020](../../memory-bank/decisions.md#d-020)). With the app's "you are here" figure placed, "here" is the start
  and the Guide never asks where the user is. Not in this building → `search_nearby_buildings` /
  `route_to_building` for located buildings ([D-021](../../memory-bank/decisions.md#d-021), `agent/campus.py`).
- **Directions a person can follow:** landmarks from assets/room names ("past the printers", "through the
  double door into Hall 0.02"), floor changes explicit, metres rounded. Voice gets shorter steps than text.
- **Robust to tricky users:** vague ("the printer"), wrong ("room 9.99" → nearest matches), mid-course
  changes ("actually avoid the lift"), multilingual (ElevenLabs language detection).

### Implementation — `agent/guide.py` (2026-10-24)

`Guide(session, client=None)` is one conversation: `guide.reply(text) → GuideTurn(text, tool_calls, events,
ungrounded, stop_reason)`. A manual tool-use loop over `client.beta.messages.create` (≤ 12 tool rounds per turn):
every `tool_use` block goes to `BuildingSession.call`, all results return in one user message (`is_error` on
`{"error": …}`), text written before tool calls is kept in the reply.

| Aspect | How |
|---|---|
| Model | `GUIDE_MODEL` (default `claude-opus-5-5`), `GUIDE_EFFORT` (default `medium`); thinking left at the model default (adaptive); `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`, as in `agent/llm_parser.py`. **Fast mode** (2026-10-27): `speed: "fast"` + beta `fast-mode-2026-02-01` on every Guide request (same model, faster output, 2× token price; Claude API only, Opus 5.5 / 5 / 4.8); `GUIDE_SPEED=standard` turns it off; a 429 on fast mode's own limit retries that request at standard speed. Measured on dev-004, 3 turns: 12.1–15.8 s → 7.2–7.4 s |
| Caching | system = fixed instructions + building overview (static `BuildingMap.overview()`, no profile/closures) with `cache_control`; tools render before it, so both are cached; top-level `cache_control` also caches the growing history |
| History | append-only (assistant `response.content` stored unchanged), so the cached prefix and thinking blocks stay valid |
| Confirm before edit | `apply_change` for a change proposed in the **same user turn** is refused with an error telling the model to show the summary and wait — enforced in code, not only in the prompt |
| Profile safety net | a deterministic cue detector reads every user message (wheelchair, pram, no lifts, trolley width, reset…); if the model's turn left the cue unhonoured the Guide calls `set_profile` itself, appends a one-line confirmation and, if the turn already routed, asks once for a redo. `set_profile` takes persona presets ([routing-profiles.md](../product/routing-profiles.md#implemented-presets)); tests `tests/test_profiles.py` |
| D-003 grounding | after each turn, every number and id in the reply must appear in a tool result, the overview or the user's own messages (a number counts if a known number rounds half-up to it at the same precision, or if it is the length of a list in a tool result; numbers glued to a unit like "120m" are checked; numbered-list markers and clock times ignored — ported from the v1 Guide 2026-10-24). Fails → one repair round ("[grounding check] … appear in no tool result"); anything still ungrounded is returned in `GuideTurn.ungrounded` |
| Place names | `BuildingSession.resolve` → `agent/places.py` (ported from the v1 Guide): id, asset id, exact ref/name after dropping "the / a / room", asset name, exact asset type ("the 3D printer" → the room holding it), then word search. One candidate → its id; several → `MapError` listing each as `id (name, ref, type, floor)` and telling the model to ask what tells them apart ([D-012](../../memory-bank/decisions.md#d-012)); none → near-miss names ("Did you mean …"). `find_route` / `tour` resolve their stops this way; a destination that fits 2–8 spaces returns every option with its route length, shortest first, and draws no route. Tests `tests/test_places.py` |
| No key | `make_client()` → `agent/offline_llm.py` `OfflineClient`: keyword rules choose tools, replies are composed only from tool results (demo + backend tests). `GUIDE_LLM=offline|anthropic` forces either |

Tests: `tests/test_guide.py` — a scripted fake client plays the tricky user (vague printer → ≤ 3 options;
ambiguous "the meeting room" → search → ≤ 3 options with floors; "I use a wheelchair" → `set_profile`, remembered
on the next route; "the lift is broken" → propose, same-turn apply refused, apply after "yes"; route after the
closure 124.24 m → 132.2 m via Lift 2, `compare_routes` +7.96 m), plus request shape (cached system, env model,
append-only history, every tool_use answered), the repair round, and the offline client.

**Live check (2026-10-24, `scripts/live_guide.py`, same 7 turns, train campus 000):**

| Model · effort | s / turn | $ / 7 turns | Behaviour |
|---|---|---|---|
| Opus 5.5 · medium (default) | ~5.9–7.3 (7.3 pre-fix, 5.9 post-fix) | 0.13–0.16 | all turns correct; inferred "the lift" = Lift 1 on the route; most thorough, longest replies |
| Opus 5.5 · low | ~6.8 (one pre-fix run) | 0.12 | same quality, no clear speed gain (one pre-fix run; not directly comparable) |
| Sonnet 5.5 · low | ~3.3–3.9 (3.3 pre-fix, 3.9 post-fix) | 0.06 | correct and shortest (best for voice); applied the routing-profiles wheelchair default 0.8 m door width and said so |

All runs: 0 ungrounded replies, no same-turn apply, cache reads on every request after the first. Fixed from
the first runs: lost-room list was capped at 15; a parallel `compare_routes` guessed a change id; an
unsupported "nothing upstairs" claim → impact moved into `propose_change`, two prompt sentences added. Model
choice stays open ([Q-012](../../memory-bank/open-questions.md#q-012)).

## Voice path

Per [elevenlabs.md](../research/elevenlabs.md#tldr-recommendation): ElevenLabs Agent handles STT, turn-taking,
interruptions and TTS; its **Custom LLM** points at our backend's OpenAI-compatible streaming endpoint, which
wraps the same Building Guide (one brain for text and voice) — skeleton in `backend/` (see
[commands.md](../guides/commands.md#backend-guide-api)). Map actions reach the browser as ElevenLabs
**client tools** and/or our own realtime channel. Fallback: Scribe Realtime → Guide → TTS WebSocket.
Per-building **keyterms** (room names, machine names) go to Scribe for accurate recognition.
A **transcript rewriter** normalises each STT transcript to the building's vocabulary before the Guide sees it
(original transcript passed along too); typed chat has no rewriter ([D-013](../../memory-bank/decisions.md#d-013)).
Implemented in `agent/rewriter.py`: one `claude-haiku-5-5` call (effort low, JSON schema `{rewritten}`) with the
building vocabulary as cached system prompt; `Guide.reply(..., channel="voice")` sends the model
`<rewritten>\n\n[speech transcript as heard: <original>]`, adds both to the grounding corpus and returns
`GuideTurn.rewritten`. Only with the real API client; `GUIDE_REWRITER=off` disables it, `GUIDE_REWRITER_MODEL`
overrides the model. Any doubt (API error, refusal, empty, a number in neither the transcript nor the building)
keeps the transcript as heard. Live (train campus 000): "lab two seventeen" → "Lab 2.17", "office zero oh two"
→ "Office 0.02", "the kitchen" and "the second floor" unchanged; ~1–2 s per call. Tests `tests/test_rewriter.py`.

**What the app runs today (2026-10-25):** the ElevenLabs Agent above is not wired up. The app listens with
ElevenLabs Scribe Realtime (`voice/scribe.ts`, token from `POST /stt/token`) when `/health` says `"stt": true`, with the
browser's SpeechRecognition as the fallback (`frontend/app/src/voice/useVoice.ts`), and speaks with **ElevenLabs TTS through our
backend**: `voice/tts.ts` splits the reply into sentences (short first piece, then ≤ 220-char groups), fetches each
from `POST /tts` (`backend/tts.py`: Flash v2.5, voice "River", key server-side) while the previous one plays, and
drives the orb from the audio's real level. No key, a failed request or locked audio → the browser's
speechSynthesis (a piece that fails is retried once; failing again pauses ElevenLabs for 15 s, `COOL_OFF_MS`). [D-016](../../memory-bank/decisions.md#d-016).
Live (Chrome, 3-sentence test reply): first sound 371 ms after speaking starts. Tests `tests/test_tts.py`.

**Speaking while the Guide works (2026-10-25, [D-017](../../memory-bank/decisions.md#d-017)):** on voice turns with a
listener (`Guide.on_say`, set by `/chat/stream`) the Guide streams its requests (`messages.stream`, real client only;
offline/test clients feed whole text blocks) into `agent/speech.py` `SpokenStream`: each complete sentence that
passes `ungrounded()` against the corpus so far goes out at once as a `say` line; the first ungrounded sentence, a
grounding repair or a profile redo holds live speech (a message with an unsatisfied profile cue is held from the
start), and at the end `finish(turn.text)` says what of the final reply was not said yet. `VOICE_STYLE` asks for
one short fact-free sentence before the first tool call ("Let me look up the way to the kitchen."), which is spoken
while the tools run. The app opens a voice queue on the first `say` (`voice/tts.ts` `openSpeech`; text that arrives
while a piece plays is fetched at once). Live (Opus 5.5 medium, train campus 000): first sound at 2.35 s in a turn
whose answer came at 10.4 s (6 tool calls); before, nothing was heard until the reply. The answer after the tools
arrived from the API in one burst in every traced turn, so its sentences gain little from streaming yet.
Tests `tests/test_speech.py`, `tests/test_backend.py::test_chat_stream_voice_says_sentences_before_the_reply`.

**Conversation, pauses and barge-in (2026-10-25, [D-018](../../memory-bank/decisions.md#d-018)), all in
`frontend/app/src/voice/useVoice.ts`:** recognition runs `continuous` and the utterance ends after 1.0 s without new
words (`END_PAUSE_MS`, was 1.3 s before the latency pass; 8 s with none at all after a tap), so a short pause mid-question no longer sends half of it. A spoken question
starts a conversation: from the reply's first sound (`onStart`, which can be the fact-free preamble while the turn
is still pending) a second recogniser listens while the Guide speaks (restarted after 250 ms if the browser ends it
early; aborted on speech end, `stop()`, when listening starts, or once it has fired);
`voice/bargeIn.ts` drops what is the Guide's own echo (its words, three-letter stems, numbers, single letters), and
`interruption` decides on the user's part (`userPart`): a stop word in a phrase of at most three words → "stop";
three or more own words that are at least half of what was heard → "talk"; else nothing (was: one own word of three
letters already counted, which cut the Guide off on misheard echo and room noise — tightened 2026-10-25). Results in
the first 1 s of the voice are ignored (`BARGE_GRACE_MS`), and "talk" must hold on two results in a row or a final
one. "Talk" cuts the voice and becomes the next question (their words carried over, sent after 2 s unless
more follow); "stop" (stop words: "stop", "wait", "stopp", "dur", …) just stops it. When the reply ends, the Guide
listens again by itself (after 200 ms) and ends the conversation quietly after 6 s of silence. Typed questions and walk-mode step
readings don't start a conversation. An utterance spoken while a Guide turn is still pending (for example a
barge-in over the preamble) is queued and sent once that turn is done (`building/BuildingScreen.tsx` `queued`); the
rest of the interrupted reply is not spoken. Verified in Chrome with a scripted SpeechRecognition (real UI, offline Guide, real ElevenLabs): pause
kept, echo ignored, interruption sent as "actually where is the nearest toilet", "stop" stopped, auto-listen
ended after 6 s without an error. Not verified with a real microphone and speakers (echo levels, Bluetooth).

**Scribe Realtime for the user's words (2026-10-25, [D-019](../../memory-bank/decisions.md#d-019)):** with
`/health` `"stt": true` the recogniser is `voice/scribe.ts` `ScribeRecognition`, which has the SpeechRecognition
shape: `POST /stt/token` (`backend/stt.py`) gives a single-use token plus the building's keyterms (one fetched
ahead), the mic is captured first (an AudioWorklet averages it down to 16 kHz int16, 100 ms chunks, buffered until the
socket opens) and streamed to `wss://api.elevenlabs.io/v1/speech-to-text/realtime` with `commit_strategy=manual`;
changed partials are the interim result, committed segments the finals, and `stop()` commits and waits 0.8 s (`COMMIT_WAIT_MS`) for the
last segment. The mic is opened through `voice/mic.ts` (skips virtual inputs, remembers the real one) and kept
warm for 8 s after a listen (`MIC_WARM_MS`), so the next listen starts at once; a Scribe failure still means browser
recognition for 60 s. Verified live: `keyterms` are repeated query parameters, more than 50 or longer than 20 characters are
refused (`invalid_request`); Scribe re-sends an unchanged partial about every second through silence. End to end in
Chrome (ElevenLabs-spoken "Where is the CNC mill?" as the mic, factory dev-003): first partial 0.3 s after the audio
ended, committed and sent ~1.9 s after it, answered aloud, barge-in watcher on its own Scribe session; with the token
request failing, browser recognition took over with no error. The transcript rewriter (D-013) still runs:
[Q-020](../../memory-bank/open-questions.md#q-020).

**Implemented (2026-10-24):** `Guide.reply(text, channel="voice")` — used by `/v1/chat/completions` — adds the
`VOICE_STYLE` instruction (plain spoken sentences, ≤ ~3 sentences, first 2–3 steps then offer to continue) as a
mid-conversation **system message** after the user turn on models that support it (Opus 5/5.5, Opus 4.8, Fable,
Sonnet 5.5, Haiku 5.5 — keeps the cached prefix), else as a note in the user turn; then `agent/speech.py`
`speakable()` deterministically strips markdown, list markers, ids and symbols and spells out units (it never adds
a number, so grounding holds). `GuideTurn.spoken` carries the result; the chat panel keeps the text channel.
Live (Sonnet 5.5 low, `scripts/live_guide.py --channel voice`): 7 turns, ~3 s/turn, $0.054, 0 ungrounded, no ids
or markdown in speech. Tests: `tests/test_speech.py`. Still open: ElevenLabs account wiring (session id, system
tools) — needs the public deploy.

## Benchmark pipeline

```
question text ─► template parser ──ok──► solver(kind, params) ─► formatter ─► reply + "Answer: …"
                     │ fail                        ▲
                     └► LLM extractor (strict schema) ┘  (resolved + validated in code)
```

Implemented: `agent/benchmark_agent.py` (`answer()` for `benchmark.evaluate --agent`) and `agent/run_benchmark.py`
(second test CLI; the submission uses `agent/run_benchmark_v1.py`, [BENCHMARK.md](../../SUBMISSION/BENCHMARK.md)). Dev 138/138 end to end. Warm-up kinds (locate, count,
route, step-free, closure, tour) parse via `core/basic_parser.py` → `core/navigation.py`: 2120/2130 train+dev
from text, 100% with gold ids (`scripts/validate_warmup.py`).

Parser evidence and accuracy: [question-parsing.md](../research/question-parsing.md) ([Q-008](../../memory-bank/open-questions.md#q-008)).
Solvers: [solver-plan.md](solver-plan.md). The same solvers back the Guide's `room_facts` / `find_route` tools,
so benchmark work directly improves the product.

### Parser modes

Set with `PARSER_MODE` ([D-007](../../memory-bank/decisions.md#d-007)).

| Mode | Behaviour | Use for |
|---|---|---|
| `hybrid` (default) | regex template first; LLM (`agent/llm_parser.py`) only if no template matches or a slot doesn't resolve | benchmark + Sunday |
| `regex` | deterministic only; unknown wording → `ParseError` | reproducibility checks |
| `llm` | LLM only | robustness experiments, conversational input |
| `crosscheck` | both; keep regex result, note `agree` / `disagree` | measuring the LLM parser |

Why regex stays first even though credits don't matter: on template wording it is **provably** 100% (655/655),
**reproducible** (judges may re-run our command and get identical output), and instant. The LLM can at best
tie there, and is non-deterministic. Where the LLM wins is wording the templates don't cover — so it is the
fallback, not the default. Both paths share one `Resolver`: the LLM returns raw slot text chosen from the
building's vocabulary (never ids or numbers), code resolves it, and a resolution error is sent back once for
correction. Measure live with `scripts/eval_llm_parser.py [--paraphrase]`.

### Sunday layers: route specs, solver agent, decision cache (2026-10-25)

The submission pipeline (`agent/answer.py` → `agent/run_benchmark_v1.py`) now has three layers after the
templates, so unseen wording, combined constraints and new kinds get an answer instead of a near-miss kind:

```
question ─► regex templates ──ok──────────────────────────────► v1 solver ─► reply + "Answer: …"
              │ fail                                                ▲
              ▼                                                     │
            LLM slots (agent/llm_parser.py, asks_for + kind) ──────┤  warm-up kinds when the spec is simple
              │ route spec with combined constraints ─► core/route_query.py (canonical core.navigation)
              │ kind `other`, asks_for ≠ kind, never resolves, solver error
              ▼
            solver agent (agent/solver_agent.py): python sandbox over the building + submit_answer,
            2 runs (+1 tie-break), majority; the Answer: line is written by code
every model decision ─► decision cache (agent/llm_cache.py, llm_cache/decisions.json) ─► replayed on re-runs
```

- **Route spec** (`route` kind in the LLM schema): start, destination, ordered stops; each place a room name, a
  room type ("the nearest toilet") or an item ("a forklift charging station" → the room of the nearest one);
  constraints combine freely: `step_free`, `forklift`, `min_width_m`, `closures` (lifts, stairs, rooms, corridors,
  doors). A spec that is exactly a warm-up kind keeps that kind and its v1 solver (answers unchanged); anything
  richer is `route_query` on `core.navigation`, which reproduces every warm-up route answer
  (`tests/test_navigation.py`).
- **`asks_for`**: what the question wants back (room, item_location, area_m2, count, distance_m, route, other). A
  kind that cannot answer it, or kind `other`, raises `NeedsAgent`.
- **Solver agent**: Opus 5.5 at effort `medium` (`SOLVER_AGENT_EFFORT`); tools `python` (restricted builtins, module whitelist, 30 s limit, a
  deep copy of the building per run; helpers `route`, `place`, `spaces`, `area`, `solve` over the canonical core)
  and `submit_answer` (number / space / no_route / text, validated). Two independent runs, a third when they
  disagree, majority wins (`SOLVER_AGENT_RUNS`, `SOLVER_AGENT=off`).
- **Decision cache**: the parser's slots and the agent's submission (with the code it ran), keyed by the building's
  content hash, the question text and a schema version. Re-running the command — also without an API key, as the
  organisers may — replays them and reproduces `answers.json`; numbers are recomputed by code from replayed slots.
  `LLM_CACHE=off` asks the model again; `parser` in `answers.json` says `llm-cache` / `agent-cache` on replay.
- **Probe**: `scripts/eval_sunday_probe.py` runs `tests/sunday_probe/*.json` (reworded questions, new constraints,
  new kinds; expected answers computed by direct code) through this path and scores them.

## Deterministic vs adaptive — the split

The brief asks for a "mostly deterministic" core. Our rule for which side does what:

| Deterministic (code, `core/`) | Adaptive (Claude) |
|---|---|
| every number, id, route, count, area, distance | understanding the request (parsing, intent, references like "the printer", "it", "there") |
| graph, costs, profiles, closures, edits applied | deciding what to ask when the request is ambiguous or a constraint is missing |
| the final `Answer:` line | explaining *why* (route choice, what a closure changes) in plain words |
| validation of every edit before it is applied | choosing landmarks / phrasing for directions; language; voice brevity |
| benchmark output (reproducible) | Builder: proposing rooms/doors from a plan image (then validated by code) |

So the answer is always correct-by-construction, and the agent's job is to get the *right question* into the
solver and the *answer* back to the person in a form they can use. When the agent and a tool disagree, the
tool wins.

## Builder (Level 4)

Edit mode design (step 1 of the Builder): [builder-edit-mode-design](../superpowers/specs/2026-10-24-builder-edit-mode-design.md).
**Milestone 1 implemented (2026-10-24, branch `2-builder-edit`):** Edit button on the building screen (Atahan's
new UI, merged from `dev`); drag corners (shared walls stay shared), doors along walls and assets on a 2D plan with
the 3D `PlanView` of the draft as a live inset; undo; validator issues
in red (pre-existing issues of the original are warnings); save as `user/<slug>`, then the Guide routes in it.
Code: `core/edits.py`, `core/validate.py`, `backend/drafts.py` + `/drafts`, `frontend/app/src/edit/`. **Milestone 2 implemented (2026-10-24):** prompt edits — the Builder agent (`agent/builder.py`,
`agent/builder_tools.py`, offline `agent/builder_offline.py`; `BUILDER_MODEL` default `claude-opus-5-5`) proposes
op lists with `propose_edit` (dry run, area effect, new problems), never applies; the Edit mode's chat shows the
proposal as a ghost on the plan with Apply / Cancel, a plain "yes" also applies; hand edits drop an open proposal
(stale ones are refused server-side). Live (Opus 5.5 medium, `scripts/live_builder.py`): move a machine 7.6 s, add a
door 13.1 s, an ambiguous "widen the lab into the next room" asked which side (5.4 s), then proposed `move_edge` and
flagged the sink left outside (6.9 s); 0 ungrounded; ~$0.02–0.04 per turn. A proposal is open for one exchange
only (the next message or Apply); another turn, Cancel or a hand edit closes it, and only a bare "yes"/"ok" applies
without the model. **Milestone 3 built (2026-10-24, deploy pending):** with `SUPABASE_DB_URL` drafts, saved buildings
and the Builder's conversation live in Postgres (`builder_drafts`, `saved_buildings`), so any serverless instance
serves any request — a proposal made on one instance can be applied on another; each person edits their own draft,
concurrent writes are version-checked (409); saved buildings are shared with everyone
([milestone 3 plan](../superpowers/plans/2026-10-24-builder-edit-mode-m3.md)). Plan images (project 2): the Creator agent, [design](../superpowers/specs/2026-10-25-plan-import-design.md) and [plan](../superpowers/plans/2026-10-25-plan-import.md) (in progress, 2026-10-25).

1. Upload plan image (PNG/PDF page) or describe changes by conversation.
2. Claude vision drafts `floors`/`spaces`/`openings` in our schema (scale from a known dimension the user gives
   or a scale bar).
3. **Validator in code:** valid polygons, no overlaps, every opening lies on a shared wall, every room reachable
   from an entrance, connectors link existing spaces. Errors go back to the model (loop ≤ N times).
4. Render the draft over the image; user confirms or corrects by chat ("the door is on the north wall").
5. Measure on our own data: rebuild train buildings from `floor_*_plain.png` and compare to `building.json`
   (room count, area error, connectivity) — a measurable L4 score.

### Creator — plans → building (`agent/creator.py`, 2026-10-25)

[Design](../superpowers/specs/2026-10-25-plan-import-design.md) · [plan](../superpowers/plans/2026-10-25-plan-import.md).
Upload PDFs / photos / scans (HEIC too) → the Creator, a Claude tool loop (`CREATOR_MODEL`, default
`claude-opus-5-5`, `CREATOR_EFFORT` medium) over the deterministic stages in `core/plan_import/`, builds the whole
building without asking anything; the result opens as a draft on a private base `import/<id>` and the Builder above
corrects it. Code does all geometry (wall mask → cells → doors, colour separators, scale, stacking); the model reads
the drawings (which page is which floor, what each numbered cell is, names from legends and signs) and looks at its
own overlays. Fallbacks it chooses itself: colour segmentation, `add_rooms` (cut merged rooms out, or add open rooms
with cell 0), coarse boxes per room (marked `low_confidence`). Stairs / lifts join floors by name, then distance;
floors that would stay unconnected get their nearest pair (`synthetic: true`). Import notes (scale method, segmentation,
alignment, carved rooms) are kept in `building.source_ref.import`.

Measured (live, Opus 5.5 medium, 2026-10-25): `eval_import.py --full --n 8` on dataset renders — median room-count
ratio 0.97, median IoU 0.91, median door pairs found 89 %, 6/8 runs without errors, ≈ $1.09 for all 8 (16–152 s each;
weakest: a 71-room OSM basement, 21 % of doors). Urban Colab escape-plan photos (11 HEIC originals): 5 floors / 104
spaces, all floors joined by real stairs + lift, 23 errors left (13 doors off a shared wall, 7 unreachable, 3 overlaps)
for the Builder to fix, 766 s, ≈ $1.73. Residenz brochure PDF: 2 floors / 56 spaces / 0 errors, 174 s (coarse boxes,
legend names). Rathaus 1900s drawing: 59 spaces / 0 errors, 139 s, ≈ $0.35. Projektsteckbrief (text + landscape plans):
`no_plan` in 10 s. Segmentation alone (no model) on 30 renders: median IoU 0.40 — the Creator's labelling and fixes take
it to 0.91. Cost lesson: keep the prompt prefix stable (an earlier version dropped one image per turn and paid ≈ $4.4
of ≈ $4.8 per Urban Colab run in cache writes).

## Budget

$150 Claude credits ([Q-012](../../memory-bank/open-questions.md#q-012)). Benchmark runs are ~free once the
parser + solvers are deterministic; spend goes to Guide conversations, Builder vision calls and dev agents.
Cache the building overview in the system prompt; keep tool results compact.

## Related
- [overview.md](overview.md) · [solver-plan.md](solver-plan.md) · [routing-profiles.md](../product/routing-profiles.md) · [Phase 3 Guide design](../superpowers/specs/2026-10-24-guide-agent-design.md)
