# KampusPing M1 (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the universal template into a working MVP: import tuition invoices from CSV/Excel, schedule and send WhatsApp reminders (fake provider or Baileys gateway) to unpaid students only, log every send, and show a basic dashboard, all behind permission-based roles.

**Architecture:** FastAPI modules (one folder per domain, copied from the `example` pattern) backed by PostgreSQL; a separate worker process (`python -m app.cli run-worker`) plans and sends messages from the `messages` table through a `WhatsAppProvider`; a Node gateway (`kampusping-wa-gateway/`) owns the Baileys session; the Next.js app gets Indonesian screens for each module.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, pytest; Next.js 16, MUI 9, RHF + Zod, Vitest, Playwright; Node 20+, TypeScript, Fastify, Baileys, Vitest. New libraries (approved in the spec, plus two the plan needs and the user must confirm): `openpyxl`, `python-multipart` (required by FastAPI for file uploads), `tzdata` (Windows has no IANA time zone database for `zoneinfo`), `@whiskeysockets/baileys`, `fastify`; plus `qrcode.react` in the frontend, only after the user approves it (Task 18).

**Spec:** `docs/superpowers/specs/2026-10-31-kampusping-design.md` (BRD: `docs/BRD-penagihan-uang-kuliah-whatsapp.md`; ADRs 0002, 0003). M2 and M3 get their own plans; this plan only covers spec section 9, row "M1".

## Global Constraints

- Timestamps stored in UTC; business dates ("today", send window) computed in `APP_TIMEZONE=Asia/Jakarta`. Time is always injected as a `Clock` (`Callable[[], datetime]`), never read inside rule code.
- Defaults: send window 08:00-17:00, working days Monday-Friday (`working_days=[1,2,3,4,5]`); throttle 8-20 s; `daily_cap=200`; `max_attempts=3` with retry delays 5, 15, 45 minutes; `consecutive_failure_limit=5`; `escalation_offset_days=14`; planning window 3 days; a `sending` message older than 10 minutes is recovered; `WORKER_TICK_SECONDS=60`; import limits 5 MB and 20,000 rows; `auto_send_enabled=false` until staff enable it.
- Message statuses: `queued`, `sending`, `sent`, `delivered`, `read`, `failed`, `cancelled`. `cancel_reason` in: `paid`, `opted_out`, `exempt`, `phone_invalid`, `expired`, `superseded`, `manual`, `escalated`. `messages` is unique on (`invoice_id`, `rule_id`).
- Footer on every automatic message: `Balas STOP untuk berhenti.`. Template variables: `nama`, `nim`, `semester`, `nominal`, `tanggal_jatuh_tempo`, `cara_bayar`, `link_pembayaran`, `kontak_keuangan`, `nama_kampus`. Unknown variables reject saving.
- Phone numbers are stored as `+62...`; logs show only the last 4 digits. Gateway: `Authorization: Bearer <WA_GATEWAY_API_KEY>`, listens on 127.0.0.1:8095; webhook header `X-Signature: sha256=<hex HMAC-SHA256 of the raw body, key WA_WEBHOOK_SECRET>`.
- UI strings, WhatsApp text, import row errors and API error messages shown to users are Indonesian; identifiers, migrations, comments and commit messages are English. Errors keep the `{"error": {"code", "message", "details"}}` envelope; lists keep `{items, total, page, page_size}`.
- Permissions are `resource:action`, enforced with `require_permissions(...)` and mirrored in `src/core/auth/permissions.ts`. Never branch on role names or ids.
- Migrations are numbered, named descriptively, implement `downgrade()`, use `id_column()`/`audit_columns()`, and are checked with `alembic upgrade head` then `downgrade base` on a temporary SQLite file.
- Each repo is its own git repo on branch `development`; commit inside the repo, Conventional Commits, end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Never push, merge, tag or deploy.
- Quality gates: backend `ruff check . && ruff format --check . && pyright && pytest`; frontend `npm run check`; gateway `npm run check`.

## Review Focus

Inputs the spec implies but its tests would not exercise; each is pinned by a test in the named task.

1. Excel cells that are not text: phone as a float (`6.2812345678e11`) or without the leading zero, NIM as a float (`20210001.0`), dates as `datetime` cells (Task 7).
2. CSV exported by Indonesian-locale Excel: UTF-8 BOM and `;` delimiter (Task 7).
3. The same invoice code twice in one file, and pressing "Terapkan" twice on one preview (Task 8).
4. The midnight boundary: 17:30 UTC is already the next day in WIB for planning, and the send window is re-checked after the throttle sleep (Tasks 11, 12).
5. A student with two unpaid invoices due the same day: only one message per day, the other must not be lost (Task 12).

## File Structure

```text
kampusping-backend/app/
  shared/{clock.py, phone.py}                    # Clock, local_today(); normalize_phone()
  core/permissions.py                            # new codes + roles admin / staf_keuangan / pimpinan
  modules/settings/        {model,schema,service,router,constants}.py
  modules/audit/           {model,schema,service,router}.py    # record_audit()
  modules/students/        {model,schema,repository,service,router}.py
  modules/invoices/        {model,schema,repository,service,router}.py
  modules/imports/         {model,schema,columns,parser,validation,service,router}.py
  modules/templates/       {model,schema,rendering,repository,service,router,seed}.py
  modules/schedules/       {model,schema,repository,service,router}.py
  modules/whatsapp/        {provider,fake,gateway,signature,router,deps}.py
  modules/messages/        {model,constants,schema,repository,planner,sender,runner,router}.py
  modules/dashboard/       {schema,service,router}.py
  cli.py                                         # + run-worker
kampusping-wa-gateway/     # new repo: src/{app,client,baileys,webhook,config,index}.ts + tests
kampusping-frontend/src/modules/{import,students,invoices,templates,schedules,messages,settings,audit}/  + dashboard rewrite
```

---

### Task 1: Rebrand to KampusPing and remove the example module

**Files:**
- Modify: whole workspace via `scripts/init.py`; `kampusping-backend/app/db/models/__init__.py`, `app/api/v1/router.py`, `app/core/permissions.py`, `tests/`; `kampusping-frontend/src/{core/config/menu.config.ts,core/config/route.config.ts,core/auth/permissions.ts,modules/dashboard/components/DashboardPage.tsx}`, `e2e/app.spec.ts`
- Delete: `app/modules/example/`, `alembic/versions/002_create_example_items.py`, `tests/test_example.py`, `src/modules/example/`, `src/app/(app)/example/`
- Test: existing suites

**Interfaces:**
- Produces: package/PM2/Docker names `kampusping-*`, brand color `#0F766E`, `NEXT_PUBLIC_LOCALE=id`; no `examples:*` permission; dashboard shows a plain welcome card until Task 17.

- [ ] **Step 1:** In each app repo run `git status` and `git branch --show-current`; switch to `development` if needed (create it from the current branch if it does not exist). Confirm no database has run migration `002` (dev SQLite/Postgres used only for local tries); if one has, drop it.
- [ ] **Step 2:** Run `python scripts/init.py --dry-run --name "KampusPing" --slug kampusping --color "#0F766E"`, then the same without `--dry-run` plus `--make-env`. Set `NEXT_PUBLIC_LOCALE=id` in `kampusping-frontend/.env.example` and `.env.local`.
- [ ] **Step 3:** Delete the files listed above; remove `ExampleItem`, `EXAMPLES_*`, the example router, menu entry, route and permission mirrors; replace the dashboard body with a welcome card; drop the example cases from `e2e/app.spec.ts` and the example-dependent assertions in unit tests.
- [ ] **Step 4:** Verify. Backend: `alembic upgrade head` against a temp SQLite file creates only auth tables, then `pytest`. Frontend: `npm run check`. Expected: all green, no remaining `example` or `webapp` strings (`grep -ri "webapp\|example" --include=*.py --include=*.ts --include=*.tsx --include=*.md` finds only intentional hits such as `admin@example.com`).
- [ ] **Step 5:** Commit in each repo (`chore: rebrand template as KampusPing and remove the example module`) and in the root repo for the files `init.py` changed outside the app folders.

---

### Task 2: Indonesian UI and API messages for the existing screens

**Files:**
- Modify: `kampusping-frontend/src/{components/layout/*,modules/auth/*,modules/users/*,modules/roles/*,modules/profile/*,app/**/*.tsx (metadata titles),core/http/*,core/validation/*,core/notify/*}`, existing `*.test.ts(x)`, `e2e/app.spec.ts`; `kampusping-backend/app/{core/exceptions.py,core/security.py,modules/auth,modules/users,modules/roles}` user-visible messages and `tests/` assertions on message text
- Test: `src/modules/auth/components/LoginForm.test.tsx`, `src/components/layout/RequirePermission.test.tsx`, `src/core/http/*.test.ts`, backend `tests/`

**Interfaces:**
- Produces: the glossary every later screen reuses: Masuk, Keluar, Pengguna, Peran, Izin, Simpan, Batal, Hapus, Ubah, Tambah, Cari, Memuat, Aksi, Status, Dasbor, Profil, Kata sandi, Email. Default API error text for 401/403/404/422/429/500 in Indonesian.

- [ ] **Step 1:** Update the existing tests first to the target Indonesian strings (e.g. LoginForm test expects button `Masuk`, label `Kata sandi`; e2e `signIn` clicks `Masuk`, heading `Pengguna`). Run `npm test`; expected FAIL on the changed strings.
- [ ] **Step 2:** Translate every user-visible string in the files above (labels, buttons, empty states, dialog titles, Zod messages, snackbar texts, `loading.tsx`, `error.tsx`, `not-found.tsx`, metadata titles). No i18n framework; strings stay inline. Check dates/numbers use `appConfig.locale` (`id`).
- [ ] **Step 3:** Translate backend messages that reach the UI (`AppException` texts in auth, users, roles; password-policy errors; the default 401/403/404/422/429/500 envelopes). Update the backend tests that assert on message text.
- [ ] **Step 4:** Verify: `npm run check` and `pytest` pass; `grep -rn "Sign in\|Sign out\|Cancel\|Delete\|Loading" kampusping-frontend/src --include=*.tsx` returns nothing user-visible.
- [ ] **Step 5:** Commit per repo (`ux: translate the existing screens and API messages to Indonesian`).

---

### Task 3: Domain permissions and system roles

**Files:**
- Modify: `kampusping-backend/app/core/permissions.py`, `app/db/seed.py` (only if needed), `tests/conftest.py`, `tests/test_users_roles.py`; `kampusping-frontend/src/core/auth/permissions.ts`, `permissions.test.ts`
- Create: `kampusping-backend/tests/test_permissions_seed.py`

**Interfaces:**
- Produces (constants in `permissions.py`, mirrored camelCase in `permissions.ts`): `DASHBOARD_READ`, `IMPORTS_READ`, `IMPORTS_CREATE`, `STUDENTS_READ`, `STUDENTS_UPDATE`, `INVOICES_READ`, `INVOICES_UPDATE`, `TEMPLATES_READ|CREATE|UPDATE|DELETE`, `SCHEDULES_READ|CREATE|UPDATE|DELETE`, `MESSAGES_READ`, `MESSAGES_CANCEL`, `SETTINGS_READ`, `SETTINGS_UPDATE`, `AUDIT_READ` (code = `resource:action`, descriptions in Indonesian); role names `ADMIN_ROLE="admin"`, `STAF_KEUANGAN_ROLE="staf_keuangan"`, `PIMPINAN_ROLE="pimpinan"` replacing `MEMBER_ROLE`.

- [ ] **Step 1: Write failing tests** in `test_permissions_seed.py`: `test_admin_holds_every_permission`; `test_staf_keuangan_has_everything_except_users_roles_audit` (asserts no code starting `users:`, `roles:`, `audit:`); `test_pimpinan_has_only_dashboard_read`; `test_seed_is_idempotent_and_keeps_edited_non_admin_roles` (remove a permission from `staf_keuangan`, reseed, still removed).
- [ ] **Step 2:** Run `pytest tests/test_permissions_seed.py -v`; expected FAIL (names undefined).
- [ ] **Step 3:** Define the codes, `PERMISSIONS`, and `SYSTEM_ROLES` for the three roles; replace `MEMBER_ROLE` in `conftest.py` (`member_headers` becomes `pimpinan_headers`) and in existing tests; mirror the codes in `permissions.ts` and extend its unit test.
- [ ] **Step 4:** `pytest` and `npm test`; expected PASS.
- [ ] **Step 5:** Commit per repo (`feat: add domain permissions and the admin, staf_keuangan and pimpinan roles`).

---

### Task 4: Settings and audit log

**Files:**
- Create: `app/modules/settings/{__init__,constants,model,schema,service,router}.py`, `app/modules/audit/{__init__,model,schema,service,router}.py`, `alembic/versions/002_app_settings_and_audit.py`, `tests/test_settings_audit.py`
- Modify: `app/db/models/__init__.py`, `app/api/v1/router.py`, `app/core/config.py` (`app_timezone`, `worker_tick_seconds`, `wa_provider`, `wa_gateway_url`, `wa_gateway_api_key`, `wa_webhook_secret`), `.env.example`, `deploy/.env.production.example`; create `app/shared/clock.py`

**Interfaces:**
- Produces: `class AppSettings(AuditedModel)` (single row) with `campus_name`, `finance_contact`, `payment_link_siakad`, `payment_guide_sipema`, `window_start: time`, `window_end: time`, `working_days: str` (comma-separated ISO weekdays), `auto_send_enabled`, `daily_cap`, `throttle_min_s`, `throttle_max_s`, `max_attempts`, `consecutive_failure_limit`, `escalation_offset_days`, `paused_reason: str | None`; `SettingsService(db).get() -> AppSettings` (creates the default row if missing), `.update(data, actor)`, `.resume(actor)`; `async def record_audit(db, *, actor: str, action: str, entity: str, entity_id: int | str | None = None, detail: dict | None = None) -> None` (flushes, caller commits); `Clock = Callable[[], datetime]`, `local_today(now: datetime, tz_name: str) -> date`, `local_now(now, tz_name) -> datetime`. Routes: `GET/PUT /settings`, `POST /settings/resume`, `GET /audit-events` (`ListQuery`, filters `action`, `entity`, sort `at`).

- [ ] **Step 1: Write failing tests:** `test_get_settings_returns_defaults` (window 08:00-17:00, `auto_send_enabled` false, `daily_cap` 200); `test_update_settings_validates` (window start >= end -> 422, `throttle_min_s > throttle_max_s` -> 422, `working_days` outside 1..7 -> 422); `test_settings_require_permissions` (pimpinan 403 on both verbs, staf_keuangan 200); `test_update_and_resume_write_audit_events`; `test_resume_clears_paused_reason`; `test_audit_events_admin_only` (staf_keuangan 403); `test_local_today_crosses_midnight_in_jakarta` (17:30 UTC -> next day).
- [ ] **Step 2:** Run them; expected FAIL.
- [ ] **Step 3:** Implement models, services, routers, the migration (`alembic upgrade head` / `downgrade base` check), `Settings` fields, and env examples. `local_today` uses `zoneinfo.ZoneInfo`; add `tzdata` to `requirements.txt` and `pyproject.toml`.
- [ ] **Step 4:** `pytest`; expected PASS. Then ruff + pyright.
- [ ] **Step 5:** Commit (`feat: add application settings and the audit log`).

---

### Task 5: Students and invoices

**Files:**
- Create: `app/shared/phone.py`, `app/modules/students/*`, `app/modules/invoices/*` (full module set), `alembic/versions/003_students_and_invoices.py`, `tests/test_phone.py`, `tests/test_students_invoices.py`
- Modify: `app/db/models/__init__.py`, `app/api/v1/router.py`

**Interfaces:**
- Produces: `normalize_phone(raw: str | int | float | None) -> str | None` returning `+62...` or `None`; `Student(AuditedModel)`: `nim` (unique), `name`, `study_program`, `cohort`, `phone`, `phone_status` (`valid|invalid|missing`), `opted_out_at`, `opted_out_reason`; `Invoice(AuditedModel)`: `invoice_code` (unique), `student_id`, `semester`, `amount: int`, `due_date: date`, `status` (`unpaid|paid`), `paid_at: date | None`, `paid_via`, `source` (`siakad|sipema`), `exempt_reason`, `exempt_until`, `escalated_at`; index `(status, due_date)`. Routes: `GET /students` (search nim/name; filters `study_program`, `cohort`, `phone_status`), `GET /students/{id}`, `PATCH /students/{id}` (`{"phone"}`; invalid number -> 422; sets `phone_status`), `GET /invoices` (filters `status`, `semester`, `due_from`, `due_to`, `student_id`; each row embeds `student: {id, nim, name}`), `PATCH /invoices/{id}/status` (`{"status": "paid"|"unpaid"}`; audit event `invoice.status_changed`).

- [ ] **Step 1: Write failing tests:** `test_normalize_phone` parametrized: `"0812-3456-7890"`, `"+62 812 3456 7890"`, `"62812345678901"`, `"812345678"`, `628123456789` (int), `6.28123456789e11` (float) all give `+62...`; `""`, `None`, `"abc"`, `"12345"`, `"+6512345678"` give `None`. API tests: list/search/filter and pagination for both; `PATCH` phone valid/invalid; `test_invoice_status_revert_is_audited`; 401/403 per role (pimpinan cannot read students or invoices).
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement `normalize_phone` (strip non-digits, accept leading `0`, `62`, `8`; length 9-13 digits after `62`), models, repositories (`sort_fields` declared), services, routers, migration.
- [ ] **Step 4:** `pytest`; ruff + pyright. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add students and invoices with phone normalisation`).

---

### Task 6: Import parsing and row validation (pure functions)

**Files:**
- Create: `app/modules/imports/{__init__,columns,parser,validation}.py`, `tests/test_import_parsing.py`
- Modify: `requirements.txt`, `pyproject.toml` (`openpyxl`, `python-multipart`)

**Interfaces:**
- Produces: `columns.CANONICAL_FIELDS` and `columns.ALIASES: dict[str, dict[str, tuple[str, ...]]]` keyed by source (`siakad`, `sipema`; M1 uses the same aliases for both) mapping `nim`, `name`, `study_program`, `cohort`, `phone`, `invoice_code`, `amount`, `due_date`, `status`, `paid_at`, `paid_via`, `semester` to lower-case header aliases (Indonesian and English); `REQUIRED_FIELDS = (nim, invoice_code, amount, due_date, status)`.
  `parser.parse_upload(filename: str, content: bytes) -> ParsedSheet` where `ParsedSheet(headers: list[str], rows: list[list[object]])`, raising `ImportFileError(message)` for: unsupported extension, over 5 MB, over 20,000 rows, empty file, unreadable `.xlsx`. CSV: decode `utf-8-sig`, sniff delimiter among `, ; \t`.
  `parser.resolve_columns(headers: list[str], source: str) -> dict[str, int]` raising `ImportFileError` listing missing required fields.
  `validation.ValidRow` (frozen dataclass: `row_number, nim, name, study_program, cohort, phone, invoice_code, semester, amount, due_date, status, paid_at, paid_via`) and `validation.RowIssue(row_number: int, field: str, message: str)`; `validate_row(row_number, cells, columns, *, default_semester: str | None, source: str) -> ValidRow | list[RowIssue]`; `parse_amount(value) -> int | None`; `parse_date(value) -> date | None`; `parse_status(value) -> Literal["paid","unpaid"] | None`.

- [ ] **Step 1: Write failing tests:**
  - `test_csv_with_bom_and_semicolon_delimiter` (Review Focus 2) and `test_csv_comma_and_tab_delimiters`.
  - `test_xlsx_numeric_cells`: build a workbook with openpyxl where NIM is `20210001.0`, phone is `6.28123456789e11`, due date is a `datetime`; the validated row has `nim == "20210001"`, `phone == "+628123456789"`, `due_date == date(...)` (Review Focus 1).
  - `test_parse_amount` parametrized: `"1.500.000"`, `"Rp1.500.000"`, `"Rp 1.500.000,00"`, `"1,500,000"`, `"1500000"`, `1500000.0` all give `1500000`; `"0"`, `"-5"`, `"abc"`, `""` give `None`.
  - `test_parse_date`: `2026-11-15`, `15/11/2026`, `15-11-2026`, `datetime` accepted; `31/02/2026` and `"besok"` give `None`.
  - `test_parse_status`: `lunas`, `Sudah Bayar`, `paid` -> `paid`; `belum lunas`, `Belum Bayar`, `unpaid` -> `unpaid`; `"?"` -> `None`.
  - `test_missing_required_header_names_the_field` (message in Indonesian lists `jatuh tempo`); `test_rejects_over_limits_and_bad_extension`; `test_row_without_semester_uses_default_or_errors`; `test_row_issues_are_indonesian_and_per_field`.
- [ ] **Step 2:** Run `pytest tests/test_import_parsing.py -v`; expected FAIL.
- [ ] **Step 3:** Implement with `csv`, `io` and `openpyxl.load_workbook(read_only=True, data_only=True)`; cells are normalized to text only at validation time so numeric/date cells keep their type.
- [ ] **Step 4:** Run the file; expected PASS. ruff + pyright.
- [ ] **Step 5:** Commit (`feat: add import file parsing and row validation`).

---

### Task 7: Import preview, apply and history

**Files:**
- Create: `app/modules/imports/{model,schema,service,router}.py`, `alembic/versions/004_imports.py`, `tests/test_imports_api.py`
- Modify: `app/db/models/__init__.py`, `app/api/v1/router.py`

**Interfaces:**
- Consumes: Task 6 functions; `Student`, `Invoice` (Task 5); `record_audit` (Task 4).
- Produces: `ImportBatch(AuditedModel)`: `source`, `file_name`, `semester`, `status` (`preview|applied|discarded`), `summary: JSON` (`rows_total, rows_valid, rows_error, students_new, students_updated, invoices_new, invoices_updated, invoices_skipped`), `rows: JSON` (validated rows for preview), `applied_at`; `ImportRowError(AuditedModel)`: `batch_id, row_number, field, message` (store at most 500, count all). Routes under `/imports`: `POST` (multipart `file`, `source`, optional `semester`; returns batch in `preview`), `POST /{id}/apply`, `POST /{id}/discard`, `GET` (list), `GET /{id}`, `GET /{id}/errors` (`ListQuery`). Permissions `imports:create` (POST) and `imports:read`.

- [ ] **Step 1: Write failing tests:**
  - `test_preview_changes_no_business_data`; preview reports counts and the first errors.
  - `test_apply_upserts_students_and_invoices`; second import of a changed amount updates the invoice.
  - `test_paid_is_sticky`: file 2 says `belum lunas` for an already paid invoice -> stays `paid`, counted in `invoices_skipped`.
  - `test_paid_row_sets_paid_at_and_paid_via`; `paid_via` falls back to the batch source.
  - `test_valid_phone_not_overwritten_by_invalid`; `test_missing_phone_marks_student_missing`; `test_import_never_changes_opted_out_at`.
  - `test_unlisted_invoices_untouched`.
  - `test_duplicate_invoice_code_in_file_is_a_row_error_for_the_second_row` (Review Focus 3).
  - `test_apply_twice_returns_409_and_creates_nothing_new` (Review Focus 3); `test_apply_discarded_batch_409`.
  - `test_new_student_without_name_is_row_error`.
  - Access: 401, pimpinan 403, staf_keuangan 201; audit events `import.previewed`/`import.applied`.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement. Apply runs in one transaction and locks the batch row (`UPDATE ... WHERE status='preview'` returning count) so concurrent applies cannot both win; parse errors become 422 with the Indonesian message from `ImportFileError`.
- [ ] **Step 4:** `pytest`, ruff, pyright; migration up/down check. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add import preview and apply with sticky paid status`).

---

### Task 8: Message templates and schedule rules (with defaults)

**Files:**
- Create: `app/modules/templates/{__init__,model,schema,rendering,repository,service,router,seed}.py`, `app/modules/schedules/*`, `alembic/versions/005_templates_and_schedules.py`, `tests/test_templates_schedules.py`
- Modify: `app/db/seed.py` (call the default seeders), `app/db/models/__init__.py`, `app/api/v1/router.py`

**Interfaces:**
- Produces: `ALLOWED_VARIABLES: tuple[str, ...]` (see Global Constraints), `OPT_OUT_FOOTER = "Balas STOP untuk berhenti."`; `unknown_variables(body: str) -> list[str]`; `format_rupiah(amount: int) -> str` (`1250000 -> "1.250.000"`); `format_date_id(d: date) -> str` (`"15 November 2026"`); `render_body(body: str, context: Mapping[str, str]) -> str`; `build_message_body(template: MessageTemplate, *, student: Student, invoice: Invoice, settings: AppSettings) -> str` (renders, picks `payment_link_siakad`/`payment_guide_sipema` by `invoice.source`, appends `"\n\n" + OPT_OUT_FOOTER`); `MessageTemplate(AuditedModel)`: `name` (unique), `body: Text`, `is_active`; `ScheduleRule(AuditedModel)`: `name`, `offset_days: int`, `template_id`, `is_active`. Routes `/templates` (CRUD + `POST /templates/preview` `{body}` -> rendered with sample data), `/schedule-rules` (CRUD). `seed_default_templates_and_rules(db)` creates, only when no templates exist, the two BRD templates ("Pengingat sebelum jatuh tempo", "Tunggakan setelah jatuh tempo") and six rules `-7, -3, -1, 0` -> reminder, `3, 7` -> arrears.

- [ ] **Step 1: Write failing tests:** `test_unknown_variable_rejects_save_with_422_naming_it`; `test_render_body_formats_amount_and_date_in_indonesian`; `test_build_message_body_appends_footer_and_picks_link_by_source`; `test_footer_cannot_be_removed` (template containing the footer text still gets exactly one footer appended at send time, i.e. footer is not part of the stored body check); `test_seed_creates_defaults_once_and_never_overwrites_edits`; `test_duplicate_active_offset_409`; `test_delete_template_used_by_active_rule_409`; `test_template_and_rule_changes_write_audit_events` (`template.created|updated|deleted`, `schedule_rule.created|updated|deleted`); permission matrix (pimpinan 403).
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement; use regex `\{\{\s*(\w+)\s*\}\}` for variables; month names in a constant tuple; service checks duplicate offsets among non-deleted active rules.
- [ ] **Step 4:** `pytest`, ruff, pyright, migration check. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add message templates, schedule rules and BRD default seed`).

---

### Task 9: WhatsApp provider layer and webhook signature

**Files:**
- Create: `app/modules/whatsapp/{__init__,provider,fake,gateway,signature,deps}.py`, `tests/test_whatsapp_providers.py`

**Interfaces:**
- Produces: `SendResult(provider_message_id: str)`; `ProviderStatus(state: Literal["connected","connecting","qr","disconnected"], qr: str | None = None)`; exceptions `NotOnWhatsApp`, `ProviderUnavailable`; `class WhatsAppProvider(Protocol)` with `async send(self, *, phone: str, text: str, client_ref: str) -> SendResult`, `async status(self) -> ProviderStatus`, `async logout(self) -> None`; `FakeProvider` (records `sent: list[SentMessage]`; `state` attribute; `fail_next(exc)`; `unregistered: set[str]` raising `NotOnWhatsApp`); `GatewayProvider(base_url, api_key, client: httpx.AsyncClient)` (HTTP 404 `not_on_whatsapp` -> `NotOnWhatsApp`; 503 or connection error -> `ProviderUnavailable`); `sign_body(secret: str, body: bytes) -> str` returning `sha256=<hex>`; `verify_signature(secret, body, header) -> bool` (constant time); `get_provider() -> WhatsAppProvider` (cached, `WA_PROVIDER=fake|gateway`).

- [ ] **Step 1: Write failing tests** (httpx `MockTransport` for the gateway): `test_gateway_send_posts_bearer_and_returns_id`; `test_gateway_404_maps_to_not_on_whatsapp`; `test_gateway_503_and_timeout_map_to_unavailable`; `test_fake_provider_records_and_fails_on_demand`; `test_signature_roundtrip_and_tamper_detection` (flipped byte, wrong secret, missing `sha256=` prefix all false); `test_phone_is_masked_in_gateway_logs` (caplog contains only last 4 digits).
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement; the gateway request body is `{"to": phone, "text": text, "client_ref": client_ref}` and the response `{"provider_message_id": str}`; status endpoint `GET /status -> {"state", "qr"}`; logout `POST /logout`.
- [ ] **Step 4:** Tests, ruff, pyright. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add the WhatsApp provider interface with fake and gateway implementations`).

---

### Task 10: Messages model and the planner

**Files:**
- Create: `app/modules/messages/{__init__,constants,model,repository,planner}.py`, `alembic/versions/006_messages.py`, `tests/test_planner.py`
- Modify: `app/db/models/__init__.py`

**Interfaces:**
- Consumes: `build_message_body` (Task 8), `local_today` (Task 4), `AppSettings`, `Invoice`, `Student`, `ScheduleRule`.
- Produces: `Message(AuditedModel)` with the columns in spec section 3 (`student_id, invoice_id, rule_id, kind, batch_ref, scheduled_date, body, status, cancel_reason, attempts, provider_message_id, error, queued_at, sent_at, delivered_at, read_at, next_attempt_at`) and `UniqueConstraint(invoice_id, rule_id)`; `PlanReport(created: int, expired: int, superseded: int, escalated: int)`; `async def plan_messages(db: AsyncSession, *, now: datetime) -> PlanReport` (commits).

- [ ] **Step 1: Write failing tests** with fixtures that create students/invoices/rules/settings directly and pass `now` explicitly:
  - `test_creates_message_when_rule_date_is_today`; `test_rule_date_in_past_3_days_is_still_planned` (Friday rule date, planned on Monday); `test_rule_date_older_than_3_days_not_planned`; `test_planning_twice_is_idempotent`.
  - `test_skips_paid_opted_out_exempt_and_invalid_phone`.
  - `test_midnight_boundary_uses_jakarta_date` (`now=2026-11-14T17:30Z` plans rules for 2026-11-15) (Review Focus 4).
  - `test_queued_older_than_3_days_become_cancelled_expired`.
  - `test_only_latest_rule_survives_per_invoice` (older queued -> `cancelled(superseded)`).
  - `test_invoice_past_escalation_offset_gets_escalated_at_and_no_message`.
  - `test_message_body_is_rendered_at_planning_time_with_footer`.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement as set-based queries (one pass per rule, `INSERT` guarded by the unique key via existence check plus `IntegrityError` safety); body rendered with `build_message_body`; `scheduled_date = due_date + offset`.
- [ ] **Step 4:** `pytest`, ruff, pyright, migration check. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add the messages queue model and the planner`).

---

### Task 11: The sender (send phase)

**Files:**
- Create: `app/modules/messages/sender.py`, `tests/test_sender.py`

**Interfaces:**
- Consumes: Task 9 provider types, Task 10 model/planner, `AppSettings`, `local_now`.
- Produces: `SendOutcome = Literal["sent","cancelled","deferred","retry","failed","idle"]`; `async def send_next(session_factory, provider, *, now: datetime, sleep: Callable[[float], Awaitable[None]], jitter: Callable[[int, int], float]) -> SendOutcome` (claims and processes at most one message in its own transaction); `async def run_send_phase(session_factory, provider, *, clock: Clock, sleep, jitter) -> int` (loops `send_next` until idle, gated, or paused; returns messages handled).

- [ ] **Step 1: Write failing tests** (FakeProvider, injected clock/sleep recording requested delays):
  - Gates: `test_nothing_sent_when_auto_send_disabled`; `test_nothing_sent_outside_window` (07:59 and 17:01 WIB, Saturday); `test_window_is_rechecked_after_throttle_sleep` (clock moves past 17:00 during the sleep -> remaining messages stay `queued`) (Review Focus 4); `test_daily_cap_stops_sending_and_counts_local_day`.
  - Re-check (FR-06): `test_paid_invoice_is_cancelled_not_sent` (`cancel_reason="paid"`), likewise `opted_out`, `exempt`, `phone_invalid`.
  - AB-03: `test_one_automatic_message_per_student_per_day_and_second_is_deferred_not_lost` (two invoices due the same day: one sent today; the other still `queued` and sent on the next working day; oldest due date first) (Review Focus 5).
  - Throttle: `test_sleeps_between_messages_within_configured_range`.
  - Errors: `test_provider_failure_retries_with_5_15_45_minute_backoff_then_fails` (sets `next_attempt_at`, `attempts`); `test_not_on_whatsapp_fails_immediately_and_marks_student_invalid`; `test_one_failure_does_not_stop_the_rest`; `test_circuit_breaker_after_5_consecutive_failures_sets_paused_reason_and_stops`; `test_provider_unavailable_pauses_without_burning_attempts`; `test_stale_sending_message_is_requeued_after_10_minutes_unless_provider_id_set`.
  - `test_claim_is_atomic` (two concurrent `send_next` calls send a message once).
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement. Claim with a conditional `UPDATE messages SET status='sending' WHERE id=:id AND status='queued'` and proceed only if one row changed (use `FOR UPDATE SKIP LOCKED` when the engine is PostgreSQL). Order candidates by `scheduled_date`, then invoice `due_date`, then `id`; skip those with `next_attempt_at > now`. Reset the consecutive-failure counter on any success; keep the counter derived from the most recent messages' outcomes (no new column).
- [ ] **Step 4:** `pytest tests/test_sender.py -v`, ruff, pyright. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add the message sender with re-check, throttling, retries and circuit breaker`).

---

### Task 12: Worker loop and CLI

**Files:**
- Create: `app/modules/messages/runner.py`, `tests/test_runner.py`
- Modify: `app/cli.py` (`run-worker [--once]`, docstring), `deploy/ecosystem.prod.config.js`, `deploy/ecosystem.config.cjs`

**Interfaces:**
- Produces: `async def run_worker(*, session_factory, provider, clock: Clock, sleep, jitter, tick_seconds: int, once: bool = False) -> None` (each tick: `plan_messages` then `run_send_phase`; exceptions in a tick are logged and the loop continues; stops cleanly on `asyncio.CancelledError`); CLI `python -m app.cli run-worker` and `--once`.

- [ ] **Step 1: Write failing tests:** `test_once_runs_plan_then_send` (FakeProvider receives the message); `test_exception_in_plan_does_not_kill_the_loop` (second tick still sends); `test_stops_on_cancellation`.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement; add the PM2 process `kampusping-worker` (`python -m app.cli run-worker`, same env as the API).
- [ ] **Step 4:** `pytest`; manual check: with `WA_PROVIDER=fake` and a seeded SQLite DB, `python -m app.cli run-worker --once` exits 0 and prints counts.
- [ ] **Step 5:** Commit (`feat: add the worker loop and the run-worker command`).

---

### Task 13: Message log API, WhatsApp status and the webhook

**Files:**
- Create: `app/modules/messages/{schema,router}.py`, `app/modules/whatsapp/router.py`, `tests/test_messages_api.py`
- Modify: `app/api/v1/router.py`

**Interfaces:**
- Consumes: `get_provider`, `verify_signature`, `Message`.
- Produces: `GET /messages` (`ListQuery`; filters `status`, `student_id`, `invoice_id`, `date_from`, `date_to`; rows embed `student: {nim, name}` and mask the phone), `GET /messages/{id}`, `POST /messages/{id}/cancel` (`queued` only, `cancel_reason="manual"`, audit; else 409); `GET /whatsapp/status` (`settings:read`) -> `{state, qr, paused_reason}`; `POST /whatsapp/logout` (`settings:update`, audit); `POST /webhooks/whatsapp` (no user auth; requires valid `X-Signature` else 401): `{"type":"status","provider_message_id","state":"delivered"|"read"|"failed"}` updates the message (`delivered_at`/`read_at`; never regresses `read` to `delivered`), `{"type":"connection","state"}` is acknowledged, `{"type":"inbound",...}` is acknowledged with 202 and ignored until M3. Unknown `provider_message_id` -> 202.

- [ ] **Step 1: Write failing tests:** list/filter/pagination; phone masked in responses; `test_cancel_only_queued`; `test_webhook_rejects_missing_or_bad_signature_with_401`; `test_webhook_status_updates_delivered_then_read_and_never_regresses`; `test_webhook_unknown_id_is_202`; `test_whatsapp_status_uses_provider_and_requires_permission`; permission matrix (pimpinan 403 on messages).
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement; the webhook reads `await request.body()` for the HMAC before JSON parsing.
- [ ] **Step 4:** `pytest`, ruff, pyright. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add the message log, WhatsApp status and the signed webhook`).

---

### Task 14: Dashboard summary API

**Files:**
- Create: `app/modules/dashboard/{__init__,schema,service,router}.py`, `tests/test_dashboard.py`
- Modify: `app/api/v1/router.py`

**Interfaces:**
- Produces: `GET /dashboard/summary?semester=` (`dashboard:read`) -> `{"invoices": {"total","total_amount","paid","paid_amount","unpaid","overdue","overdue_amount"}, "messages": {"queued","sent","delivered","read","failed","cancelled"}, "warnings": {"paused_reason": str | null}}`. `overdue` = unpaid with `due_date` before today in `APP_TIMEZONE`. No personal data in the response.

- [ ] **Step 1: Write failing tests:** counts and amounts on a seeded dataset; `semester` filter; `overdue` boundary (due today is not overdue); pimpinan allowed, staf_keuangan allowed, anonymous 401; response contains no `nim`, `name` or `phone` keys.
- [ ] **Step 2-4:** Run (FAIL), implement with aggregate queries, run (PASS), ruff + pyright.
- [ ] **Step 5:** Commit (`feat: add the dashboard summary endpoint`).

---

### Task 15: WhatsApp gateway service (Baileys)

**Files:**
- Create (new repo `kampusping-wa-gateway/`, `git init`, branch `development`): `package.json`, `tsconfig.json`, `eslint.config.mjs`, `.prettierrc.json`, `.gitignore` (includes `auth_state/`, `.env`), `.env.example`, `README.md`, `src/{config,webhook,app,client,baileys,index}.ts`, `src/*.test.ts`, `deploy/ecosystem.prod.config.js`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `interface WaClient { start(): Promise<void>; sendText(phone: string, text: string): Promise<{ id: string }>; isOnWhatsApp(phone: string): Promise<boolean>; logout(): Promise<void>; onEvent(handler: (event: GatewayEvent) => void): void; snapshot(): { state: 'connected' | 'connecting' | 'qr' | 'disconnected'; qr: string | null } }`; `type GatewayEvent = { type: 'status'; provider_message_id: string; state: 'delivered' | 'read' | 'failed' } | { type: 'connection'; state: string }`; `createApp({ client, apiKey, webhook }): FastifyInstance` with `POST /messages` (`{to, text, client_ref}` -> `200 {provider_message_id}`, `404 {error:"not_on_whatsapp"}`, `503 {error:"disconnected"}`), `GET /status`, `POST /logout`, all requiring `Authorization: Bearer <apiKey>` (401 otherwise); `createWebhookSender({ url, secret, fetch })` posting events signed as `X-Signature: sha256=<hex>`; `createBaileysClient({ authDir, logger })` (the only file importing Baileys); env: `GATEWAY_HOST=127.0.0.1`, `GATEWAY_PORT=8095`, `WA_GATEWAY_API_KEY`, `WA_WEBHOOK_URL`, `WA_WEBHOOK_SECRET`, `WA_AUTH_DIR=./auth_state`.

- [ ] **Step 1:** Create the project with Node 20+, ESM, TypeScript strict, Vitest, ESLint, Prettier. Pin exact versions of `fastify` and `@whiskeysockets/baileys` after checking `npm view <pkg> version` and the Baileys README for the current connection and `messages.update` APIs; record the pinned versions in the README.
- [ ] **Step 2: Write failing tests** with a fake `WaClient`: `test_requests_without_bearer_are_401`; `test_send_returns_provider_message_id`; `test_send_unregistered_number_is_404_not_on_whatsapp`; `test_send_while_disconnected_is_503`; `test_status_returns_snapshot_with_qr`; `test_logout_calls_client`; `test_webhook_sender_signs_body_with_hmac_sha256` (recompute with `crypto` and compare); `test_events_from_client_are_forwarded_to_webhook`; `test_phone_digits_are_normalised_to_jid_without_plus` (unit test for the helper that builds `<digits>@s.whatsapp.net`).
- [ ] **Step 3:** Run `npm test`; expected FAIL.
- [ ] **Step 4:** Implement `app.ts`, `webhook.ts`, `config.ts`, `index.ts`, then `baileys.ts` against the real library: `useMultiFileAuthState(authDir)`, reconnect with backoff unless logged out, map connection updates to `snapshot()` and `connection` events, map message ack statuses (`DELIVERY_ACK` -> `delivered`, `READ` -> `read`, error -> `failed`) from `messages.update` to `status` events keyed by the sent message id, `onWhatsApp` for `isOnWhatsApp`. Never log full phone numbers (last 4 digits). `baileys.ts` is excluded from unit tests; it is covered by the manual smoke test in Task 19.
- [ ] **Step 5:** `npm run check` (lint, typecheck, format, test) and `npm run build`; expected PASS. Commit (`feat: add the Baileys WhatsApp gateway service`).

---

### Task 16: Frontend foundation, menu and the import screen

**Files:**
- Create: `src/modules/import/{types.ts,services/import.service.ts,components/ImportPage.tsx,components/ImportPreview.tsx,components/ImportHistory.tsx}`, `src/app/(app)/import/page.tsx`, tests `ImportPage.test.tsx`
- Modify: `src/core/config/{menu.config.ts,route.config.ts}`, `src/core/auth/permissions.ts` (if not complete from Task 3), `src/core/http/api-client.ts` only if multipart upload needs `apiClient.upload(path, FormData)`

**Interfaces:**
- Produces: routes `import`, `students`, `invoices`, `templates`, `schedules`, `messages`, `settings`, `audit` (English paths, Indonesian labels); menu groups: *Penagihan* (Dasbor, Impor Data, Mahasiswa, Tagihan, Pengiriman), *Pengaturan Pesan* (Template Pesan, Jadwal), *Administrasi* (Pengaturan, Pengguna, Peran, Audit), each item guarded by the Task 3 permission; `importService.preview(file: File, source: 'siakad' | 'sipema', semester?: string)`, `.apply(id)`, `.discard(id)`, `.list(query)`, `.errors(id, query)` returning types mirrored from `app/modules/imports/schema.py`.

- [ ] **Step 1: Write failing tests** (Vitest + Testing Library, `importService` mocked): `shows the preview counts and first errors after upload`; `Terapkan stays disabled until a preview exists and blocks double submit`; `shows the Indonesian server error when the file is rejected`; `menu hides Impor Data without imports:read` (extend `RequirePermission`/menu test).
- [ ] **Step 2:** Run `npm test`; expected FAIL.
- [ ] **Step 3:** Implement the page: source select, optional semester field, file input accepting `.csv,.xlsx`, preview card (counts + error table via `AppDataGrid`), buttons Terapkan / Batalkan, history grid. Follow `src/modules/README.md` and the patterns of the users module (`useServerGrid`, `AppDataGrid`, `PageHeader`).
- [ ] **Step 4:** `npm run check`. Expected PASS.
- [ ] **Step 5:** Commit (`feat: add the Indonesian menu and the data import screen`).

---

### Task 17: Frontend lists: students, invoices, messages

**Files:**
- Create: `src/modules/{students,invoices,messages}/{types.ts,services/*.service.ts,components/*ListPage.tsx}`, `src/modules/students/components/PhoneDialog.tsx`, `src/app/(app)/{students,invoices,messages}/page.tsx`, tests `StudentsListPage.test.tsx`, `InvoicesListPage.test.tsx`, `MessagesListPage.test.tsx`

**Interfaces:**
- Consumes: Task 5 and 13 routes. Produces: list pages with search, filters (students: prodi, angkatan, status nomor; invoices: status, semester, jatuh tempo range; messages: status, date range), status chips (`AppStatusChip` tones: `paid`/`delivered`/`read` success, `queued` default, `failed` error, `cancelled` warning with the Indonesian cancel reason), phone shown as stored for staff, edit-phone dialog (RHF + Zod, server error mapped with `handleFormApiError`), mark-unpaid action for invoices (`AppConfirmDialog`), cancel action for queued messages.

- [ ] **Step 1: Write failing tests:** each page renders rows from a mocked service and shows Indonesian column headers; `PhoneDialog` shows the server's 422 message on the field; invoice revert asks for confirmation before calling the service; cancel button appears only for `queued` rows and only with `messages:cancel`.
- [ ] **Step 2-4:** Run (FAIL), implement following `UsersListPage`, run `npm run check` (PASS).
- [ ] **Step 5:** Commit (`feat: add student, invoice and message log screens`).

---

### Task 18: Frontend templates, schedules, settings, audit and dashboard

**Files:**
- Create: `src/modules/{templates,schedules,settings,audit}/...` (types, services, list/form components, `WhatsAppPanel.tsx`), `src/app/(app)/{templates,schedules,settings,audit}/page.tsx`; rewrite `src/modules/dashboard/components/DashboardPage.tsx`; tests per module
- Modify: none outside these folders except the menu entries already added in Task 16

**Interfaces:**
- Consumes: Tasks 4, 8, 13, 14 routes. Produces: template form with variable chips and a live preview (`POST /templates/preview`, debounced), warning text that the footer is added automatically; schedule rules grid with offset label (`H-7`, `H`, `H+3`) and template select; settings form (identity, payment texts, send window as time fields, working days checkboxes, safeguards) with the `auto_send_enabled` switch behind an `AppConfirmDialog` explaining the BAILEYS risk in Indonesian; `WhatsAppPanel` polling `GET /whatsapp/status` every 3 s while the QR is shown, rendering the QR string as an image with `qrcode.react` (a new frontend library: ask the user to approve it before installing; until then show the raw QR string in a monospace box), `paused_reason` banner with a "Lanjutkan" button (`POST /settings/resume`); audit log grid; dashboard with stat cards (tagihan, lunas, belum lunas, tunggakan, pesan terkirim, delivered %) and a `PieChart` of invoice status using theme CSS variables, warning alerts for `paused_reason` and a disconnected WhatsApp.

- [ ] **Step 1: Write failing tests:** `TemplateFormDialog` shows an unknown-variable error returned by the API under the body field and keeps the dialog open; the live preview calls the service once after the debounce; `SettingsPage` requires confirmation before enabling auto-send; `WhatsAppPanel` shows the QR when `state === "qr"` and "Terhubung" when connected; `DashboardPage` renders the cards from a mocked summary and the paused warning; audit page hidden without `audit:read`.
- [ ] **Step 2-4:** Run (FAIL), implement, `npm run check` (PASS).
- [ ] **Step 5:** Commit (`feat: add template, schedule, settings, audit screens and the real dashboard`).

---

### Task 19: Deploy assets, e2e, docs and manual smoke test

**Files:**
- Modify: `docker-compose.yml`, `kampusping-backend/deploy/{deploy-prod.sh,.env.production.example}`, `.env.example` files, `README.md` (root, backend, frontend, gateway), `kampusping-backend/docs/{adding-a-module.md}` (remove example references) + new `kampusping-backend/docs/messaging.md`, `CLAUDE.md` (status and test counts), `kampusping-frontend/e2e/app.spec.ts` and `e2e/README.md`
- Create: `docs/runbook-whatsapp.md` (linking the WhatsApp number, QR, backups of `auth_state/`, what to do on a ban or disconnect)

**Interfaces:**
- Produces: compose services `worker` and `wa-gateway`; PM2 apps `kampusping-worker` and `kampusping-wa-gateway`; e2e flow: sign in -> upload a small CSV on `/import` -> Terapkan -> row appears in `/students` and `/invoices`.

- [ ] **Step 1:** Add the Playwright test for the import flow (failing until the full stack runs); add a CSV fixture under `e2e/fixtures/`.
- [ ] **Step 2:** Start backend (`WA_PROVIDER=fake`, SQLite or Postgres), frontend, run `npm run test:e2e` on free ports per `e2e/README.md`; expected PASS.
- [ ] **Step 3:** Update compose, deploy scripts, env examples and READMEs; write `messaging.md` (queue states, rules AB-01..AB-08 mapping, how to run the worker) and the WhatsApp runbook; update `CLAUDE.md` Status, commands and counts from real runs; do not run any production deploy.
- [ ] **Step 4:** Run every gate: backend `ruff check . && ruff format --check . && pyright && pytest`; frontend `npm run check` and `npm run build`; gateway `npm run check`. Record the real test counts in `CLAUDE.md`.
- [ ] **Step 5:** Manual smoke test (user, on a real phone; cannot be automated): start the gateway, scan the QR from Pengaturan, set `WA_PROVIDER=gateway`, import two test invoices (one paid, one unpaid) for a number you own, enable auto-send, run `python -m app.cli run-worker --once` inside the send window; expected: only the unpaid student receives a message, `messages` shows `sent`, then `delivered`/`read` after the phone receives it. Report the outcome.
- [ ] **Step 6:** Commit per repo (`docs: add messaging docs, runbook and deploy assets`; `test: cover the import flow end to end`).
