---
name: ship
description: Verified commit workflow for this repo. Use whenever work is ready to commit (or the user says "commit", "ship", "/ship"). Ensures .claude/worklog/PENDING.md lists the claims, runs the commit-verifier and code-reviewer agents on the staged diff, loops commit-fixer until both pass (max 3 rounds), and commits only after a PASS. Direct `git commit` is blocked by a hook without a fresh PASS stamp.
---

# /ship — verified commit

A commit is allowed only after an **independent** `commit-verifier` agent confirms that what
`.claude/worklog/PENDING.md` promises is actually in the staged change (including no new ruff findings), and an
independent `code-reviewer` agent finds no BLOCKER defect in it. A PreToolUse hook
(`.claude/hooks/require-verification.py`) blocks `git commit` unless `.claude/worklog/.verified` holds the
hash of the exact staged tree.

Optional argument: `push` → also `git push` after a successful commit (only if a remote exists).

## Steps

### 1. Worklog
- If `.claude/worklog/PENDING.md` does not exist, the implementer (you) writes it now from
  `.claude/worklog/TEMPLATE.md`: every promise as a checkable claim, the checks you actually ran with real
  output, knowledge-base updates, known gaps. Do this honestly — the verifier will check it.
- Make sure the session protocol from `CLAUDE.md` was followed (project-state, log, decisions/questions).

### 2. Stage
- `git status --short`, then `git add` the intended paths (never `.env`, never secrets). Include PENDING.md.
- Nothing staged → stop and tell the user.

### 3. Verify + review (two fresh agents, every round, in parallel)
Spawn both in the same message (both are read-only, so they can run side by side):
- `subagent_type: "commit-verifier"`, prompt:
  > Verify the currently staged change against .claude/worklog/PENDING.md. Follow your procedure exactly and
  > return your report in the required format.
- `subagent_type: "code-reviewer"`, prompt:
  > Review the currently staged change for defects. Follow your procedure exactly and return your report in the
  > required format.

Save the reports to `.claude/worklog/VERIFICATION.md` and `.claude/worklog/REVIEW.md` (overwrite per round). Record each
round in PENDING.md under "## Verification rounds" as `- round N: verifier PASS|FAIL, reviewer PASS|BLOCK` (never
copy the reports' `VERDICT:` / `REVIEW:` lines there — the stamp script looks for those at line start).

The round **passes** only if the verifier says `VERDICT: PASS` **and** the reviewer says `REVIEW: PASS`.

### 4. Round did not pass → fix → re-check
- Spawn `subagent_type: "commit-fixer"` with the verifier report (if FAIL) and the reviewer's BLOCKER findings
  (if BLOCK) in the prompt.
- After it returns, go back to step 3 with **new** verifier and reviewer agents (never reuse the old ones: no
  anchoring).
- Max **3** fix rounds. Still not passing → stop, do not commit, show the user the remaining required fixes and
  BLOCKERs.

### 5. On PASS → archive, stamp, commit
Run these as **separate** Bash commands (the hook checks the index at the moment of `git commit`):
1. Archive: `mkdir -p .claude/worklog/history` then move PENDING.md to
   `.claude/worklog/history/<YYYY-MM-DD-HHMM>-<slug>.md` and append the VERIFICATION.md and REVIEW.md reports
   to that file; delete both. `git add .claude/worklog/`.
2. Stamp: `python3 .claude/hooks/stamp-verified.py .claude/worklog/history/<file>.md` — it refuses unless the
   entry says `VERDICT: PASS` and `REVIEW: PASS` and the file is staged; writes the staged-tree hash to
   `.claude/worklog/.verified`.
3. Commit: `git commit -m "<title from worklog>" -m "<summary + claim ids>" -m "Verified-by: commit-verifier + code-reviewer (<n> round(s)), log: <history file>"`
   plus the attribution trailer required for this session.
4. `git log -1 --stat | head -20` and report to the user: commit hash, rounds, any warnings, and the reviewer's
   MAJOR / MINOR findings (they don't block, the user decides).
5. If the argument was `push`: `git push`.

## Notes
- Anything staged after stamping changes the tree hash → the hook blocks; re-run from step 3.
- Humans committing from their own terminal are not blocked (the hook only guards Claude's Bash tool), but should
  still run `/ship`.
- Parallel sessions: only one PENDING.md at a time — finish or ship before starting another chunk.
