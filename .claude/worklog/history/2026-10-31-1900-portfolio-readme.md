# Portfolio README: hero screenshot, results, architecture, run commands

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-31
- **Related:** user request: the repo is a portfolio project and should look like utkukalkanli/agent-router

## Summary
Rewrites README.md as a showcase in the style of the agent-router repo, adds screenshots of the live app and the
logo under `assets/`, commits the technical explanation the README links, and gitignores Playwright output.
Docs-only change; no code touched.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Every relative link and image in README.md resolves to a file in the commit | `README.md`, `assets/`, `docs/submission/` | for each `](path)` / `src="path"` in README, check the file exists in the staged tree |
| C2 | README numbers match sources: 138/138 dev, 1,338/1,338 routes, 145/145 test, 280 buildings (technical-explanation.html); 0.885 on 252 auto-scored questions (memory-bank/project-state.md "organisers' internal evaluation set"); 17 buildings on the map (project-state / live app) | `README.md` Result table | grep the cited sources |
| C3 | Run commands in README exist in docs/guides/commands.md or SUBMISSION/BENCHMARK.md (uvicorn with GUIDE_LLM=offline, npx vite --port 5181, benchmark.evaluate, run_benchmark_v1, PARSER_MODE=regex) | `README.md` Run it locally | grep those docs |
| C4 | README makes no claim that `llm_cache/decisions.json` exists (it is not in the repo) | `README.md` | `grep -n llm_cache README.md` → nothing |
| C5 | Clone URL points at utkukalkanli/industrial-agents-hackathon (the real origin) | `README.md` | `git remote -v` |
| C6 | `.playwright-mcp/` is gitignored | `.gitignore` | `git check-ignore .playwright-mcp/x` |
| C7 | Log entry added for this chunk | `memory-bank/log.md` top entry 2026-10-31 | read it |

## Checks I ran
- `python3 scripts/check_links.py` → `OK: all links resolve in 39 files`
- existence loop over README link targets → all `ok` except `llm_cache/decisions.json` (README claim then removed)
- `gh repo view` after `gh repo edit` → description + 15 topics set (GitHub side, not part of the diff)

## Knowledge base updates
- [ ] `memory-bank/project-state.md` updated — not needed: no product/code state changed
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: README.md only

## Known gaps / not done
- `SUBMISSION/BENCHMARK.md` still says the LLM cache is committed; not fixed here (logged as Next).
- Production ElevenLabs key is invalid (502 on /api/tts); not fixed here.
- Team line lists the two git authors (Atahan Kılıç, Utku Kalkanlı); user to confirm if more members.
- Screenshots are dark-theme desktop captures at 1440×900; no mobile screenshot or demo GIF.

## Verification rounds
- round 1: verifier PASS, reviewer PASS

---
# Verification report (round 1)
VERDICT: PASS
TREE: bc090af7818c183aa9a0fbcca35cd11aae2ddb6e
C1–C7 all MET. Standard checks: pytest 1063 passed, 2 skipped; links OK in 39 files; ruff 0 new findings (no .py staged);
no secrets; score.py unchanged; no hard-coding. Not blocking: docs/submission/ not linked from docs/README.md.

---
# Review report (round 1)
REVIEW: PASS
TREE: bc090af7818c183aa9a0fbcca35cd11aae2ddb6e
| R1 | MINOR | README "The benchmark" block | example run writes to the committed SUBMISSION/answers.json | suggest a scratch output path |
| R2 | MINOR | docs/submission/ | not linked from docs/README.md, no front matter (submission artifact, judgement call) | link it from docs/README.md |
