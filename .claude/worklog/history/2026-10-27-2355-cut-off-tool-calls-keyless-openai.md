# Cut-off tool calls never reach the history; keyless OpenAI client reports `auth`

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-27 23:50
- **Related:** D-024, commit 9de6162 (reviewer findings R1–R4 and verifier notes in
  `.claude/worklog/history/2026-10-27-2350-openai-provider-ruff-code-reviewer.md`)

## Summary
Fixes the code-reviewer's non-blocking findings on 9de6162 (Utku asked for all of them in one commit): a reply cut
off by the token limit no longer leaves a tool call in the history (or runs it) in any agent loop; an OpenAI client
without a key builds and fails its first request as a readable `auth` error; a test isolation fix, a docstring and
the commands.md env rows.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `llm_client.kept_content(response)` returns the content unchanged unless `stop_reason == "max_tokens"`; then without tool_use blocks, or a placeholder text block if nothing is left | `agent/llm_client.py:kept_content` | `uv run pytest -q tests/test_openai_llm.py -k kept_content` |
| C2 | the Guide, Builder, Creator and solver agent append `kept_content(...)` to their history and take tool calls only from it | `agent/guide.py` (run), `agent/builder.py` (run), `agent/creator.py` (run), `agent/solver_agent.py` (run_once) | read diffs; `uv run pytest -q tests/test_guide.py -k dangling tests/test_creator.py -k cut_off` |
| C3 | a Guide reply cut off mid tool call: the turn says it was cut off, and the next request has no tool_use and no empty assistant message | `tests/test_guide.py:test_a_reply_cut_off_mid_tool_call_leaves_no_dangling_call` | run it |
| C4 | the Creator does not run a tool call cut off by the token limit | `tests/test_creator.py:test_a_tool_call_cut_off_by_the_token_limit_is_not_run` | run it |
| C5 | `OpenAIClient()` without `OPENAI_API_KEY` builds; its first request raises `anthropic.AuthenticationError`, which `backend.service_errors.code_of` maps to `auth` | `agent/openai_llm.py:MissingKey`, `OpenAIClient.__init__` | `uv run pytest -q tests/test_openai_llm.py -k without_an_openai_key` |
| C6 | the Builder provider test clears `GUIDE_LLM` first (R3) | `tests/test_openai_llm.py:test_the_builder_uses_the_provider_guide_llm_names` | read |
| C7 | `openai_llm.py` docstring: `OPENAI_SERVICE_TIER` sends another tier ("default" = standard speed) (R4) | `agent/openai_llm.py` module docstring | read |
| C8 | commands.md env rows: `ANTHROPIC_API_KEY` only for provider `anthropic`; `OPENAI_API_KEY` is the default provider's key, missing → `auth` error | `docs/guides/commands.md` (Vercel env table) | read |
| C9 | log entry for this chunk | `memory-bank/log.md` (2026-10-27 23:45) | read; `python3 scripts/check_links.py` |

## Checks I ran

- New tests red before the fix: `tests/test_guide.py`, `tests/test_creator.py`, `tests/test_openai_llm.py -k "cut_off or
  dangling or kept_content"` → `3 failed, 1 passed`; `-k "without_an_openai_key or builder_uses"` → `1 failed,
  1 passed` (the keyless client).
- After: `tests/test_guide.py tests/test_creator.py tests/test_openai_llm.py tests/test_builder*.py
  tests/test_solver_agent.py` → `74 passed`; `tests/test_openai_llm.py` → `14 passed`.
- `uv run pytest -q -p no:cacheprovider` → `1060 passed, 2 skipped, 18 warnings in 281.12s`
- `uv run python scripts/check_links.py` → `OK: all links resolve in 39 files`
- `uv run python scripts/ruff_new.py` after staging → first `1 new finding` (RUF100 unused `noqa` on a test lambda →
  turned into a nested `def`), then `0 new finding(s)`, exit 0; `tests/test_guide.py -k dangling` passes again.

## Knowledge base updates
- [x] `memory-bank/project-state.md`: not needed — no new capability or next step; behaviour fix inside D-024
- [x] `memory-bank/log.md` entry added (23:45)
- [x] decisions / open questions touched: none (fixes within D-024)
- [x] docs touched: `docs/guides/commands.md`

## Known gaps / not done
- Whether the OpenAI Responses API really refuses a `function_call` without output (the reviewer's 400) was not
  checked live; the fix removes the case for both providers either way.
- `kept_content` drops every tool call of a cut-off reply, including complete ones before the cut: none of them
  would get a result in that turn anyway.
- Benchmark still not re-measured on OpenAI; `OPENAI_API_KEY` not yet in Vercel (unchanged from 9de6162).

## Verification rounds
- round 1: verifier PASS, reviewer PASS

---

# Verifier report (round 1)

VERDICT: PASS
TREE: c3d9e33a6bdc748a511969aeddd035bb94c5ead7

## Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | `agent/llm_client.py` `kept_content`: `list(response.content)` unless `stop_reason == "max_tokens"`; then tool_use blocks dropped, `[{"type":"text","text":"(cut off by the token limit)"}]` if empty. `test_kept_content_drops_tool_calls_of_a_cut_off_reply` passed |
| C2 | MET | `agent/guide.py:576`, `agent/builder.py:215`, `agent/creator.py:133`, `agent/solver_agent.py:358` append `kept_content(response)` and build `uses` from `content`; `pytest tests/test_guide.py -k dangling tests/test_creator.py -k cut_off` → 2 passed |
| C3 | MET | `test_a_reply_cut_off_mid_tool_call_leaves_no_dangling_call` passed (asserts "cut off", no tool_use next request, no empty assistant message) |
| C4 | MET | `test_a_tool_call_cut_off_by_the_token_limit_is_not_run` passed |
| C5 | MET | `MissingKey.create` raises `openai.AuthenticationError` (401); `OpenAIClient.__init__` catches `openai.OpenAIError` → `MissingKey`; `httpx`/`REQUEST` exist (lines 31, 42); `test_without_an_openai_key_the_client_builds_and_requests_fail_as_auth` passed, asserts `code_of(...) == "auth"` |
| C6 | MET | `test_the_builder_uses_the_provider_guide_llm_names` delenvs `LLM_PROVIDER` and `GUIDE_LLM`; passed |
| C7 | MET | docstring: `OPENAI_SERVICE_TIER sends another tier instead ("default" = standard speed)` |
| C8 | MET | `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` rows in `docs/guides/commands.md` updated as claimed |
| C9 | MET | `memory-bank/log.md` entry 2026-10-27 23:45; check_links OK |

## Standard checks
- pytest: `1060 passed, 2 skipped, 18 warnings in 259.85s` (matches)
- links: `OK: all links resolve in 39 files`
- ruff (new findings): `ruff_new: 0 new finding(s) in staged .py files`, exit 0
- secrets: none found (only `.env` match is an unchanged context line in commands.md; no .env staged)
- score.py unchanged: yes
- hard-coding: none found
- Checks I ran re-run: full suite, links, ruff match. Targeted run now `75 passed` vs claimed `74 passed` (likely counted before the last test was added; all pass — minor). "Red before the fix" not re-runnable without changing the tree.

## Undeclared changes
- None significant; PENDING.md is the worklog.
- Behaviour note: in the Creator a cut-off reply now has no tool calls → `not uses` path → uses the one-time `NUDGE`; a second non-finishing stop then fails the import (before: the cut call ran with truncated input). Reasonable, not stated.
- Untracked files not staged, not claimed.

## Knowledge base
- No project-state.md update justified (fix inside D-024); log.md and commands.md updated.

---

# Reviewer report (round 1)

REVIEW: PASS
TREE: c3d9e33a6bdc748a511969aeddd035bb94c5ead7

No BLOCKER. Three MINOR (do not block).

## Findings
| # | Severity | Where | Problem | Failure scenario | Suggested fix |
|---|---|---|---|---|---|
| R1 | MINOR | agent/creator.py:142-148 | A reply cut off mid tool call is now treated as a turn without a tool call and uses up the single `NUDGE`; a later turn without a tool call then fails the import ("stopped without finishing"), where the old code would have nudged. | Creator hits `max_tokens` once mid-call, later ends a turn without a tool call → `failed`. | Skip/reset `nudged` when `stop_reason == "max_tokens"`, or send a "cut off, retry the call" note instead. |
| R2 | MINOR | tests/test_creator.py:137-145 | Test only checks `steps[0] != {"kind":"tool","name":"finish"}` and ignores the result; a later run of the cut call or an extra step key would still pass. | n/a (weak test; does fail on old code). | Assert no `finish` step before the second request, or that `finish` never ran with `{"name": "Half"}`. |
| R3 | MINOR | agent/llm_client.py:kept_content | Placeholder is a plain dict among SDK block objects; all current consumers cope (`openai_llm.plain`, `backend/persistence.plain`, `getattr(..., "type", None)` filters), but future `block.type` reads on history would raise. | n/a today | Build it with `offline_llm.text_block(...)` / `BetaTextBlock`. |

## Reviewed
- files read: full staged diff (llm_client, openai_llm, guide, builder, creator, solver_agent, the three test files, commands.md), PENDING.md, openai_llm `plain`/`input_items`/error wrapping, backend/persistence `plain`/`plain_messages`, creator `__init__`/`run`/`prune`, lazy clients in llm_parser/solver_agent, guide `llm_mode`/`make_client`/`request`, offline_llm block builders, both ScriptedClients.
- checks run: `pytest tests/test_openai_llm.py tests/test_guide.py tests/test_creator.py tests/test_solver_agent.py` → 47 passed; grep of history consumers and client construction (Guide still offline without key via `has_key()`); `MissingKey` error mapped to anthropic error in both `create` and `stream` → `auth`; Guide test's history holds SDK objects so its assertion can fail on old code.
