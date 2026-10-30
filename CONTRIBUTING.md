# Contributing

## Workflow

- Work on `development` (or a branch cut from it); `master` is the release branch and receives
  changes only through reviewed pull requests.
- Keep each commit to one logical change. Backend and frontend are separate repositories; commit
  inside the matching folder.
- Mark releases with tags such as `v1.2.0`.

## Commit messages (Conventional Commits)

`<type>: <short, clear description>`, for example `fix: return 409 for a duplicate email`.

| Type | Use for |
| --- | --- |
| `feat`, `fix`, `refactor`, `perf`, `style`, `test` | Code changes |
| `docs`, `chore`, `deps`, `config`, `build`, `ci` | Docs and maintenance |
| `db`, `migration`, `seed` | Schema, migration files, seed data |
| `api`, `ui`, `ux` | Endpoint contract, visuals, flows |
| `security`, `hotfix`, `release`, `revert` | Safety and releases |

## Before you push

Backend (`webapp-backend/`):

```bash
ruff check . && ruff format --check . && pyright && pytest
```

Frontend (`webapp-frontend/`):

```bash
npm run check          # lint, typecheck, format check, unit tests
npm run build
```

CI runs the same commands. For changes that touch both sides, also run the e2e suite
(`webapp-frontend/e2e/README.md`).

## Guidelines

- Authorization is enforced on the server with permission codes. Never rely on hiding UI.
- No secrets, hosts or credentials in committed files; add new settings to the `*.example` env files.
- New tables use `AuditedModel` and a hand-written Alembic migration with a working `downgrade()`.
- New screens use the `App*` components and theme tokens (no hex literals).
- Add tests with the change, including the failure and 401/403 cases.
