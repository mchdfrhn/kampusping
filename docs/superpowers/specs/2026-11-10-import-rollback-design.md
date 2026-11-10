# KampusPing: desain rollback impor data

- Tanggal: 2026-11-10
- Status: disetujui, diimplementasikan (cabang `feat/import-rollback` di repo backend dan frontend)
- Kebutuhan induk: FR-01 di [`docs/BRD-penagihan-uang-kuliah-whatsapp.md`](../../BRD-penagihan-uang-kuliah-whatsapp.md); desain induk di [`2026-10-31-kampusping-design.md`](2026-10-31-kampusping-design.md)
- Aturan bisnis yang tidak boleh melemah: AB-01 / FR-06 (hanya tagihan belum lunas yang ditagih, lunas bersifat sticky lintas sumber impor), NFR-07 (audit), NFR-08 (data hanya masuk lewat berkas)

## 1. Tujuan

Di halaman **Impor Data**, bagian *Riwayat impor*, staf dapat menghapus sebuah impor yang berstatus
*Diterapkan*. Penghapusan itu mengembalikan data seperti sebelum impor tersebut dijalankan
(rollback), dengan kata lain mahasiswa dan tagihan yang dibuat impor itu hilang lagi, dan tagihan yang
hanya diubah kembali ke nilai semula.

Kebutuhan muncul karena berkas yang salah unggah (misalnya semester atau sumber keliru) saat ini
tidak bisa dibatalkan setelah diterapkan; satu-satunya jalan adalah "Hapus via berkas" di halaman
Tagihan, yang hanya menghapus tagihan dan tidak mengembalikan perubahan lain.

**Kriteria berhasil**
1. Setelah rollback, `students` dan `invoices` sama dengan keadaan sebelum impor diterapkan
   (nilai field bisnis, status lunas, dan status terhapus).
2. Tidak ada data yang diubah staf setelah impor tertimpa diam-diam.
3. Pesan yang masih antre untuk data yang dihapus tidak akan terkirim.
4. Setiap rollback tercatat di audit dan terlihat di riwayat impor.

**Di luar cakupan**
- Rollback impor yang diterapkan sebelum fitur ini ada (nilai lamanya tidak pernah disimpan).
- Menarik kembali pesan WhatsApp yang sudah terkirim.
- Rollback sebagian atau memilih baris tertentu.
- Menghapus impor berstatus *Pratinjau* (sudah ada: aksi "buang" / discard).

## 2. Keputusan yang sudah disepakati

| Keputusan | Pilihan |
| --- | --- |
| Cakupan data | Rollback penuh: yang dibuat dihapus, yang diubah dikembalikan ke nilai sebelum impor |
| Urutan | Hanya impor *Diterapkan* yang terbaru yang boleh di-rollback; setelah itu impor sebelumnya baru boleh |
| Pendekatan | Tabel log perubahan `import_changes` (bukan kolom batch di tabel bisnis, bukan snapshot tabel) |

## 3. Temuan pada kode saat ini

- `students` dan `invoices` tidak menyimpan batch asalnya.
- `apply_rows` ([`app/modules/imports/apply.py`](../../../kampusping-backend/app/modules/imports/apply.py)) menimpa `name`, `study_program`, `cohort`, `phone`, `phone_status`
  pada mahasiswa dan `amount`, `due_date`, `semester`, `source`, `status`, `paid_at`, `paid_via` pada tagihan, tanpa menyimpan nilai lama.
- Baris yang soft-deleted dipulihkan oleh `_restore` (`deleted_at` dan `deleted_by` menjadi `NULL`);
  pencarian di [`existing.py`](../../../kampusping-backend/app/modules/imports/existing.py) sengaja ikut membaca baris terhapus karena `nim` dan `invoice_code` unik.
- Tagihan belum lunas milik mahasiswa yang menerima kode tagihan baru otomatis ditandai lunas
  ("superseded") dan pesan antre-nya dibatalkan dengan alasan `paid`.
- `opted_out_at`, `opted_out_reason` pada mahasiswa tidak pernah disentuh impor, jadi tidak ikut di-rollback.
- Dua impor *Diterapkan* yang ada sekarang (3 Nov dan 5 Nov 2026) tidak punya log.

## 4. Desain

### 4.1 Data

Migrasi baru `008_import_changes` (revisi sebelumnya `007`):

`import_changes` (mewarisi `AuditedModel`, sama seperti tabel bisnis lain)

| Kolom | Tipe | Keterangan |
| --- | --- | --- |
| `batch_id` | FK `import_batches.id`, indeks | impor yang menghasilkan perubahan |
| `entity` | string(10) | `student` atau `invoice` |
| `entity_id` | BIGINT | id baris yang dibuat atau diubah |
| `action` | string(10) | `created` atau `updated` |
| `before` | JSON, null untuk `created` | hanya field yang berubah, nilai sebelum impor |
| `after` | JSON | hanya field yang berubah, nilai setelah impor |

- Indeks `(batch_id, entity)`.
- `ImportStatus` mendapat nilai `rolled_back`; `import_batches.status` sudah string(10), cukup.
- `import_batches` mendapat kolom `rolled_back_at` (DateTime, nullable).
- Pemulihan baris soft-deleted oleh `_restore` dicatat sebagai `updated` dengan `deleted_at` dan `deleted_by` di `before` / `after`.
- `import_batches` mendapat kolom `has_change_log` (boolean, default false). Kolom ini, bukan keberadaan baris
  `import_changes`, menentukan apakah impor dapat di-rollback: impor yang diterapkan sebelum fitur ini bernilai false
  (tidak dapat di-rollback), sedangkan impor baru yang kebetulan tidak mengubah apa pun tetap bernilai true.

### 4.2 Pencatatan saat impor diterapkan

`apply_rows` ditambah pencatatan di transaksi yang sama, tanpa mengubah logika AB-01, sticky paid, atau penghitungan:

- Mahasiswa atau tagihan baru: satu baris `created`.
- Mahasiswa atau tagihan yang berubah (`_set` / `_restore` melaporkan perubahan): satu baris `updated` dengan
  `before` dan `after` untuk field yang benar-benar berubah. Satu entitas yang disentuh dua baris berkas
  digabung menjadi satu catatan (`before` dari keadaan awal, `after` dari keadaan akhir).
- Tagihan "superseded" yang otomatis lunas: baris `updated` (`status`, `paid_at`, `paid_via`).
- Baris yang dilewati (sticky skip, milik NIM lain) tidak mencatat apa pun.
- Batch ditandai `has_change_log = true`.

### 4.3 Rollback

Endpoint `POST /api/v1/imports/{id}/rollback` dan `GET /api/v1/imports/{id}/rollback-preview` (hitungan dampak
tanpa mengubah data, dipakai dialog konfirmasi). Rollback berjalan dalam **satu transaksi**.

**Syarat** (gagal dengan 409 dan pesan Indonesia yang spesifik):
1. `status == applied`.
2. `has_change_log == true`; selain itu: "Impor ini diterapkan sebelum fitur rollback ada dan tidak dapat dibatalkan."
3. Batch ini memiliki `applied_at` paling baru di antara semua batch `applied`. Batch `rolled_back`, `preview`, dan `discarded` tidak dihitung.
4. Klaim atomik `UPDATE ... WHERE status = 'applied'` (pola yang sama dengan `claim_preview`), supaya dua rollback bersamaan tidak berjalan dua kali.

**Pengecekan konflik:** untuk setiap catatan `updated`, nilai field saat ini harus sama dengan `after`. Untuk setiap catatan
`created`, baris tidak boleh sudah terhapus atau berubah di luar impor yang tercatat. Jika ada yang berbeda (mis. staf
mengubah status tagihan manual setelah impor), **seluruh rollback ditolak** dengan 409 dan daftar baris yang bentrok
(maksimal 50 ditampilkan, ditambah total). Tidak ada rollback sebagian.

**Penyesuaian setelah review (2026-11-10):**
- Perubahan pada `phone_status` mahasiswa (diubah sistem saat pengiriman gagal) bukan konflik.
- Baris yang sudah dihapus permanen (hard delete) dilewati, bukan konflik.
- Rollback dan apply diserialisasi dengan advisory lock PostgreSQL (`imports/locking.py`); rollback mengunci baris terkait (`FOR UPDATE`) selama pengecekan konflik. Belum diuji pada PostgreSQL (tes memakai SQLite).
- Impor ulang setelah rollback memperlakukan tagihan yang dipulihkan sebagai baru: status lunas/belum ditentukan ulang oleh berkas dan tagihan lama mahasiswa di-supersede lagi.
- Keterbatasan yang diketahui: pesan antre yang dibatalkan rollback tetap menempati `(invoice_id, rule_id)`, sehingga aturan itu tidak direncanakan ulang untuk tagihan yang dipulihkan.

**Eksekusi:**
- `created`: mahasiswa dan tagihan di-soft-delete (`deleted_at`, `deleted_by`).
- `updated`: field dikembalikan ke `before`.
- Pesan: pesan berstatus `queued` untuk tagihan yang dihapus menjadi `cancelled` (alasan `manual`, error "Impor dibatalkan").
  Pesan yang sudah terkirim tetap di log pengiriman.
- Batch menjadi `rolled_back` dengan `rolled_back_at`; `rows` tetap `NULL`.
- Audit `import.rolled_back` dengan `detail` berisi jumlah per jenis perubahan dan jumlah pesan yang dibatalkan.

**Tidak berubah oleh rollback:** `opted_out_at`, `opted_out_reason`, `exempt_reason`, `exempt_until` (impor tidak menyentuhnya).

### 4.4 Izin

Izin baru `imports:rollback` di `app/core/permissions.py` (dicerminkan di `src/core/auth/permissions.ts`), dipakai lewat
`require_permissions(...)` di server. Awalnya hanya dimiliki `admin` (otomatis lewat seed). `staf_keuangan` tidak otomatis mendapat izin baru
(lihat batasan di CLAUDE.md); jika ingin diberikan, migrasi 008 menambahkannya seperti pola migrasi 007.
**Perlu keputusan:** apakah `staf_keuangan` juga mendapat izin ini. Default spec ini: hanya `admin`.

### 4.5 Antarmuka

Halaman Impor Data, tabel Riwayat impor:
- Kolom Aksi pada baris *Diterapkan* mendapat ikon hapus/rollback bila pengguna punya `imports:rollback`. Jika syarat 2 atau 3 tidak terpenuhi,
  ikon nonaktif dengan tooltip alasan ("Impor lama tanpa log" atau "Rollback impor yang lebih baru lebih dulu").
- Klik membuka dialog konfirmasi yang memanggil `rollback-preview`: jumlah mahasiswa baru yang dihapus, tagihan baru yang dihapus,
  tagihan yang dikembalikan, pesan antre yang dibatalkan, dan peringatan bahwa pesan yang sudah terkirim tidak dapat ditarik.
- Jika ada konflik, dialog menampilkan daftar bentrok dan tombol Hapus dinonaktifkan.
- Chip status baru "Dikembalikan" untuk `rolled_back` ("Dibatalkan" sudah dipakai status `discarded`).
- Semua teks UI berbahasa Indonesia, memakai komponen `App*` dan token tema sesuai README frontend.

### 4.6 Pengujian

Backend (pytest, jam disuntik, `DATABASE_ENGINE=sqlite`):
- apply mencatat `created` dan `updated` dengan `before` dan `after` yang benar, termasuk tagihan superseded dan baris yang dipulihkan.
- rollback mengembalikan `students` dan `invoices` persis seperti sebelum apply (bandingkan snapshot).
- hanya impor terbaru yang boleh di-rollback; setelah rollback, impor sebelumnya menjadi eligible.
- edit manual setelah impor menyebabkan 409 dan tidak ada perubahan data.
- impor lama tanpa log ditolak; batch `preview`, `discarded`, `rolled_back` ditolak.
- pesan antre dibatalkan, pesan terkirim tidak disentuh.
- impor ulang berkas yang sama setelah rollback memulihkan baris yang di-soft-delete.
- dua rollback bersamaan: satu berhasil, satu 409.
- akses: 401 tanpa login, 403 tanpa `imports:rollback`.

Frontend (Vitest): tombol dan tooltip nonaktif, dialog dampak, tampilan konflik, chip status baru.
E2E (Playwright, `WA_PROVIDER=fake`, `E2E_FAKE_PROVIDER=1`): unggah, terapkan, rollback, data kembali.

### 4.7 Dokumen yang diperbarui

`kampusping-backend/docs/messaging.md` bila perilaku pesan relevan, `docs/BRD` tidak diubah (FR-01 tetap), CLAUDE.md
(daftar tabel dan status), dan catatan database untuk migrasi 008.

## 5. Risiko dan hal yang perlu diverifikasi saat perencanaan

- **Planner dan tagihan yang kembali belum lunas.** Tagihan yang dibalikkan dari lunas ke belum lunas akan kembali masuk
  perencanaan pesan. Verifikasi di `messaging.md` dan planner bahwa pesan yang dulu dibatalkan karena `paid` tidak menimbulkan
  duplikat atau pengiriman di luar aturan AB-03 (satu pesan per mahasiswa per hari).
- **Ukuran log.** Impor 20.000 baris menghasilkan hingga puluhan ribu catatan; sisipkan dalam potongan (pola `_chunks`) dan beri indeks `batch_id`.
- **Retensi.** Log perubahan memuat data pribadi (nama, nomor HP). Retensi belum ditentukan (UU PDP); ikuti keputusan retensi kampus nanti dan jangan menyimpan lebih dari yang perlu (hanya field yang berubah).
- **Pesan terkirim ke tagihan yang dihapus.** Mahasiswa mungkin sudah menerima pengingat dari data yang di-rollback; ini tidak bisa dibatalkan dan hanya diperingatkan di dialog.
