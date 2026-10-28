# "Nearest X" routes show their Start card: find_nearest no longer highlights after the route

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-28 17:30
- **Related:** D-020 (route card + Start), Utku: "sometimes it says press Start and nothing appears"

## Summary
`find_nearest` emitted a highlight after its route event; the app keeps only the latest route/highlight answer, so
the route (and its Start card) vanished for every "nearest X" request. The highlight is gone (the route event
already focuses the destination room).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `tool_find_nearest` and `nearest_item` no longer call `self.highlight` after routing; nothing else in them changed | `agent/tools.py` | `git diff --cached agent/tools.py` |
| C2 | The app keeps only the latest route/highlight event as the answer, and a route event focuses its last space — so the removed highlight was redundant and replaced the route | `frontend/app/src/dev/story.ts` `applyEvents` | read |
| C3 | New test: `find_nearest` for a room kind ("meeting room" → `tool_find_nearest`'s own room path) and an item ("whiteboard" → `nearest_item`; in this building "toilet" is an item too) leaves exactly one route/highlight event, the route; it fails on HEAD's `agent/tools.py` for both queries (`['route', 'highlight']`) | `tests/test_guide_sunday_tools.py::test_nearest_leaves_the_route_as_the_last_answer` | `uv run pytest -q tests/test_guide_sunday_tools.py` |
| C4 | Full test suite passes; no new ruff findings | — | `uv run pytest -q`; `uv run python scripts/ruff_new.py` |
| C6 | ai-agents.md no longer says find_nearest highlights: tool-table row and the "Nearest place" paragraph say one route event that focuses the room, no highlight | `docs/architecture/ai-agents.md` | `grep -n highlight docs/architecture/ai-agents.md` |
| C5 | Log entry 2026-10-28 17:30 (cause, fix, live evidence, Vercel rename + URL); project-state git section has the production URL | `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` |

## Checks I ran
- Live (OpenAI, proc-campus-train-000), before the fix: "Take me to the kitchen." → tools `['find_nearest']`, events `['route', 'highlight']`; "I need to print something." and "how do I get to the nearest toilet?" the same; `find_route` turns → events `['route']`.
- Red: `AssertionError: ('toilet', ['route', 'highlight'])`. Green after the fix.
- `uv run pytest -q tests/test_guide_sunday_tools.py tests/test_guide.py tests/test_guide_tools.py tests/test_places.py tests/test_guide_loop.py` → `60 passed`.
- `python3 scripts/check_links.py` → OK.

## Knowledge base updates
- [x] `memory-bank/project-state.md` (production URL)
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none
- [x] docs: `docs/architecture/ai-agents.md` (find_nearest row in the tool table, "Nearest place and the step card" paragraph: one route event, no highlight)

## Known gaps / not done
- Not yet checked on production (after the push).
- A route request with no known start still gets a question, not a card (expected).
- Three deferred MINOR findings on dae9d7c still open.

## Verification rounds
- round 1: verifier FAIL (C3: "toilet" is an item here, so the room path had no test — fixed with "meeting room"; red on HEAD for both queries checked in a scratch worktree), reviewer PASS (no findings)
- round 2: verifier FAIL (ai-agents.md still said find_nearest highlights — fixed, C6), reviewer PASS (no findings)
- round 3: verifier PASS, reviewer PASS (no findings)

## Verifier report (round 3)

VERDICT: PASS
TREE: 552f138c0e576e8402bffcc9ebcc45f4af0ee94f

C1–C6 MET: two hunks in agent/tools.py remove the highlight after the route; applyEvents lets a later highlight replace the route; the test is red on HEAD for "meeting room" (room path) and "whiteboard" (nearest_item) and green staged; ai-agents.md updated; log + project-state URL. Standard checks: pytest 1062 passed, 2 skipped; links OK; ruff new 0; secrets none; score.py unchanged.

## Reviewer report (round 3)

REVIEW: PASS
TREE: 552f138c0e576e8402bffcc9ebcc45f4af0ee94f

No findings. Also noted: during tracking, a one-room highlight counts as a position fix (BuildingScreen), so the old highlight could also drop a "nearest X" route while tracking; removed with it.
