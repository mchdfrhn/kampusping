# KampusPing: desain sistem penagihan uang kuliah via WhatsApp

- Tanggal: 2026-10-31
- Status: draf untuk direview
- Sumber kebutuhan: [`docs/BRD-penagihan-uang-kuliah-whatsapp.md`](../../BRD-penagihan-uang-kuliah-whatsapp.md) (BRD v0.1)
- Keputusan terkait: [ADR 0002](../../adr/0002-baileys-whatsapp-gateway.md) (Baileys), [ADR 0003](../../adr/0003-database-backed-queue-and-worker-process.md) (antrean di database + worker)

## 1. Tujuan dan ruang lingkup

Mengubah template web universal di workspace ini menjadi sistem penagihan uang kuliah untuk Bagian
Keuangan: data tagihan masuk lewat berkas ekspor SIAKAD/Civitas dan SIPEMA, lalu pengingat dikirim
otomatis lewat WhatsApp hanya ke mahasiswa yang belum lunas. Pembayaran tetap terjadi di SIAKAD/SIPEMA.

Cakupan: seluruh FR-01 sampai FR-17 dan NFR-01 sampai NFR-10 dari BRD, dibangun dalam tiga tahap
(bagian 9). Di luar cakupan sama seperti BRD bagian 4: pembayaran lewat WhatsApp, API SIAKAD,
penagihan ke orang tua, kanal selain WhatsApp, dan penerbitan keringanan.

**Satu penyimpangan dari BRD:** kanal WhatsApp memakai Baileys (tidak resmi), bukan Cloud API yang
direkomendasikan BRD. Risiko dan mitigasinya ada di ADR 0002. Konsekuensinya NFR-04 ("template
disetujui") tidak berlaku apa adanya.

## 2. Arsitektur

```text
Browser ─► Next.js (UI Indonesia) ─► FastAPI API ─► PostgreSQL ◄─ Worker (python -m app.cli run-worker)
                                          ▲                            │ WhatsAppProvider
                                          │ webhook (status, balasan)  ▼
                                     Gateway Node + Baileys (kampusping-wa-gateway/) ◄─► WhatsApp
```

| Folder / proses | Isi | Repo |
| --- | --- | --- |
| `kampusping-backend/` | API FastAPI, model, migrasi, CLI, worker | repo sendiri |
| `kampusping-frontend/` | Next.js 16 + MUI 9, UI berbahasa Indonesia | repo sendiri |
| `kampusping-wa-gateway/` (baru) | Node 20+, TypeScript, Baileys, HTTP server kecil (Fastify) | repo sendiri |
| Worker | proses terpisah dari API, kode di backend | bagian backend |

- Backend hanya mengenal `WhatsAppProvider` (`send`, `status`, `qr`). Implementasi: `GatewayProvider`
  (HTTP ke gateway) dan `FakeProvider` (dev dan tes, mencatat pesan di memori). Dipilih lewat
  `WA_PROVIDER=fake|gateway`.
- Gateway menyimpan sesi Baileys di folder lokal (di luar git dan di luar web root). API gateway
  memakai `Authorization: Bearer <WA_GATEWAY_API_KEY>`; webhook ke backend ditandatangani HMAC-SHA256
  (`X-Signature`, kunci `WA_WEBHOOK_SECRET`). Gateway hanya mendengarkan di `127.0.0.1`.
- Waktu disimpan UTC. Tanggal bisnis (jatuh tempo, jendela kirim, "hari ini") dihitung di
  `APP_TIMEZONE=Asia/Jakarta`.
- Nomor HP dan NIM adalah data pribadi (UU PDP): log aplikasi menyamarkan nomor (hanya 4 digit
  terakhir), respons API hanya memuat data yang dibutuhkan layar, akses dibatasi izin.

## 3. Model data

Semua tabel bisnis mewarisi `AuditedModel` (id BIGINT, kolom audit, soft delete). Basis data bawaan
PostgreSQL.

| Tabel | Kolom penting |
| --- | --- |
| `students` | `nim` (unik), `name`, `study_program`, `cohort` (angkatan), `phone` (`+62…`), `phone_status` (`valid`/`invalid`/`missing`), `opted_out_at`, `opted_out_reason` |
| `invoices` | `invoice_code` (unik), `student_id`, `semester`, `amount` (rupiah, bigint), `due_date`, `status` (`unpaid`/`paid`), `paid_at`, `paid_via` (`siakad`/`sipema`), `source` (`siakad`/`sipema`, asal baris impor), `exempt_reason`, `exempt_until`, `escalated_at` |
| `import_batches` | `source`, `file_name`, `status` (`preview`/`applied`/`discarded`), `semester`, jumlah baris (valid, error, baru, diperbarui, dilewati), `rows` (JSON baris tervalidasi untuk tahap preview), `applied_at` |
| `import_row_errors` | `batch_id`, `row_number`, `field`, `message` |
| `message_templates` | `name`, `body`, `is_active` (variabel divalidasi saat simpan) |
| `schedule_rules` | `name`, `offset_days` (negatif = sebelum jatuh tempo), `template_id`, `is_active` |
| `messages` | `student_id`, `invoice_id`, `rule_id` (null untuk manual), `kind` (`auto`/`manual`), `batch_ref`, `scheduled_date`, `body` (hasil render), `status`, `cancel_reason`, `attempts`, `provider_message_id`, `error`, `queued_at`, `sent_at`, `delivered_at`, `read_at` |
| `replies` | `student_id` (boleh null bila nomor tak dikenal), `phone`, `body`, `received_at`, `status` (`new`/`handled`), `note`, `handled_by`, `handled_at` |
| `app_settings` | satu baris: lihat bagian 8 |
| `audit_events` | `actor`, `action`, `entity`, `entity_id`, `detail` (JSON), `at` |

Batasan penting:

- `messages` unik pada (`invoice_id`, `rule_id`) bila `rule_id` tidak null, sehingga perencanaan
  idempoten walau worker dijalankan ulang.
- Status `messages`: `queued → sending → sent → delivered → read`; cabang akhir `failed` dan
  `cancelled`. Nilai `cancel_reason`: `paid`, `opted_out`, `exempt`, `phone_invalid`, `expired`,
  `superseded`, `manual`, `escalated`.
- `students.opted_out_at` tidak pernah diubah oleh impor.
- Modul `example` dan tabel `example_items` dihapus. Migrasi `002_create_example_items` diganti
  dengan migrasi domain KampusPing, dengan syarat belum ada database yang pernah menjalankannya
  (dikonfirmasi di rencana implementasi; bila sudah ada, dibuat migrasi penghapus).

## 4. Impor data (FR-01, FR-02, FR-09)

1. Staf memilih sumber (`siakad` atau `sipema`), mengisi semester bila berkas tidak punya kolom
   semester, lalu mengunggah `.csv` atau `.xlsx` (batas 5 MB, 20.000 baris).
2. Header dicocokkan dengan alias Indonesia/Inggris (mis. `NIM`, `Nama`, `Prodi`/`Program Studi`,
   `Angkatan`, `No WA`/`HP`, `Kode Tagihan`, `Nominal`, `Jatuh Tempo`, `Status`, `Tanggal Bayar`,
   `Kanal Pembayaran`). Kolom wajib: NIM, kode tagihan, nominal, jatuh tempo, status. Header wajib
   yang hilang menolak berkas dengan pesan jelas.
3. Setiap baris divalidasi (NIM ada, nominal > 0, tanggal terbaca, status dikenali, nomor HP
   dinormalisasi ke `+62…`). Hasilnya **pratinjau**: jumlah baris valid, daftar galat per baris, dan
   perkiraan baris baru/diperbarui. Belum ada data bisnis yang berubah.
4. Staf menekan **Terapkan**; seluruh batch diterapkan dalam satu transaksi:
   - mahasiswa di-upsert menurut NIM (nama, prodi, angkatan diperbarui);
   - nomor HP diganti hanya bila nomor baru valid; nomor tidak valid tidak menimpa nomor valid
     yang sudah ada; mahasiswa tanpa nomor valid ditandai `invalid`/`missing`;
   - tagihan di-upsert menurut kode tagihan (nominal, jatuh tempo, semester diperbarui);
   - **lunas bersifat lengket:** baris `lunas` mengubah tagihan menjadi `paid` (mengisi `paid_at`,
     `paid_via`). Baris `belum lunas` tidak membatalkan tagihan yang sudah `paid`; baris itu dihitung
     sebagai "dilewati". Staf bisa membatalkan status lunas secara manual (tercatat di audit);
   - tagihan yang tidak muncul di berkas tidak diubah.
5. Format ekspor SIAKAD dan SIPEMA belum diketahui (pertanyaan terbuka BRD). Alias header disimpan
   sebagai konstanta per sumber agar mudah disesuaikan tanpa mengubah logika.
6. `.xlsx` memakai **openpyxl**; `.csv` memakai modul standar.

## 5. Penjadwalan dan pengiriman (worker; FR-04 sampai FR-09, NFR-05, NFR-06)

Worker menjalankan loop async tiap `WORKER_TICK_SECONDS` (default 60) dengan dua fase.

**Fase rencana.** Untuk setiap tagihan `unpaid` yang tidak dikecualikan, milik mahasiswa yang tidak
opt-out dan bernomor `valid`, dan untuk setiap aturan aktif: bila tanggal aturan
(`due_date + offset_days`) berada antara 3 hari lalu dan hari ini (jendela 3 hari agar tanggal yang
jatuh di akhir pekan tetap terkirim di hari kerja berikutnya), pesan dibuat dengan status `queued`, teks sudah dirender dari template. Kunci unik
mencegah duplikat. Pesan yang tertunda lebih dari 3 hari menjadi `cancelled(expired)`. Bila satu
tagihan punya beberapa pesan menunggu, hanya aturan terbaru yang dikirim; yang lama
`cancelled(superseded)`. Tagihan yang melewati batas eskalasi (default H+14) tidak lagi diberi pesan
otomatis; tagihan itu diberi `escalated_at` dan muncul di daftar "Perlu tindak lanjut staf" (AB-07).

**Fase kirim.** Hanya berjalan bila semua syarat ini benar: `auto_send_enabled`, sekarang berada di
jendela kirim (default 08.00 sampai 17.00 WIB, Senin sampai Jumat), provider terhubung, pengaman
data impor tidak aktif (M2), kuota harian belum habis. Untuk satu pesan pada satu waktu:

1. Ambil pesan `queued` tertua secara atomik (`queued → sending`).
2. **Cek ulang (FR-06):** muat ulang tagihan, mahasiswa, dan pengecualian dari database. Bila tagihan
   `paid`, mahasiswa opt-out, tagihan dikecualikan, atau nomor `invalid`, pesan menjadi
   `cancelled` dengan alasannya dan tidak dikirim.
3. **Satu pesan otomatis per mahasiswa per hari (AB-03):** bila mahasiswa sudah menerima pesan
   otomatis hari ini, pesan dikembalikan ke `queued` untuk hari kerja berikutnya. Tagihan yang paling
   lama jatuh temponya didahulukan.
4. Kirim lewat `WhatsAppProvider`, simpan `provider_message_id`, status `sent`.
5. Tunggu jeda acak `throttle_min_s` sampai `throttle_max_s` (default 8 sampai 20 detik).

Penanganan galat:

- Gagal kirim: `attempts` naik; ulang sampai 3 kali dengan jeda 5, 15, 45 menit; setelah itu
  `failed`. Provider melaporkan nomor tidak terdaftar di WhatsApp: pesan `failed`, mahasiswa
  ditandai `invalid`, tidak diulang (FR-08).
- Kegagalan satu pesan tidak menghentikan antrean (NFR-06). **Pemutus sirkuit:** 5 kegagalan
  beruntun atau sesi terputus menjeda fase kirim dan memunculkan peringatan di dasbor sampai staf
  mengaktifkan kembali atau sesi pulih.
- Worker yang mati saat `sending`: pesan `sending` yang lebih tua dari 10 menit dikembalikan ke
  `queued` pada tick berikutnya, kecuali `provider_message_id` sudah terisi (dianggap terkirim).

**Kirim manual atau massal (FR-12, M3).** Staf memfilter angkatan, prodi, rentang nominal, dan status,
memilih template, lalu melihat pratinjau jumlah penerima beserta yang dikecualikan (lunas, opt-out,
dikecualikan, nomor tidak valid). Pesan masuk antrean yang sama (`kind=manual`), sehingga cek ulang,
jendela kirim, jeda, dan kuota harian tetap berlaku. AB-03 hanya berlaku untuk pesan otomatis.

**Template (FR-03).** Variabel yang diizinkan: `nama`, `nim`, `semester`, `nominal` (format
`1.250.000`), `tanggal_jatuh_tempo` (mis. `15 November 2026`), `cara_bayar`, `link_pembayaran`,
`kontak_keuangan`, `nama_kampus`. Variabel tidak dikenal menolak penyimpanan. `link_pembayaran` dan
`cara_bayar` diambil dari pengaturan menurut `invoices.source`. Pratinjau memakai data contoh. Setiap
pesan otomatis diberi footer "Balas STOP untuk berhenti" (NFR-03) yang tidak bisa dihapus dari
template. Dua template contoh dari BRD (pengingat dan tunggakan) dan enam aturan standar AB-02
dibuat oleh seed.

## 6. Balasan dan opt-out (FR-10, FR-11, FR-17; M3)

- Gateway meneruskan pesan masuk lewat webhook. Backend mencari mahasiswa dari nomor pengirim dan
  menyimpan `replies`. Bila nomor tidak dikenal, balasan tetap disimpan tanpa `student_id`.
- Pesan yang (setelah trim, huruf kecil, tanda baca dibuang) sama persis dengan `stop`, `berhenti`,
  atau `unsubscribe` mengisi `opted_out_at`, membatalkan pesan antre mahasiswa itu
  (`cancelled(opted_out)`), dan memicu satu pesan konfirmasi. Opt-in kembali hanya oleh staf (tercatat
  di audit).
- Balasan lain muncul di halaman **Balasan** dengan status baru atau ditindaklanjuti dan catatan.
- Balasan otomatis `BANTUAN` (FR-17, prioritas Could) mengirim teks cara bayar dan kontak keuangan
  dari pengaturan; dikerjakan paling akhir.
- Risiko teknis: versi Baileys terbaru dapat memberi pengirim dalam bentuk LID, bukan nomor telepon.
  Gateway wajib memetakannya ke nomor; bila gagal, balasan disimpan tanpa mahasiswa untuk ditinjau
  staf. Opt-out dari nomor yang tidak terpetakan tidak bisa diterapkan otomatis.

## 7. Dasbor, laporan, peran

**Dasbor (FR-13)**, dapat difilter per semester:

- tagihan: jumlah dan nilai total, lunas, belum lunas, tunggakan (belum lunas dan lewat jatuh tempo);
- pesan: terkirim, delivered %, dibaca %, gagal %, dibatalkan karena lunas;
- lunas setelah pesan: tagihan yang `paid_at`-nya setelah pesan pertama terkirim;
- ketepatan waktu (T1): % tagihan `paid_at <= due_date` dari tagihan yang sudah jatuh tempo atau lunas;
- peringatan: sesi WhatsApp terputus, pemutus sirkuit aktif, data impor kedaluwarsa, jumlah tagihan
  yang menunggu tindak lanjut.

**Laporan (FR-14, M3):** ringkasan penagihan per periode (preset mingguan dan akhir semester) dengan
rincian per prodi dan angkatan serta daftar tunggakan; ekspor Excel (openpyxl) dan PDF
(**reportlab**). Dibuat saat diminta; tidak ada pengiriman email otomatis.

**Peran dan izin (FR-15, NFR-01, NFR-07).** Izin berbentuk `resource:action`, dicek di server dengan
`require_permissions(...)`, dan dicerminkan di `permissions.ts`.

| Sumber daya | Izin |
| --- | --- |
| `dashboard` | `read` |
| `imports` | `read`, `create` |
| `students` | `read`, `update` |
| `invoices` | `read`, `update` (pengecualian, ubah status manual) |
| `templates` | `read`, `create`, `update`, `delete` |
| `schedules` | `read`, `create`, `update`, `delete` |
| `messages` | `read`, `send`, `cancel` |
| `replies` | `read`, `update` |
| `reports` | `read`, `export` |
| `settings` | `read`, `update` (termasuk kontrol WhatsApp) |
| `audit` | `read` |
| `users`, `roles` | tetap seperti template |

Peran sistem hasil seed: `admin` (semua izin, disinkronkan tiap seed), `staf_keuangan` (semua kecuali
`users:*`, `roles:*`, `audit:*`), `pimpinan` (`dashboard:read`, `reports:read`, `reports:export`).
`pimpinan` tidak melihat nomor HP mahasiswa.

**Audit (NFR-07).** Setiap impor, penerapan impor, perubahan template, aturan, pengaturan,
pengecualian, perubahan status manual, kirim manual, opt-out/opt-in, dan penautan WhatsApp menulis
`audit_events` (pelaku, waktu, detail). Pengiriman tercatat di `messages` itu sendiri.

## 8. Pengaturan (`app_settings`)

Satu baris, diubah lewat halaman **Pengaturan** (admin dan staf keuangan):

| Kelompok | Kolom (default) |
| --- | --- |
| Identitas | `campus_name`, `finance_contact` |
| Pembayaran | `payment_link_siakad`, `payment_guide_sipema` (teks `cara_bayar` per sumber) |
| Jendela kirim | `window_start` (08:00), `window_end` (17:00), `working_days` (Senin sampai Jumat) |
| Pengaman | `auto_send_enabled` (false sampai diaktifkan staf), `daily_cap` (200), `throttle_min_s` (8), `throttle_max_s` (20), `max_attempts` (3), `consecutive_failure_limit` (5), `escalation_offset_days` (14) |
| Data impor (M2) | `stale_after_working_days` (2), `required_sources` |

Rahasia tidak masuk basis data: `WA_GATEWAY_API_KEY`, `WA_WEBHOOK_SECRET`, `WA_GATEWAY_URL`,
`WA_PROVIDER`, `APP_TIMEZONE`, `WORKER_TICK_SECONDS` dibaca dari `.env` lewat `Settings`, dan
ditambahkan ke setiap `.env.example`. Penautan WhatsApp (memindai QR, melihat status, keluar) dilakukan
dari **Pengaturan → WhatsApp**, memanggil gateway lewat backend.

## 9. Tahapan

Tiap tahap berdiri sendiri, diakhiri quality gate (ruff, pyright, pytest, `npm run check`, tes
gateway) dan daftar UAT BRD bagian 14 yang relevan.

| Tahap | Isi |
| --- | --- |
| **M1, MVP (fase 1 BRD)** | Penamaan KampusPing lewat `scripts/init.py`; hapus modul `example`; model `students`, `invoices`, impor (pratinjau dan terapkan); template dan aturan jadwal beserta seed; pengaturan; antrean `messages`, worker, **cek ulang sebelum kirim (FR-06, ditarik dari fase 2 karena menyangkut keamanan)**; gateway Baileys dan `FakeProvider`; log pengiriman; dasbor dasar; izin, peran, dan audit; UI Indonesia |
| **M2, penggabungan (fase 2)** | Profil kolom SIPEMA; laporan selisih antar sumber (nominal, jatuh tempo, nomor); pengaman data impor kedaluwarsa per sumber; dasbor lengkap (lunas setelah pesan, ketepatan waktu, peringatan) |
| **M3, penyempurnaan (fase 3)** | Kotak masuk balasan, opt-out lewat kata kunci, eskalasi, kirim manual/massal, pengecualian keringanan/cicilan, ekspor Excel dan PDF, balasan otomatis BANTUAN |

## 10. Pengujian

- **Backend (pytest, `FakeProvider`):** aturan jadwal dan jendela 3 hari; jendela kirim dan akhir
  pekan; jeda, kuota harian, dan pemutus sirkuit; perencanaan idempoten; pembatalan karena lunas,
  opt-out, pengecualian, nomor tidak valid; AB-03; `superseded`/`expired`; pemulihan pesan `sending`
  yang macet; validasi dan penerapan impor (lunas lengket, nomor valid tidak tertimpa);
  variabel template; webhook (tanda tangan salah ditolak); 401/403 untuk setiap izin dan peran.
  Waktu diinjeksi sebagai dependensi agar tes tidak bergantung jam sistem.
- **Frontend (Vitest, Playwright):** formulir dan validasi Zod, halaman impor (pratinjau sampai
  terapkan), navigasi menurut izin, alur masuk sampai impor di e2e.
- **Gateway (Vitest):** kontrak HTTP, pemeriksaan kunci API dan tanda tangan webhook, pemetaan
  JID dan LID ke nomor, dengan Baileys di-mock.
- **Tidak bisa diverifikasi otomatis:** pengiriman dan penerimaan asli lewat Baileys. Perlu uji
  manual di nomor WhatsApp sungguhan sebelum UAT.

## 11. Rapikan repo dan dokumentasi

- BRD disimpan di `docs/BRD-penagihan-uang-kuliah-whatsapp.md`; ADR 0002 dan 0003 ditulis.
- `CLAUDE.md` diperbarui: aturan Hino tidak berlaku, ringkasan produk, tiga layanan, perintah, aturan
  bisnis, dan bagian "Deviations from company rules" dihapus.
- `scripts/init.py` dijalankan (`--dry-run` dulu) agar nama paket, PM2, Docker, dan warna merek
  berubah menjadi KampusPing; skrip dan `docker-compose.yml` diperluas agar mengenal worker dan
  gateway (PM2 `kampusping-worker`, `kampusping-wa-gateway` pada 127.0.0.1).
- README root dan README tiap repo diperbarui dari "template universal" menjadi KampusPing, termasuk
  cara menautkan WhatsApp dan menjalankan worker.

## 12. Batasan dan risiko yang diketahui

- Baileys melanggar ketentuan WhatsApp; nomor dapat diblokir (ADR 0002). Gunakan nomor khusus.
- Baileys dapat rusak saat WhatsApp mengubah protokolnya; versi dikunci dan dipastikan saat rencana
  implementasi.
- Penyimpanan sesi Baileys berbasis berkas (`useMultiFileAuthState`) tidak direkomendasikan
  dokumentasi Baileys untuk produksi berbeban berat; untuk volume ini diterima, dengan opsi pindah ke
  penyimpanan database nanti. Folder sesi diperlakukan sebagai rahasia dan dicadangkan (NFR-09).
- Cek lunas sebelum kirim hanya melihat data impor terakhir. Pembayaran setelah impor terakhir tidak
  terlihat, itu sebabnya ada pengaman data kedaluwarsa (M2) dan impor harian dianjurkan.
- Hari libur nasional tidak dikenali: jendela kirim hanya memakai hari kerja Senin sampai Jumat.
- Kebijakan retensi pesan dan data mahasiswa belum ditetapkan (UU PDP); diputuskan kampus.
- Pertanyaan terbuka BRD bagian 14 yang memengaruhi implementasi: bentuk berkas ekspor, sumber dan
  persetujuan nomor WhatsApp, volume pesan, dan kebijakan keringanan. Desain ini mengasumsikan alias
  header yang bisa diubah dan persetujuan ditangani lewat footer opt-out.
- `docker-compose.yml` dan Dockerfile belum pernah dijalankan (catatan template); tidak diandalkan
  sebelum dibangun.
