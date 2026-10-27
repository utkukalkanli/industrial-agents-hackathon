# OpenAI provider (D-024, revised) + review fixes; ruff and a code reviewer in /ship (D-025); app named Floorwise

- **Author:** Claude Code sessions (Utku) · **Date:** 2026-10-27 23:40
- **Related:** D-024 (revised 2026-10-27), D-025, D-008, docs/guides/dev-workflow.md, docs/architecture/ai-agents.md

## Summary
Three chunks in one commit (Utku's choice). (A) Every LLM part can run on OpenAI: `agent/llm_client.py` picks the
provider, `agent/openai_llm.py` serves the Anthropic Messages interface from the Responses API; the app is named
Floorwise. (B) Fixes from `/code-review` on (A): OpenAI is the default provider (Utku: Anthropic credit is gone),
decision-cache keys carry the provider, `GUIDE_LLM` forces a provider for Guide/Builder/Creator, the voice rewriter
shares the Guide's client, a token-limited tool call stops with `max_tokens`, key names in messages follow the
provider, unused imports gone. (C) ruff as a dev dependency, a report-only ruff PostToolUse hook, a new-findings
gate in the verifier, and a `code-reviewer` agent next to the verifier in every `/ship` round.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| A1 | `llm_client.provider()`: `LLM_PROVIDER` wins; unset → `anthropic` only when `ANTHROPIC_API_KEY` is the only key, else `openai`; `make(max_retries, name)`, `key_name()`, `has_key()`, `live()` | `agent/llm_client.py` | `uv run pytest -q tests/test_openai_llm.py -k "provider_follows or key_name"` |
| A2 | `OpenAIClient` maps Anthropic-shaped requests to the Responses API and back (system, history, tools, tool_choice, effort, json_schema, images, model family mapping, ultrafast tier for opus-mapped calls) and OpenAI errors to anthropic error classes | `agent/openai_llm.py` | `uv run pytest -q tests/test_openai_llm.py` |
| A3 | Guide, rewriter, LLM parser, solver agent, Builder, Creator get their client from `llm_client` instead of `anthropic.Anthropic()` | `agent/guide.py`, `rewriter.py`, `llm_parser.py`, `solver_agent.py`, `builder.py`, `creator.py` | `grep -n "anthropic.Anthropic()" agent/*.py` → none in these six; read diffs |
| A4 | `openai` dependency added; app named Floorwise (tab title, README); `.env.example` documents `LLM_PROVIDER` / `OPENAI_*` | `pyproject.toml`, `uv.lock`, `frontend/app/index.html`, `README.md`, `.env.example` | read diffs |
| B1 | decision-cache keys carry the provider (`<ns>@openai/…`; Claude's keys unchanged) | `agent/llm_cache.py:decision_key` | `uv run pytest -q tests/test_openai_llm.py -k cached_decisions` |
| B2 | `GUIDE_LLM=openai\|anthropic` forces that provider for the Guide, Builder and Creator | `agent/guide.py:llm_mode/make_client`, `agent/builder.py:make_builder_client`, `agent/creator.py` | `uv run pytest -q tests/test_openai_llm.py -k "guide_llm_naming or builder_uses"` |
| B3 | the Guide's `TranscriptRewriter` uses the Guide's own client | `agent/guide.py` (rewriter construction) | `uv run pytest -q tests/test_guide.py tests/test_rewriter.py` |
| B4 | an OpenAI response cut off by `max_output_tokens` stops with `max_tokens` even mid tool call | `agent/openai_llm.py:anthropic_message` | `uv run pytest -q tests/test_openai_llm.py -k cut_off` |
| B5 | Creator and `scripts/live_builder.py` messages name the provider's key; Creator API errors read "LLM API error" | `agent/creator.py`, `scripts/live_builder.py`, `tests/test_creator.py` | `uv run pytest -q tests/test_creator.py -k without_a_key` |
| B6 | unused `import anthropic` removed from builder, llm_parser, solver_agent | those files | `uv run python scripts/ruff_new.py` → 0 new |
| C1 | ruff 0.17.3 is a dev dependency | `pyproject.toml`, `uv.lock` | `uv run ruff --version` |
| C2 | PostToolUse hook on `Write\|Edit` lints the edited `.py` with `ruff check --no-fix` (`.venv/bin/ruff`, else `uv run ruff`) and returns findings as `additionalContext`; silent for clean / non-`.py` files and on errors | `.claude/hooks/ruff-lint.py`, `.claude/settings.json` | `echo '{"tool_input":{"file_path":"'$PWD'/.claude/hooks/remind-log.py"}}' \| python3 .claude/hooks/ruff-lint.py` → JSON with S110/BLE001; with `core/__init__.py` or `CLAUDE.md` → no output |
| C3 | `scripts/ruff_new.py` reports only findings the staged change adds (HEAD vs index by rule + stripped line); exit 0/1/2 | `scripts/ruff_new.py` | run it on this staged change → 0 new; read the script |
| C4 | verifier runs `ruff_new.py`; new code-reviewer agent (read-only, BLOCKER/MAJOR/MINOR, `REVIEW: PASS\|BLOCK`); `/ship` runs both per round; fixer handles BLOCKERs (fix or dispute with evidence); stamp needs `VERDICT: PASS` and `REVIEW: PASS` | `.claude/agents/commit-verifier.md`, `code-reviewer.md`, `commit-fixer.md`, `.claude/skills/ship/SKILL.md`, `.claude/hooks/stamp-verified.py` | read; probe entries with only `VERDICT: PASS` or with `REVIEW: BLOCK` → refused |
| D1 | docs and memory bank match A–C | `docs/guides/dev-workflow.md`, `docs/guides/commands.md`, `docs/architecture/ai-agents.md`, `SUBMISSION/BENCHMARK.md`, `memory-bank/decisions.md` (D-024 + revision, D-025), `project-state.md`, `log.md` | read; `python3 scripts/check_links.py` |

## Checks I ran

- `uv run pytest -q -p no:cacheprovider` (before the Builder/Creator `name=mode` change) →
  `1055 passed, 2 skipped, 18 warnings in 251.31s`; after it: `tests/test_creator.py tests/test_builder*.py
  tests/test_openai_llm.py` → `48 passed`, then `tests/test_openai_llm.py` → `12 passed` (full run repeated below
  after staging).
- After staging: `uv run python scripts/ruff_new.py` first reported 9 new findings in the new files (S110/BLE001 in
  `ruff-lint.py` → `# noqa` with the reason: a lint hook must never break an edit; I001 in `live_builder.py` →
  imports sorted, all still after the `sys.path` setup, `--help` runs; six C408 `dict()` calls in
  `tests/test_openai_llm.py` → literals). Then `ruff_new: 0 new finding(s)`, exit 0; full suite
  `1056 passed, 2 skipped, 18 warnings in 269.89s`; links OK.
- New tests were red before their fixes: 4 in `tests/test_openai_llm.py` (`4 failed, 7 passed`), and
  `test_the_builder_uses_the_provider_guide_llm_names` failed against HEAD's `agent/builder.py`.
- `uv run python scripts/check_links.py` → `OK: all links resolve in 39 files`
- C2 pipe test → JSON with `S110`, `BLE001` for remind-log.py; no output for `core/__init__.py`, `CLAUDE.md`
  (also with `"cwd":"/tmp"`). Live: a Write of a file with `import os` got `F401` back.
- C3 on a temporary index (real index untouched): unchanged → `0 new`, exit 0; `import os` prepended → only
  `I001`, `F401`, exit 1; new file with `import sys` → `F401`, exit 1.
- C4 stamp probes → `refused: ... no 'REVIEW: PASS' line` (twice), `refused: ... is not staged`.
- A: live checks were run by the earlier session that wrote the OpenAI switch (log 2026-10-27 22:10:
  `scripts/eval_guide.py` 18/18 on OpenAI, rewriter, LLM parser, live_builder). Not re-run here (paid API calls).

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (Floorwise/OpenAI header, workflow line, next priorities)
- [x] `memory-bank/log.md` entries 22:10 (D-024), 22:20 (D-025), 23:10 (review fixes)
- [x] decisions: D-024 added and revised 2026-10-27, D-025 added
- [x] docs touched: dev-workflow.md, commands.md, ai-agents.md, SUBMISSION/BENCHMARK.md, README.md, .env.example

## Known gaps / not done
- Benchmark not re-measured on OpenAI; `llm_cache/decisions.json` does not exist yet (first OpenAI run fills it).
- `OPENAI_API_KEY` not yet in Vercel; Creator not tried on OpenAI (from D-024's next steps).
- `/code-review` finding "effort `max` invalid on OpenAI" not acted on: the installed SDK's `ReasoningEffort`
  includes `max`; whether every OpenAI model accepts it is untested.
- `ruff format` not enforced; no `[tool.ruff]` rule set chosen (ruff defaults apply).
- The `REVIEW:` stamp check, like `VERDICT:`, guards against sloppy agents, not a security boundary.
- Untracked files not part of this commit and left alone: `.claude/skills/supabase*/`, `.mcp.json`,
  `.vercelignore`, `building_plans/`, `demo_videos/`, `docs/submission/`, `*.zip`, `skills-lock.json`.

## Verification rounds
- round 1: verifier PASS, reviewer PASS

---

# Verifier report (round 1)

VERDICT: PASS
TREE: e2c25c5601fa115cacb2b2e9cb4f7eb983fe1681

## Claims
| # | Status | Evidence |
|---|---|---|
| A1 | MET | `agent/llm_client.py:16-45`: `provider()` follows `LLM_PROVIDER`, then picks `anthropic` only when ANTHROPIC_API_KEY is set and OPENAI_API_KEY is not; `make`, `key_name`, `has_key`, `live` present. `-k "provider_follows or key_name"` → 2 passed, 10 deselected |
| A2 | MET | `agent/openai_llm.py` (257 lines): `openai_request`, `anthropic_message`, `anthropic_error`, `Stream`, `Messages`, `OpenAIClient`; mapping covers system→instructions, history/tool_use/tool_result, tools, tool_choice, effort, json_schema, images, model families, ultrafast tier for opus calls only. `tests/test_openai_llm.py` → 12 passed |
| A3 | MET | `grep -n "anthropic.Anthropic()" agent/*.py` → only `agent/llm_client.py:39`; guide/rewriter/llm_parser/solver_agent/builder/creator use `llm_client.make(...)` |
| A4 | MET | `pyproject.toml` `openai>=3.40.0`; `uv.lock` adds openai 3.40.0; `frontend/app/index.html` title Floorwise; README retitled; `.env.example` documents LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL/MID/SMALL |
| B1 | MET | `agent/llm_cache.py:decision_key` tag "" for anthropic, `@<provider>` otherwise; `-k cached_decisions` → 1 passed |
| B2 | MET | `guide.py:llm_mode` returns GUIDE_LLM when in PROVIDERS; `make_client`, `builder.py:make_builder_client`, `creator.py:__init__` call `llm_client.make(name=mode)`; `-k "guide_llm_naming or builder_uses"` → 2 passed (Creator path by code reading only) |
| B3 | MET | `guide.py`: `TranscriptRewriter(session.building, client=self.client) if llm_client.live(self.client)`; `tests/test_guide.py tests/test_rewriter.py` → 17 passed |
| B4 | MET | `anthropic_message` checks `incomplete_details.reason == "max_output_tokens"` before tool_use; `-k cut_off` → 1 passed |
| B5 | MET | creator.py "the Creator needs an LLM key (set {llm_client.key_name()})" and "LLM API error: …"; live_builder.py `needs {llm_client.key_name()}`; `test_creator.py -k without_a_key` → 1 passed (both key names) |
| B6 | MET | `import anthropic` removed from builder.py, llm_parser.py, solver_agent.py; `ruff_new.py` → 0 new |
| C1 | MET | `uv run ruff --version` → `ruff 0.17.3`; dev group + uv.lock |
| C2 | MET | hook registered as PostToolUse `Write\|Edit`; pipe test on remind-log.py → JSON with S110, BLE001; `core/__init__.py`, `CLAUDE.md`, `"cwd":"/tmp"` variant → no output |
| C3 | MET | HEAD vs index Counter of (code, stripped line), exit 0/1/2; on this change `ruff_new: 0 new finding(s)`, exit 0 |
| C4 | MET | verifier ruff_new step; code-reviewer.md new (read-only, BLOCKER/MAJOR/MINOR, `REVIEW: PASS\|BLOCK`); fixer fixes or disputes with evidence; SKILL.md runs both per round; stamp loops over VERDICT and REVIEW — probes: only VERDICT PASS → refused (no REVIEW PASS); REVIEW BLOCK → refused; only REVIEW PASS → refused (no VERDICT PASS) |
| D1 | MET | dev-workflow.md, commands.md, ai-agents.md, SUBMISSION/BENCHMARK.md, decisions.md (D-024, D-025), project-state.md, log.md (22:10, 22:20, 23:10) describe A–C; `check_links.py` → OK, 39 files |

## Standard checks
- pytest: `1056 passed, 2 skipped, 18 warnings in 269.98s`, exit 0 (matches PENDING)
- links: `OK: all links resolve in 39 files`
- ruff (new findings): `ruff_new: 0 new finding(s) in staged .py files`, exit 0 (6 pre-existing RUF100 in live_builder.py matched by line text)
- secrets: none found (only hit: the verifier's own rule text; tests use "test-key"; no .env staged)
- score.py unchanged: yes
- hard-coding: none found
- Checks I ran (PENDING): re-ran pytest, ruff_new, check_links, C2 pipe test, C4 stamp probes — outputs match. Not re-run: temp-index C3 experiment, live OpenAI checks (listed as not re-run).

## Undeclared changes
- `agent/guide.py` INSTRUCTIONS now start "You are Floorwise, the building guide" — recorded in log 22:10; trivial.
- `agent/guide.py` `send()` streaming condition `isinstance(..., anthropic.Anthropic)` → `llm_client.live(...)` — part of A3.
- PENDING.md staged (expected); untracked files listed in Known gaps, not staged.

## Notes (non-blocking)
- commands.md Vercel env table: `ANTHROPIC_API_KEY` row still says "without it the Guide runs the offline rules" — only true with LLM_PROVIDER=anthropic now; rows below clarify.
- B2 Creator path checked by code reading only; new tests cover Guide and Builder.

---

# Reviewer report (round 1)

REVIEW: PASS
TREE: e2c25c5601fa115cacb2b2e9cb4f7eb983fe1681

No BLOCKER. One MAJOR, three MINOR (do not block).

## Findings
| # | Severity | Where | Problem | Failure scenario | Suggested fix |
|---|---|---|---|---|---|
| R1 | MAJOR | agent/openai_llm.py:165 (`anthropic_message`), agent/guide.py:576-586, agent/builder.py:216-225 | After the B4 fix a cut-off tool call stops with `max_tokens`, but the Guide/Builder append `response.content` to history before checking `stop_reason`, so the truncated `tool_use` block stays in `self.messages` without a `tool_result`; the next turn sends a `function_call` with no `function_call_output`, which the Responses API normally rejects with 400 (not confirmed offline). Same dangling-tool_use issue pre-existed for Claude; more likely on OpenAI since reasoning tokens count toward `max_output_tokens` (16000). | OpenAI Guide at high effort writes a long `trace` call that hits the limit → "(My answer was cut off…)"; every following message → BadRequestError → "internal". | Strip `tool_use` blocks from the assistant message when `stop_reason == "max_tokens"` (Guide/Builder loops), or drop truncated `function_call` items in `anthropic_message` when incomplete; add a test that the next turn still builds a valid request. |
| R2 | MINOR | agent/llm_client.py:33-38, agent/guide.py:276-277 | `GUIDE_LLM=openai` without `OPENAI_API_KEY` → `OpenAIClient()` raises raw `openai.OpenAIError` at construction, not an anthropic error class, so backend handlers don't map it (`anthropic.Anthropic()` without key constructs fine). | Backend conversation creation → generic 500. | Map the construction error through `anthropic_error` / `AuthenticationError`, or make `llm_mode()` return "offline" when the forced provider has no key. |
| R3 | MINOR | tests/test_openai_llm.py:209-218 | `test_the_builder_uses_the_provider_guide_llm_names` does not clear `GUIDE_LLM` before its first assertion. | A shell with `GUIDE_LLM` exported fails the test. | `monkeypatch.delenv("GUIDE_LLM", raising=False)`. |
| R4 | MINOR | agent/openai_llm.py:20 (docstring) | Says `OPENAI_SERVICE_TIER=default` turns ultrafast off; code sends `service_tier="default"` (same effect, wording implies omission). | — | Reword, or treat "default" as omit. |

## Reviewed
- files read: full staged diff of agent/, scripts/, .claude/hooks/, .claude/settings.json, pyproject.toml, .env.example; all of agent/openai_llm.py and agent/llm_client.py; agent/guide.py 560-664; backend/service_errors.py; PENDING.md; tests/test_openai_llm.py.
- checks run: grep for leftover `anthropic.Anthropic()` / `llm_mode() == "anthropic"` (none broken); no committed llm_cache/decisions.json; OpenAI quota error still maps to `credits`; keyless client construction (anthropic OK, OpenAIClient raises → R2); SDK `Responses.create` accepts `service_tier`; `pytest tests/test_openai_llm.py tests/test_creator.py tests/test_rewriter.py` → 29 passed; `ruff_new.py` → 0 new; new tests make no network calls.
