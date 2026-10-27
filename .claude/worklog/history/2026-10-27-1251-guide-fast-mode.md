# Guide on Opus fast mode (GUIDE_SPEED), standard-speed retry on its rate limit

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-27 12:51
- **Related:** user request "make the model calls fast"; docs/architecture/ai-agents.md (Guide model row)

## Summary
Measured where a Guide turn's time goes (model calls; caching already hits) and turned on Opus fast mode for every
Guide request: same model, faster output, 2× token price. `GUIDE_SPEED=standard` turns it off; a 429 on fast mode's
own rate limit retries that request at standard speed. Also a cosmetic whitespace fix in `agent/places.py`.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | With a real `anthropic.Anthropic` client, a model in FAST_MODELS (opus 5.5 / 5 / 4.8) and `GUIDE_SPEED` unset or `fast`, every Guide request sends `speed: "fast"` and betas `[server-side-fallback-2026-07-01, fast-mode-2026-02-01]`; everything else in the request is unchanged | `agent/guide.py` (`FAST_BETA`, `FAST_MODELS`, `Guide.__init__` `self.fast`, `request`) | `uv run pytest -q tests/test_guide.py -k fast_mode` |
| C2 | A `RateLimitError` on the fast request retries the same request once without `speed` and without the fast beta | `agent/guide.py` (`request`) | `tests/test_guide.py::test_guide_asks_for_fast_mode_and_falls_back_to_standard_on_its_rate_limit` |
| C3 | `GUIDE_SPEED=standard` sends no `speed`; offline/test clients (not `anthropic.Anthropic`) never get fast mode | `agent/guide.py` | `::test_guide_speed_standard_turns_fast_mode_off`; the existing offline Guide tests still pass |
| C4 | Streaming/non-streaming dispatch moved into `Guide.send` unchanged; `track` counts `fast_requests` from `usage.speed` | `agent/guide.py` (`send`, `track`, `Usage.fast_requests`) | read the diff |
| C5 | Docs: ai-agents.md Guide model row (fast mode, measurement), commands.md `GUIDE_SPEED`; log entry | `docs/architecture/ai-agents.md`, `docs/guides/commands.md`, `memory-bank/log.md` | read; `uv run python scripts/check_links.py` → OK |
| C6 | `agent/places.py`: `named =[` → `named = [` only | `agent/places.py` | `git diff --cached agent/places.py` |
| C7 | Full suite green | all | `uv run pytest -q` |
| C8 | project-state.md records fast mode (Guide bullet), the Haiku/Sonnet comparison, and the deploy / zip next steps | `memory-bank/project-state.md` | read the diff |

## Checks I ran

- Live probe (Claude API): `speed="fast"` with `fallbacks="default"` and both betas → accepted, `usage.speed = fast`, 0.80 s vs 1.65 s standard (one 15-token answer).
- Live Guide with Haiku 5.5 (low 10.43–11.58 s, medium 11.41 s) and Sonnet 5.5 low (12.77 s), same 3 questions, standard speed: not faster than Opus fast.
- Live Guide, dev-004, the same 3 questions, two runs each: standard `[6.24, 3.54, 6.02]` = 15.8 s and `[5.37, 3.35, 3.42]` = 12.14 s; fast `[3.18, 2.05, 2.01]` = 7.24 s and `[3.17, 2.1, 2.17]` = 7.44 s; fast runs: 7 of 7 requests `fast`.
- Before the change, live: 3 turns read 14–18k cached input tokens each, 6–8 uncached (prompt cache hits).
- `uv run pytest -q tests/test_guide.py -k fast_mode` → `2 passed`
- `uv run pytest -q` → `1044 passed, 2 skipped, 18 warnings in 269.12s`
- `uv run python scripts/check_links.py` → `OK: all links resolve in 39 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (Last updated line, Building Guide bullet: fast mode + timings, Next priorities item 0)
- [x] `memory-bank/log.md` entry added (12:51)
- [x] decisions / open questions touched: none
- [x] docs touched: ai-agents.md, commands.md

## Known gaps / not done
- Fast mode costs 2× per token on every Guide request (the user asked for it).
- The Builder, Creator, LLM parser and solver agent still run at standard speed.
- The voice transcript rewriter (Haiku, 1.3–1.9 s per voice turn) is unchanged; fast mode is Opus-only.
- A 429 raised mid-stream after spoken text was fed would replay the request at standard speed (speech may repeat); in practice the 429 comes before the stream opens.
- `.vercelignore` (`*.zip` added) is untracked, so it is not in this commit.
- The new fast-mode tests were written with the change, not run against the old code first.

## Verification rounds
- Round 1: FAIL — project-state.md not updated for the default behaviour/cost change
- Round 2: PASS (tree aaf123b61f839eddd510b514a61c9edeac2feb55)

## Fix round 1 (implementer)
- project-state.md: Last updated line, Building Guide bullet (fast mode, timings, Haiku/Sonnet comparison), Next priorities item 0.

---

# Verification

## Round 1

VERDICT: FAIL
TREE: 89591f7585eb450d4de716c4de1601fd5fcbefa8

C1–C7 MET; pytest 1044 passed, 2 skipped; links OK; no secrets. Required: memory-bank/project-state.md must record
the default behaviour/cost change (fast mode).

## Round 2

VERDICT: PASS
TREE: aaf123b61f839eddd510b514a61c9edeac2feb55

C1–C8 MET. pytest 1044 passed, 2 skipped; links OK (39 files); no secrets; score.py unchanged; no hard-coding.
Notes: httpx2 comes in through anthropic; the 429 fallback catches any RateLimitError on a fast request.
