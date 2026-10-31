# README benchmark example writes to a scratch path; submission docs linked from the doc map

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-31
- **Related:** the two MINOR review findings (R1, R2) on commit 9005caf

## Summary
Fixes the two non-blocking review findings from the portfolio README commit. Docs only.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | The README's one-command benchmark example writes to `/tmp/answers.json`, not the committed `SUBMISSION/answers.json` | `README.md` "The benchmark" block | `grep -n run_benchmark_v1 README.md` |
| C2 | `docs/README.md` links both files in `docs/submission/` under a new "Submission" section marked as frozen | `docs/README.md` end of "All docs" | read it; `python3 scripts/check_links.py` |

## Checks I ran
- `python3 scripts/check_links.py` → `OK: all links resolve in 39 files`

## Knowledge base updates
- [ ] `memory-bank/project-state.md` — not needed: no product/code state changed
- [ ] `memory-bank/log.md` — not needed: follow-up to the 2026-10-31 entry, which covers this README work
- [ ] decisions / open questions touched: none
- [x] docs touched: README.md, docs/README.md

## Known gaps / not done
- `SUBMISSION/BENCHMARK.md` still says the LLM cache is committed (logged as Next on 2026-10-31).

## Verification rounds
- round 1: verifier PASS, reviewer PASS

---
# Verification report (round 1)
VERDICT: PASS
TREE: 6873da397ad3474f9a3b9473caadc1b38b636b5b
C1, C2 MET. pytest 1063 passed, 2 skipped; links OK in 39 files; ruff 0 new; no secrets; score.py unchanged.

---
# Review report (round 1)
REVIEW: PASS
TREE: 6873da397ad3474f9a3b9473caadc1b38b636b5b
No findings.
