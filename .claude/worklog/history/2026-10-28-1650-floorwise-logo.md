# Floorwise logo top left of the map panel and the list page; favicon redrawn

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-28 16:50
- **Related:** app named Floorwise (9de6162); Utku: "sol üstte isimle güzel bir logo"

## Summary
A Floorwise logo (mark + wordmark) top left of the map landing panel and the list page; the favicon shows the same
mark.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `Logo` component: inline SVG mark (3×3 faint dot grid, path M5 19H12V12H19V5, start dot r2.6, end dot r3.4, all `currentColor`) + wordmark "Floor" + lighter "wise" | `frontend/app/src/ui/Logo.tsx` | read |
| C2 | Logo styles use the theme tokens (`--ink`, `--ink-2`), so they follow light/dark | `frontend/app/src/styles.css` `.logo*` | read |
| C3 | Logo shown at the top of the map panel header (above "Buildings") and of the list page header (above "Find a building"), with spacing rules in their CSS | `src/map/MapLanding.tsx`, `src/map/map.css`, `src/search/BuildingSearch.tsx`, `src/search/search.css` | diff |
| C4 | `public/favicon.svg` is the same mark, black in light and white in dark system theme | `frontend/app/public/favicon.svg` | read |
| C5 | Type-check + build pass; oxlint clean on the changed files | — | `cd frontend/app && npm run build`; `npx oxlint src/ui/Logo.tsx src/map/MapLanding.tsx src/search/BuildingSearch.tsx` → exit 0, no output |
| C6 | Log entry 2026-10-28 16:50 (logo, GitHub deployments setting, deleted records, homepage) | `memory-bank/log.md` | read; `python3 scripts/check_links.py` |

## Checks I ran
- `npm run build` → `✓ built in 1.21s` (tsc -b first).
- `npx oxlint` on the three changed TSX files → exit 0, no warnings.
- Screenshots (headless Chrome on `vite preview`): list page shows the mark + "Floorwise" above "Find a building"; map page (with `--enable-unsafe-swiftshader --use-angle=swiftshader`) shows it top left of the panel above "Buildings". Both in the dark theme; light theme not screenshotted.
- `python3 scripts/check_links.py` → OK.

## Knowledge base updates
- [ ] `memory-bank/project-state.md` — not needed (small UI addition; log carries it)
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none
- [ ] docs: none (visualization.md doesn't describe the landing header)

## Known gaps / not done
- Light theme not checked by screenshot (styles use the same tokens as the text around it).
- Building screen and Import screen have no logo (only the two landing views, the top left the user sees first).
- No frontend unit tests exist for these views.

## Verification rounds
- round 1: verifier stopped (tree changed), reviewer PASS (MINOR R1: favicon CSS stroke rule hit the circles — fixed, circles fill-only, stroke only on the path; MINOR R2: `.tsx` in the Logo imports — kept, Root.tsx imports its components the same way)
- round 2: verifier PASS, reviewer PASS (MINOR R1: narrow-screen logo margin — cosmetic, left)

## Verifier report (round 2)

VERDICT: PASS
TREE: bfd08373fb0be468016d6639ba7071340fad56d5

C1–C6 MET (Logo.tsx mark + wordmark; theme tokens; placed on the map panel and list page; favicon same mark, fill-only circles; build + oxlint clean; log entry). Standard checks: pytest 1061 passed, 2 skipped; links OK; ruff new 0; secrets none; score.py unchanged.

## Reviewer report (round 2)

REVIEW: PASS
TREE: bfd08373fb0be468016d6639ba7071340fad56d5

| # | Severity | Where | Problem | Failure scenario | Suggested fix |
|---|---|---|---|---|---|
| R1 | MINOR | frontend/app/src/map/map.css:15 | logo margin not reduced in the narrow-screen query | cosmetic only | smaller margin in the media query |
