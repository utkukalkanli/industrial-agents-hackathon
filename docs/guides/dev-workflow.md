---
id: guide-dev-workflow
summary: Development workflow — branch, commit normally, open a pull request into main; GitHub Actions CI is the gate. The earlier local /ship verification (D-008) is retired.
sources: [.github/workflows/ci.yml, .github/workflows/deploy.yml, docs/guides/ci-cd.md]
related: [ci-cd.md, commands.md, ../../memory-bank/decisions.md, ../../CLAUDE.md]
---

# Development workflow

[Docs index](../README.md) · Decision: [D-025](../../memory-bank/decisions.md#d-025) (supersedes D-008) · CI/CD:
[ci-cd.md](ci-cd.md)

```
 branch off main ──► commit (plain git commit) ──► push ──► pull request into main
                                                              │  CI: Python tests, Integration (Postgres + API),
                                                              │      Frontend lint + build, Vercel preview
                                                              ▼
                                                 green + reviewed ──► merge ──► deploy.yml → production
```

- Work on a branch, never directly on `main`. Commit with plain `git commit`; small, focused commits.
- Before pushing, run what CI runs for the parts you touched ([ci-cd.md](ci-cd.md#run-the-same-checks-locally)):
  `uv run pytest -q -n auto`, `python3 scripts/check_links.py`, and `npm run lint && npm run build` in
  `frontend/app/`.
- Open a pull request into `main`. The required checks must pass; the preview URL lands as a PR comment.
- Write the PR description as claims a reviewer can check (what changed, how it was verified, known gaps) — the
  habit the old worklog taught, now in the PR.
- Session protocol (CLAUDE.md) still applies: update `memory-bank/` and docs in the same PR.
- Parallel sessions: separate git worktrees per branch (`git worktree add ../<dir> -b <branch> origin/main`).

## History

Until 2026-10-25 every commit went through `/ship`: a worklog of claims, an independent `commit-verifier` agent,
a `commit-fixer` loop and a PreToolUse hook that blocked `git commit` without a PASS stamp
([D-008](../../memory-bank/decisions.md#d-008)). Retired because CI now runs the same checks on every PR in a
clean environment, and the per-commit verifier cost minutes and tokens per round. The archived entries and
reports stay in `.claude/worklog/history/` as the audit trail of those commits.

## Related
- [ci-cd.md](ci-cd.md) · [commands.md](commands.md) · [CLAUDE.md](../../CLAUDE.md#working-conventions)
