# Route replies: "found it, press Start", no route summary (D-020 revised)

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-28 15:00
- **Related:** D-020 (revised), D-012

## Summary
Utku: the Guide summarised the whole route in chat; one sentence is enough. The directions rule in the Guide's
text and voice instructions and the `route_to_building` tool description now say: name the place found, then
"Press Start or say "start" to begin the guide." — no steps, distance or floors unless asked.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `INSTRUCTIONS` directions bullet: no steps, distance or floors; one short sentence naming the place (which one if several fit; a constraint or closure that changed the route in a few words), then "Press Start or say "start" to begin the guide."; distances/floors/steps only when asked. The [route note] / show_route_step sentence is kept. | `agent/guide.py` INSTRUCTIONS | `git diff --cached agent/guide.py`; `uv run python -c "import agent.guide as g; print(g.INSTRUCTIONS)"` |
| C2 | `VOICE_STYLE` directions sentence says the same (found the place, say "start"); the rest of the string unchanged in meaning (only re-wrapped) | `agent/guide.py` VOICE_STYLE | diff |
| C3 | `route_to_building` description no longer asks for totals and first steps | `agent/tools.py` CAMPUS_TOOLS | diff |
| C4 | D-020 marked revised 2026-10-28 with the new rule; ai-agents.md bullet updated; log entry 2026-10-28 15:00 | `memory-bank/decisions.md`, `docs/architecture/ai-agents.md`, `memory-bank/log.md` | read; `python3 scripts/check_links.py` |
| C6 | When no route was found (unreachable, closed) the Guide says so and why from the tool result and doesn't mention Start (INSTRUCTIONS and VOICE_STYLE); D-020 says the same; nested quotes in the docs/log/decision written as 'start' | `agent/guide.py`, `memory-bank/decisions.md`, `docs/architecture/ai-agents.md`, `memory-bank/log.md` | diff |
| C7 | Asked-for distances are still given as about_m, never the exact length_m (the old clause, kept) | `agent/guide.py` INSTRUCTIONS | diff |
| C5 | Full test suite passes; no new ruff findings | — | `uv run pytest -q`; `uv run python scripts/ruff_new.py` |

## Checks I ran
- Live on OpenAI (`LLM_PROVIDER=openai`, building `data/train/proc-campus-train-000`): "I'm in Corridor 0.01. Take me to Kitchen 3.23." → "I found Kitchen 3.23. Press Start or say “start” to begin the guide."; "Kitchen 3.23 odasındayım, en yakın tuvalete götür beni." → "En yakın tuvalet olan Toilet 3.21’i buldum. Rehberi başlatmak için Start’a bas veya “start” de."
- `uv run pytest -q tests/test_guide.py tests/test_guide_loop.py tests/test_speech.py tests/test_access.py tests/test_guide_sunday_tools.py` → `64 passed`.
- `python3 scripts/check_links.py` → `OK: all links resolve in 39 files`.

## Knowledge base updates
- [ ] `memory-bank/project-state.md` — not needed (prompt wording; D-020 and log carry it)
- [x] `memory-bank/log.md` entry added
- [x] decisions: D-020 revised
- [x] docs: `docs/architecture/ai-agents.md`

## Known gaps / not done
- Prompt behaviour has no automated test (live LLM only; tests use scripted clients). Checked by two live calls.
- The interaction eval's "directions" rubric may score these replies lower (noted in the log).
- Three deferred MINOR findings on dae9d7c still open.

## Verification rounds
- round 1: verifier stopped (tree changed), reviewer PASS (MINOR R1 no-route case, R3 nested quotes — fixed; R2 search reply distance — left: distance there is about the neighbour building, not the route)
- round 2: verifier stopped (tree changed), reviewer PASS (MINOR R1: about_m rule dropped — restored)
- round 3: verifier PASS, reviewer PASS (no findings)

## Verifier report (round 3)

VERDICT: PASS
TREE: 074608de21ee7530f4a8c15cddb80c8c7c040bba

| # | Status | Evidence |
|---|---|---|
| C1 | MET | INSTRUCTIONS directions bullet: no steps, distance or floors; one sentence naming the place, then "Press Start or say "start" to begin the guide."; [route note] sentence kept. |
| C2 | MET | VOICE_STYLE: found the place, say "start" (if no route was found, say why instead); rest only re-wrapped. |
| C3 | MET | agent/tools.py:1007 route_to_building: "say which building and place you found, not the route." |
| C4 | MET | D-020 revised 2026-10-28; ai-agents.md bullet; log entry 2026-10-28 15:00; check_links OK. |
| C6 | MET | no-route clause in INSTRUCTIONS, VOICE_STYLE, D-020; nested quotes as 'start'. |
| C7 | MET | "(distance as about_m, "about 85 m", never the exact length_m)". |
| C5 | MET | `uv run pytest -q` 1061 passed, 2 skipped; ruff_new 0 new findings. |

Standard checks: pytest 1061 passed; links OK; ruff new 0; secrets none; score.py unchanged; hard-coding none.

## Reviewer report (round 3)

REVIEW: PASS
TREE: 074608de21ee7530f4a8c15cddb80c8c7c040bba

No findings. Reviewed the staged diff, NextMove.tsx / BuildingScreen.tsx (Start command exists, "start"/"başla"); 64 targeted tests passed; no test depends on the old wording.
