# Deteksi lunas dan tagihan baru pada impor Rekap Tunggakan: rencana implementasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preview impor Rekap Tunggakan menampilkan tagihan baru, nominal berubah dan diduga lunas; hanya yang dipilih staf yang ditandai lunas saat Terapkan.

**Architecture:** Parser menandai batch `kind="rekap"`. `build_preview` mengklasifikasi baris lewat satu fungsi pembanding (`diff.py`) yang juga dipakai `apply_rows`, mencari kandidat diduga lunas (`absent.py`), dan menyimpan rincian di kolom JSON `import_batches.details`. Endpoint `details` melayani frontend; `apply` menerima `mark_paid_invoice_ids`.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, pytest (backend); Next.js 16, MUI 9, Vitest (frontend).

**Spec:** [`docs/superpowers/specs/2026-11-16-import-rekap-diff-design.md`](../specs/2026-11-16-import-rekap-diff-design.md)

## Repositori dan cabang

Backend dan frontend adalah repo git sendiri. Buat cabang `feat/import-rekap-diff` di `kampusping-backend` (dari `master`) dan di `kampusping-frontend` (dari `master`; HEAD frontend sekarang ada di `style/format-import-history`, jangan ikut). Repo root sudah di cabang `feat/import-rekap-diff` (spec ada di sana). Jangan push, merge, atau deploy.

Perintah backend dijalankan di `kampusping-backend/` dengan:
`export DATABASE_ENGINE=sqlite DATABASE_URL=sqlite+aiosqlite:////tmp/kp-test.db` lalu `.venv/bin/python -m pytest ...` (atau `python -m` bila launcher gagal). Jangan pernah menjalankan terhadap database `.env`.

## Global Constraints

- `ImportKind` hanya `standard` dan `rekap`; aturan baru berlaku untuk `rekap` kecuali pembanding `invoices_updated`/`invoices_unchanged` (semua format).
- Kandidat diduga lunas: `deleted_at IS NULL`, `status = unpaid`, `invoice_code` berawalan `TGK-`, `semester` sama persis dengan semester di baris valid file, kode tidak ada di file.
- `INCOMPLETE_EXPORT_THRESHOLD = 0.30`; peringatan bila kandidat / kolam **lebih dari** ambang (bukan sama dengan).
- Lunas sticky (AB-01) tidak melemah; tagihan ditandai lunas: `paid_at` = hari ini `APP_TIMEZONE`, `paid_via` = `source` batch, pesan antre dibatalkan `CancelReason.PAID`.
- Tanpa nomor telepon di `details`. Izin: `imports:read` untuk `details`, `imports:create` untuk apply. Tidak ada permission baru.
- Migrasi `011` (revisi terakhir saat ini `010`). Tidak ada dependensi baru.
- UI dan pesan bahasa Indonesia; kode, field API, komentar, commit dalam bahasa Inggris (Conventional Commits). Waktu disuntikkan lewat `Clock`.
- Jangan menyimpan atau meng-commit berkas SIAKAD nyata (NIM dan nama = data pribadi); semua fixture sintetis.
- Kontrak API: tubuh sukses polos, daftar `{items, total, page, page_size}`, `MAX_PAGE_SIZE = 100`.

## Review Focus

1. File rekap tanpa baris valid atau semester kosong: tidak boleh menghasilkan kandidat (jangan "semua hilang = lunas"). Tes di Task 5.
2. Batas peringatan: tepat 30% tidak memperingatkan; kolam kosong tidak membagi nol. Tes di Task 5.
3. `mark_paid_invoice_ids` berisi duplikat, id bukan kandidat, atau tagihan yang sudah lunas/dihapus sejak preview: diabaikan tanpa error. Tes di Task 6.
4. Batch preview yang dibuat sebelum migrasi (`details` NULL): endpoint `details` mengembalikan halaman kosong, apply dengan id tidak menandai apa pun. Tes di Task 5 dan 6.
5. Dua preview berurutan yang memuat kandidat yang sama: apply kedua tidak menghitung ulang yang sudah lunas. Tes di Task 6.

---

### Task 1: Parser menandai `kind` dan memakai tanggal lokal

**Files:**
- Modify: `kampusping-backend/app/modules/imports/constants.py`, `app/modules/imports/parser.py`, `app/modules/imports/service.py` (panggilan `parse_upload`)
- Test: `kampusping-backend/tests/test_import_parsing.py`, `tests/imports_helpers.py` (helper rekap)

**Interfaces:**
- Produces in `constants.py`: `class ImportKind(StrEnum): STANDARD = "standard"; REKAP = "rekap"`; `REKAP_CODE_PREFIX = "TGK-"`; `INCOMPLETE_EXPORT_THRESHOLD = 0.30`.
- Produces: `ParsedSheet.kind: ImportKind = ImportKind.STANDARD` (field terakhir, default). `parse_upload(filename: str, content: bytes, *, today: date) -> ParsedSheet`; `_try_parse_siakad_rekap(records, today: date)` memakai `today` sebagai jatuh tempo (ganti `date.today()`) dan mengembalikan `kind=ImportKind.REKAP`.
- Produces in `tests/imports_helpers.py`: `rekap_xlsx(*items: tuple[str, str, int]) -> bytes` (item = `(nim, "2026/2027 Ganjil", amount)`; membuat lembar dengan 4 baris judul/kosong, header `No, PRODI, Jenis Kelas, NIM, Nama, No Hp, Tahun Akademik, Komponen Biaya, Rincian, Rekap`, NIM diberi spasi di belakang seperti SIAKAD, nama `NAMA {nim}`, telepon `081234567890`); `preview_rekap(client, headers, *items) -> dict` (upload `filename="rekap.xlsx", semester=None`, assert 201); `import_rekap(client, headers, *items) -> dict` (preview lalu apply); `apply(client, headers, batch_id, mark_paid_invoice_ids: list[int] | None = None)` (kirim JSON `{"mark_paid_invoice_ids": [...]}` bila tidak `None`).

- [ ] **Step 1: Tulis tes gagal** di `tests/test_import_parsing.py`:
  `test_rekap_sheet_is_marked_rekap_and_uses_given_today`: `parse_upload("rekap.xlsx", rekap_xlsx(("1001", "2026/2027 Ganjil", 100)), today=date(2026, 11, 16))` → `sheet.kind == ImportKind.REKAP`, `sheet.rows[0][5] == "TGK-1001-20261"`, `sheet.rows[0][8] == "2026-11-16"`, `sheet.rows[0][9] == "belum lunas"`.
  `test_standard_sheet_is_marked_standard`: CSV biasa → `sheet.kind == ImportKind.STANDARD`.
  Perbarui semua pemanggil `parse_upload(...)` di tes agar memberi `today=date(2026, 11, 16)`.
- [ ] **Step 2: Jalankan** `pytest tests/test_import_parsing.py -q`. Expected: FAIL (`kind`/`today` belum ada).
- [ ] **Step 3: Implementasi** sesuai Interfaces. Di `ImportService.preview` hitung `today = local_today(self.clock(), settings.app_timezone)` dan teruskan ke `parse_upload`; `local_today` sudah diimpor di service.
- [ ] **Step 4: Jalankan** `pytest tests/test_import_parsing.py tests/test_imports_preview.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(imports): mark rekap sheets and use the local date for new due dates`.

### Task 2: Migrasi 011 dan kolom `kind`, `details`

**Files:**
- Create: `kampusping-backend/alembic/versions/011_import_batch_kind_and_details.py`
- Modify: `app/modules/imports/model.py`, `app/modules/imports/schema.py`, `app/modules/imports/repository.py`, `app/modules/imports/service.py` (isi `kind` saat membuat batch)
- Test: `kampusping-backend/tests/test_imports_preview.py`, `tests/test_import_batch_migration.py` (baru, mengikuti pola `tests/test_reports_migration.py`)

**Interfaces:**
- Produces: `ImportBatch.kind: Mapped[str]` (`String(10)`, `nullable=False`, `default="standard"`, `server_default="standard"`); `ImportBatch.details: Mapped[dict[str, list[dict[str, Any]]] | None]` (`JSON(none_as_null=True)`, `deferred=True`). `ImportBatchRead.kind: str`. `ImportBatchRepository.get_with_details(batch_id: int) -> ImportBatch | None` (seperti `get_with_rows`, `undefer(ImportBatch.details)` + `populate_existing`).
- Migrasi `011`: `down_revision = "010"`, `batch_alter_table` menambah dua kolom; `downgrade` menghapusnya.

- [ ] **Step 1: Tulis tes gagal**: `test_preview_response_has_kind` (unggah CSV standar → `body["kind"] == "standard"`; unggah `rekap_xlsx` → `"rekap"`; `ImportService.preview` mengisi `kind=sheet.kind.value`). `test_migration_011_adds_columns_and_downgrades` memuat modul migrasi dengan `importlib` seperti tes 007, membuat tabel `import_batches` lama di SQLite memori (tanpa dua kolom) lewat `sa.create_engine("sqlite://")`, menjalankan `upgrade()` dengan `alembic.operations.Operations` dan `MigrationContext`, lalu mengecek kolom `kind` (default `standard` pada baris lama) dan `details` ada, `downgrade()` menghapusnya.
- [ ] **Step 2: Jalankan** kedua tes. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai Interfaces; `alembic check` harus bersih terhadap SQLite sementara.
- [ ] **Step 4: Jalankan** `pytest tests/test_imports_preview.py tests/test_import_batch_migration.py -q` dan `alembic upgrade head && alembic check` (SQLite sementara). Expected: PASS.
- [ ] **Step 5: Commit** `feat(imports): add kind and details columns to import batches`.

### Task 3: Pembanding tagihan tunggal (`diff.py`) dan angka preview/apply yang jujur

**Files:**
- Create: `kampusping-backend/app/modules/imports/diff.py`
- Modify: `app/modules/imports/preview.py` (`_predict`), `app/modules/imports/apply.py` (hitungan), `app/modules/imports/constants.py` (`SUMMARY_KEYS`)
- Test: `tests/test_imports_diff.py` (baru), `tests/test_imports_preview.py`, `tests/test_imports_apply.py`, `tests/imports_helpers.py` (`SUMMARY_KEYS` tes)

**Interfaces:**
- Produces in `diff.py`:
  - `InvoiceFieldChanges = dict[str, tuple[object, object]]`
  - `invoice_changes(invoice: Invoice, row: ValidRow, *, kind: ImportKind, source: str) -> InvoiceFieldChanges`: membandingkan `amount`, `due_date` (dilewati bila `kind == REKAP`), `semester`, `source` (dengan argumen `source` batch), status menjadi `paid` (`"status": ("unpaid", "paid")` bila baris lunas dan tagihan belum), dan `"restored": (True, False)` bila `invoice.deleted_at is not None`.
  - `class RowClass(StrEnum): NEW, CHANGED, UNCHANGED, SKIPPED`
  - `@dataclass(frozen=True) class ChangedRow: row: ValidRow; invoice: Invoice; fields: InvoiceFieldChanges`
  - `@dataclass(frozen=True) class Classification: new: list[ValidRow]; changed: list[ChangedRow]; unchanged: list[ValidRow]; skipped: list[ValidRow]`
  - `classify_rows(rows: Sequence[ValidRow], invoices: dict[str, Invoice], *, kind: ImportKind, source: str) -> Classification`. Urutan prioritas per baris: tagihan tidak ada → `new`; tagihan aktif dan `is_sticky_skip` → `skipped`; ada perubahan → `changed`; selain itu `unchanged`.
- `SUMMARY_KEYS` ditambah `"invoices_unchanged"`. `_predict` memakai `classify_rows`: `invoices_updated = len(changed) + superseded_count`, `invoices_unchanged = len(unchanged)`. `apply_rows` menambah `"invoices_unchanged": 0` ke hitungan; di loop tagihan yang ada: `skipped` → `invoices_skipped`, `changed` (variabel yang sudah ada, termasuk status lunas) → `invoices_updated`, selain itu `invoices_unchanged`.

- [ ] **Step 1: Tulis tes gagal** `tests/test_imports_diff.py` (tanpa database, objek `Invoice`/`ValidRow` dibuat langsung): `test_new_row`, `test_amount_change_is_changed_with_old_and_new` (`fields == {"amount": (100, 200)}`), `test_identical_row_is_unchanged`, `test_paid_invoice_with_unpaid_row_is_skipped`, `test_deleted_paid_invoice_with_unpaid_row_is_changed_not_skipped` (`"restored" in fields`), `test_rekap_ignores_due_date_difference`, `test_standard_notices_due_date_difference`, `test_unpaid_invoice_with_paid_row_reports_status`. Di `test_imports_preview.py`/`test_imports_apply.py`: impor ulang file identik → `invoices_updated == 0`, `invoices_unchanged == n`; satu tes konsistensi `test_preview_and_apply_report_the_same_counts` untuk campuran baru/berubah/tidak berubah/dilewati (kunci `invoices_new`, `invoices_updated`, `invoices_unchanged`, `invoices_skipped` sama). Perbarui asersi ringkasan lama dan `SUMMARY_KEYS` di `imports_helpers.py`.
- [ ] **Step 2: Jalankan** `pytest tests/test_imports_diff.py -q`. Expected: FAIL (modul belum ada).
- [ ] **Step 3: Implementasi** `diff.py` dan perbaikan `_predict`/`apply_rows`. `apply_rows` mendapat parameter kw-only `kind: ImportKind = ImportKind.STANDARD` yang diteruskan ke `invoice_changes`/`classify_rows`; `ImportService.apply` mengisinya di Task 4.
- [ ] **Step 4: Jalankan** `pytest tests/test_imports_diff.py tests/test_imports_preview.py tests/test_imports_apply.py tests/test_imports_rollback_core.py tests/test_imports_rollback_api.py -q`. Expected: PASS (setelah asersi lama diperbarui).
- [ ] **Step 5: Commit** `feat(imports): count only invoices that really change as updated`.

### Task 4: Aturan rekap: tanpa supersede, jatuh tempo stabil

**Files:**
- Modify: `kampusping-backend/app/modules/imports/preview.py`, `app/modules/imports/apply.py`, `app/modules/imports/service.py`
- Test: `tests/test_imports_rekap_rules.py` (baru)

**Interfaces:**
- Consumes: `ParsedSheet.kind`, `ImportBatch.kind`, `ImportKind` (Task 1-2); `classify_rows`.
- Produces: `build_preview(db, sheet, columns, *, source, semester) -> PreviewResult` memakai `sheet.kind`; `PreviewResult.kind: ImportKind`. `apply_rows(..., kind: ImportKind = ImportKind.STANDARD, ...)`: bila `kind == REKAP`, `students_with_new_invoice` kosong (tidak ada supersede) dan `_set(invoice, "due_date", ...)` dilewati untuk tagihan yang sudah ada (tagihan baru dan tagihan yang di-restore tetap mengisi `due_date`). `ImportService.apply` meneruskan `kind=ImportKind(batch.kind)`.

- [ ] **Step 1: Tulis tes gagal** `tests/test_imports_rekap_rules.py` (memakai `import_rekap`, `invoice_by_code`; jam dibekukan dengan `freeze_clock`): 
  `test_rekap_new_invoice_does_not_pay_off_older_arrears`: impor `("1001","2025/2026 Genap",900)` lalu `("1001","2026/2027 Ganjil",100)` → `TGK-1001-20252` tetap `unpaid`, `invoices_updated == 0` pada impor kedua.
  `test_standard_import_still_supersedes_older_unpaid_invoices`: perilaku lama format CSV tetap (regresi).
  `test_rekap_reimport_keeps_existing_due_date`: impor pada 2026-11-16, jam digeser ke 2026-11-20, impor ulang → `due_date == date(2026, 11, 16)`; tagihan baru di impor kedua mendapat `date(2026, 11, 20)`.
  `test_rekap_due_date_uses_jakarta_date`: jam `2026-11-16T18:00Z` → `due_date == date(2026, 11, 17)`.
- [ ] **Step 2: Jalankan** tes baru. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai Interfaces; `build_preview` juga mematikan `superseded` untuk rekap sehingga `invoices_updated` preview sama dengan apply.
- [ ] **Step 4: Jalankan** `pytest tests/test_imports_rekap_rules.py tests/test_imports_preview.py tests/test_imports_apply.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(imports): stop rekap imports from paying off older arrears and shifting due dates`.

### Task 5: Kandidat diduga lunas, rincian preview, endpoint `details`

**Files:**
- Create: `kampusping-backend/app/modules/imports/absent.py`, `app/modules/imports/details.py`
- Modify: `app/modules/imports/preview.py`, `app/modules/imports/service.py`, `app/modules/imports/router.py`, `app/modules/imports/schema.py`, `app/modules/imports/constants.py` (`SUMMARY_KEYS` + `paid_suspected`, `incomplete_warning`; pesan 409 yang sudah ada dipakai ulang)
- Test: `tests/test_imports_suspected_paid.py` (baru), `tests/test_imports_details_api.py` (baru)

**Interfaces:**
- Produces in `absent.py`:
  - `@dataclass(frozen=True) class SuspectedPaid: invoice_id: int; invoice_code: str; nim: str; name: str; study_program: str | None; semester: str; amount: int`
  - `@dataclass(frozen=True) class SuspectedPaidResult: items: list[SuspectedPaid]; pool_size: int` dengan property `incomplete -> bool` = `pool_size > 0 and len(items) / pool_size > INCOMPLETE_EXPORT_THRESHOLD`
  - `async def find_suspected_paid(db: AsyncSession, rows: Sequence[ValidRow]) -> SuspectedPaidResult`: semester = himpunan `row.semester` dari `rows`; `rows` kosong → hasil kosong (`pool_size=0`). Kolam = tagihan aktif, `unpaid`, kode berawalan `REKAP_CODE_PREFIX`, semester dalam himpunan (join `Student` untuk `nim`, `name`, `study_program`). `items` = kolam yang kodenya tidak ada di `rows`. Urut `nim`, `invoice_code`.
- Produces in `details.py`: `class DetailCategory(StrEnum): NEW = "new"; CHANGED = "changed"; SUSPECTED_PAID = "suspected_paid"`; `build_details(classification: Classification, students: dict[str, Student], suspected: SuspectedPaidResult | None) -> dict[str, list[dict[str, Any]]]` dengan kunci `DetailCategory.value`; bentuk item sesuai tabel spec bagian 4.3 (`new`: `invoice_code, nim, name, semester, amount`; `changed`: `invoice_id, invoice_code, nim, name, semester, fields` dengan `fields` = `{field: [lama, baru]}` berisi nilai JSON-aman; `suspected_paid`: field `SuspectedPaid`). `name` memakai `row.name` atau nama mahasiswa tersimpan.
- `PreviewResult` ditambah `details: dict[str, list[dict[str, Any]]]`; `summary` ditambah `paid_suspected` (jumlah item, 0 bila bukan rekap) dan `incomplete_warning` (0/1). `ImportService.preview` menyimpan `kind` dan `details` pada batch; `apply` dan `discard` mengosongkan `details` (`batch.details = None`; untuk discard tambahkan `"details": None` pada nilai claim).
- Endpoints (`imports:read`, hanya batch `preview`, selain itu 409 `_not_in_preview()`):
  - `GET /imports/{id}/details?category=new|changed|suspected_paid&page=&page_size=` → `Page[dict]` (kategori tak dikenal 422). Skema `ImportDetailItem = dict[str, Any]`.
  - `GET /imports/{id}/details/ids?category=suspected_paid` → `{"ids": list[int]}` (id `invoice_id`; kategori selain `suspected_paid` 422). Dipakai frontend untuk "Pilih semua" lintas halaman.
  - `ImportService.list_details(batch_id, category, page, page_size) -> tuple[list[dict], int]` dan `list_detail_ids(batch_id) -> list[int]`; `details is None` diperlakukan sebagai daftar kosong.

- [ ] **Step 1: Tulis tes gagal** `tests/test_imports_suspected_paid.py` (rekap; `make_student`/`make_invoice` dari `tests/test_students_invoices.py` untuk menanam data): 
  `test_absent_invoice_of_a_semester_in_the_file_is_suspected`;
  `test_semester_not_in_the_file_is_never_suspected`;
  `test_non_tgk_paid_and_deleted_invoices_are_not_suspected`;
  `test_file_without_valid_rows_yields_no_suspects` (Review Focus 1: file dengan semua baris tidak valid, `summary["paid_suspected"] == 0`);
  `test_incomplete_warning_boundary` (kolam 10, 3 hilang → `incomplete_warning == 0`; 4 hilang → `1`; kolam kosong → `0` tanpa error; Review Focus 2);
  `test_realistic_rekap_update_counts`: tanam 226 tagihan `TGK-…-20261` (150 tetap, 53 dengan nominal beda di file baru, 23 hilang) + 2 tunggakan `…-20252`, impor file baru dengan 4 NIM tambahan → ringkasan `invoices_new == 4`, `invoices_updated == 53`, `invoices_unchanged == 150`, `paid_suspected == 23` (tunggakan `…-20252` tidak ikut).
  `tests/test_imports_details_api.py`: halaman tiap kategori, `total`, isi `fields["amount"] == [lama, baru]`, tidak ada field `phone`; 401 tanpa token, 403 tanpa `imports:read`; 409 untuk batch `applied`; kategori tak dikenal 422; endpoint `ids` mengembalikan semua id lintas halaman; batch dengan `details` NULL (set langsung lewat sesi: `ImportBatch.details = None` pada batch `preview`) → halaman kosong `total == 0` (Review Focus 4).
- [ ] **Step 2: Jalankan** kedua berkas. Expected: FAIL.
- [ ] **Step 3: Implementasi** `absent.py`, `details.py`, integrasi `build_preview` (kandidat hanya bila `sheet.kind == REKAP`), kolom batch, service, router. Satu query kolam (kolom `Invoice` + `Student`), tidak N+1; hindari `IN` dengan banyak kode (bandingkan di Python).
- [ ] **Step 4: Jalankan** `pytest tests/test_imports_suspected_paid.py tests/test_imports_details_api.py tests/test_imports_preview.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(imports): list new, changed and suspected-paid invoices in the preview`.

### Task 6: Apply menandai lunas yang dipilih

**Files:**
- Modify: `kampusping-backend/app/modules/imports/apply.py`, `app/modules/imports/service.py`, `app/modules/imports/router.py`, `app/modules/imports/schema.py`, `app/modules/imports/constants.py` (`SUMMARY_KEYS` + `invoices_paid_by_absence`)
- Test: `tests/test_imports_mark_paid.py` (baru), `tests/test_imports_rollback_core.py`

**Interfaces:**
- Consumes: `details["suspected_paid"]` (Task 5), `ChangeRecorder.snapshot`, `cancel_pending_messages_for_invoices`.
- Produces: `class ImportApplyRequest(BaseModel): mark_paid_invoice_ids: list[int] = Field(default_factory=list, max_length=20_000)` di `schema.py`; `POST /imports/{id}/apply` menerima body opsional ini (tanpa body = daftar kosong). `ImportService.apply(batch_id: int, actor: User, mark_paid_invoice_ids: Sequence[int] = ()) -> ImportBatch`: `selected = {item["invoice_id"] for item in batch.details["suspected_paid"]} & set(mark_paid_invoice_ids)` (details NULL → kosong). `apply_rows(..., paid_by_absence_ids: Collection[int] = ())`: muat `Invoice` dengan id tersebut yang masih `deleted_at IS NULL` dan `status == unpaid`; `snapshot` sebelum mutasi (bersama snapshot yang sudah ada); set `status=paid`, `paid_at=today`, `paid_via=source`, `_touch`; ikut `paid_invoice_ids` agar pesan antre dibatalkan; hitungan `invoices_paid_by_absence` (tidak masuk `invoices_updated`).

- [ ] **Step 1: Tulis tes gagal** `tests/test_imports_mark_paid.py` (jam dibekukan): 
  `test_only_selected_suspects_become_paid` (3 kandidat, kirim 2 id → 2 `paid` dengan `paid_at` hari lokal dan `paid_via == "siakad"`, 1 tetap `unpaid`; ringkasan `invoices_paid_by_absence == 2`);
  `test_apply_without_body_marks_nothing`;
  `test_queued_messages_of_newly_paid_invoices_are_cancelled` (buat `Message` antre untuk salah satu, setelah apply status dibatalkan dengan alasan `paid`);
  `test_unknown_duplicate_and_non_suspect_ids_are_ignored` (id ganda, id tagihan lain yang bukan kandidat, id acak; Review Focus 3; tidak error, hitungan benar);
  `test_invoice_paid_manually_between_preview_and_apply_is_not_counted` (Review Focus 3);
  `test_second_preview_cannot_pay_twice` (dua preview berurutan, apply pertama menandai lunas, apply kedua dengan id yang sama menghitung 0; Review Focus 5);
  `test_audit_event_carries_paid_by_absence_count`;
  `test_selecting_ids_requires_imports_create` (403 tanpa izin).
  Di `tests/test_imports_rollback_core.py`: `test_rollback_restores_invoices_marked_paid_by_absence` (setelah rollback status kembali `unpaid`, `paid_at`/`paid_via` `None`).
- [ ] **Step 2: Jalankan** tes baru. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai Interfaces; `ImportBatchRead.summary` tidak berubah bentuk. Perbarui `SUMMARY_KEYS` dan tes yang menegaskannya.
- [ ] **Step 4: Jalankan** seluruh paket impor: `pytest tests -q -k "import"` lalu `pytest -q`. Expected: PASS (lihat catatan 6 kegagalan `.env` di CLAUDE.md; jalankan tanpa `.env` gateway).
- [ ] **Step 5: Commit** `feat(imports): mark selected suspected-paid invoices as paid when applying`.
- [ ] **Step 6: Gerbang kualitas** `ruff check . && ruff format --check . && pyright`. Expected: bersih; perbaiki bila perlu lalu commit `chore(imports): satisfy lint and types`.

### Task 7: Frontend: tab rincian, pilihan lintas halaman, kirim pilihan

**Files:**
- Modify: `kampusping-frontend/src/modules/import/types.ts`, `src/modules/import/services/import.service.ts`, `src/modules/import/components/ImportPreview.tsx`, `src/modules/import/components/ImportPage.tsx`, `src/modules/import/components/ImportPage.test.tsx`
- Create: `src/modules/import/components/ImportDetailsPanel.tsx`, `src/modules/import/components/ImportDetailsPanel.test.tsx`

**Interfaces:**
- `types.ts`: `ImportKind = 'standard' | 'rekap'`; `ImportBatch.kind: ImportKind`; `ImportSummary` ditambah opsional `invoices_unchanged?`, `paid_suspected?`, `incomplete_warning?`, `invoices_paid_by_absence?` (batch lama tidak punya); `ImportDetailCategory = 'new' | 'changed' | 'suspected_paid'`; `ImportDetailNew`, `ImportDetailChanged` (`fields: Record<string, [unknown, unknown]>`), `ImportDetailSuspectedPaid` (`invoice_id`, `invoice_code`, `nim`, `name`, `study_program`, `semester`, `amount`).
- `import.service.ts`: `apply(id: number, markPaidInvoiceIds?: number[])` (kirim `{ mark_paid_invoice_ids }` hanya bila array diberikan), `details(id, category, query)` → `Page<...>`, `detailIds(id): Promise<{ ids: number[] }>` (kategori `suspected_paid`).
- `ImportDetailsPanel` props: `{ batch: ImportBatch; selectedIds: Set<number>; onSelectedChange: (ids: Set<number>) => void; disabled: boolean }`. Tab (`AppTabs`): "Tagihan baru (n)", "Nominal berubah (n)", "Diduga lunas (n)" (hanya bila `batch.kind === 'rekap'`), "Masalah (n)" (tabel galat yang ada dipindah ke sini). Tab "Diduga lunas" memakai `AppDataGrid` dengan kotak centang yang bertahan lintas halaman, tombol "Pilih semua" (memakai `detailIds`) dan "Kosongkan", serta teks "Dipilih x dari y". Tab tanpa isi menampilkan `AppEmptyState` ("Tidak ada tagihan baru", "Tidak ada nominal yang berubah", "Tidak ada tagihan yang diduga lunas", "Tidak ada baris bermasalah").
- `ImportPreview`: `onApply: (batch: ImportBatch, markPaidInvoiceIds: number[]) => Promise<void>`; pilihan awal = semua id (dari `detailIds`) kecuali `summary.incomplete_warning === 1` (kosong); `COUNTS` ditambah "Tagihan tidak berubah" dan "Diduga lunas" (rekap) dan "Tagihan diperbarui" tetap; `Alert` peringatan bila `incomplete_warning` ("Lebih dari 30% tagihan semester ini hilang dari berkas. Kemungkinan ekspor tidak lengkap. Tidak ada yang dipilih; periksa daftar sebelum menandai lunas."); teks info rekap: "Tagihan yang hilang dari berkas ditampilkan sebagai Diduga lunas dan hanya ditandai lunas bila dipilih. Tunggakan semester yang tidak ada di berkas tidak diubah." (format standar mempertahankan teks lama); Terapkan membuka konfirmasi yang menyebut jumlah dipilih ("{n} tagihan akan ditandai lunas.") bila `n > 0`. `describeApplied` di `ImportPage` menambahkan "{n} ditandai lunas" bila `invoices_paid_by_absence > 0`.

- [ ] **Step 1: Tulis tes gagal** `ImportDetailsPanel.test.tsx` (mock `importService`): render tab dan hitungan dari ringkasan; empty state tiap tab; tab "Diduga lunas" tidak ada untuk `kind: 'standard'`; "Pilih semua" memanggil `detailIds` dan mengisi seluruh id walau halaman pertama hanya 100; "Kosongkan" mengosongkan; pilihan bertahan setelah pindah halaman dan pindah tab. `ImportPage.test.tsx`: Terapkan mengirim `mark_paid_invoice_ids` sesuai pilihan; pilihan awal semua bila tanpa peringatan dan kosong dengan `incomplete_warning: 1`; peringatan tampil; dialog konfirmasi menyebut jumlah; tanpa kandidat tidak ada dialog tambahan.
- [ ] **Step 2: Jalankan** `npm test -- src/modules/import`. Expected: FAIL.
- [ ] **Step 3: Implementasi** sesuai Interfaces, mengikuti `src/modules/README.md` dan README frontend (komponen `App*`, token tema, tanpa warna hard-coded).
- [ ] **Step 4: Jalankan** `npm test -- src/modules/import` lalu `npm run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(import): review new, changed and suspected-paid invoices before applying`.

### Task 8: E2E, dokumen, dan verifikasi akhir

**Files:**
- Modify: `kampusping-frontend/e2e/billing.spec.ts` (atau berkas baru `e2e/import-rekap.spec.ts`), `CLAUDE.md` (root), spec bagian Status
- Test: Playwright dengan `WA_PROVIDER=fake`, `E2E_FAKE_PROVIDER=1` (lihat `kampusping-frontend/e2e/README.md`, port selain 3000/8000)

- [ ] **Step 1: Tulis e2e** `import-rekap.spec.ts`: login staf, unggah rekap xlsx sintetis (tiga mahasiswa), Terapkan; unggah rekap kedua (satu hilang, satu nominal berubah, satu baru); di preview tab "Diduga lunas" berisi satu baris dan terpilih, lepas centang, Terapkan → halaman Tagihan menunjukkan tagihan itu tetap belum lunas; ulangi, biarkan tercentang → lunas. Jangan pernah menjalankan gateway.
- [ ] **Step 2: Jalankan** e2e sesuai README. Expected: PASS.
- [ ] **Step 3: Dokumen**: perbarui `CLAUDE.md` (daftar migrasi/tabel hingga `011`, status fitur: deteksi lunas pada impor rekap, aturan supersede hanya untuk format standar), tandai spec `Status: disetujui, diimplementasikan`, dan cari teks lama ("otomatis ditandai lunas", "supersede") di docs untuk disesuaikan (`rg -n "otomatis ditandai lunas|supersed" docs kampusping-backend/docs kampusping-frontend/src`).
- [ ] **Step 4: Verifikasi akhir** (skill `superpowers:verification-before-completion`): `pytest -q`, `ruff check . && ruff format --check . && pyright` di backend; `npm test && npm run check && npm run build` di frontend. Catat hasil nyata.
- [ ] **Step 5: Commit** per repo (`test(e2e): cover rekap import review`, `docs: record rekap import review in CLAUDE.md and the design spec`). Jangan push atau merge.

---

## Self-review

**Cakupan spec:** 4.1 kind → Task 1-2; 4.2 kandidat dan peringatan → Task 5; 4.3 rincian, endpoint, summary → Task 3 dan 5; 4.4 supersede/due date → Task 4, mark paid/log/summary → Task 6; 4.5 migrasi → Task 2; 4.6 tampilan → Task 7; pengujian bagian 6 → tes di tiap task + Task 8; batasan dan dokumen → Task 8. Kriteria berhasil 1 → `test_realistic_rekap_update_counts`; 2-3 → Task 4/6; 4 → Task 4; 5 → rollback test Task 6.

**Keputusan yang melebihi spec (tandai saat review):** endpoint `GET /imports/{id}/details/ids` ditambah karena `MAX_PAGE_SIZE = 100` dan "Pilih semua" harus lintas halaman; `invoice_changes` membandingkan `source` karena `apply_rows` menimpa `source`; klasifikasi `skipped` kini memeriksa tagihan aktif (preview lama menghitung tagihan terhapus yang lunas sebagai dilewati, apply memperlakukannya sebagai restore).
