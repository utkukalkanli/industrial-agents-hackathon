---
id: ci-cd
summary: GitHub Actions CI/CD on our own Supabase + Vercel accounts — what runs when, one-time setup, secrets, rollback.
sources: [.github/workflows/ci.yml, .github/workflows/deploy.yml, .github/dependabot.yml, vercel.json, .vercelignore, scripts/smoke_test.py, supabase/migrations/]
related: [commands.md, dev-workflow.md, ../architecture/overview.md, ../../memory-bank/decisions.md]
---

# CI/CD (GitHub Actions → Supabase + Vercel)

[Docs index](../README.md) · Decision: [D-024](../../memory-bank/decisions.md#d-024) · Manual deploy notes:
[commands.md](commands.md#deploy-vercel)

Repository: `utkukalkanli/industrial-agents-hackathon`, detached from Atahan's fork network on 2026-10-25 (nothing here
affects his repo or deployment). Our own Supabase project and
Vercel project, not Atahan's deployment. GitHub Actions does both CI and the deploys; Vercel's own Git deploys are
off (`"git": {"deploymentEnabled": false}` in `vercel.json`), so a deploy only happens after the checks pass.

## What runs when

| Event | Workflow | Jobs |
|---|---|---|
| Pull request | `ci.yml` | `python`, `integration`, `frontend` in parallel → `preview` (same-repo PRs) |
| Push to any branch but `main` | `ci.yml` | `python`, `integration`, `frontend` |
| Push to `main` (= a merged PR) | `deploy.yml` | `ci` (all of `ci.yml`) → `migrate` → `deploy` |
| Weekly | Dependabot | PRs for Actions, `uv` and `npm` updates (each runs CI + preview) |

- **`python`** — `uv sync --locked`, `scripts/check_links.py`, `pytest -n auto` (pytest-xdist). Includes the
  whole-dataset regression tests (solvers on train+dev, warm-up routes, benchmark replies); ~4–6 min. Always the
  offline Guide (`GUIDE_LLM=offline`): CI never calls a model and needs no API key.
- **`integration`** — a `postgres:17` service container; `supabase db push --db-url … --include-all` applies
  `supabase/migrations/` (the same command as production), a dry run then must find nothing left; the live store
  tests (`PERSIST_LIVE_TEST=1 pytest -k live_postgres`: conversations, drafts, saved buildings); then uvicorn on that
  database and `scripts/smoke_test.py --chat` (health, buildings, create + read a conversation, one Guide turn that
  must remember "I use a wheelchair").
- **`frontend`** — `npm ci`, `npm run lint` (oxlint), `npm run build` (`tsc -b` + Vite).
- **`preview`** — `vercel deploy` (remote build of both services), `smoke_test.py --frontend` against the preview
  URL, a sticky PR comment with the URL. Skipped for PRs from forks (no secrets there).
- **`migrate`** — dry run (prints pending migrations), then `supabase db push` on the production database.
- **`deploy`** — `vercel deploy --prod --skip-domain` → smoke test that deployment → `vercel promote` (only now
  does the production domain move) → smoke test `PRODUCTION_URL` if that variable is set.

A failing smoke test leaves production on the previous deployment. Migrations run before the deploy and must stay
additive (`create … if not exists`, new nullable columns); a breaking change needs two releases (expand, then
contract).

## One-time setup

### 1. Supabase (production database)

1. [supabase.com](https://supabase.com) → New project (note the database password).
2. Project → **Connect**:
   - *Transaction pooler* URI (port 6543) → the app's `SUPABASE_DB_URL` (Vercel, step 2).
   - *Session pooler* URI (port 5432) → GitHub secret `SUPABASE_MIGRATIONS_DB_URL` (step 3). Migrations need a
     session connection; the transaction pooler does not keep one. Percent-encode special characters in the password.
3. Project Settings → API Keys: `SUPABASE_URL`, publishable key (`SUPABASE_ANON_KEY`), secret key
   (`SUPABASE_SERVICE_ROLE_KEY`) — only needed with `ACCESS_MODE=on`.
4. Nothing to run by hand: the first `deploy.yml` run applies every migration.

Optional staging: a second Supabase project for previews (Vercel *Preview* env vars point at it). Without one,
previews use whatever `SUPABASE_DB_URL` the Preview environment has — leave it unset to run previews without a
database (sessions in memory, `/drafts` 503).

### 2. Vercel project

1. Vercel → *Add New → Project* → import `utkukalkanli/industrial-agents-hackathon`, Root Directory = repo root
   (`vercel.json` defines the `web` and `api` services). Git deploys stay off because of `vercel.json`.
2. Settings → Environment Variables (Production, and Preview where wanted) — the table in
   [commands.md](commands.md#deploy-vercel) (`ANTHROPIC_API_KEY`, `SUPABASE_DB_URL`, `ELEVENLABS_API_KEY`, `GUIDE_MODEL`,
   …) plus, for access mode, `ACCESS_MODE`, `ADMIN_EMAIL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`.
3. Project ids: run `npx vercel link` once locally, then read `.vercel/project.json` (`orgId`, `projectId`;
   `.vercel/` is not committed). Or Settings → General (Project ID) and the team's Settings (Team ID).
4. Account Settings → Tokens → create a token for CI (scope: the team that owns the project).
5. If Deployment Protection (Vercel Authentication) is on for previews: Settings → Deployment Protection →
   *Protection Bypass for Automation* → copy the secret, so the smoke test can reach the preview.

### 3. GitHub (repo Settings)

*Secrets and variables → Actions*:

| Name | Kind | Value |
|---|---|---|
| `VERCEL_TOKEN` | secret | token from 2.4 |
| `VERCEL_ORG_ID` | secret | `orgId` from 2.3 |
| `VERCEL_PROJECT_ID` | secret | `projectId` from 2.3 |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | secret | from 2.5 (optional) |
| `SUPABASE_MIGRATIONS_DB_URL` | secret (environment `production`) | session pooler URI from 1.2 |
| `PRODUCTION_URL` | variable | e.g. `https://<project>.vercel.app` (optional, final smoke test) |

*Environments*: `production` and `preview` are created on the first run. Optional hardening on `production`:
required reviewers (a deploy waits for an approval), deployment branches = `main` only.

*Branches → Branch protection* for `main` (or a ruleset): require a pull request, require the status checks
`Python tests`, `Integration (Postgres + API)`, `Frontend lint + build`, block force pushes. With the GitHub CLI:

```bash
gh api -X PUT repos/utkukalkanli/industrial-agents-hackathon/branches/main/protection --input - <<'EOF'
{"required_status_checks": {"strict": true, "contexts": ["Python tests", "Integration (Postgres + API)", "Frontend lint + build"]},
 "enforce_admins": false, "required_pull_request_reviews": {"required_approving_review_count": 0},
 "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
EOF
```

*Code security → Dependabot*: the config is `.github/dependabot.yml`; enable Dependabot security updates too.

## Run the same checks locally

```bash
uv sync && uv run pytest -q -n auto                     # python job
uv run python scripts/check_links.py
cd frontend/app && npm ci && npm run lint && npm run build   # frontend job
# integration job (needs Docker):
docker run -d --rm --name pg -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:17
npx supabase@2.122.0 db push --db-url postgresql://postgres:postgres@localhost:55432/postgres --include-all --yes
PERSIST_LIVE_TEST=1 SUPABASE_DB_URL=postgresql://postgres:postgres@localhost:55432/postgres uv run pytest -q -k live_postgres
GUIDE_LLM=offline SUPABASE_DB_URL=… uv run uvicorn backend.app:app --port 8000 &
uv run python scripts/smoke_test.py http://127.0.0.1:8000 --chat
```

## New migrations

Add `supabase/migrations/<YYYYMMDDHHMMSS>_<name>.sql`, idempotent and additive. CI applies it to a fresh Postgres
on the PR; merging to `main` applies it to production before the new code goes live. `supabase db push` records
applied versions in `supabase_migrations.schema_migrations`.

## Rollback

- App: `npx vercel rollback --token …` (or Vercel → Deployments → *Instant Rollback*). The previous deployment is
  served at once; a rolled-back project stops auto-promoting until a `vercel promote`.
- Database: migrations are not reversed automatically; write a new forward migration.

## Versions and pins

Actions are pinned to commit SHAs (comment = version); Dependabot moves them. CLI versions sit in each workflow's
`env`: uv `0.13.5`, Supabase CLI `2.122.0`, Vercel CLI `65.2.0`, Node `24`, Python `3.12`.

## UNVERIFIED until the first run on our accounts

- `vercel deploy` (CLI, remote build) with the beta Services config; the upload honouring `.vercelignore`.
- `supabase db push --db-url` against the plain `postgres:17` service (no Supabase roles needed by our migrations).
- Cold start of the `api` function within the smoke test's retries (20 × 3 s).

## Related
- [commands.md](commands.md#deploy-vercel) · [dev-workflow.md](dev-workflow.md) · [overview.md](../architecture/overview.md)
