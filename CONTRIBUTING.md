# Contributing

## Repositories

The workspace is four git repos. Run git, install, test and deploy commands from inside the matching
folder, and never commit an app folder into the root repo.

| Repo | Branches | Holds |
| --- | --- | --- |
| root (this folder) | `development`, `main` | README, `CLAUDE.md`, `docs/`, `docker-compose.yml`, `.env.example` |
| `kampusping-backend/` | its own `.git` | FastAPI API, migrations, CLI, worker |
| `kampusping-frontend/` | its own `.git` | Next.js web app |
| `kampusping-wa-gateway/` | its own `.git` | Node WhatsApp gateway |

## Workflow

- Work on `development` (or a branch cut from it); `main` is the release branch and receives
  changes only through reviewed pull requests. Exception: `kampusping-backend` and
  `kampusping-frontend` currently work on `refactor/universal-template`, because their
  `development` branch still holds the older lineage this project was built from.
- Keep each commit to one logical change; commit inside the repo the change belongs to.
- Never push, merge, tag or deploy unless explicitly asked. Mark releases with tags such as `v1.2.0`.

## Language

- **UI strings and WhatsApp message text are Indonesian**, written inline (no i18n framework; locale
  `id-ID`). API error messages shown to users are Indonesian too.
- **Code, identifiers, API field names, migrations, ADRs, comments and commit messages are
  English.** The BRD and the design spec are Indonesian; the two operator documents
  (`docs/runbook-whatsapp.md`, `docs/manual-smoke-test.md`) are Indonesian because campus staff and IT
  run them.

## Commit messages (Conventional Commits)

`<type>: <short, clear description>`, for example `fix: return 409 for a duplicate email`.

| Type | Use for |
| --- | --- |
| `feat`, `fix`, `refactor`, `perf`, `style`, `test` | Code changes |
| `docs`, `chore`, `deps`, `config`, `build`, `ci` | Docs and maintenance |
| `db`, `migration`, `seed` | Schema, migration files, seed data |
| `api`, `ui`, `ux` | Endpoint contract, visuals, flows |
| `security`, `hotfix`, `release`, `revert` | Safety and releases |

Requirement codes (FR-xx, NFR-xx, AB-xx, BR-xx from the BRD) may appear in code comments, tests and
commit bodies.

## Before you push

Backend (`kampusping-backend/`, inside the virtualenv):

```bash
ruff check . && ruff format --check . && pyright && pytest
```

Frontend (`kampusping-frontend/`) and gateway (`kampusping-wa-gateway/`):

```bash
npm run check          # lint, typecheck, format check, unit tests
npm run build          # frontend and gateway
```

CI runs the same commands. For changes that touch both the API and the UI, also run the e2e suite
(`kampusping-frontend/e2e/README.md`) with `WA_PROVIDER=fake`; end-to-end runs must never use the
real WhatsApp gateway. Changes to the gateway need the manual test on a real phone
(`docs/manual-smoke-test.md`) before a release.

## Guidelines

- Authorization is enforced on the server with permission codes (`require_permissions(...)`). Never
  branch on role names or ids, and never rely on hiding UI.
- No secrets, hosts or credentials in committed files; add new settings to the `*.example` env files.
- New business tables inherit `AuditedModel` and get a hand-written Alembic migration with a working
  `downgrade()`. Migrations are numbered and named descriptively (`006_messages.py`); never reuse a
  revision id that may already exist in someone's database.
- New screens use the `App*` components and theme tokens (no hex literals).
- Inject the clock (`Clock`) instead of reading system time in business rules, so tests never depend
  on it. Timestamps are stored in UTC; business dates use `APP_TIMEZONE`.
- Phone numbers and NIM are personal data (UU PDP): mask phone numbers in logs and return only what a
  screen needs.
- Ask before adding a library that is not already in the project.
- Add tests with the change, including the failure and 401/403 cases.
