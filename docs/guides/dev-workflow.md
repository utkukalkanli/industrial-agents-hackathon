---
id: guide-dev-workflow
summary: Agentic development workflow — every commit goes through a worklog of claims, an independent verifier agent and an independent code reviewer, an optional fixer loop, and a hook-enforced PASS stamp; a PostToolUse hook lints every edited .py file with ruff.
sources: [.claude/skills/ship/SKILL.md, .claude/agents/commit-verifier.md, .claude/agents/code-reviewer.md, .claude/agents/commit-fixer.md, .claude/hooks/require-verification.py, .claude/hooks/stamp-verified.py, .claude/hooks/remind-log.py, .claude/hooks/ruff-lint.py, scripts/ruff_new.py, .claude/settings.json]
related: [commands.md, ../../memory-bank/decisions.md, ../../CLAUDE.md]
---

# Development workflow: verified commits

[Docs index](../README.md) · Decisions: [D-008](../../memory-bank/decisions.md#d-008),
[D-025](../../memory-bank/decisions.md#d-025)

**Promise → evidence → review → commit.** Whoever implements writes down what they claim; a fresh agent that did
not write the code checks every claim against the staged diff, and a second fresh agent reviews the same diff for
defects; only a round where both pass can be committed.

```
 implement ──► .claude/worklog/PENDING.md (claims, checks run, gaps)
                     │  /ship
                     ▼
               git add <paths>
                     ▼
        ┌──► commit-verifier ─┐ (two fresh read-only agents, in parallel)
        │    code-reviewer  ──┴─ both PASS ──► archive log → stamp tree hash → git commit
        │            │ verifier FAIL and/or reviewer BLOCK
        │            ▼
        └──── commit-fixer (fixes code, corrects a claim, or disputes a finding with evidence; restages;
                            never commits)                                                  max 3 rounds
```

## Pieces (all in `.claude/`)

| File | Role |
|---|---|
| `worklog/TEMPLATE.md` | format of a worklog entry: summary, **claims table** (claim · where · how to verify), checks run, KB updates, known gaps |
| `worklog/PENDING.md` | the current, not-yet-committed entry (one at a time) |
| `worklog/history/` | archived entries + their verifier report, one per commit — the audit trail |
| `agents/commit-verifier.md` | read-only subagent: verifies each claim, runs tests + link check + `scripts/ruff_new.py` (any **new** ruff finding fails), scans for secrets, hard-coded test answers, edits to `benchmark/score.py`, undeclared changes, stale knowledge base → `VERDICT: PASS/FAIL` |
| `agents/code-reviewer.md` | read-only subagent: reviews the staged diff for defects and project-rule breaks (checklist in the agent file). Each finding is BLOCKER (needs a concrete failure scenario), MAJOR or MINOR → `REVIEW: PASS/BLOCK`; only BLOCKERs block, MAJOR/MINOR go to the user |
| `agents/commit-fixer.md` | fixes only the listed issues (verifier required fixes, reviewer BLOCKERs) or honestly downgrades the claim to a known gap, or disputes a reviewer finding with evidence in PENDING.md; restages; never commits |
| `../scripts/ruff_new.py` | ruff on the HEAD and staged version of each staged `.py` file; findings compared by (rule, source line) so only findings the change adds count. Exit 0 none, 1 new findings, 2 error. The repo has many pre-existing findings (165 on 2026-10-27), which therefore never block |
| `skills/ship/SKILL.md` | the orchestration (`/ship`, `/ship push`) |
| `hooks/require-verification.py` | PreToolUse hook on Bash: blocks `git commit` unless `worklog/.verified` = hash of the staged tree (`git write-tree`); also blocks `--amend`, `-a`, and `git add … && git commit` one-liners. Checks the repository the commit runs in (tool-call `cwd`, then `cd <dir>` / `git -C <dir>` in the command), so a commit in a git worktree is checked against that worktree's index and stamp although settings.json runs the main checkout's copy of the hook. Commit-like text anywhere in a Bash command (even inside a heredoc) is treated as a commit |
| `hooks/stamp-verified.py` | writes the stamp; refuses unless the archived entry is staged and says `VERDICT: PASS` and `REVIEW: PASS` |
| `hooks/ruff-lint.py` | PostToolUse hook on `Write\|Edit`: runs `ruff check --no-fix` (`.venv/bin/ruff`, else `uv run ruff`) on the edited `.py` file and gives the findings to Claude as context. Report-only (no auto-fix, no format) so diffs stay limited to the real change; silent for clean or non-Python files and on any error |
| `hooks/remind-log.py` | Stop hook (runs with system `python3`): at the first stop of a session, blocks once if tracked files differ from HEAD (`memory-bank/log.md` and `worklog/` excluded) and `memory-bank/log.md` is unchanged; the reason asks Claude to add a log.md entry or say why none is needed. Never blocks when `stop_hook_active` is set; per-session marker `.git/claude-log-reminded/<session_id>`; any error lets the stop through |
| `settings.json` | registers the hooks: PreToolUse `require-verification.py`, PostToolUse `ruff-lint.py`, Stop `remind-log.py` (project-wide, committed) |

## How to use

- Agents: keep `PENDING.md` current while working (copy the template at the start of a work chunk), then run
  `/ship`. Never call `git commit` directly — the hook will refuse.
- Humans: say "ship it" / `/ship` in Claude Code. Commits from your own terminal are not hooked (escape hatch),
  but skip the verification — avoid it.
- Any change after the stamp (even one more `git add`) invalidates it → re-verify.

## Limits (honest)

- A guard against sloppy or over-claiming agents, not a security boundary: an agent could forge a stamp by
  hand. The verifier report is archived in `worklog/history/` with each commit, so this is visible in review.
- One `PENDING.md` at a time; parallel sessions should ship in turn or use separate worktrees.
- Verification costs tokens (a verifier and a reviewer run per round); budget
  [Q-012](../../memory-bank/open-questions.md#q-012).
- The reviewer is an LLM: it can miss defects and can raise false ones. BLOCKERs need a written failure scenario,
  and the fixer may dispute one with evidence, which the next fresh reviewer reads.
- `ruff format` is not enforced: 173 files were unformatted on 2026-10-27; a repo-wide format is a separate,
  one-off commit.
- The Stop hook fires at the end of every turn but reminds at most once per session; a session started before the
  hook existed may need `/hooks` or a restart to load it.

## Related
- [commands.md](commands.md) · [CLAUDE.md](../../CLAUDE.md#working-conventions)
