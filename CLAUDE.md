# Universal Web App Template (backend + frontend workspace)

<!-- Company rules (C:/hino-fullstack-rules/RULES.md) load from ~/.claude/CLAUDE.md.
     This template intentionally deviates from some of them: see "Deviations" at the bottom. -->

## Overview

- Purpose: a universal, brand-neutral starter for business web apps: FastAPI backend + Next.js/MUI frontend with local JWT auth and RBAC. Real projects are created from it with `python scripts/init.py`; nothing here is a business app.
- Status: transformed from the Hino HIS standard template (tag `hino-final` in both repos marks the last Hino version).
- Auth: local users/roles/permissions in the app database. **No IAM, no launcher, no Hino branding.**
- Related systems: none. Do not add integrations to the template itself.

## Layout

Each app folder is its **own git repo** (own `.git`, `.gitignore`, history); the workspace root repo holds the shared files (README, `docker-compose.yml`, `scripts/init.py`, `docs/`, this file). Run git, install, test and deploy commands from inside the matching folder.

| Folder                                | Stack                                                        |
| ------------------------------------- | ------------------------------------------------------------ |
| [webapp-backend/](webapp-backend/)    | FastAPI, async SQLAlchemy 2, Alembic, Argon2 + JWT, pytest   |
| [webapp-frontend/](webapp-frontend/)  | Next.js 16, React 19, MUI 9, React Hook Form + Zod, Zustand  |

Reference modules to copy: `webapp-backend/app/modules/example/` and `webapp-frontend/src/modules/example/`. Read each repo's README and `docs/` first.

## Commands

Backend commands run in `webapp-backend/`, frontend commands in `webapp-frontend/`.

| Task                          | Backend                                            | Frontend                                |
| ----------------------------- | -------------------------------------------------- | --------------------------------------- |
| Install                       | `pip install -r requirements-dev.txt` (in `.venv`) | `npm install`                           |
| Run dev                       | `uvicorn app.main:app --reload` (:8000)            | `npm run dev` (:3000)                   |
| Migrate                       | `alembic upgrade head`                             | n/a                                     |
| New migration                 | `alembic revision -m "<message>"`                  | n/a                                     |
| First admin / seed            | `python -m app.cli create-admin` / `seed`          | n/a                                     |
| Test                          | `pytest`                                           | `npm test` (unit), `npm run test:e2e`   |
| Quality gate                  | `ruff check . && ruff format --check . && pyright` | `npm run check`                         |
| Build                         | n/a                                                | `npm run build`                         |
| Deploy prod (only when asked) | `bash deploy/deploy-prod.sh --migrate --all`       | `bash deploy/deploy-prod.sh --all`      |

## Project specifics

- PM2 names: `webapp-backend`, `webapp-frontend` (production ports 8093 / 8094). `scripts/init.py` renames everything for a real project.
- Tables: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `refresh_tokens`, `example_items` (migrations `001`, `002`). Business tables inherit `AuditedModel` (BIGINT id, audit columns, soft delete).
- Permissions are `resource:action` codes in `app/core/permissions.py` (mirrored in `src/core/auth/permissions.ts`); enforce them on the server with `require_permissions(...)`. Never branch on role names or ids.
- API contract: plain success bodies, errors as `{"error": {"code", "message", "details"}}`, lists as `{items, total, page, page_size}`.
- Database: PostgreSQL by default; MySQL, SingleStore (best-effort, untested) and SQLite (dev/tests only) are supported through the async drivers.
- Tests: backend 63 pytest cases; frontend 53 Vitest tests + 7 Playwright e2e tests (need the backend running, see `webapp-frontend/e2e/README.md`).
- Ports 3000/8000 are often taken on developer machines; run e2e on other ports (see the e2e README).

## Known limitations

- `docker-compose.yml` and both Dockerfiles have not been run (no Docker on the machine where they were written). Build them before relying on them.
- SingleStore and MySQL paths are untested; `SHARD KEY` / `SORT KEY` DDL is not generated (see `webapp-backend/docs/database.md`).
- Route protection in the frontend is client-side (the refresh cookie is scoped to the API path, so Next.js middleware cannot see the session). The API is the real gate.
- No i18n (dates/numbers honour `NEXT_PUBLIC_LOCALE`; UI strings are English).
## Skill routing

Use the matching skill automatically; do not wait for me to name it. Skip any skill that is not installed.
If several rows match, run process skills first (brainstorming, debugging, planning), then domain skills.
**The rules in this file and each repo's README/`docs/` override any skill's advice** (stack, folder layout, `App*` components, theme tokens, permission codes instead of role ids, no deploy without my request). If a skill suggests something that conflicts, follow the rules and mention the conflict.

### Planning & process

| Context                                                                      | Skill                                         |
| ---------------------------------------------------------------------------- | --------------------------------------------- |
| New feature or behavior change (before any code)                             | `brainstorming`, then `writing-plans`         |
| Migrating an existing app onto this template                                 | `writing-plans` + `engineering:system-design` |
| Architecture decision, tech choice, trade-offs (ADR)                         | `engineering:architecture`                    |
| New module/service boundaries, data modeling, external integrations          | `engineering:system-design`                   |
| Starting feature work that needs isolation                                   | `using-git-worktrees`                         |
| Executing a written plan (inline)                                            | `executing-plans`                             |
| Executing a plan with independent tasks                                      | `subagent-driven-development`                 |
| 2+ independent tasks with no shared state                                    | `dispatching-parallel-agents`                 |

### Implementation

| Context                                                                                         | Skill                                             |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Implementing a feature or bugfix                                                                | `test-driven-development` (pytest on the backend) |
| Feature spanning FastAPI + Next.js + SingleStore                                                | `fullstack-guardian`                              |
| REST endpoint design under `/api/v1`, request/response schemas                                  | `api-designer`                                    |
| React components, hooks, RHF/Zod forms, Zustand state                                           | `react-expert`                                    |
| Next.js App Router pages, layouts, routing                                                      | `nextjs-developer`                                |
| Shared types, API response types, generics                                                      | `typescript-pro`                                  |
| SingleStore schema (SHARD/SORT KEY), slow queries, MySQL/PostgreSQL/MSSQL → SingleStore mapping | `sql-pro`                                         |
| PostgreSQL tuning, EXPLAIN, JSONB                                                               | `postgres-pro`                                    |
| JWT/refresh-token handling, permission checks, input validation, OWASP hardening                | `secure-code-guardian`                            |

### UI & design (within this template's design system)

| Context                                                | Skill                                                                                                  |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| New page or screen layout                              | `frontend-design`, constrained to the frontend README (`App*` components, theme tokens, Inter)         |
| Figma link → code                                      | `figma:figma-design-to-code`                                                                           |
| Accessibility / WCAG check                             | `design:accessibility-review`                                                                          |
| Component states, tokens, handoff spec                 | `design:design-handoff`                                                                                |
| Microcopy, error messages, empty states, button labels | `design:ux-copy`                                                                                       |
| Charts, dashboards, KPI tiles                          | `dataviz`                                                                                              |

### Testing & debugging

| Context                                                       | Skill                                                                   |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Test strategy / test plan                                     | `engineering:testing-strategy`                                          |
| Unit / integration tests (pytest, incl. 401/403 access tests) | `test-master`                                                           |
| E2E / browser tests (login → page → CRUD)                     | `playwright-expert`                                                     |
| Bug, stack trace, failing test                                | `systematic-debugging` (plus `debugging-wizard` for log/stack analysis) |
| Works in dev but not prod, regression after deploy            | `engineering:debug`                                                     |

### Review & release

| Context                                                                            | Skill                                                              |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Reviewing a diff or PR                                                             | `code-reviewer` (plus `engineering:code-review` for security/perf) |
| Requesting review after a major feature                                            | `requesting-code-review`                                           |
| Receiving review feedback                                                          | `receiving-code-review`                                            |
| PM2 / Nginx configs, `deploy/` scripts, CI/CD pipeline                             | `devops-engineer`                                                  |
| Preparing a release with Alembic migrations (prepare only; deploy only when I ask) | `engineering:deploy-checklist`                                     |
| Production incident, postmortem                                                    | `engineering:incident-response`                                    |
| Before claiming work is done                                                       | `verification-before-completion`                                   |
| Work done and tests pass, deciding merge/PR to `development`                       | `finishing-a-development-branch`                                   |

### Docs & maintenance

| Context                                       | Skill                       |
| --------------------------------------------- | --------------------------- |
| README, runbook, API docs, onboarding guide   | `engineering:documentation` |
| Refactor priorities, code health, legacy debt | `engineering:tech-debt`     |

## Deviations from company rules

Approved on 2026-10-30 when this template was turned into a universal one. `C:/hino-fullstack-rules/RULES.md` itself is unchanged and still applies to Hino HIS projects, which should start from the `hino-final` tag, not from this template.

- Section 0 (standard repos): this workspace **replaces** the HIS standard repos as the starting point for new projects.
- Section 3 (stack): same FastAPI/Next.js/MUI stack, but the database default is PostgreSQL (SingleStore optional), the UI font is Inter instead of Poppins, and the HIS design system tokens are replaced by neutral ones. New libraries approved: PyJWT, argon2-cffi, slowapi, aiosqlite, pytest-asyncio, pyright (backend); MUI X Charts, Vitest, Testing Library, Playwright (frontend).
- Section 4 (database): tables use `BIGINT` ids with audit columns and soft delete, but not `AS SEQUENCE` / `SHARD KEY` / `SORT KEY`, and time is stored in UTC, not Asia/Jakarta.
- Section 9 (auth): local email + password login with JWT and refresh cookies replaces HIS IAM. Local user and role tables are allowed here by design.
- Section 7 (runtime): PM2 + Nginx are kept; ports are 8093 (API) and 8094 (web).