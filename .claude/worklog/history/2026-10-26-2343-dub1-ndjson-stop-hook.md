# Production in dub1, NDJSON streams not gzipped; Stop hook reminds about log.md

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-26 23:43
- **Related:** user report "deployment slower, voice weird"; memory-bank/README.md (log rules); D-008 (/ship)

## Summary
Pins the Vercel functions to `dub1` (next to the Supabase database in eu-west-1; they ran in `iad1`), keeps the
Guide's NDJSON stream out of the backend GZip middleware (with a test), adds a Stop hook that reminds Claude once
per session to write a `memory-bank/log.md` entry when tracked files changed, and records the session (incl. access
mode switched off in production) in the memory bank.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `vercel.json` gets top-level `"regions": ["dub1"]`; nothing else in it changes | `vercel.json` | `git diff --cached vercel.json` → 1 added line |
| C2 | GZipMiddleware excludes `application/x-ndjson` (plus starlette's defaults); other responses (the plan) still gzip | `backend/app.py` (middleware setup, import of `DEFAULT_EXCLUDED_CONTENT_TYPES`) | `uv run pytest -q tests/test_backend.py -k gzip` → 2 passed |
| C3 | New test `test_chat_stream_is_not_gzipped` fails without the fix and passes with it | `tests/test_backend.py` | `git stash`-free check: read the test; it asserts no `content-encoding` on `/chat/stream` with `Accept-Encoding: gzip` |
| C4 | Stop hook `.claude/hooks/remind-log.py` registered in `.claude/settings.json` under `hooks.Stop`; existing PreToolUse hook unchanged | `.claude/settings.json`, `.claude/hooks/remind-log.py` | `jq '.hooks' .claude/settings.json`; `git diff --cached .claude/settings.json` |
| C5 | Hook behaviour: blocks (JSON `decision: block`) only when tracked files differ from HEAD outside `memory-bank/log.md` / `.claude/worklog/` and log.md is unchanged; once per session (marker under `.git/claude-log-reminded/<session_id>`); never when `stop_hook_active`; any error → no output | `.claude/hooks/remind-log.py` | read the script; pipe-test in a scratch git repo (see Checks) |
| C6 | Hook runs under system `python3` (3.9) | `.claude/hooks/remind-log.py` | `echo '{"session_id":"x","cwd":"."}' \| python3 .claude/hooks/remind-log.py; echo $?` → exit 0 |
| C7 | memory-bank/log.md: new top entry `## 2026-10-26 23:43 — ...` (Did / Learned / Changed docs / Next), pure addition vs HEAD | `memory-bank/log.md` | `git diff --cached memory-bank/log.md` → only `+` lines |
| C8 | project-state.md matches: access mode off in production (ACCESS_MODE removed), production `dpl_F8wfKMwVTZZ1WjjbEZ5ESLFkduRH`, functions in `dub1` | `memory-bank/project-state.md` (Access mode bullet, Next item 3 Deploy) | `git diff --cached memory-bank/project-state.md` |
| C10 | dev-workflow.md documents the Stop hook: `sources:` lists `.claude/hooks/remind-log.py`; Pieces table has a `hooks/remind-log.py` row and the `settings.json` row says it registers both hooks; Limits notes once-per-session + `/hooks`/restart | `docs/guides/dev-workflow.md` | `git diff --cached docs/guides/dev-workflow.md` |
| C9 | Doc links resolve | docs, memory-bank | `uv run python scripts/check_links.py` → OK |

## Checks I ran

- `uv run pytest -q tests/test_backend.py -k gzip` before the fix → `1 failed, 1 passed` (`test_chat_stream_is_not_gzipped` AssertionError); after → `uv run pytest -q tests/test_backend.py` → `24 passed in 5.35s`
- Stop hook pipe-tests (scratch repo, system python3): clean → no output; code changed, no log → `{"decision": "block", ...}`; same session again → no output; `stop_hook_active: true` → no output; log.md changed → no output; only `.claude/worklog/` changed → no output; all exit 0. It also fired for real in this session at the end of a turn.
- `jq -e '.hooks.Stop[] | .hooks[] | select(.type == "command") | .command' .claude/settings.json` → prints the remind-log command
- `uv run python scripts/check_links.py` → `OK: all links resolve in 39 files`
- Fix round 1: `uv run python scripts/check_links.py` → `OK: all links resolve in 39 files`; `uv run pytest -q` → `1029 passed, 2 skipped, 18 warnings in 253.99s (0:04:13)`; `git diff HEAD memory-bank/log.md` → no removed lines
- Outside the diff (deployment): preview `5cffjwmw7` → `x-vercel-id: fra1::dub1::…`, create-session 0.37 s (production on iad1: 1.01 s); stream lines arrived at 4.34 / 4.52 / 7.48 s (incremental). After `vercel env rm ACCESS_MODE` (production, preview) + promote: production `dpl_F8wfKMwVTZZ1WjjbEZ5ESLFkduRH` READY, `/api/config` → `{"access_mode":false}`, `x-vercel-id: fra1::dub1::…`.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (access mode bullet, Deploy item)
- [x] `memory-bank/log.md` entry added (23:43)
- [x] decisions / open questions touched: none
- [x] docs touched: `docs/guides/dev-workflow.md` (sources, remind-log.py row, settings.json row, Limits line); docs/guides/commands.md not changed

## Known gaps / not done
- Vercel's edge still gzips the NDJSON stream (content-encoding: gzip seen on the deployment); lines were measured arriving incrementally, so left as is.
- Voice in a real browser on production not tested (only server-side timings).
- The Stop hook fires at every turn end (Claude Code has no "session end" event that lets Claude act); it reminds at most once per session.
- `.claude/settings.json` hook may need `/hooks` or a restart to load in sessions started before it existed.
- `ADMIN_EMAIL` stays set on Vercel (no effect while access mode is off).

## Verification rounds
- Round 1: FAIL — dev-workflow.md missing the Stop hook
- Round 2: PASS (tree 5d7250bc5d0102837b125f8f8f0947d935a084e6)

## Fix round 1
- dev-workflow.md missing the Stop hook: implemented — `docs/guides/dev-workflow.md`: added `.claude/hooks/remind-log.py` to `sources:`, a `hooks/remind-log.py` row in the Pieces table, `settings.json` row now says it registers both hooks (PreToolUse require-verification, Stop remind-log), and a Limits line (fires every turn, reminds at most once per session; `/hooks` or restart for older sessions).
- log.md Changed docs line: implemented — `memory-bank/log.md` 23:43 entry now also names [dev-workflow.md](../docs/guides/dev-workflow.md); log.md still a pure addition vs HEAD.
- PENDING.md: "docs touched" corrected; claim C10 added; full `uv run pytest -q` now run (removed from Known gaps).

---

# Verification

## Round 1

VERDICT: FAIL
TREE: bcb7e8dcddeb0071b91fb09f9d8e4fce0585ea99

Claims C1–C9 MET. pytest 1029 passed, 2 skipped; links OK; no secrets; score.py unchanged; no hard-coding.

Required fix: docs/guides/dev-workflow.md (sources: .claude/settings.json, .claude/hooks/*) does not list the new
Stop hook `hooks/remind-log.py`, and its settings.json row says it registers "the hook" (singular). Add the row,
fix the settings.json row, optionally a Limits line, add the hook to `sources:`, update PENDING.md "docs touched"
and the log entry's "Changed docs", re-run check_links.

## Round 2

VERDICT: PASS
TREE: 5d7250bc5d0102837b125f8f8f0947d935a084e6

Claims C1–C10 MET. pytest 1029 passed, 2 skipped; links OK; no secrets; score.py unchanged; no hard-coding.
C3 reproduced (pre-fix copy: test_chat_stream_is_not_gzipped fails). Note: system python3 here reports 3.8.18;
the hook works on it.
