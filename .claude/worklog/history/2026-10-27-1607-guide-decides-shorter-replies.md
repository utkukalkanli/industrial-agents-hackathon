# Guide decides instead of asking: nearest of several destinations, shorter replies (D-012 revised)

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-27 16:07
- **Related:** D-012 (revised by Utku, 2026-10-27: "daha az soru ve daha kısa cevap istiyorum")

## Summary
The Guide asked too much and talked too long. `find_route` to a name that fits several places now routes to the
nearest reachable one (listing the next two) instead of returning an "ambiguous" error, the Guide prompt says
decide rather than ask and keep replies to two or three sentences, and a grounding false positive
("step-by-step" read as an id) is fixed.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `tool_find_route`: a destination that fits several places routes to the nearest reachable option (from `destination_options`, shortest first) and adds `chosen` = {note, others: next ≤2 reachable options}; it returns the old error+options dict only when no option is reachable; a single match behaves as before | `agent/tools.py` `tool_find_route`, `destination_options` (now also returns `destination`) | read; `uv run python -m pytest -q tests/test_places.py` |
| C2 | `find_route` tool description mentions the nearest choice and `chosen` | `agent/tools.py` TOOL_DEFINITIONS find_route | read |
| C3 | Guide prompt: the "Ask only what changes the answer" bullet is replaced by "Don't ask; decide" (take the nearest, name it in a few words, list others only if asked, ask only when nothing tells places apart and the answer depends on it, no offers); directions bullet no longer asks for a from→to echo line; last bullet is "Be short: two or three sentences…" | `agent/guide.py` INSTRUCTIONS | read |
| C4 | Grounding `IDENTIFIER` regex needs a digit, so hyphenated words ("step-by-step") are not flagged; ids like `x-F3-S008` still are | `agent/guide.py` IDENTIFIER; `tests/test_guide.py::test_ungrounded_rules` | `uv run python -m pytest -q tests/test_guide.py -k ungrounded` |
| C5 | Tests updated to the new behaviour: tricky-user conversation's vague meeting-room turn routes to the nearest with 2 `chosen.others`, no question; places test checks route to nearest + `chosen.others`; conversation fixture `printers_two_rooms.json` turn 2 expects `asked: false`, `route_to` F1-S014 | `tests/test_guide.py`, `tests/test_places.py`, `tests/guide_conversations/printers_two_rooms.json` | `uv run python -m pytest -q tests/test_guide.py tests/test_places.py tests/test_guide_conversations.py` |
| C6 | `scripts/eval_guide.py` `routes()` counts reachable `find_nearest` results too (it routes to what it finds); docstring updated | `scripts/eval_guide.py` | read |
| C7 | Docs: D-012 marked revised 2026-10-27 with the new Guide rule; ai-agents.md behaviour contract "Decide, don't ask" + "Short replies"; log entry 2026-10-27 16:07; project-state header, Guide paragraph and Next priorities item 0 updated (fast-mode Guide in production) | `memory-bank/decisions.md`, `docs/architecture/ai-agents.md`, `memory-bank/log.md`, `memory-bank/project-state.md` | read; `uv run python scripts/check_links.py` |

## Checks I ran
- `uv run python -m pytest -q -k "not live"` (before the grounding regex change) → `1040 passed, 6 deselected`
- `uv run python -m pytest -q tests/test_guide.py tests/test_places.py tests/test_guide_conversations.py` (after all changes) → `30 passed`
- `LLM_CACHE=off uv run --env-file .env python scripts/eval_guide.py` (live, Opus fast) → `18/18 turns PASS, 44.9s, total cost ~$0.1575`
- Live samples (dev-001): "Take me to the meeting room" from the main lobby → find_nearest, "nearest meeting room, Meeting room 0.03 … about 10 m", no question.
- `uv run python scripts/check_links.py` → `OK: all links resolve in 39 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: D-012 revised
- [x] docs touched: `docs/architecture/ai-agents.md`

## Known gaps / not done
- Not deployed yet (preview, then the user promotes).
- `places.problem` text (still "Ask the user which one") is unchanged: the Builder uses it and should still ask; the Guide only sees it now when a start is ambiguous or no destination option is reachable.
- The full suite was not re-run after the IDENTIFIER regex change; only the Guide/places/conversation tests and the live eval were.

## Verification rounds
- Round 1: PASS (commit-verifier; full suite re-run by the verifier after the IDENTIFIER change → 1040 passed, 6 deselected)

## Verification report (round 1)
VERDICT: PASS
TREE: 99058dd5751bd1a8582bab13f14678e1045f3559
C1–C7 MET. pytest -k "not live" → 1040 passed, 6 deselected; tests/test_guide.py tests/test_places.py tests/test_guide_conversations.py → 30 passed; check_links OK (39 files); no secrets staged; score.py unchanged; no hard-coding (only a dev-building id in a test fixture). Not re-run: live eval_guide.py (paid). Undeclared: the prompt no longer asks which room when items sit in several rooms (part of C3).
