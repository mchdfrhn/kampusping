# Desain: Ekspor laporan penagihan ke Excel dan PDF (FR-14)

Tanggal: 2026-11-05. Status: diimplementasi (rencana: `docs/superpowers/plans/2026-11-05-kampusping-reports-export.md`; kode ada di branch `feat/reports-export` repo backend dan frontend, belum di-merge). Sumber: BRD FR-14, BR-06; spec desain §7
(`2026-10-31-kampusping-design.md`). Kode kebutuhan (FR/NFR/AB/BR) merujuk ke BRD.

## 1. Tujuan

Pimpinan dan staf keuangan dapat mengunduh laporan efektivitas penagihan dalam bentuk Excel
(`.xlsx`) dan PDF langsung dari aplikasi, untuk transparansi (T5) dan tindak lanjut tunggakan.
Laporan dibuat saat diminta; tidak ada pengiriman email, jadwal otomatis, atau penyimpanan berkas.

## 2. Keputusan yang sudah diambil

| Topik | Keputusan |
| --- | --- |
| Pembaca laporan | Pimpinan dan staf keuangan; satu laporan, isi Excel dan PDF sama. |
| Data pribadi di daftar tunggakan | NIM dan nama. **Nomor HP tidak pernah ikut** (UU PDP, NFR-02). |
| Periode | Dua preset: `weekly` (7 hari terakhir) dan `semester` (pilih satu semester). Tanpa rentang bebas. |
| Pendekatan | Dibuat sinkron di backend saat diminta dan dikirim sebagai unduhan (bukan job latar, bukan dibuat di browser). |
| Library | `openpyxl` (sudah terpasang) dan `reportlab` (disebut di spec §7; ditambahkan dengan versi terkunci). |

## 3. Cakupan

Di dalam: modul backend `reports`, tiga endpoint, izin `reports:read` dan `reports:export` beserta
migrasi izin, audit unduhan, halaman **Laporan** di frontend, tes.

Di luar: laporan terjadwal atau email, rentang tanggal bebas, grafik, penyimpanan berkas hasil,
laporan selisih antar sumber (M2), perubahan pada dasbor.

## 4. Isi laporan

Tanggal selalu dalam zona `APP_TIMEZONE` (Asia/Jakarta). "Hari ini" berasal dari clock yang
diinjeksi, bukan jam sistem.

**Cakupan data per preset**

- `weekly`: kondisi tagihan **saat ini** untuk semua semester, ditambah aktivitas pada jendela
  `[hari ini - 6, hari ini]` (7 hari, inklusif).
- `semester`: seluruh angka dibatasi pada tagihan semester yang dipilih (pesan dibatasi lewat
  tagihannya, seperti dasbor).

**Bagian 1, Ringkasan**

- Tagihan: jumlah dan nominal total, lunas, belum lunas, lewat jatuh tempo; persentase lunas
  (menurut jumlah dan menurut nominal). Definisi lewat jatuh tempo sama dengan dasbor: belum lunas
  dan `due_date < hari ini`.
- Tagihan dengan `exempt_reason` terisi **tidak dihitung** sebagai lewat jatuh tempo dan tidak
  masuk daftar tunggakan; jumlahnya tampil terpisah sebagai "Dikecualikan" (AB-05).
- Pesan menurut status (`queued`, `sent`, `delivered`, `read`, `failed`, `cancelled`). Pada
  `weekly`, pesan dihitung menurut `scheduled_date` dalam jendela 7 hari (tipe `Date`, bebas
  ambiguitas zona waktu); pada `semester`, seluruh pesan dari tagihan semester itu.
- Pembayaran dalam periode: pada `weekly`, jumlah dan nominal tagihan dengan `paid_at` dalam
  jendela.
- **Lunas setelah pesan:** tagihan lunas yang memiliki minimal satu pesan berstatus `sent`,
  `delivered`, atau `read` dengan tanggal kirim (zona lokal) `<= paid_at`. Cakupan: pada `weekly`
  hanya tagihan yang `paid_at`-nya jatuh dalam jendela 7 hari; pada `semester` seluruh tagihan
  lunas semester itu. Dihitung di Python agar hasilnya sama di PostgreSQL dan SQLite.

**Bagian 2, Per prodi dan angkatan.** Satu baris per pasangan (prodi, angkatan): jumlah tagihan,
lunas, belum lunas, lewat jatuh tempo, nominal tunggakan, persentase lunas. Nilai kosong tampil
sebagai "(tanpa prodi)" dan "(tanpa angkatan)".

**Bagian 3, Daftar tunggakan.** Kolom: NIM, nama, prodi, angkatan, semester, kode tagihan, nominal,
jatuh tempo, hari terlambat, jumlah pesan terkirim, tanggal dan status pesan terakhir. Urutan: hari
terlambat terbanyak lebih dulu, lalu NIM. Tanpa batas jumlah baris (lihat risiko di §10).

**Bentuk berkas**

- Excel: tiga sheet (Ringkasan, Per Prodi-Angkatan, Tunggakan). Header tebal dan beku, filter otomatis
  pada Tunggakan, format `"Rp"#,##0` untuk nominal dan `dd-mm-yyyy` untuk tanggal.
- PDF: A4 landscape, judul, periode, waktu dan pembuat laporan, ketiga bagian di atas, baris header
  tabel berulang di tiap halaman, nomor halaman, dan catatan "Berisi data pribadi mahasiswa; jangan
  disebarluaskan."
- Nama berkas: `laporan-penagihan-<mingguan|semester-SLUG>-<YYYYMMDD>.<xlsx|pdf>`.

## 5. Backend

Modul baru `kampusping-backend/app/modules/reports/` mengikuti `docs/adding-a-module.md`:

| Berkas | Tanggung jawab |
| --- | --- |
| `constants.py` | Preset, format, nama aksi audit (`report.exported`), batas panjang semester (memakai `SEMESTER_MAX_LENGTH` dasbor). |
| `schema.py` | `ReportData` (ringkasan, kelompok prodi-angkatan, daftar tunggakan) dan skema JSON pratinjau. |
| `service.py` | `ReportService.build(preset, semester, clock)`: menghitung `ReportData` dengan beberapa kueri agregat tetap (tanpa N+1: satu kueri tunggakan, satu kueri agregat pesan per tagihan). |
| `xlsx_builder.py` | Fungsi murni `ReportData -> bytes` (openpyxl). |
| `pdf_builder.py` | Fungsi murni `ReportData -> bytes` (reportlab). |
| `router.py` | Tiga endpoint di bawah. |

Pembuatan berkas berjalan di `asyncio.to_thread` agar tidak memblokir event loop API. Worker adalah
proses terpisah dan tidak terpengaruh.

**Endpoint** (semua di bawah `/api/v1`)

| Metode dan jalur | Izin | Keterangan |
| --- | --- | --- |
| `GET /reports/options` | `reports:read` | Daftar semester yang ada pada tagihan. |
| `GET /reports/billing?preset=&semester=` | `reports:read` | JSON pratinjau: ringkasan, kelompok prodi-angkatan, dan **hanya jumlah** tunggakan. Tidak ada data pribadi di JSON. |
| `GET /reports/billing/export?preset=&semester=&format=xlsx\|pdf` | `reports:export` | Berkas dengan `Content-Type` dan `Content-Disposition: attachment`. |

Validasi: `preset=semester` wajib menyertakan `semester` (422); `format` dan `preset` di luar daftar
ditolak 422; semester yang tidak punya tagihan menghasilkan laporan sah berisi nol (sama seperti
dasbor). Galat memakai bentuk `{"error": {"code", "message", "details"}}`.

## 6. Izin dan migrasi

- Kode baru di `app/core/permissions.py`: `REPORTS_READ = "reports:read"` dan
  `REPORTS_EXPORT = "reports:export"`, dicerminkan di `src/core/auth/permissions.ts`.
- `admin` otomatis mendapat keduanya lewat seed. `staf_keuangan` dan `pimpinan` hanya dibuat sekali
  oleh seed (catatan di CLAUDE.md), sehingga ditambah migrasi data `007_reports_permissions`:
  membuat dua baris izin dan menautkannya ke peran sistem `staf_keuangan` dan `pimpinan` **bila
  peran itu ada dan belum memilikinya**. Idempoten, tidak menimpa perubahan peran lewat UI, dan
  `downgrade()` menghapus tautan dan izin tersebut.
- Deskripsi peran `pimpinan` pada seed diperbarui menjadi "melihat dasbor dan laporan" (hanya
  berlaku untuk database baru).
- Server menegakkan izin dengan `require_permissions`; menyembunyikan tombol di UI hanyalah
  kenyamanan.

## 7. Audit dan keamanan

- Setiap unduhan menulis `AuditEvent` `report.exported` dengan pelaku, `preset`, `semester`,
  `format`, dan jumlah baris tunggakan. Tanpa data pribadi (NFR-07).
- Sel teks Excel selalu ditulis sebagai string (`data_type = "s"`), tidak pernah sebagai formula,
  sehingga nama atau kode dari berkas impor yang diawali `=`, `+`, `-`, `@` tidak dieksekusi.
- Nomor HP tidak dibaca oleh kueri laporan sama sekali.
- Respons unduhan memakai `Cache-Control: no-store`.

## 8. Frontend

Modul `kampusping-frontend/src/modules/reports/` mengikuti `src/modules/README.md`, rute
`/reports`, item menu **Laporan** (izin `reports:read`). Halaman: pilihan preset (dan dropdown
semester untuk preset semester), kartu ringkasan dan tabel prodi-angkatan sebagai pratinjau, serta
tombol **Unduh Excel** dan **Unduh PDF** (tampil bila punya `reports:export`). Unduhan memakai
`apiClient.download` yang sudah ada. Seluruh teks UI berbahasa Indonesia; tanpa library frontend baru.

## 9. Pengujian

Backend (pytest, clock diinjeksi): hitungan agregat per preset; batas jendela 7 hari pada pergantian
tanggal zona Asia/Jakarta; baris soft-delete dan tagihan berkeringanan tidak ikut; "lunas setelah
pesan"; kelompok prodi-angkatan termasuk nilai kosong. Berkas: Excel dibaca balik dengan `openpyxl`
(sheet, header, nilai, tipe string untuk teks berawalan `=`); PDF valid (`%PDF`, tidak kosong) dan
diuji pula pada ribuan baris tunggakan. API: 401 tanpa login, 403 tanpa `reports:export`, header
unduhan, audit tertulis, tidak ada nomor HP di keluaran mana pun, 422 untuk parameter salah.
Migrasi: peran yang ada mendapat izin, dijalankan dua kali tanpa duplikat, `downgrade()` bersih.

Frontend (Vitest): pilihan preset dan semester, pratinjau tampil, tombol unduh memanggil servis
dengan parameter benar, tombol disembunyikan tanpa `reports:export`, pesan galat saat gagal.

## 10. Risiko dan pertanyaan terbuka

- **Tanpa batas baris:** daftar tunggakan yang sangat panjang bisa lambat atau memakan memori saat
  PDF dibuat. Ada tes dengan ribuan baris; bila terbukti lambat, tambahkan batas dan catatan
  "dipotong" pada PDF (Excel tetap lengkap).
- **Selisih dengan dasbor:** dasbor saat ini menghitung tagihan berkeringanan sebagai lewat jatuh
  tempo, laporan tidak. Saat ini belum ada layar yang mengisi `exempt_reason` (FR-16), jadi angkanya
  identik; samakan dasbor ketika layar pengecualian dibangun.
- **Versi `reportlab`:** dipilih dan dikunci saat implementasi setelah memeriksa rilis stabil
  terbaru yang kompatibel dengan Python 3.12.
- **Font PDF:** font bawaan (Helvetica) cukup untuk huruf Latin berbahasa Indonesia; nama
  bermuatan aksara non-Latin tidak dijamin tampil benar di PDF (di Excel tetap utuh).

## 11. Kriteria penerimaan

1. Staf, pimpinan, dan admin dapat membuka Laporan, memilih preset, dan mengunduh `.xlsx` dan `.pdf`
   dengan isi yang sama sesuai §4.
2. Pengguna tanpa `reports:export` tidak dapat mengunduh (403 dari server), tanpa `reports:read`
   tidak dapat melihat pratinjau.
3. Tidak ada nomor HP di berkas, JSON, maupun log.
4. Setiap unduhan tercatat di audit.
5. Seluruh tes baru lulus bersama gerbang kualitas yang ada (`ruff`, `pyright`, `pytest`, `eslint`,
   `tsc`, `vitest`).
