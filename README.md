# KampusPing

Tuition billing reminders over WhatsApp for the Finance Department (Bagian Keuangan) of a campus.

Finance staff upload export files (CSV or Excel) from **SIAKAD/Civitas** and **SIPEMA**. KampusPing
keeps the invoices, plans reminders on a schedule (H-7, H-3, H-1, H, H+3, H+7 by default) and sends
them over WhatsApp, **only to students whose invoice is still unpaid**. Payment itself stays in
SIAKAD/SIPEMA; WhatsApp is only the reminder channel. There is no API or database connection to
those systems (NFR-08): data enters through uploaded export files only.

- Requirements: [BRD v0.1](docs/BRD-penagihan-uang-kuliah-whatsapp.md) (Indonesian). Requirement
  codes (FR-xx, NFR-xx, AB-xx, BR-xx) in code comments, tests and commits refer to it.
- Design: [docs/superpowers/specs/2026-10-31-kampusping-design.md](docs/superpowers/specs/2026-10-31-kampusping-design.md).
- Status: **milestone M1 (MVP) is implemented and reviewed** (2026-11-02). M2 and M3 are not started
  (see [What is implemented](#what-is-implemented-and-what-is-not)).

```text
Browser ─► Next.js (UI Indonesia) ─► FastAPI ─► PostgreSQL ◄─ Worker ──► Gateway (Baileys) ─► WhatsApp
                                        ▲                                    │
                                        └──── webhook: delivery receipts ────┘
```

The worker is a separate process of the backend (`python -m app.cli run-worker`). It plans messages
from the schedule rules and sends them through a `WhatsAppProvider`: the `fake` provider (records in
memory, for development) or the `gateway` provider (HTTP to the Node gateway that owns the WhatsApp
session). See [ADR 0003](docs/adr/0003-database-backed-queue-and-worker-process.md) and
[`kampusping-backend/docs/messaging.md`](kampusping-backend/docs/messaging.md).

## Folders

Each app folder is its **own git repo** (own history and `.gitignore`); this root repo holds the
shared files. Run git, install, test and deploy commands from inside the matching folder.

| Folder | What it is | Docs |
| --- | --- | --- |
| [`kampusping-backend/`](kampusping-backend/) | FastAPI API, Alembic migrations, CLI and the worker (Python 3.11+) | [README](kampusping-backend/README.md), [messaging](kampusping-backend/docs/messaging.md) |
| [`kampusping-frontend/`](kampusping-frontend/) | Next.js 16 + MUI 9 web app, Indonesian UI | [README](kampusping-frontend/README.md), [e2e](kampusping-frontend/e2e/README.md) |
| [`kampusping-wa-gateway/`](kampusping-wa-gateway/) | Node 20+ service that owns the Baileys (WhatsApp) session | [README](kampusping-wa-gateway/README.md) |
| `docs/` | BRD, design spec, plan, ADRs, runbook, manual smoke test | see [Documents](#documents) |
| `docker-compose.yml`, `.env.example`, `CLAUDE.md`, `CONTRIBUTING.md` | Whole-stack compose file, its variables, guidance for AI assistants, workflow | |

## Quick start

> **Docker was never available where this was written.** `docker-compose.yml` and both Dockerfiles
> (backend and gateway; the frontend one too) have **not been built or run yet**. Build them and
> fix what you find before relying on them. Option B below was exercised (backend and frontend on
> SQLite, the Playwright suite against it).

### A. Docker Compose (fake WhatsApp provider)

```bash
docker compose up --build
```

Open http://localhost:3000 and sign in with `admin@example.com` / `ChangeMe-12345` (development
defaults; override with `ADMIN_EMAIL` / `ADMIN_PASSWORD`, see [`.env.example`](.env.example)). API
docs: http://localhost:8000/docs. The stack is PostgreSQL, API, worker and web app. The worker runs
with `WA_PROVIDER=fake`: messages are recorded in the worker's memory and **nothing reaches
WhatsApp**. Run exactly one worker; never scale it.

The real gateway is an optional compose profile and needs a dedicated WhatsApp number (read
[ADR 0002](docs/adr/0002-baileys-whatsapp-gateway.md) first):

```bash
# root .env: WA_PROVIDER=gateway, WA_GATEWAY_API_KEY=<random 16+>, WA_WEBHOOK_SECRET=<other random 16+>
docker compose --profile whatsapp up --build
```

### B. Run each part directly

Ports in development: API 8000, web 3000 (production by convention: API 8093, web 8094, gateway
127.0.0.1:8095).

```bash
# 1. Backend. SQLite is for a trial only; use PostgreSQL for real work.
cd kampusping-backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env     # then set DATABASE_ENGINE=sqlite and DATABASE_URL=sqlite+aiosqlite:///./dev.db
alembic upgrade head
python -m app.cli create-admin     # first administrator; also seeds roles, default templates and rules
uvicorn app.main:app --reload      # http://localhost:8000/docs

# 2. Frontend (another terminal)
cd kampusping-frontend
cp .env.example .env.local
npm install && npm run dev         # http://localhost:3000

# 3. Optional: one worker tick (plan + send) with the fake provider
cd kampusping-backend
python -m app.cli run-worker --once      # without --once it loops every WORKER_TICK_SECONDS (60)
```

`create-admin` reads `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_NAME` and `INITIAL_ADMIN_PASSWORD` from
`.env` (or prompts for the password). Automatic sending is **off** until staff switch it on in
Pengaturan, so a worker tick on a fresh database does nothing. Do not point `.env` at a database you
care about while trying things out.

For real WhatsApp sending follow [docs/runbook-whatsapp.md](docs/runbook-whatsapp.md), and test with
[docs/manual-smoke-test.md](docs/manual-smoke-test.md) before any real use.

## Roles and permissions

Users, roles and permissions live in the application database (no external IAM, see
[ADR 0001](docs/adr/0001-local-auth-instead-of-iam.md)). Permissions are `resource:action` codes in
`kampusping-backend/app/core/permissions.py` (mirrored in
`kampusping-frontend/src/core/auth/permissions.ts`) and are enforced on the server with
`require_permissions(...)`; hiding a menu entry in the UI is convenience only.

| System role | Permissions | Intended for |
| --- | --- | --- |
| `admin` | Everything (re-synced on every seed) | IT / system administrator |
| `staf_keuangan` | Everything except `users:*`, `roles:*` and `audit:*` | Finance staff running the daily workflow |
| `pimpinan` | `dashboard:read` only | Leadership (read-only dashboard) |

`admin` is re-synced to hold every permission each time `python -m app.cli seed` runs; the other two
roles are created once, so edits made in the UI are kept. That also means `staf_keuangan` does **not**
automatically receive permissions added by later milestones in an existing database.

Permission groups: `users`, `roles` (CRUD), `dashboard:read`, `imports` (read, create), `students`
(read, update), `invoices` (read, update), `templates` and `schedules` (CRUD), `messages` (read,
cancel), `settings` (read, update; includes the WhatsApp controls) and `audit:read`.

## Daily flow for finance staff

1. **Sign in** and open **Pengaturan**: fill in the campus name, the finance contact and the payment
   link or guide (these go into the messages). Link the dedicated WhatsApp number under
   **Koneksi WhatsApp** (scan the QR code) once, with an administrator or IT.
2. **Impor Data**: choose the source (SIAKAD or SIPEMA), optionally the semester, and upload the
   `.csv` or `.xlsx` export (5 MB, 20,000 rows at most).
3. **Check the preview**: counts of valid and invalid rows, new and updated students and invoices,
   and the list of row errors. Nothing has changed yet.
4. **Terapkan** to save the valid rows (or **Batalkan** to discard the preview). "Paid" is sticky: a
   later file that says "belum lunas" never turns a paid invoice back to unpaid. Import again
   before each billing cycle so payments are visible.
5. Review **Template Pesan** and **Jadwal** (the defaults are the two BRD templates and the six
   rules H-7, H-3, H-1, H, H+3, H+7; edit them if the campus wants different wording or timing).
6. In **Pengaturan**, switch on **Pengiriman otomatis** (a confirmation explains the ban risk) and
   save. From then on the worker plans and sends inside the send window.
7. Watch **Pengiriman** (the send log: Antre, Terkirim, Diterima, Dibaca, Gagal, Dibatalkan with the
   reason) and **Dasbor** (invoice totals, overdue amount, message counts, a banner when sending is
   paused). A queued message can be cancelled from the log; an invoice can be marked paid or unpaid
   by hand in **Tagihan**; a student's phone number can be corrected in **Mahasiswa**.

## Safeguards (BRD business rules)

| Rule | State in M1 | Where |
| --- | --- | --- |
| AB-01 / FR-06: only unpaid invoices get a message; status, opt-out, exemption and phone validity are re-checked from the database right before sending | Implemented | `modules/messages/send_rules.py` (`recheck`), `planner.py` |
| AB-02: default schedule H-7, H-3, H-1, H, H+3, H+7 | Implemented (rules are data, editable) | `modules/templates/seed.py`, **Jadwal** |
| AB-03: at most one automatic message per student per day | Implemented | `modules/messages/send_repository.py` |
| AB-04: send window (default 08:00-17:00 WIB, Monday-Friday) | Implemented (settings) | `send_rules.schedule_open`; no public holidays |
| AB-05: students with an approved exemption get nothing | Enforced in the planner and the re-check, but **there is no screen or endpoint to set an exemption yet** (M3) | `modules/invoices` |
| AB-06 / FR-11: opt-out (`STOP`, `BERHENTI`, `UNSUBSCRIBE`) | The footer "Balas STOP untuk berhenti." is on every message and the opt-out flag is honoured when set, but **a student's STOP reply is not read or processed yet** (M3) | `modules/templates/rendering.py` |
| AB-07: automatic messages stop after the escalation offset (default H+14) | Implemented (invoice gets `escalated_at`, queued messages are cancelled); the staff follow-up list is not built yet | `modules/messages/planner.py` |
| AB-08: polite tone | Default templates; staff own the wording | **Template Pesan** |
| NFR-08: no direct connection to SIAKAD/SIPEMA | By design: uploaded files only | `modules/imports` |

Throttle and limits (all settings, defaults in brackets): random pause between messages (8-20 s),
daily cap (200 messages), at most 3 attempts per message with back-off (5 then 15 minutes),
**circuit breaker** (5 consecutive failures pause all automatic sending until staff press
"Lanjutkan pengiriman"), automatic sending off until staff enable it, one worker only. Phone
numbers are masked in logs (last four digits only).

## What is implemented, and what is not

**M1 (done):** CSV/Excel import with preview and apply; students and invoices; message templates
and schedule rules with seed data; settings; the message queue, planner and sender with the FR-06
re-check, retries and circuit breaker; the Baileys gateway with durable `client_ref` dedupe and
delayed, signed delivery receipts; the send log (Antre to Dibaca); dashboard (invoice totals,
overdue, message counts, pause banner); users, roles, permissions and the audit log; Indonesian UI.

**Not implemented yet:**

- **M2:** SIPEMA column profile and cross-source difference report, stale-import guard,
  complete dashboard (paid after message, on-time rate, warnings).
- **M3:** reply inbox and handling of student replies, **opt-out by keyword (STOP)**, escalation
  follow-up list, **manual and bulk send**, **exemption (keringanan/cicilan) screen**, **Excel and
  PDF export**, automatic `BANTUAN` reply. `reportlab` is not a dependency yet. There is no `replies`
  table yet.

Until M3, treat the system as one-way: students cannot opt out through WhatsApp, so keep the sending
number monitored by a person and handle "stop" requests by hand (for example by correcting the
student's phone number, or by turning automatic sending off).

## Tests

Re-run the suites before trusting these numbers; they change as milestones land.

| Suite | Count at the last full run | Command |
| --- | --- | --- |
| Backend (pytest) | 675 passed | `cd kampusping-backend && pytest` |
| Frontend (Vitest) | 302 tests in 32 files | `cd kampusping-frontend && npm test` |
| Gateway (Vitest) | 93 tests in 12 files | `cd kampusping-wa-gateway && npm test` |
| End to end (Playwright) | 13 tests (8 in `app.spec.ts`, 5 in `billing.spec.ts`) | needs the stack running, see [e2e/README.md](kampusping-frontend/e2e/README.md) |

Quality gates: backend `ruff check . && ruff format --check . && pyright && pytest`; frontend and
gateway `npm run check`. **Real sending through Baileys cannot be verified by automated tests**; it
needs the manual test on a real phone ([docs/manual-smoke-test.md](docs/manual-smoke-test.md)).

## Known limitations

- **Baileys is an unofficial WhatsApp library** and violates WhatsApp's terms; the number can be
  banned, possibly permanently, and it can break when WhatsApp changes its protocol. This deviates
  from the BRD recommendation (official Cloud API), see [ADR 0002](docs/adr/0002-baileys-whatsapp-gateway.md).
  Use a dedicated number and keep the safeguards on. NFR-04 (approved templates) does not apply.
- **Licensing:** Baileys depends on `libsignal`, which is GPL-3.0, while this project is MIT.
  Running it as a self-hosted internal service is fine; reconsider before distributing or selling
  KampusPing as closed software.
- The gateway queues webhook events **in memory**: receipts still queued when it stops are lost.
  Receipts are also dropped if the backend's commit of a send takes longer than the gateway's delay
  plus retries (the gateway replays delivered receipts once after 30 s to reduce this). A lost
  receipt only leaves a message at `Terkirim` instead of `Diterima`/`Dibaca`.
- The pre-send re-check only sees the latest imported data; payments made after the last import are
  invisible. Import before each cycle.
- Public holidays are not known; the send window uses the configured working days only.
- The Docker artifacts (compose file, Dockerfiles) were never built or run.
- Route protection in the frontend is client-side (the refresh cookie is scoped to the API path); the
  API is the real gate.
- Retention of messages and student data (UU PDP) is not defined yet; the campus has to decide.
- `staf_keuangan` does not gain permissions added in later milestones on an existing database.
- A database created from the old universal template needs a one-time repair before the new
  migrations run: see [Upgrading a database that was created from the old template](kampusping-backend/docs/database.md#upgrading-a-database-that-was-created-from-the-old-template).

## Documents

| Document | Purpose |
| --- | --- |
| [docs/BRD-penagihan-uang-kuliah-whatsapp.md](docs/BRD-penagihan-uang-kuliah-whatsapp.md) | Requirements (Indonesian) |
| [docs/superpowers/specs/2026-10-31-kampusping-design.md](docs/superpowers/specs/2026-10-31-kampusping-design.md) | Design (Indonesian) |
| [docs/superpowers/plans/2026-10-31-kampusping-m1-mvp.md](docs/superpowers/plans/2026-10-31-kampusping-m1-mvp.md) | M1 implementation plan |
| [docs/adr/](docs/adr/) | 0001 local auth, 0002 Baileys gateway, 0003 database queue and worker |
| [docs/runbook-whatsapp.md](docs/runbook-whatsapp.md) | Operating the WhatsApp number (Indonesian) |
| [docs/manual-smoke-test.md](docs/manual-smoke-test.md) | Manual real-phone test (Indonesian) |
| [kampusping-backend/docs/messaging.md](kampusping-backend/docs/messaging.md) | Message lifecycle, planner, sender, rules |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Workflow, commit types, checks |

## License

[MIT](LICENSE)
