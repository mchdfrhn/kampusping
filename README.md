# Universal Web App Template

A production-minded starting point for business web applications: a **FastAPI** backend and a
**Next.js + MUI** frontend with local authentication, role-based access control, a reference CRUD
module and a tested, documented structure you can clone and make your own.

```text
Browser ──► Next.js (MUI, light/dark) ──► FastAPI ──► PostgreSQL
              login, guards, grids        JWT + RBAC     (MySQL / SQLite also supported)
```

| | |
| --- | --- |
| **Backend** [`webapp-backend/`](webapp-backend/README.md) | Async SQLAlchemy 2, Alembic, Argon2 + JWT with rotating refresh tokens, permission checks, soft delete, 63 tests |
| **Frontend** [`webapp-frontend/`](webapp-frontend/README.md) | Login, permission-aware navigation, dashboard, users, roles, example CRUD, 53 unit + 7 e2e tests |

## Try it

### Option A: Docker Compose

```bash
docker compose up --build
```

Open http://localhost:3000 and sign in with `admin@example.com` / `ChangeMe-12345`
(override with `ADMIN_EMAIL` / `ADMIN_PASSWORD`; see [`.env.example`](.env.example)).
API docs: http://localhost:8000/docs.

### Option B: Run each side directly

```bash
# backend: zero-setup with SQLite (PostgreSQL recommended for real use)
cd webapp-backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env     # set DATABASE_ENGINE=sqlite and DATABASE_URL=sqlite+aiosqlite:///./dev.db
alembic upgrade head && python -m app.cli create-admin
uvicorn app.main:app --reload

# frontend (another terminal)
cd webapp-frontend
cp .env.example .env.local
npm install && npm run dev
```

## Make it yours

```bash
python scripts/init.py --name "Acme Portal" --slug acme-portal --color "#0F766E"
```

Renames the folders, packages, PM2/Nginx/Docker names and the brand color, and sets your production
ports. Add `--make-env` to create local env files with a fresh `SECRET_KEY`, `--dry-run` to preview.
Run it once, before your first commit. Then:

1. Replace the example module with your first real module
   ([backend guide](webapp-backend/docs/adding-a-module.md), [frontend guide](webapp-frontend/README.md#add-a-module)).
2. Edit the sidebar in `webapp-frontend/src/core/config/menu.config.ts` and the permissions in
   `webapp-backend/app/core/permissions.py`.
3. Create your remote repositories and push (each folder is its own repo).

## What you get

- **Security by default:** Argon2id, short-lived access tokens, rotating hashed refresh tokens with
  reuse detection, lockout, rate limiting, CSRF-safe cookie endpoints, strict production config
  validation, security headers.
- **Server-side authorization:** `resource:action` permissions checked on every route; the UI
  adapts but never decides.
- **Consistent contracts:** one error envelope, one list contract (`page`, `page_size`, `search`,
  `sort_by`, `sort_order`), soft delete and audit columns on business tables.
- **Modern UI:** MUI 9 with CSS-variable themes (light/dark/system), brand color from one variable,
  accessible components, responsive layout.
- **Quality gates:** Ruff, Pyright, pytest, ESLint, Prettier, TypeScript strict, Vitest, Playwright,
  GitHub Actions workflows in each repo.

## Repository layout

```text
.
├── webapp-backend/      # FastAPI service (own git repo)
├── webapp-frontend/     # Next.js web app (own git repo)
├── docs/adr/            # architecture decisions
├── scripts/init.py      # project initialiser
├── docker-compose.yml   # whole stack for local use
├── CONTRIBUTING.md      # workflow, commit types, checks
└── CLAUDE.md            # guidance for AI assistants working in this workspace
```

## Notes

- Docker files are provided but were written without Docker available to run them; build them before
  depending on them.
- MySQL and SingleStore are supported through the async MySQL driver but are untested.
- Created from the Hino HIS standard template; see
  [ADR 0001](docs/adr/0001-local-auth-instead-of-iam.md) for why IAM was replaced.

## License

[MIT](LICENSE)
