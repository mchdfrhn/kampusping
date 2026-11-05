# Ekspor Laporan Penagihan (Excel/PDF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pimpinan dan staf keuangan dapat melihat pratinjau dan mengunduh laporan penagihan (ringkasan, per prodi-angkatan, daftar tunggakan) sebagai `.xlsx` dan `.pdf` (FR-14).

**Architecture:** Modul backend `reports` menghitung satu struktur `ReportData` lewat `ReportService`; JSON pratinjau, `xlsx_builder`, dan `pdf_builder` memakai struktur yang sama. Berkas dibuat saat diminta di `asyncio.to_thread`. Izin `reports:read` / `reports:export` ditegakkan di server; frontend menambah halaman Laporan dan memakai `apiClient.download` yang sudah ada.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, openpyxl 3.1.5 (sudah ada), reportlab (baru, dikunci), pytest; Next.js 16, MUI 9, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-05-kampusping-reports-export-design.md` (baca bersama rencana ini).

## Global Constraints

- Kode, identifier, komentar, nama migrasi, dan pesan commit berbahasa **Inggris**; teks UI dan isi laporan **Indonesia**.
- **Nomor HP tidak pernah** ada di `ReportData`, JSON, berkas, maupun log.
- Tanggal bisnis dalam `settings.app_timezone` (Asia/Jakarta); "hari ini" dari `Clock` yang diinjeksi, bukan jam sistem; timestamp tersimpan UTC (`ensure_utc` dari `app.shared.utils` untuk nilai naif dari SQLite).
- Preset: `weekly` dan `semester`. Jendela mingguan = `[hari ini - 6, hari ini]` inklusif (7 hari).
- Izin: `reports:read` (pratinjau, opsi) dan `reports:export` (unduhan), ditegakkan dengan `require_permissions`.
- Aksi audit `report.exported`, entity `report`; detail tanpa data pribadi.
- Nama berkas: `laporan-penagihan-<mingguan|semester-SLUG>-<YYYYMMDD>.<xlsx|pdf>`.
- Dependensi baru hanya `reportlab` (backend, versi dikunci). **Tidak ada** dependensi frontend baru.
- Conventional Commits, satu perubahan logis per commit, **jangan push**. Folder app adalah repo git sendiri: commit file backend dari `kampusping-backend/`, frontend dari `kampusping-frontend/`, dokumen dari root. Kerja di branch `development` masing-masing.
- Perintah backend dari `kampusping-backend/`: `export DATABASE_ENGINE=sqlite DATABASE_URL="sqlite+aiosqlite:///$TEMP/kp_reports.db"` lalu `.venv/Scripts/python.exe -m pytest|ruff|pyright`. Di mesin ini `.env` lokal berisi `WA_PROVIDER=gateway`, sehingga beberapa tes di `test_whatsapp_providers.py` dan `test_settings_audit.py` gagal **sebelum** perubahan ini; kegagalan lain adalah milikmu.
- Perintah frontend dari `kampusping-frontend/`: `npx vitest run <path>`, `npm run lint`, `npm run typecheck`. `npm run format:check` gagal di Windows karena CRLF; periksa file yang kamu ubah dengan `npx prettier --check --end-of-line auto <file>`.

## Review Focus

Masukan yang tersirat di spec tetapi mudah luput; tiap baris punya tesnya di task pemilik kode:

1. Prodi/angkatan `NULL` atau `""` harus tampil sebagai "(tanpa prodi)" / "(tanpa angkatan)", bukan baris kosong atau error (Task 3).
2. Pergantian hari WIB: `now = 2026-11-02 17:30 UTC` berarti hari ini 2026-11-03, jadi jendela mingguan `2026-10-28..2026-11-03` (Task 3, 4).
3. Nama mahasiswa berawalan `=` harus tetap string di Excel, dan nama berisi `&`, `<`, `>` tidak boleh membuat PDF error (Task 5, 6).
4. Data kosong (nol tagihan) menghasilkan laporan sah, tanpa pembagian dengan nol (Task 3, 5, 6).
5. Semester bergaris miring ("Ganjil 2026/2027") tidak boleh merusak nama berkas atau header `Content-Disposition` (Task 7).

## File Structure

Backend (`kampusping-backend/`):

| Berkas | Tanggung jawab |
| --- | --- |
| `app/core/permissions.py` (ubah) | Konstanta dan definisi izin laporan; peran `pimpinan` mendapat keduanya. |
| `alembic/versions/007_reports_permissions.py` (baru) | Data migrasi sekali jalan untuk peran sistem yang sudah ada. |
| `app/modules/reports/constants.py`, `schema.py` | Enum, label, nama audit; model `ReportData`, `ReportPreview`, `ReportOptions`. |
| `app/modules/reports/service.py` | `ReportService`: seluruh perhitungan. |
| `app/modules/reports/xlsx_builder.py`, `pdf_builder.py` | Fungsi murni `ReportData -> bytes`. |
| `app/modules/reports/router.py` (+ daftar di `app/api/v1/router.py`) | Tiga endpoint, audit, header unduhan. |
| `requirements.txt` (ubah) | `reportlab==<versi terkunci>`. |

Frontend (`kampusping-frontend/src/`): `core/auth/permissions.ts`, `core/config/route.config.ts`, `core/config/menu.config.ts` (ubah); `core/utils/download.util.ts` (baru); `modules/reports/{types.ts,services/reports.service.ts,components/ReportsPage.tsx}` (baru); `app/(app)/reports/page.tsx` (baru).

---

### Task 1: Izin laporan dan peran sistem

**Files:**
- Modify: `kampusping-backend/app/core/permissions.py`
- Modify: `kampusping-backend/tests/test_permissions_seed.py`

**Interfaces:**
- Produces: `REPORTS_READ = "reports:read"`, `REPORTS_EXPORT = "reports:export"` (ada di `PERMISSIONS` dan `ALL_PERMISSION_CODES`); peran `pimpinan` memiliki `{DASHBOARD_READ, REPORTS_READ, REPORTS_EXPORT}`; `staf_keuangan` otomatis memiliki keduanya (turunan `ALL_PERMISSION_CODES`).

- [ ] **Step 1: Ubah tes (gagal dulu).** Di `test_permissions_seed.py` ganti `test_pimpinan_has_only_dashboard_read` menjadi `test_pimpinan_has_dashboard_and_report_permissions` yang mengharapkan `{DASHBOARD_READ, REPORTS_READ, REPORTS_EXPORT}`; tambah `test_staf_keuangan_holds_report_permissions` (kedua kode ada di `_role_codes(STAF_KEUANGAN_ROLE)`) dan `test_admin_holds_report_permissions`.
- [ ] **Step 2: Jalankan** `pytest tests/test_permissions_seed.py -q`. Expected: gagal (`ImportError` untuk `REPORTS_READ`).
- [ ] **Step 3: Implementasi** di `permissions.py`: dua konstanta, dua `PermissionDef` dengan deskripsi persis `"Melihat laporan penagihan"` dan `"Mengunduh laporan penagihan (Excel/PDF)"`, dan `PIMPINAN_ROLE` menjadi `RoleDef("Melihat dasbor dan laporan penagihan", (DASHBOARD_READ, REPORTS_READ, REPORTS_EXPORT))`.
- [ ] **Step 4: Jalankan** `pytest tests/test_permissions_seed.py -q`. Expected: semua lulus. Lalu `ruff check . && ruff format --check . && pyright`.
- [ ] **Step 5: Commit** (di `kampusping-backend/`): `git add app/core/permissions.py tests/test_permissions_seed.py && git commit -m "feat: add the reports:read and reports:export permissions"`.

### Task 2: Migrasi data izin untuk peran yang sudah ada

**Files:**
- Create: `kampusping-backend/alembic/versions/007_reports_permissions.py`
- Test: `kampusping-backend/tests/test_reports_migration.py`

**Interfaces:**
- Produces (di modul migrasi, revision `"007"`, `down_revision = "006"`): `grant_reports_permissions(connection: sa.engine.Connection) -> None` dan `revoke_reports_permissions(connection: sa.engine.Connection) -> None`; `upgrade()`/`downgrade()` memanggilnya dengan `op.get_bind()`.

Aturan: izin dan deskripsi di-hardcode di migrasi (migrasi tidak boleh bergantung pada kode aplikasi yang berubah) dan **sama persis** dengan Task 1. `grant`: buat baris `permissions` yang belum ada; untuk peran bernama `staf_keuangan` dan `pimpinan` **jika ada**, tautkan kedua izin yang belum tertaut. Idempoten; tidak menyentuh peran lain (termasuk `admin`, yang disinkronkan seed). `revoke`: hapus tautan `role_permissions` lalu baris `permissions` untuk dua kode itu.

- [ ] **Step 1: Tes (gagal dulu).** Muat modul lewat `importlib.util.spec_from_file_location` (nama berkas diawali angka). Pakai `sa.create_engine("sqlite://")`, `Base.metadata.create_all(engine)` dan `sqlalchemy.orm.Session` untuk menyiapkan data. Tes: `test_grant_links_existing_system_roles` (peran `staf_keuangan` dan `pimpinan` tanpa izin laporan → keduanya mendapat dua izin; peran `lainnya` tidak), `test_grant_is_idempotent` (dua kali jalan, tidak ada duplikat baris `permissions`/`role_permissions`), `test_grant_keeps_the_other_permissions_of_a_role` (izin yang sudah dimiliki peran tetap ada setelah `grant`), `test_grant_without_roles_only_creates_permissions` (tanpa peran, hanya dua baris izin dibuat), `test_revoke_removes_links_and_permissions`.
- [ ] **Step 2: Jalankan** `pytest tests/test_reports_migration.py -q`. Expected: gagal (berkas migrasi belum ada).
- [ ] **Step 3: Implementasi** `007_reports_permissions.py` mengikuti header `006_messages.py`; gunakan `sa.table()`/`sa.select()` Core atau model `Permission`/`role_permissions` lewat `Connection`, bukan SQL mentah khusus dialek.
- [ ] **Step 4: Jalankan** tes di atas. Expected: lulus. Lalu verifikasi rantai Alembic: `.venv/Scripts/python.exe -m alembic heads` (hanya `007`) dan, pada SQLite sementara di luar repo, `alembic upgrade head` lalu `alembic downgrade -1` berhasil.
- [ ] **Step 5: Commit**: `git add alembic/versions/007_reports_permissions.py tests/test_reports_migration.py && git commit -m "migration: grant the report permissions to the existing system roles"`.

### Task 3: ReportService, bagian tagihan (ringkasan, kelompok, tunggakan)

**Files:**
- Create: `kampusping-backend/app/modules/reports/__init__.py`, `constants.py`, `schema.py`, `service.py`
- Test: `kampusping-backend/tests/test_reports_service.py`

**Interfaces:**
- Produces (`constants.py`): `class ReportPreset(StrEnum): WEEKLY="weekly"; SEMESTER="semester"`; `class ReportFormat(StrEnum): XLSX="xlsx"; PDF="pdf"`; `WEEKLY_WINDOW_DAYS = 7`; `NO_PROGRAM_LABEL = "(tanpa prodi)"`; `NO_COHORT_LABEL = "(tanpa angkatan)"`; `AUDIT_REPORT_EXPORTED = "report.exported"`; `AUDIT_ENTITY_REPORT = "report"`; `REACHED_STATUSES = ("sent", "delivered", "read")` (nilai `MessageStatus`).
- Produces (`schema.py`, semua `BaseModel`): `InvoiceFigures(total, total_amount, paid, paid_amount, unpaid, unpaid_amount, overdue, overdue_amount, exempt, exempt_amount: int; paid_percent_count, paid_percent_amount: float)`; `MessageFigures(queued, sending, sent, delivered, read, failed, cancelled: int)`; `PaymentsInPeriod(count: int, amount: int)`; `ReportSummary(invoices: InvoiceFigures, messages: MessageFigures, paid_after_message: int, payments_in_period: PaymentsInPeriod | None)`; `GroupRow(study_program: str, cohort: str, total, paid, unpaid, overdue, overdue_amount: int, paid_percent: float)`; `ArrearsRow(nim, name, study_program, cohort, semester, invoice_code: str; amount: int; due_date: date; days_overdue, messages_sent: int; last_message_date: date | None; last_message_status: str | None)`; `ReportData(preset, semester: str | None, period_start: date | None, period_end: date | None, generated_at: datetime, generated_by: str, summary, groups: list[GroupRow], arrears: list[ArrearsRow])`; `ReportPreview` (field sama dengan `ReportData` tetapi `arrears_count: int` menggantikan `arrears`); `ReportOptions(semesters: list[str])`.
- Produces (`service.py`): `class ReportService(db: AsyncSession, clock: Clock)` dengan `async build(preset: ReportPreset, semester: str | None, generated_by: str) -> ReportData` dan `async semesters() -> list[str]` (distinct `Invoice.semester` non-kosong, terbaru dulu).
- Pada task ini field pesan ada tetapi nol: `MessageFigures` semua `0`, `paid_after_message = 0`, `messages_sent = 0`, `last_message_* = None`. Task 4 mengisinya.

Aturan hitung (ikuti spec §4): hanya `Invoice` dan `Student` yang `deleted_at IS NULL`; lingkup `semester` membatasi `Invoice.semester == semester`; lewat jatuh tempo = `status == unpaid AND due_date < hari_ini AND exempt_reason IS NULL`; dikecualikan = `status == unpaid AND exempt_reason IS NOT NULL`; persentase dibulatkan 1 desimal, pembagi 0 → `0.0`; `payments_in_period` hanya untuk `weekly` (invoice `paid`, `paid_at` dalam jendela), `None` pada `semester`; `period_start/end` terisi hanya pada `weekly`; kelompok diurutkan `(study_program, cohort)` dengan label pengganti untuk `NULL`/`""`; tunggakan diurutkan `days_overdue` menurun lalu `nim`. `preset == semester` tanpa `semester` → `AppException(..., status_code=422, code=VALIDATION_ERROR)`. Gunakan kueri agregat tetap (jangan N+1) dan jangan memfilter dengan daftar id Python.

- [ ] **Step 1: Tes (gagal dulu)** di `test_reports_service.py`, memanggil `ReportService(db, lambda: NOW).build(...)` langsung dengan `get_session_factory()`; `NOW = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)` (hari ini 2026-11-02). Nama tes dan asersi kunci:
  - `test_summary_counts_and_amounts_per_status` (paid/unpaid/overdue/total, nominal, `paid_percent_count == 33.3` untuk 1 dari 3).
  - `test_overdue_excludes_paid_due_today_exempt_and_deleted` (jatuh tempo hari ini tidak lewat; berkeringanan masuk `exempt`/`exempt_amount` bukan `overdue`; tagihan atau mahasiswa soft-delete tidak dihitung).
  - `test_semester_preset_restricts_to_the_semester_and_has_no_period` (`period_start is None`, `payments_in_period is None`).
  - `test_weekly_window_edges` (`paid_at` 2026-10-27 masuk, 2026-10-26 tidak; 2026-11-02 masuk, 2026-11-03 tidak; `period_start == date(2026,10,27)`).
  - `test_weekly_window_follows_jakarta_midnight` (`now = 2026-11-02 17:30 UTC` → `period_end == date(2026,11,3)`, `period_start == date(2026,10,28)`).
  - `test_groups_use_labels_for_missing_program_and_cohort_and_are_sorted`.
  - `test_arrears_rows_sorted_with_days_overdue_and_labels` (`days_overdue == (hari_ini - due_date).days`).
  - `test_empty_database_yields_zeros_without_division_error` (`paid_percent_* == 0.0`, `groups == []`, `arrears == []`).
  - `test_semester_preset_requires_a_semester` (422) dan `test_unknown_semester_yields_zero_report`.
  - `test_semesters_lists_distinct_non_empty_newest_first`.
- [ ] **Step 2: Jalankan** `pytest tests/test_reports_service.py -q`. Expected: gagal (`ModuleNotFoundError`).
- [ ] **Step 3: Implementasi** `constants.py`, `schema.py`, `service.py` sesuai antarmuka di atas. Struktur `service.py`: satu method privat per bagian (`_invoice_figures`, `_groups`, `_arrears`, `_payments_in_period`) memakai predikat bersama (satu fungsi yang membangun filter lingkup) supaya definisi lewat jatuh tempo tidak terduplikasi.
- [ ] **Step 4: Jalankan** tes. Expected: lulus. `ruff check . && ruff format --check . && pyright`.
- [ ] **Step 5: Commit**: `git add app/modules/reports tests/test_reports_service.py && git commit -m "feat: compute the billing report figures, groups and arrears list"`.

### Task 4: ReportService, bagian pesan

**Files:**
- Modify: `kampusping-backend/app/modules/reports/service.py`
- Test: `kampusping-backend/tests/test_reports_service.py`

**Interfaces:**
- Consumes: `ReportService`, `MessageFigures`, `ArrearsRow`, `REACHED_STATUSES` (Task 3).
- Produces: `summary.messages`, `summary.paid_after_message`, `ArrearsRow.messages_sent/last_message_date/last_message_status` terisi.

Aturan: pesan dihitung hanya bila `Message`, `Invoice`, dan `Student` tidak soft-delete. `weekly`: hitung per status untuk pesan dengan `scheduled_date` dalam jendela; `semester`: seluruh pesan dari tagihan semester itu (pesan dibatasi lewat tagihannya, seperti dasbor). `paid_after_message`: untuk tagihan lunas dalam lingkup (`weekly`: `paid_at` dalam jendela; `semester`: semua lunas semester itu), hitung yang punya minimal satu pesan berstatus `REACHED_STATUSES` dengan **tanggal lokal** `sent_at` `<= paid_at`; ambil `(invoice_id, MIN(sent_at))` lewat satu kueri lalu bandingkan di Python (`ensure_utc` lalu `local_now(..., settings.app_timezone).date()`). Baris tunggakan: `messages_sent` = jumlah pesan `REACHED_STATUSES` pada tagihan itu; `last_message_date/status` dari pesan `REACHED_STATUSES` dengan `sent_at` terbaru (tanggal lokal). Ambil data pesan tunggakan dengan satu kueri yang di-join ke predikat tunggakan yang sama, bukan `IN (daftar id)`.

- [ ] **Step 1: Tes (gagal dulu)** di `test_reports_service.py`: `test_message_counts_weekly_use_scheduled_date_window`, `test_message_counts_semester_follow_the_invoice_semester`, `test_deleted_messages_invoices_and_students_are_not_counted`, `test_paid_after_message_counts_only_messages_on_or_before_payment_day` (pesan `sent` pada hari yang sama dengan `paid_at` dihitung; sehari sesudahnya tidak; status `queued`/`failed`/`sending` tidak dihitung), `test_paid_after_message_weekly_scope_is_paid_in_window`, `test_paid_after_message_uses_jakarta_local_date` (`sent_at = 2026-11-01 18:00 UTC` = 2 November WIB, `paid_at = 2026-11-01` → tidak dihitung), `test_arrears_rows_report_messages_sent_and_last_message` (dua pesan terkirim, satu `failed` diabaikan; `last_message_status` dari yang terbaru).
- [ ] **Step 2: Jalankan** `pytest tests/test_reports_service.py -q`. Expected: tes baru gagal, tes Task 3 tetap lulus.
- [ ] **Step 3: Implementasi** di `service.py`: method privat `_message_figures`, `_paid_after_message`, `_arrears_messages`; ganti nilai nol bawaan Task 3.
- [ ] **Step 4: Jalankan** seluruh `pytest tests/test_reports_service.py -q`. Expected: lulus; `ruff` dan `pyright` bersih.
- [ ] **Step 5: Commit**: `git add app/modules/reports/service.py tests/test_reports_service.py && git commit -m "feat: add message figures and paid-after-message to the billing report"`.

### Task 5: Pembuat Excel

**Files:**
- Create: `kampusping-backend/app/modules/reports/xlsx_builder.py`
- Test: `kampusping-backend/tests/test_reports_xlsx.py`

**Interfaces:**
- Consumes: `ReportData` (Task 3, 4).
- Produces: `build_xlsx(data: ReportData) -> bytes`.

Bentuk berkas (spec §4): sheet `Ringkasan`, `Per Prodi-Angkatan`, `Tunggakan`; header tebal dan beku (`freeze_panes`); filter otomatis pada `Tunggakan`; nominal bertipe angka dengan `number_format` `"Rp"#,##0`; tanggal bertipe `date` dengan `dd-mm-yyyy`; lebar kolom wajar. `Ringkasan` memuat judul, preset/periode (teks Indonesia, mis. "7 hari terakhir (28-10-2026 s/d 03-11-2026)" atau "Semester: <nama>"), waktu dan pembuat laporan (WIB), lalu angka-angkanya sebagai pasangan label/nilai. **Semua sel teks ditulis sebagai string**: setelah mengisi nilai, set `cell.data_type = "s"` untuk teks sehingga `=`, `+`, `-`, `@` di awal tidak menjadi formula.

- [ ] **Step 1: Tes (gagal dulu)**: buat `ReportData` contoh lewat fungsi lokal. Baca balik dengan `openpyxl.load_workbook(io.BytesIO(...))`. `test_sheet_names_and_headers`, `test_arrears_values_and_number_formats` (nominal angka dengan format rupiah, `due_date` bertipe `date`), `test_text_starting_with_equals_stays_a_string` (nama `=1+1` dan `@SUM(A1)` terbaca kembali sebagai string dengan `data_type == "s"`), `test_empty_report_is_valid` (tanpa kelompok dan tunggakan: sheet tetap ada, hanya header), `test_no_phone_column_anywhere` (tidak ada sel berisi "HP"/"WA" pada header dan tidak ada nilai yang cocok dengan nomor contoh).
- [ ] **Step 2: Jalankan** `pytest tests/test_reports_xlsx.py -q`. Expected: gagal (`ModuleNotFoundError`).
- [ ] **Step 3: Implementasi** `build_xlsx` dengan `openpyxl.Workbook`, satu fungsi privat per sheet; simpan ke `BytesIO` dan kembalikan `getvalue()`.
- [ ] **Step 4: Jalankan** tes. Expected: lulus; `ruff`/`pyright` bersih.
- [ ] **Step 5: Commit**: `git add app/modules/reports/xlsx_builder.py tests/test_reports_xlsx.py && git commit -m "feat: build the billing report as an Excel workbook"`.

### Task 6: Pembuat PDF

**Files:**
- Create: `kampusping-backend/app/modules/reports/pdf_builder.py`
- Modify: `kampusping-backend/requirements.txt`
- Test: `kampusping-backend/tests/test_reports_pdf.py`

**Interfaces:**
- Consumes: `ReportData`; `format_rupiah(amount: int) -> str` dari `app.modules.templates.rendering` (periksa keluarannya `Rp1.500.000`).
- Produces: `build_pdf(data: ReportData) -> bytes`; fungsi tabel murni yang dipakai tes dan builder: `summary_table(data) -> list[list[str]]`, `groups_table(data) -> list[list[str]]`, `arrears_table(data) -> list[list[str]]` (baris pertama = header; nominal `Rp1.500.000`, tanggal `dd-mm-yyyy`, persen `85,5%` dengan koma desimal).

Dependensi: tambahkan `reportlab==5.1.0` ke `requirements.txt` (rilis terbaru di PyPI saat rencana ini ditulis) dan `pip install -r requirements.txt`. Bila 5.1.0 gagal terpasang atau diimpor di Python 3.12, turunkan ke rilis stabil sebelumnya (`5.0.1`, lalu `4.5.1`) dan catat alasannya di pesan commit.

Bentuk berkas: A4 landscape (`reportlab.platypus.SimpleDocTemplate`), judul, periode, waktu dan pembuat laporan, tiga bagian (Ringkasan, Per Prodi dan Angkatan, Daftar Tunggakan), baris header tabel berulang (`repeatRows=1`), nomor halaman di footer, dan catatan "Berisi data pribadi mahasiswa; jangan disebarluaskan." Teks yang masuk ke `Paragraph` **harus di-escape** (`xml.sax.saxutils.escape`) karena `Paragraph` mem-parse markup; sel panjang dibungkus (`Paragraph`) agar tidak menabrak kolom.

- [ ] **Step 1: Tes (gagal dulu)**: `test_build_pdf_returns_a_valid_document` (`startswith(b"%PDF")`, mengandung `%%EOF`), `test_pdf_with_many_arrears_spans_several_pages` (300 baris tunggakan → jumlah kecocokan `rb"/Type\s*/Page\b"` ≥ 2), `test_markup_characters_in_names_do_not_break_the_pdf` (nama `Budi & Co <b>Tebal</b>` tidak melempar), `test_empty_report_builds` , `test_arrears_table_formats_and_has_no_phone` (header, `Rp1.500.000`, `dd-mm-yyyy`, tidak ada kolom nomor HP), `test_summary_and_groups_tables_format_percentages_with_comma`.
- [ ] **Step 2: Jalankan** `pytest tests/test_reports_pdf.py -q`. Expected: gagal.
- [ ] **Step 3: Implementasi** `pdf_builder.py`; font bawaan Helvetica.
- [ ] **Step 4: Jalankan** tes. Expected: lulus; `ruff`/`pyright` bersih (jika `pyright` mengeluh tentang tipe `reportlab`, tambahkan `# pyright: ignore[...]` seperlunya dan hanya pada baris yang bermasalah).
- [ ] **Step 5: Commit**: `git add requirements.txt app/modules/reports/pdf_builder.py tests/test_reports_pdf.py && git commit -m "feat: build the billing report as a PDF document"`.

### Task 7: Endpoint, audit, dan unduhan

**Files:**
- Create: `kampusping-backend/app/modules/reports/router.py`
- Modify: `kampusping-backend/app/api/v1/router.py`
- Test: `kampusping-backend/tests/test_reports_api.py`

**Interfaces:**
- Consumes: `ReportService`, `build_xlsx`, `build_pdf`, `ReportPreset`, `ReportFormat`, `ReportPreview`, `ReportOptions`, `record_audit`, `SEMESTER_MAX_LENGTH` dari `app.modules.dashboard.constants`.
- Produces: `GET /api/v1/reports/options` → `ReportOptions`; `GET /api/v1/reports/billing?preset=&semester=` → `ReportPreview`; `GET /api/v1/reports/billing/export?preset=&semester=&format=` → berkas. `preset` default `weekly`; `format` wajib. Fungsi `report_filename(data: ReportData, fmt: ReportFormat, today: date) -> str` di `router.py`.

Aturan: `options` dan `billing` memakai `require_permissions(REPORTS_READ)`; `export` memakai `require_permissions(REPORTS_EXPORT)`. `export`: bangun `ReportData` (`generated_by = user.email`), buat berkas lewat `asyncio.to_thread`, tulis audit `report.exported` dengan detail `{preset, semester, format, arrears_rows}`, `commit`, kembalikan `Response` dengan `Content-Type` (xlsx: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`; pdf: `application/pdf`), `Content-Disposition: attachment; filename="..."`, dan `Cache-Control: no-store`. Slug semester: huruf kecil, selain `[a-z0-9]` menjadi `-`, rentetan `-` dirapatkan dan dipangkas (`"Ganjil 2026/2027"` → `ganjil-2026-2027`). `billing` menghitung `ReportData` lalu memetakan ke `ReportPreview` (`arrears_count = len(arrears)`, tanpa daftar).

- [ ] **Step 1: Tes (gagal dulu)** di `test_reports_api.py` (fixture `client`, `admin_headers`, `staf_headers`, `pimpinan_headers`, `freeze` seperti `test_dashboard.py`): `test_endpoints_require_authentication` (401 untuk ketiganya); `test_pimpinan_and_staf_can_preview_and_export`; `test_export_requires_export_permission` (pengguna dengan peran khusus hanya `reports:read` → 200 untuk `billing`, 403 untuk `export`); `test_preview_has_no_personal_data` (kunci JSON tepat; tanpa NIM, nama, nomor HP, kode tagihan; ada `arrears_count`, tidak ada `arrears`); `test_xlsx_export_headers_and_content` (content-type, `Content-Disposition` `laporan-penagihan-mingguan-20261102.xlsx`, `Cache-Control: no-store`, berkas terbuka dengan `openpyxl` dan memuat NIM serta nama tetapi tidak nomor HP); `test_pdf_export_starts_with_pdf_signature`; `test_semester_filename_slug` (`laporan-penagihan-semester-ganjil-2026-2027-20261102.xlsx`); `test_export_writes_one_audit_event_without_personal_data` (`detail` hanya `preset`, `semester`, `format`, `arrears_rows`); `test_validation_errors` (422: `preset=semester` tanpa `semester`; `format=csv`; `format` hilang; `semester` lebih dari batas panjang); `test_options_lists_semesters`.
- [ ] **Step 2: Jalankan** `pytest tests/test_reports_api.py -q`. Expected: gagal (404).
- [ ] **Step 3: Implementasi** `router.py` (`APIRouter(prefix="/reports", tags=["Reports"])`) dan daftarkan di `app/api/v1/router.py` setelah `dashboard_router`.
- [ ] **Step 4: Jalankan** `pytest tests/test_reports_api.py tests/test_reports_service.py tests/test_reports_xlsx.py tests/test_reports_pdf.py tests/test_reports_migration.py tests/test_permissions_seed.py -q`. Expected: lulus. Lalu `ruff check . && ruff format --check . && pyright` dan seluruh `pytest -q` (kegagalan yang sudah ada karena `.env` lokal boleh tetap; yang lain tidak).
- [ ] **Step 5: Commit**: `git add app/modules/reports/router.py app/api/v1/router.py tests/test_reports_api.py && git commit -m "feat: expose the billing report preview and Excel/PDF export endpoints"`.

### Task 8: Fondasi frontend (izin, rute, menu, util unduh, servis)

**Files:**
- Modify: `kampusping-frontend/src/core/auth/permissions.ts`, `core/config/route.config.ts`, `core/config/menu.config.ts`
- Create: `kampusping-frontend/src/core/utils/download.util.ts`, `download.util.test.ts`
- Create: `kampusping-frontend/src/modules/reports/types.ts`, `services/reports.service.ts`

**Interfaces:**
- Produces: `permissions.reportsRead = 'reports:read'`, `permissions.reportsExport = 'reports:export'`; `routes.reports = '/reports'`; menu item `Laporan` (ikon `AssessmentOutlined`, izin `reportsRead`) **tepat setelah `Dasbor`**; `saveBlob(blob: Blob, filename: string): void` (`URL.createObjectURL`, anchor sementara diklik, lalu `URL.revokeObjectURL`).
- Produces (`types.ts`): `ReportPreset = 'weekly' | 'semester'`, `ReportFormat = 'xlsx' | 'pdf'`, dan tipe `ReportPreview` dengan bentuk JSON `ReportPreview` Task 3 (`summary`, `groups`, `arrears_count`, `period_start/end`, `generated_at`, `generated_by`, `preset`, `semester`), `ReportOptions { semesters: string[] }`.
- Produces (`reports.service.ts`): `reportsService.options(signal?)`, `reportsService.preview(preset, semester?, signal?)`, `reportsService.download(preset, semester, format): Promise<{ blob: Blob; filename: string | null }>` (memakai `apiClient.download` dan `toQueryString`).

- [ ] **Step 1: Tes (gagal dulu)**: `download.util.test.ts` (`saveBlob` membuat object URL, mengklik anchor dengan atribut `download` sesuai nama, lalu me-revoke URL). Tambah ke `src/core/utils/navigation.util.test.ts` (satu-satunya tes menu/navigasi; baca dulu isinya dan perbarui asersi lama yang bergantung pada urutan atau jumlah item) asersi: pengguna dengan `dashboard:read` + `reports:read` melihat `Laporan` tepat setelah `Dasbor`; `firstAccessibleRoute` pengguna `pimpinan` (`dashboard:read`, `reports:read`, `reports:export`) tetap `/dashboard`.
- [ ] **Step 2: Jalankan** `npx vitest run src/core`. Expected: gagal.
- [ ] **Step 3: Implementasi** semua berkas di atas; salin pola `dashboard.service.ts`.
- [ ] **Step 4: Jalankan** `npx vitest run src/core src/components` lalu `npm run lint && npm run typecheck`. Expected: lulus (tes sidebar/menu yang menghitung jumlah item harus diperbarui bila ada).
- [ ] **Step 5: Commit** (di `kampusping-frontend/`): `git add src/core src/modules/reports && git commit -m "feat: add the reports permissions, menu entry, download helper and service"`.

### Task 9: Halaman Laporan

**Files:**
- Create: `kampusping-frontend/src/modules/reports/components/ReportsPage.tsx`, `ReportsPage.test.tsx`
- Create: `kampusping-frontend/src/app/(app)/reports/page.tsx`

**Interfaces:**
- Consumes: `reportsService`, `saveBlob`, `permissions.reportsRead/reportsExport`, `usePermission`, `useNotify`, `PageHeader`, `RequirePermission`, `StatCard` dari `@/modules/dashboard/components/StatCard`, `formatRupiah`/`formatNumber`.
- Produces: `ReportsPage` (tanpa props); route `/reports` dibungkus `RequirePermission permission={permissions.reportsRead}` dan `metadata.title = 'Laporan'`.

Perilaku: judul "Laporan Penagihan"; `ToggleButtonGroup` preset "7 hari terakhir" (bawaan) dan "Per semester"; pada "Per semester" tampil dropdown `Semester` dari `reportsService.options()` dan pratinjau baru dimuat setelah semester dipilih (sebelumnya pesan "Pilih semester untuk melihat laporan."); pratinjau menampilkan `StatCard` (Total tagihan, Lunas, Belum lunas, Lewat jatuh tempo `tone="error"`, Dikecualikan, Lunas setelah pesan, dan "Pembayaran 7 hari" hanya bila `payments_in_period` ada), tabel per prodi dan angkatan (MUI `Table`), dan teks "N mahasiswa menunggak; rincian nama ada di berkas unduhan."; tombol **Unduh Excel** dan **Unduh PDF** hanya bila punya `reports:export`, dinonaktifkan selama mengunduh, memanggil `reportsService.download` lalu `saveBlob(blob, filename ?? <nama bawaan>)`; kegagalan lewat `notify.error(getErrorMessage(...))`; gagal memuat pratinjau menampilkan `Alert` dengan tombol "Coba lagi". Hanya teks Indonesia; tanpa library baru.

- [ ] **Step 1: Tes (gagal dulu)** di `ReportsPage.test.tsx` (mock `../services/reports.service`, `useAuthStore.setState` untuk izin, `userEvent`): `test_loads_the_weekly_preview_by_default` (`preview('weekly', undefined)` dipanggil, kartu dan tabel tampil, "3 mahasiswa menunggak"), `test_semester_preset_waits_for_a_semester` (preview belum dipanggil; setelah memilih semester dipanggil dengan semester itu), `test_download_buttons_call_the_service_and_save_the_file` (kedua format; `saveBlob` dimock dan menerima nama berkas dari server), `test_export_buttons_hidden_without_export_permission` (hanya `reports:read`), `test_shows_an_error_with_retry_when_the_preview_fails`, `test_download_error_is_reported_and_button_is_enabled_again`. Tambah `app/(app)/reports/page.test.tsx` mengikuti `students/page.test.tsx` (tanpa `reports:read` → "tidak memiliki akses").
- [ ] **Step 2: Jalankan** `npx vitest run src/modules/reports "src/app/(app)/reports"`. Expected: gagal.
- [ ] **Step 3: Implementasi** `ReportsPage.tsx` dan `page.tsx` mengikuti `dashboard/page.tsx` dan pola `DashboardPage`.
- [ ] **Step 4: Jalankan** tes di atas, lalu `npm test`, `npm run lint`, `npm run typecheck`, dan `npx prettier --check --end-of-line auto` pada berkas yang diubah. Expected: seluruh suite lulus.
- [ ] **Step 5: Commit**: `git add src/modules/reports src/app && git commit -m "feat: add the Laporan page with preview and Excel/PDF download"`.

### Task 10: Dokumentasi dan verifikasi akhir

**Files:**
- Modify: `CLAUDE.md` (root), `docs/superpowers/specs/2026-11-05-kampusping-reports-export-design.md`

- [ ] **Step 1: Perbarui `CLAUDE.md`**: di Status, catat laporan Excel/PDF (FR-14) selesai dan bahwa kirim manual/massal (FR-12) juga sudah ada; di "Libraries added for this project" ganti catatan "`reportlab` ... not added yet" menjadi sudah ditambahkan (sebutkan versi terkunci); hapus "no manual/bulk send" dan "no Excel/PDF export" dari daftar yang belum ada; di "Known limitations" catat bahwa `staf_keuangan` mendapat izin laporan lewat migrasi `007` (bukan seed) dan dasbor masih menghitung tagihan berkeringanan sebagai lewat jatuh tempo sedangkan laporan tidak. Ubah baris "Status:" pada spec menjadi "Diimplementasi (lihat rencana)".
- [ ] **Step 2: Verifikasi penuh** (bukti sebelum klaim selesai): backend `ruff check . && ruff format --check . && pyright` dan `pytest -q` (bandingkan dengan kegagalan dasar karena `.env`); frontend `npm run lint`, `npm run typecheck`, `npm test`.
- [ ] **Step 3: Uji manual singkat** di lokal dengan `WA_PROVIDER=fake`: jalankan backend dan frontend (port bukan 3000/8000 bila terpakai), login, buka **Laporan**, unduh Excel dan PDF, buka keduanya, dan pastikan tidak ada nomor HP. Catat hasilnya; jika tidak bisa dijalankan, katakan itu apa adanya.
- [ ] **Step 4: Commit** (root): `git add CLAUDE.md docs && git commit -m "docs: record the report export in CLAUDE.md and mark its spec implemented"`.

---

## Self-Review

- **Cakupan spec:** §4 isi laporan (Task 3, 4, 5, 6), §5 backend dan endpoint (Task 3, 7), §6 izin dan migrasi (Task 1, 2), §7 audit dan keamanan (Task 5 string, Task 7 audit/no-store, tanpa HP di Task 3-7), §8 frontend (Task 8, 9), §9 pengujian (tiap task), §10 risiko (PDF ribuan baris di Task 6; selisih dasbor dicatat di Task 10).
- **Konsistensi tipe:** `ReportData`/`ReportPreview`/`ArrearsRow`/`GroupRow` didefinisikan sekali di Task 3 dan dipakai apa adanya di Task 4-7 dan tipe frontend Task 8; `report_filename`, `build_xlsx`, `build_pdf` hanya didefinisikan di task pemiliknya.
- **Proporsi:** rencana memuat tanda tangan, nama tes, dan nilai spesifik; badan fungsi dan tes diserahkan ke implementer.
