# KampusPing: tuition billing reminders over WhatsApp

<!-- The global ~/.claude/CLAUDE.md imports the Hino HIS rules. They do NOT apply to this project;
     see "Rules that do not apply". -->

## Rules that do not apply

This project has nothing to do with PT Hino Motors Sales Indonesia. **Ignore `C:/hino-fullstack-rules/RULES.md`** and anything it points to (`C:/company-rules/...`, HIS standard repos, HIS IAM, SingleStore `SHARD KEY` / `SORT KEY` / `AS SEQUENCE`, Poppins/HIS design system, `app_now()`, the Hino commit-type list). Do not ask me before deviating from them. The rules in this file and in each repo's README/`docs/` are the only project rules.

## Overview

- Purpose: a system for the Finance Department (Bagian Keuangan) of a campus. It imports tuition invoices and payment status from **SIAKAD/Civitas** and **SIPEMA** export files (CSV/Excel only, no API, no direct database access), then sends scheduled WhatsApp reminders to students who have not paid. Payment itself stays in SIAKAD/SIPEMA.
- Source of requirements: [docs/BRD-penagihan-uang-kuliah-whatsapp.md](docs/BRD-penagihan-uang-kuliah-whatsapp.md) (BRD v0.1, Indonesian). Requirement codes (FR-xx, NFR-xx, AB-xx, BR-xx) in code comments, tests and commits refer to it.
- Design: [docs/superpowers/specs/2026-10-31-kampusping-design.md](docs/superpowers/specs/2026-10-31-kampusping-design.md). Decisions: `docs/adr/` (0001 local auth, 0002 Baileys gateway, 0003 database queue + worker).
- Origin: built on a universal web-app template (FastAPI + Next.js/MUI + local JWT/RBAC); the template's `example` module and the `webapp-*` names are gone.
- Auth: local users/roles/permissions in the app database. No external IAM.
- Status (2026-11-02): **milestone M1 (MVP) is implemented and reviewed** (import, students/invoices, templates and schedules, settings, queue + worker + sender with the FR-06 re-check, Baileys gateway, send log, dashboard, roles/permissions, audit, Indonesian UI). **M2 and M3 have not started**: no reply inbox, no opt-out by keyword (STOP replies are not read), no manual/bulk send, no exemption screen, no Excel/PDF export, no `replies` table. The enforcement points for opt-out (`students.opted_out_at`) and exemption (`invoices.exempt_reason`) exist, but nothing sets them yet. Check `git log` and `docs/superpowers/plans/` before assuming a feature exists.
- Real sending through Baileys has never been verified on a phone by an agent: the manual test is `docs/manual-smoke-test.md` (the user runs it).

## Layout

Each app folder is its **own git repo** (own `.git`, `.gitignore`, history); the workspace root repo holds shared files (README, `docker-compose.yml`, `.env.example`, `docs/`, this file; `scripts/init.py` is the legacy template initialiser, see Project specifics). Run git, install, test and deploy commands from inside the matching folder. Do not commit the app folders into the root repo.

| Folder                                       | Stack                                                                   |
| -------------------------------------------- | ----------------------------------------------------------------------- |
| [kampusping-backend/](kampusping-backend/)   | FastAPI, async SQLAlchemy 2, Alembic, Argon2 + JWT, pytest; also hosts the worker (`python -m app.cli run-worker`) |
| [kampusping-frontend/](kampusping-frontend/) | Next.js 16, React 19, MUI 9, React Hook Form + Zod, Zustand            |
| [kampusping-wa-gateway/](kampusping-wa-gateway/) | Node 20+, TypeScript, Baileys, Fastify, pino; owns the WhatsApp session |

```text
Browser ─► Next.js ─► FastAPI ─► PostgreSQL ◄─ Worker ──(WhatsAppProvider)─► Gateway (Baileys) ─► WhatsApp
                          ▲                                                      │
                          └──────────── webhook: delivery status, replies ───────┘
```

Read each repo's README and `docs/` first (for the message queue, planner and sender read `kampusping-backend/docs/messaging.md`). For new backend modules follow `kampusping-backend/docs/adding-a-module.md`; the frontend counterpart is `kampusping-frontend/src/modules/README.md`.

## Commands

Backend commands run in `kampusping-backend/` (inside `.venv`; if the `.venv/Scripts/*.exe` launchers fail, use `python -m pytest|ruff|pyright`), frontend commands in `kampusping-frontend/`, gateway commands in `kampusping-wa-gateway/`. For any local python command set `DATABASE_ENGINE=sqlite` and `DATABASE_URL=sqlite+aiosqlite:///<a file outside the repo>`: the backend `.env` may point at a remote database, so never run migrations or the worker against it without being asked.

| Task                          | Backend                                            | Frontend                                | Gateway                       |
| ----------------------------- | -------------------------------------------------- | --------------------------------------- | ----------------------------- |
| Install                       | `pip install -r requirements-dev.txt`              | `npm install`                           | `npm install`                 |
| Run dev                       | `uvicorn app.main:app --reload` (:8000)            | `npm run dev` (:3000)                   | `npm run dev` (127.0.0.1:8095)|
| Worker                        | `python -m app.cli run-worker` (`--once` = one tick; exactly ONE instance) | n/a             | n/a                           |
| Migrate                       | `alembic upgrade head` (`alembic current`, `alembic check`) | n/a                            | n/a                           |
| New migration                 | `alembic revision -m "<message>"`                  | n/a                                     | n/a                           |
| First admin / seed            | `python -m app.cli create-admin` / `seed`          | n/a                                     | n/a                           |
| Other CLI                     | `python -m app.cli purge-tokens`                   | n/a                                     | n/a                           |
| Test                          | `pytest`                                           | `npm test` (unit), `npm run test:e2e`   | `npm test`                    |
| Quality gate                  | `ruff check . && ruff format --check . && pyright` (+ `pytest`) | `npm run check`            | `npm run check`               |
| Build                         | n/a                                                | `npm run build` (then `npm start`)      | `npm run build` (then `npm start`) |
| Deploy prod (only when asked) | `bash deploy/deploy-prod.sh --migrate --all`       | `bash deploy/deploy-prod.sh --all`      | `bash deploy/deploy-prod.sh`  |

The whole stack in Docker: `docker compose up --build` (fake provider) or `docker compose --profile whatsapp up --build` (with the gateway); neither has been built or run yet.

For local work without a WhatsApp number, set `WA_PROVIDER=fake`: the backend records messages in memory instead of calling the gateway. **End-to-end tests must always use `WA_PROVIDER=fake`** and never start the gateway. Run them with `E2E_FAKE_PROVIDER=1` (the settings spec is skipped without it); the full setup is in `kampusping-frontend/e2e/README.md`.

## Project specifics

- PM2 names: `kampusping-backend`, `kampusping-worker`, `kampusping-wa-gateway`, `kampusping-frontend` (production ports 8093 API / 8094 web; the gateway listens only on 127.0.0.1:8095). `scripts/init.py` was the template initialiser (names, ports, brand color); it already ran, it is **legacy** and no longer needed. The file is kept; do not run it.
- Language: **UI strings and WhatsApp message text are Indonesian** (written inline, no i18n framework; locale `id-ID`). Code, identifiers, API field names, migrations, ADRs, comments and commit messages are English. The BRD and the design spec are Indonesian. Chat with me in Indonesian.
- Tables (migrations 001-008): `users`, `roles`, `permissions`, `user_roles`, `role_permissions`, `refresh_tokens`, `app_settings`, `audit_events`, `students`, `invoices`, `import_batches`, `import_row_errors`, `import_changes`, `message_templates`, `schedule_rules`, `messages`. There is **no `replies` table yet** (M3). Business tables inherit `AuditedModel` (BIGINT id, audit columns, soft delete). Migration revision `002` was reused (the template's `002_create_example_items` became `002_app_settings_and_audit`): a database created from the old template needs the repair in `kampusping-backend/docs/database.md` before `alembic upgrade head`.
- Import rollback (post-M1): the latest applied import can be rolled back from Impor Data (`POST /imports/{id}/rollback`, permission `imports:rollback`, **admin only**; `staf_keuangan` is explicitly excluded in `app/core/permissions.py`). It uses the `import_changes` log written by apply; imports applied before migration 008 have no log and cannot be rolled back. A rollback is refused as a whole (409) if any affected row changed since the import. Design: `docs/superpowers/specs/2026-11-10-import-rollback-design.md`.
- Permissions are `resource:action` codes in `app/core/permissions.py` (mirrored in `src/core/auth/permissions.ts`); enforce them on the server with `require_permissions(...)`. Never branch on role names or ids. System roles: `admin`, `staf_keuangan`, `pimpinan` (read-only dashboard and reports).
- API contract: plain success bodies, errors as `{"error": {"code", "message", "details"}}`, lists as `{items, total, page, page_size}`; routes under `/api/v1`.
- Database: PostgreSQL by default; SQLite for dev/tests only. Timestamps are stored in UTC; business dates ("today", send window) use `APP_TIMEZONE=Asia/Jakarta`. Inject the clock so tests never depend on system time.
- Libraries added for this project: backend runtime `openpyxl` (Excel import), `python-multipart` (file upload), `tzdata` (time zones on Windows) and `httpx` (gateway client); gateway `@whiskeysockets/baileys` (6.7.24, exact), `fastify`, `pino`; frontend `qrcode.react` (pairing QR). `reportlab` (PDF) is **not added yet** (M3). Ask before adding anything else.
- Tests (last full run, 2026-11-02): backend pytest 675 passed; frontend Vitest 302 tests in 32 files; gateway Vitest 93 tests in 12 files; Playwright e2e 13 tests (8 in `app.spec.ts`, 5 in `billing.spec.ts`; needs the stack, see `kampusping-frontend/e2e/README.md`). Counts change as milestones land; do not trust them here, re-run the suites.
- Ports 3000/8000 are often taken on developer machines; run e2e on other ports (see the e2e README).

## Business rules to keep intact

These come from the BRD and must not be weakened without asking me:

- **AB-01 / FR-06:** a message is sent only for an unpaid invoice, and status, opt-out, exemption and phone validity are re-checked from the database immediately before sending. Paid is sticky across import sources.
- **AB-02:** default schedule H-7, H-3, H-1, H, H+3, H+7 (rules are data, edited by staff).
- **AB-03:** at most one automatic message per student per day.
- **AB-04:** sending only inside the send window (default 08:00-17:00 WIB, Monday to Friday).
- **AB-05:** exempted students (keringanan/cicilan) get no billing messages.
- **AB-06 / FR-11:** opt-out (`STOP`, `BERHENTI`, `UNSUBSCRIBE`) is honoured immediately; every automatic message carries the "Balas STOP untuk berhenti" footer.
- **AB-07:** automatic messages stop after the escalation offset (default H+14); staff take over.
- **AB-08:** polite, informative tone, never threatening.
- **NFR-08:** no direct connection to SIAKAD/Civitas/SIPEMA; data enters only through uploaded export files.
- Phone numbers and NIM are personal data (UU PDP): mask phone numbers in logs, expose only what a screen needs.

## Known limitations

- **Baileys is an unofficial WhatsApp library** and violates WhatsApp's terms; the number can be banned. This deviates from the BRD recommendation (see ADR 0002). Use a dedicated number and keep the safeguards (throttle, daily cap, send window, opt-out, circuit breaker). Real sending cannot be verified by automated tests; it needs a manual smoke test on a real phone.
- The re-check before sending only sees the latest imported data; payments after the last import are invisible.
- Public holidays are not known; the send window uses Monday to Friday only.
- `docker-compose.yml` and the Dockerfiles have not been run (no Docker on the machine where they were written). Build them before relying on them.
- Route protection in the frontend is client-side (the refresh cookie is scoped to the API path, so Next.js middleware cannot see the session). The API is the real gate.
- Message and student data retention is not defined yet (UU PDP); the campus has to decide.
- Baileys depends on `libsignal` (GPL-3.0) while the repos are MIT: fine for a self-hosted internal service; reconsider if KampusPing is distributed or sold as closed software.
- The gateway relays webhook events from an in-memory queue. A receipt is dropped when the backend's commit of a send takes longer than the gateway delay plus retries (`WA_STATUS_DELAY_MS`, `WA_WEBHOOK_RETRIES`; the 30 s replay `WA_STATUS_REPLAY_MS` mitigates it) or when the gateway stops with events still queued. The effect is a message that stays at `sent` instead of `delivered`/`read`.
- Existing databases: `staf_keuangan` is created once by the seed and does **not** auto-gain permissions added by later milestones (only `admin` is re-synced); handle it in the M3 plan.
- `scripts/init.py` is legacy (see Project specifics).
- The Docker artifacts (compose file and the backend, gateway and frontend Dockerfiles) were never built or run. The gateway session volume is mounted at `/app/session` with `WA_AUTH_DIR=/app/session/auth_state` by reasoning, not by test.
- The Playwright settings spec is skipped unless `E2E_FAKE_PROVIDER=1` is set (the API cannot tell the fake provider from a real gateway).
- Opt-out (a STOP reply) and exemptions have enforcement points but nothing sets them in M1; until M3 a "stop" request must be handled by a person.

## Where things are

| Need | Look at |
| --- | --- |
| Operating the WhatsApp number (QR, disconnect, ban, backup, secret rotation), Indonesian | `docs/runbook-whatsapp.md` |
| The manual real-phone test the user runs, Indonesian | `docs/manual-smoke-test.md` |
| Message lifecycle, planner and sender rules, retry, circuit breaker, gateway contract, AB-01..AB-08 in code | `kampusping-backend/docs/messaging.md` |
| A database created from the old template | `kampusping-backend/docs/database.md` |
| Decisions | `docs/adr/` (0001 local auth, 0002 Baileys gateway and its requirements, 0003 queue + worker) |
| Requirements, design, plan | `docs/BRD-penagihan-uang-kuliah-whatsapp.md`, `docs/superpowers/specs/`, `docs/superpowers/plans/` |
| Gateway HTTP contract, configuration, data on disk | `kampusping-wa-gateway/README.md` |
| End-to-end tests | `kampusping-frontend/e2e/README.md` |

## Git

Work happens on `development`; `main` is the release branch (exception: `kampusping-backend` and `kampusping-frontend` currently work on `refactor/universal-template`; their `development` branch holds the older lineage). Commit messages use Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`, ...), one logical change per commit. Never push, merge, tag or deploy unless I explicitly ask.

## Skill routing

Use the matching skill automatically; do not wait for me to name it. Skip any skill that is not installed.
If several rows match, run process skills first (brainstorming, debugging, planning), then domain skills.
**The rules in this file and each repo's README/`docs/` override any skill's advice** (stack, folder layout, `App*` components, theme tokens, permission codes instead of role ids, no deploy without my request). If a skill suggests something that conflicts, follow the rules and mention the conflict.

### Planning & process

| Context                                                                      | Skill                                         |
| ---------------------------------------------------------------------------- | --------------------------------------------- |
| New feature or behavior change (before any code)                             | `brainstorming`, then `writing-plans`         |
| Architecture decision, tech choice, trade-offs (ADR)                         | `engineering:architecture`                    |
| New module/service boundaries, data modeling, external integrations          | `engineering:system-design`                   |
| Starting feature work that needs isolation                                   | `using-git-worktrees`                         |
| Executing a written plan (inline)                                            | `executing-plans`                             |
| Executing a plan with independent tasks                                      | `subagent-driven-development`                 |
| 2+ independent tasks with no shared state                                    | `dispatching-parallel-agents`                 |

### Implementation

| Context                                                                          | Skill                                             |
| -------------------------------------------------------------------------------- | ------------------------------------------------- |
| Implementing a feature or bugfix                                                 | `test-driven-development` (pytest on the backend) |
| Feature spanning FastAPI + Next.js + the gateway                                 | `fullstack-guardian`                              |
| REST endpoint design under `/api/v1`, request/response schemas, webhooks         | `api-designer`                                    |
| React components, hooks, RHF/Zod forms, Zustand state                            | `react-expert`                                    |
| Next.js App Router pages, layouts, routing                                       | `nextjs-developer`                                |
| Shared types, API response types, generics, the Node gateway                     | `typescript-pro`                                  |
| PostgreSQL schema, indexes, slow queries, JSONB                                  | `postgres-pro` (plus `sql-pro` for query design)  |
| JWT/refresh-token handling, permission checks, webhook signing, input validation | `secure-code-guardian`                            |

### UI & design

| Context                                                | Skill                                                                                          |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| New page or screen layout                              | `frontend-design`, constrained to the frontend README (`App*` components, theme tokens, Inter) |
| Figma link → code                                      | `figma:figma-design-to-code`                                                                   |
| Accessibility / WCAG check                             | `design:accessibility-review`                                                                  |
| Component states, tokens, handoff spec                 | `design:design-handoff`                                                                        |
| Microcopy, error messages, empty states, button labels (Indonesian) | `design:ux-copy`                                                          |
| Charts, dashboards, KPI tiles                          | `dataviz`                                                                                      |

### Testing & debugging

| Context                                                       | Skill                                                                   |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Test strategy / test plan                                     | `engineering:testing-strategy`                                          |
| Unit / integration tests (pytest, incl. 401/403 access tests) | `test-master`                                                           |
| E2E / browser tests (login → import → send log)               | `playwright-expert`                                                     |
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
| Work done and tests pass, deciding merge/PR to `development`                      | `finishing-a-development-branch`                                   |

### Docs & maintenance

| Context                                       | Skill                       |
| --------------------------------------------- | --------------------------- |
| README, runbook, API docs, onboarding guide   | `engineering:documentation` |
| Refactor priorities, code health              | `engineering:tech-debt`     |
