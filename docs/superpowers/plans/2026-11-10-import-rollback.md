# Rollback Impor Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staf dengan izin `imports:rollback` dapat menghapus impor berstatus *Diterapkan* dari Riwayat impor, dan data yang dibuat atau diubah impor itu dikembalikan seperti sebelum diterapkan.

**Architecture:** Saat impor diterapkan, `ChangeRecorder` mencatat tiap mahasiswa/tagihan yang dibuat atau diubah ke tabel baru `import_changes` (nilai `before` dan `after` hanya untuk field yang berubah). Rollback membaca log itu dalam satu transaksi: menolak seluruhnya bila data sudah berubah sejak impor (konflik), selain itu soft-delete baris `created`, memulihkan field baris `updated`, dan membatalkan pesan antre. Hanya impor *Diterapkan* terbaru yang boleh di-rollback.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, pytest (backend); Next.js 16, MUI 9, Vitest, Playwright (frontend). Tanpa dependensi baru.

**Spec:** [`docs/superpowers/specs/2026-11-10-import-rollback-design.md`](../specs/2026-11-10-import-rollback-design.md)

## Global Constraints

- Teks UI dan pesan error ke pengguna berbahasa Indonesia; kode, nama field, migrasi, komentar, dan pesan commit berbahasa Inggris.
- Izin ditegakkan di server dengan `require_permissions(...)`; jangan bercabang berdasarkan nama atau id peran. Kode izin baru: `imports:rollback`, dimiliki `admin` saja (bukan `staf_keuangan`, bukan `pimpinan`).
- Kontrak API: body sukses polos, error `{"error": {"code", "message", "details"}}`, rute di bawah `/api/v1`.
- Waktu disimpan UTC; jam disuntik (`Clock`) supaya tes tidak bergantung waktu sistem.
- Perintah python lokal: `DATABASE_ENGINE=sqlite` dan `DATABASE_URL=sqlite+aiosqlite:///<file di luar repo>` (mis. `$(mktemp -d)/kp.db`); jangan menjalankan migrasi atau worker ke database remote.
- Aturan AB-01 / FR-06 (lunas sticky, cek ulang sebelum kirim), AB-03, dan NFR-07 (audit) tidak boleh melemah. Tidak menambah pustaka baru.
- Data pribadi (UU PDP): respons konflik hanya memuat NIM / kode tagihan dan **nama field**, tidak pernah nilai (nomor HP, nama).
- Tiap folder aplikasi adalah repo git sendiri: commit di repo yang sesuai (`kampusping-backend/`, `kampusping-frontend/`, root untuk `docs/` dan `CLAUDE.md`). Conventional Commits, satu perubahan logis per commit, tanpa push, merge, tag, atau deploy.
- Gerbang kualitas backend: `ruff check . && ruff format --check . && pyright && pytest`; frontend: `npm run check`.

## Review Focus

- Impor yang semua barisnya dilewati (tidak mengubah apa pun): rollback tetap berhasil dan tidak mengubah data. (Task 4)
- Rollback lalu mengunggah dan menerapkan berkas yang sama lagi: baris soft-deleted dipulihkan, tidak ada tabrakan `nim` / `invoice_code` unik. (Task 4)
- Dua permintaan rollback bersamaan untuk impor yang sama: satu berhasil, satu 409. (Task 4)
- Satu mahasiswa atau tagihan muncul di dua baris berkas: satu catatan log dengan `before` dari keadaan awal. (Task 2)
- Tagihan "superseded" yang dibalikkan ke belum lunas: pesan yang dulu dibatalkan karena `paid` tetap `cancelled` dan tidak ada duplikat pasangan (tagihan, aturan) saat planner jalan lagi. (Task 4)
- Impor lebih dari 500 baris (melewati `LOOKUP_CHUNK`): pencarian dan pembaruan dalam potongan tetap lengkap. (Task 3)

## File Structure

Backend (`kampusping-backend/`):
- `app/modules/imports/model.py` (ubah): `ImportChange`; kolom `has_change_log`, `rolled_back_at` di `ImportBatch`.
- `app/modules/imports/constants.py` (ubah): `ImportStatus.ROLLED_BACK`, `ChangeEntity`, `ChangeAction`, konstanta audit dan pesan.
- `app/modules/imports/changes.py` (baru): `ChangeRecorder`, serialisasi nilai field. Satu tanggung jawab: mencatat perubahan saat apply.
- `app/modules/imports/rollback.py` (baru): `build_plan`, `execute_plan`. Satu tanggung jawab: logika rollback di atas log.
- `app/modules/imports/apply.py`, `service.py`, `repository.py`, `schema.py`, `router.py` (ubah).
- `alembic/versions/008_import_changes.py` (baru).
- `app/db/models/__init__.py`, `app/core/permissions.py` (ubah).
- Tes: `tests/test_imports_changes.py`, `tests/test_imports_rollback_core.py`, `tests/test_imports_rollback_api.py` (baru); `tests/test_permissions_seed.py` (ubah).

Frontend (`kampusping-frontend/src/`): `core/auth/permissions.ts`, `modules/import/{types.ts,constants.ts}`, `modules/import/services/import.service.ts`, `modules/import/components/{ImportRollbackDialog.tsx (baru),ImportHistory.tsx,ImportPage.tsx,ImportPage.test.tsx}`, `e2e/billing.spec.ts`.

---

### Task 1: Model, konstanta, dan migrasi `import_changes`

**Files:**
- Modify: `kampusping-backend/app/modules/imports/model.py`, `.../constants.py`, `app/db/models/__init__.py`
- Create: `kampusping-backend/alembic/versions/008_import_changes.py`
- Test: `kampusping-backend/tests/test_imports_changes.py`

**Interfaces:**
- Produces:
  - `ImportStatus.ROLLED_BACK = "rolled_back"`; `ChangeEntity(StrEnum)`: `STUDENT="student"`, `INVOICE="invoice"`; `ChangeAction(StrEnum)`: `CREATED="created"`, `UPDATED="updated"`.
  - `AUDIT_IMPORT_ROLLED_BACK = "import.rolled_back"`.
  - `ImportChange(AuditedModel)`, tabel `import_changes`: `batch_id: int` (FK `import_batches.id`), `entity: str`(10), `entity_id: int` (BigInteger), `action: str`(10), `before: dict[str, Any] | None` (JSON), `after: dict[str, Any]` (JSON); indeks `ix_import_changes_batch_id_entity` pada `(batch_id, entity)`.
  - `ImportBatch.has_change_log: bool` (default `False`, `server_default` false), `ImportBatch.rolled_back_at: datetime | None`.

- [ ] **Step 1: Tulis tes gagal** di `tests/test_imports_changes.py`: `test_import_change_roundtrip` menyisipkan `ImportBatch` + satu `ImportChange(batch_id=..., entity="invoice", entity_id=7, action="updated", before={"amount": 1}, after={"amount": 2})` lewat `get_session_factory()`, membacanya kembali, dan meng-assert `before`/`after`; `test_batch_defaults` meng-assert `has_change_log is False` dan `rolled_back_at is None` untuk batch baru.
- [ ] **Step 2: Jalankan, pastikan gagal:** `pytest tests/test_imports_changes.py -v` → `ImportError` pada `ImportChange`.
- [ ] **Step 3: Implementasi** model dan konstanta di atas; daftarkan `ImportChange` di `app/db/models/__init__.py` (pola `ImportRowError`). Tulis `008_import_changes.py` (revisi `008`, down `007`) dengan pola `004_imports.py` (`id_column()`, `audit_columns()`, `foreign_keys(...)`): buat tabel + indeks, dan `op.add_column` untuk `has_change_log` (`sa.Boolean`, `server_default=sa.false()`, not null) dan `rolled_back_at` pada `import_batches`; `downgrade` membalik urutannya. Migrasi **tidak** memberi izin ke peran mana pun.
- [ ] **Step 4: Jalankan tes** → PASS. Lalu verifikasi migrasi pada sqlite sementara: `alembic upgrade head && alembic check` (keluaran `No new upgrade operations detected.`), lalu `alembic downgrade 007 && alembic upgrade head`.
- [ ] **Step 5: Commit** (repo backend): `feat: add import_changes table and rollback columns on import batches`

---

### Task 2: Mencatat perubahan saat impor diterapkan

**Files:**
- Create: `kampusping-backend/app/modules/imports/changes.py`
- Modify: `app/modules/imports/apply.py`, `app/modules/imports/service.py` (method `apply`)
- Test: `kampusping-backend/tests/test_imports_changes.py`

**Interfaces:**
- Consumes: Task 1 (`ImportChange`, `ChangeEntity`, `ChangeAction`, `has_change_log`).
- Produces (`changes.py`):
  - `TRACKED_FIELDS: dict[ChangeEntity, tuple[str, ...]]`: student → `name, study_program, cohort, phone, phone_status, deleted_at, deleted_by`; invoice → `semester, amount, due_date, status, paid_at, paid_via, source, deleted_at, deleted_by`.
  - `def serialize_fields(entity: ChangeEntity, obj: Student | Invoice) -> dict[str, Any]`: nilai terlacak sebagai JSON (`date`/`datetime` → `isoformat()`, lainnya apa adanya).
  - `def deserialize_value(field: str, value: Any) -> Any`: kebalikannya (`due_date`, `paid_at` → `date`; `deleted_at` → `datetime`).
  - `class ChangeRecorder`: `snapshot(self, obj: Student | Invoice) -> None` (panggilan pertama per objek menang; dipanggil sebelum mutasi), `created(self, obj: Student | Invoice) -> None`, `build(self, *, batch_id: int, actor: str, now: datetime) -> list[ImportChange]` (dipanggil setelah flush akhir; objek `created` → `action=created`, `before=None`, `after=` semua field terlacak; objek ber-snapshot → `updated` hanya bila ada field yang berbeda, `before`/`after` hanya field yang berbeda).
  - `apply_rows(..., recorder: ChangeRecorder | None = None)`.

- [ ] **Step 1: Tulis tes gagal** (lewat `import_lines`/`preview`/`apply` dari `tests/imports_helpers.py`; baca `import_changes` lewat sesi), semuanya di `tests/test_imports_changes.py`:
  - `test_apply_records_created_students_and_invoices`: dua baris baru → 2 catatan `student` + 2 `invoice` ber-`action="created"`, `before is None`, `after["amount"] == 5_000_000`; `has_change_log is True`.
  - `test_apply_records_only_changed_fields_for_updates`: impor ulang kode yang sama dengan nominal berbeda → satu catatan `invoice` `updated` dengan `before == {"amount": 5000000}` dan `after == {"amount": 6000000}` (field tak berubah tidak ada).
  - `test_apply_records_paid_transition`: baris yang sama menjadi `lunas` → `before["status"] == "unpaid"`, `after["status"] == "paid"`, `paid_at` ikut tercatat.
  - `test_apply_records_superseded_invoice`: mahasiswa menerima kode tagihan baru, tagihan lama belum lunas ikut tercatat `updated` ke `paid`.
  - `test_apply_records_restored_soft_deleted_row`: invoice yang di-soft-delete lalu diimpor ulang → `updated` dengan `deleted_at` di `before` (string ISO) dan `None` di `after`.
  - `test_sticky_skip_and_unchanged_rows_record_nothing`: impor ulang berkas identik, dan baris `belum lunas` terhadap tagihan lunas → 0 catatan baru.
  - `test_entity_touched_by_two_rows_is_one_change`: dua baris berkas dengan NIM sama (kode tagihan berbeda) pada mahasiswa yang sudah ada → tepat satu catatan `student` dengan `before` dari keadaan awal.
  - `test_serialization_roundtrip`: `deserialize_value("due_date", "2026-11-15") == date(2026, 11, 15)` dan `deserialize_value("deleted_at", None) is None`.
- [ ] **Step 2: Jalankan, pastikan gagal:** `pytest tests/test_imports_changes.py -v`.
- [ ] **Step 3: Implementasi `changes.py`**, lalu sambungkan: di `apply_rows`, sebelum mutasi pertama panggil `recorder.snapshot(...)` untuk semua mahasiswa dari `students`, semua tagihan dari `invoices`, dan `superseded_invoices`; panggil `recorder.created(...)` saat membuat `Student` / `Invoice` baru. Di `ImportService.apply`, buat `ChangeRecorder()`, teruskan ke `apply_rows`, lalu `self.db.add_all(recorder.build(batch_id=batch.id, actor=actor.email, now=now))` dan `batch.has_change_log = True` sebelum audit. Logika AB-01, sticky paid, dan hitungan `summary` tidak berubah.
- [ ] **Step 4: Jalankan seluruh tes impor:** `pytest tests/test_imports_changes.py tests/test_imports_apply.py tests/test_imports_preview.py -v` → semua PASS (tes apply yang sudah ada tidak boleh berubah).
- [ ] **Step 5: Commit** (backend): `feat: record per-row changes when an import is applied`

---

### Task 3: Inti rollback (rencana, konflik, eksekusi)

**Files:**
- Create: `kampusping-backend/app/modules/imports/rollback.py`
- Test: `kampusping-backend/tests/test_imports_rollback_core.py`

**Interfaces:**
- Consumes: Task 2 (`ImportChange` terisi, `serialize_fields`, `deserialize_value`), `_chunks` dari `existing.py`.
- Produces (`rollback.py`):
  - `@dataclass class RollbackConflict: entity: str; label: str; fields: list[str]` (`label` = NIM atau kode tagihan).
  - `@dataclass class RollbackPlan`: `changes: list[ImportChange]`, `entities: dict[tuple[str, int], Student | Invoice]`, `conflicts: list[RollbackConflict]`, `students_deleted: int`, `invoices_deleted: int`, `students_reverted: int`, `invoices_reverted: int`, `queued_messages: int`, `sent_messages: int`, `deleted_invoice_ids: list[int]`.
  - `async def build_plan(db: AsyncSession, batch_id: int) -> RollbackPlan`: memuat catatan dan entitas (termasuk yang soft-deleted) dalam potongan; konflik bila entitas hilang, atau ada field di `after` yang nilai sekarangnya berbeda; menghitung pesan `queued` dan pesan `SENT_STATUSES` untuk tagihan yang akan dihapus.
  - `async def execute_plan(db: AsyncSession, plan: RollbackPlan, *, actor: str, now: datetime) -> None`: `created` → `deleted_at/deleted_by`; `updated` → field `before` (via `deserialize_value`); keduanya mengisi `updated_by/updated_at`; pesan `queued` tagihan terhapus → `cancelled`, `cancel_reason=manual`, `error="Impor dibatalkan"`; flush. Pemanggil memiliki transaksi.

- [ ] **Step 1: Tulis tes gagal** di `tests/test_imports_rollback_core.py` (siapkan data lewat `import_lines` dengan `staf_headers`, panggil fungsi langsung lewat `get_session_factory()`):
  - `test_plan_counts_created_and_reverted`: impor A (2 mahasiswa, 2 tagihan), impor B (mengubah nominal satu tagihan A, menambah satu mahasiswa baru) → `build_plan(B)` memberi `students_deleted == 1`, `invoices_deleted == 1`, `invoices_reverted == 1`, `conflicts == []`.
  - `test_execute_restores_exact_previous_state`: ambil snapshot tabel `students` dan `invoices` (nilai bisnis + `deleted_at`) sebelum impor B, jalankan `execute_plan`, bandingkan sama persis.
  - `test_manual_change_after_import_is_a_conflict`: ubah status tagihan hasil impor lewat `PUT/PATCH` invoice atau langsung di DB → `conflicts` memuat `fields == ["status"]` dan `label` kode tagihan; nilai tidak muncul di dataclass.
  - `test_soft_deleted_created_invoice_is_a_conflict`: tagihan hasil impor di-soft-delete → konflik `fields` memuat `deleted_at`.
  - `test_queued_messages_are_cancelled_sent_ones_untouched`: buat dua `Message` untuk tagihan baru (satu `queued`, satu `sent`; helper di `tests/messages_helpers.py`) → setelah `execute_plan` yang pertama `cancelled` dengan `cancel_reason == "manual"`, yang kedua tetap `sent`; `plan.sent_messages == 1`, `plan.queued_messages == 1`.
  - `test_large_import_is_processed_in_chunks`: impor 600 baris baru, `build_plan` lalu `execute_plan` → 600 tagihan dan 600 mahasiswa ter-soft-delete.
  - `test_restored_row_is_reverted_to_deleted`: impor ulang yang memulihkan tagihan soft-deleted → rollback mengembalikannya ke soft-deleted.
- [ ] **Step 2: Jalankan, pastikan gagal:** `pytest tests/test_imports_rollback_core.py -v`.
- [ ] **Step 3: Implementasi `rollback.py`** sesuai signature di atas. Konflik membandingkan `serialize_fields(...)` saat ini dengan `after` per field; entitas yang tidak ditemukan dihitung sebagai konflik dengan `fields == ["missing"]`.
- [ ] **Step 4: Jalankan tes** → PASS.
- [ ] **Step 5: Commit** (backend): `feat: add rollback plan and execution over the import change log`

---

### Task 4: Izin, service, endpoint rollback, dan `rollback_block`

**Files:**
- Modify: `kampusping-backend/app/core/permissions.py`, `app/modules/imports/{repository.py,service.py,schema.py,router.py,constants.py}`, `tests/test_permissions_seed.py`
- Test: `kampusping-backend/tests/test_imports_rollback_api.py`

**Interfaces:**
- Consumes: Task 3 (`build_plan`, `execute_plan`, `RollbackPlan`).
- Produces:
  - `IMPORTS_ROLLBACK = "imports:rollback"`; `PermissionDef(IMPORTS_ROLLBACK, "Membatalkan impor yang sudah diterapkan (rollback)")` di `PERMISSIONS`; `STAF_KEUANGAN_PERMISSION_CODES` mengecualikan `IMPORTS_ROLLBACK` secara eksplisit (daftar itu otomatis memuat semua izin selain `users:`, `roles:`, `audit:`).
  - Repository: `ImportBatchRepository.claim_applied(batch_id: int, values: dict[str, object]) -> bool` (`UPDATE ... WHERE status='applied'`, pola `claim_preview`; keduanya berbagi satu helper privat), `latest_applied_id() -> int | None` (urut `applied_at` desc lalu `id` desc, hanya `status='applied'`, belum soft-deleted).
  - Service: `async def rollback_preview(self, batch_id: int) -> RollbackPreview`, `async def rollback(self, batch_id: int, actor: User) -> ImportBatch`, `async def read_models(self, batches: Sequence[ImportBatch]) -> list[ImportBatchRead]` (mengisi `rollback_block` dengan satu query `latest_applied_id`).
  - Schema: `ImportBatchRead` + `has_change_log: bool`, `rolled_back_at: datetime | None`, `rollback_block: Literal["no_change_log", "not_latest"] | None = None`; `RollbackConflictRead(entity: str, label: str, fields: list[str])`; `RollbackPreview(students_deleted: int, invoices_deleted: int, students_reverted: int, invoices_reverted: int, queued_messages_cancelled: int, sent_messages: int, conflicts: list[RollbackConflictRead], conflicts_total: int)` (`conflicts` maksimal 50).
  - Rute: `GET /api/v1/imports/{id}/rollback-preview` → 200 `RollbackPreview` (konflik dilaporkan di body, bukan error); `POST /api/v1/imports/{id}/rollback` → 200 `ImportBatchRead` berstatus `rolled_back`. Keduanya memakai `require_permissions(IMPORTS_ROLLBACK)`. Pelanggaran syarat → 409 `CONFLICT`; konflik data pada POST → 409 dengan `details = {"conflicts": [...], "conflicts_total": n}`. `GET ""` dan `GET /{id}` memakai `read_models`.
  - Pesan (konstanta di `constants.py`): `MSG_ROLLBACK_NOT_APPLIED = "Hanya impor berstatus Diterapkan yang dapat dibatalkan."`, `MSG_ROLLBACK_NO_LOG = "Impor ini diterapkan sebelum fitur rollback ada dan tidak dapat dibatalkan."`, `MSG_ROLLBACK_NOT_LATEST = "Batalkan impor yang lebih baru lebih dulu."`, `MSG_ROLLBACK_CONFLICT = "Data berubah sejak impor diterapkan, sehingga impor tidak dapat dibatalkan."`.
  - `rollback`: periksa syarat → `claim_applied` (gagal → 409) → `build_plan` → bila ada konflik `await self.db.rollback()` lalu 409 → `execute_plan` → set `rolled_back_at` → `record_audit(action=AUDIT_IMPORT_ROLLED_BACK, entity=AUDIT_ENTITY_IMPORT, detail={students_deleted, invoices_deleted, students_reverted, invoices_reverted, queued_messages_cancelled})` → commit.

- [ ] **Step 1: Tulis tes gagal** di `tests/test_imports_rollback_api.py` (`admin_headers` untuk rollback; impor dengan `staf_headers`):
  - akses: `POST/GET rollback-preview` tanpa token → 401; dengan `staf_headers` dan `pimpinan_headers` → 403; `test_permissions_seed.py::test_staf_keuangan_has_everything_except_users_roles_audit` diperbarui agar mengharapkan semua kode kecuali `users:`, `roles:`, `audit:`, **dan** `imports:rollback`; tambah `test_admin_has_rollback_permission`.
  - `test_rollback_latest_batch_restores_data_and_audits`: respons `status == "rolled_back"`, `rolled_back_at` terisi, tabel kembali ke snapshot, tepat satu `AuditEvent` `import.rolled_back` dengan detail hitungan.
  - `test_only_latest_applied_batch_can_be_rolled_back`: batch A lalu B → rollback A → 409 `MSG_ROLLBACK_NOT_LATEST`; daftar impor memberi A `rollback_block == "not_latest"` dan B `None`; setelah B di-rollback, A menjadi eligible.
  - `test_legacy_batch_without_change_log_is_rejected`: set `has_change_log = False` langsung di DB → 409 `MSG_ROLLBACK_NO_LOG`, `rollback_block == "no_change_log"`.
  - `test_non_applied_batches_are_rejected`: `preview`, `discarded`, `rolled_back` → 409 `MSG_ROLLBACK_NOT_APPLIED`; id tidak ada → 404.
  - `test_conflict_rejects_whole_rollback_and_changes_nothing`: ubah status satu tagihan hasil impor lewat API invoice → `POST rollback` 409, `error.details.conflicts[0]` memuat `label` dan `fields` (tanpa nilai), status batch tetap `applied`, data tak berubah; preview untuk kondisi yang sama memberi 200 dengan `conflicts_total == 1`.
  - `test_preview_reports_impact_without_changing_data`: hitungan `invoices_deleted`, `queued_messages_cancelled`, `sent_messages` sesuai.
  - `test_import_with_no_effective_changes_can_be_rolled_back`: impor ulang berkas identik (semua baris tidak berubah) → rollback 200, data tidak berubah.
  - `test_reimport_after_rollback_restores_soft_deleted_rows`: rollback lalu `import_lines` berkas yang sama → 200, tidak ada `IntegrityError`, `invoice_by_code(...).deleted_at is None`.
  - `test_concurrent_rollbacks_one_wins`: `asyncio.gather` dua `POST rollback` → satu 200 dan satu 409 (pola tes konkurensi `apply` di `test_imports_apply.py`).
  - `test_rolled_back_superseded_invoice_does_not_duplicate_messages`: tagihan lama menjadi lunas lewat superseded dengan pesan antre `cancelled(paid)`; setelah rollback tagihan kembali `unpaid`, pesan itu tetap `cancelled`, dan menjalankan planner (pola `tests/test_planner.py`) tidak membuat baris `(invoice_id, rule_id)` ganda.
- [ ] **Step 2: Jalankan, pastikan gagal:** `pytest tests/test_imports_rollback_api.py tests/test_permissions_seed.py -v`.
- [ ] **Step 3: Implementasi** semua yang tercantum di Interfaces. Jangan mengubah respons `apply`/`discard` selain field baru bernilai default.
- [ ] **Step 4: Jalankan gerbang penuh:** `ruff check . && ruff format --check . && pyright && pytest` → semua lulus (tes lain yang memeriksa bentuk `ImportBatchRead` atau jumlah izin disesuaikan seperlunya).
- [ ] **Step 5: Commit** (backend): `feat: add import rollback endpoints with imports:rollback permission`

---

### Task 5: Frontend: tipe, izin, dan service

**Files:**
- Modify: `kampusping-frontend/src/core/auth/permissions.ts`, `src/modules/import/{types.ts,constants.ts}`, `src/modules/import/services/import.service.ts`

**Interfaces:**
- Consumes: kontrak API Task 4.
- Produces:
  - `permissions.importsRollback = 'imports:rollback'`.
  - `ImportStatus` + `'rolled_back'`; `ImportBatch` + `has_change_log: boolean`, `rolled_back_at: string | null`, `rollback_block: 'no_change_log' | 'not_latest' | null`.
  - `RollbackConflict = { entity: 'student' | 'invoice'; label: string; fields: string[] }`; `RollbackPreview = { students_deleted; invoices_deleted; students_reverted; invoices_reverted; queued_messages_cancelled; sent_messages: number; conflicts: RollbackConflict[]; conflicts_total: number }`.
  - `IMPORT_STATUS_LABELS.rolled_back = 'Dikembalikan'` (label "Dibatalkan" sudah dipakai status `discarded`); `IMPORT_ROLLBACK_BLOCK_LABELS: Record<'no_change_log' | 'not_latest', string>` berisi dua pesan Indonesia yang sama dengan `MSG_ROLLBACK_NO_LOG` dan `MSG_ROLLBACK_NOT_LATEST`.
  - `importService.rollbackPreview(id: number): Promise<RollbackPreview>` (`GET /imports/{id}/rollback-preview`), `importService.rollback(id: number): Promise<ImportBatch>` (`POST /imports/{id}/rollback`).

- [ ] **Step 1:** Ubah file-file di atas. `STATUS_COLOR` di `ImportHistory.tsx` mendapat `rolled_back: 'warning'` (periksa bahwa `AppStatusChip` menerima nilai itu; jika tidak, pakai `'default'`).
- [ ] **Step 2: Verifikasi:** `npm run check` → lulus (tipe harus konsisten).
- [ ] **Step 3: Commit** (frontend): `feat: add import rollback types, permission, and service calls`

---

### Task 6: Frontend: dialog rollback dan aksi di Riwayat impor

**Files:**
- Create: `kampusping-frontend/src/modules/import/components/ImportRollbackDialog.tsx`
- Modify: `components/ImportHistory.tsx`, `components/ImportPage.tsx`
- Test: `components/ImportPage.test.tsx`

**Interfaces:**
- Consumes: Task 5.
- Produces: `ImportRollbackDialog({ batch, onClose, onDone }: { batch: ImportBatch | null; onClose: () => void; onDone: (rolledBack: ImportBatch) => void })`; `ImportHistory` mendapat props `canRollback: boolean` dan `onRollback: (batch: ImportBatch) => void`.

- [ ] **Step 1: Tulis tes gagal** di `ImportPage.test.tsx` (tambah `rollbackPreview` dan `rollback` ke mock `importService`; `signIn([...])` dengan/tanpa `imports:rollback`):
  - tanpa izin `imports:rollback`, baris *Diterapkan* tidak punya tombol rollback;
  - dengan izin, baris *Diterapkan* dengan `rollback_block: null` punya tombol `Batalkan impor tagihan.csv`; baris dengan `rollback_block: 'not_latest'` punya tombol nonaktif dan tooltip `Batalkan impor yang lebih baru lebih dulu.`; baris `preview` dan `rolled_back` tidak punya tombol;
  - klik tombol memanggil `rollbackPreview(id)` dan dialog menampilkan hitungan (`2 mahasiswa baru dihapus`, `6 tagihan baru dihapus`, `2 tagihan dikembalikan`, `3 pesan antre dibatalkan`) serta peringatan `Pesan WhatsApp yang sudah terkirim tidak dapat ditarik kembali.`; bila `sent_messages > 0` menyebut jumlahnya;
  - konfirmasi memanggil `rollback(id)`, menampilkan notifikasi sukses, dan memuat ulang riwayat;
  - `conflicts_total > 0`: daftar konflik (label dan nama field) tampil dan tombol konfirmasi nonaktif;
  - error 409 dari `rollback` menampilkan pesan server dan menutup dialog serta memuat ulang riwayat.
- [ ] **Step 2: Jalankan, pastikan gagal:** `npm test -- ImportPage`.
- [ ] **Step 3: Implementasi.** Dialog memakai pola dan tombol `AppDialog*` seperti `AppConfirmDialog` (konten kustom, jadi bukan `AppConfirmDialog` yang hanya menerima `message: string`), tombol konfirmasi berwarna `error` dengan teks `Batalkan impor`. Tombol di kolom Aksi memakai ikon dan gaya tombol aksi grid yang sudah ada (`gridActionButtonSx`; pilih varian untuk aksi hapus yang tersedia), `getActionColumnWidth(1)` tetap; tombol nonaktif dibungkus `<span>` agar tooltip tetap muncul. `ImportPage` mengatur state dialog, mengambil `usePermission(permissions.importsRollback)`, dan memanggil `refreshHistory` setelah selesai. Semua teks Indonesia, komponen `App*` dan token tema sesuai README frontend.
- [ ] **Step 4: Verifikasi:** `npm run check` → lulus.
- [ ] **Step 5: Commit** (frontend): `feat: add import rollback dialog to the import history`

---

### Task 7: E2E, dokumentasi, dan verifikasi akhir

**Files:**
- Modify: `kampusping-frontend/e2e/billing.spec.ts` (atau spec baru bila lebih rapi; ikuti pola `helpers.ts`), `kampusping-backend/docs/database.md`, `kampusping-backend/docs/messaging.md`, `CLAUDE.md` (root), `docs/superpowers/specs/2026-11-10-import-rollback-design.md` (root)

- [ ] **Step 1: E2E** (`WA_PROVIDER=fake`, `E2E_FAKE_PROVIDER=1`, ikuti `e2e/README.md`): `importViaApi` sebagai admin → buka Impor Data → klik `Batalkan impor <file>` → dialog menampilkan hitungan → konfirmasi → baris berstatus `Dikembalikan` dan tagihan hasil impor tidak lagi muncul di Tagihan. Lalu impor kedua batch dan pastikan batch yang lebih lama bertombol nonaktif.
- [ ] **Step 2: Dokumen.** `database.md`: tabel `import_changes`, kolom baru, migrasi 008, dan catatan bahwa impor sebelum 008 tidak dapat di-rollback. `messaging.md`: rollback membatalkan pesan antre tagihan terhapus (`cancel_reason=manual`), pesan terkirim tidak ditarik, dan pasangan `(invoice, rule)` yang sudah `cancelled` tidak direncanakan ulang. `CLAUDE.md`: daftar tabel (tambahkan `import_changes`; perbaiki rentang migrasi menjadi 001-008), status fitur, izin `imports:rollback` hanya `admin`, dan catatan "impor sebelum migrasi 008 tidak dapat di-rollback". Spec bagian 4.5: ganti chip "Dibatalkan" menjadi "Dikembalikan" (label "Dibatalkan" sudah dipakai status `discarded`).
- [ ] **Step 3: Verifikasi akhir** (bukti sebelum klaim selesai): backend `ruff check . && ruff format --check . && pyright && pytest`; frontend `npm run check` dan `npm run test:e2e` (di port yang bebas, lihat e2e README); catat jumlah tes sebenarnya dari keluaran.
- [ ] **Step 4: Commit** per repo: frontend `test: cover import rollback end to end`; backend `docs: document the import change log and rollback`; root `docs: record import rollback in CLAUDE.md and the design spec`.
