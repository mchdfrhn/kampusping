# Runbook WhatsApp KampusPing

Panduan untuk staf IT dan admin yang mengoperasikan nomor WhatsApp pengirim pengingat tagihan.
Untuk staf keuangan, bagian yang relevan: [status dan artinya](#2-status-koneksi-dan-artinya),
[menjeda dan melanjutkan](#5-menjeda-dan-melanjutkan-pengiriman) dan
[mematikan pengiriman otomatis](#6-mematikan-pengiriman-otomatis).

> **Peringatan.** KampusPing mengirim lewat Baileys, pustaka WhatsApp Web **tidak resmi**. Ini
> melanggar ketentuan WhatsApp: nomor dapat **diblokir, bahkan permanen**, dan Baileys dapat rusak
> kapan saja bila WhatsApp mengubah protokolnya. Keputusan ini dicatat di
> [ADR 0002](adr/0002-baileys-whatsapp-gateway.md) dan menyimpang dari rekomendasi BRD (Cloud API
> resmi). Pengaman di sistem hanya **mengurangi** risiko, tidak menghilangkannya.

## 1. Arsitektur singkat

```text
Worker (python -m app.cli run-worker) ──HTTP + kunci API──► Gateway (127.0.0.1:8095) ──Baileys──► WhatsApp
API (FastAPI) ◄──webhook bertanda tangan HMAC── Gateway     (status Diterima / Dibaca, perubahan koneksi)
Browser ──► Pengaturan ► Koneksi WhatsApp ──► API ──► Gateway (status, kode QR, Putuskan sesi)
```

- **Gateway** (`kampusping-wa-gateway/`, proses PM2 `kampusping-wa-gateway`) memegang sesi WhatsApp.
  Ia hanya mendengarkan di `127.0.0.1:8095`; tidak ada situs Nginx dan tidak boleh dibuka ke luar.
- **Worker** (PM2 `kampusping-worker`) menyusun dan mengirim pesan satu per satu. **Hanya boleh ada
  satu worker** dan satu gateway untuk satu sesi WhatsApp.
- Sesi (kredensial login WhatsApp) disimpan di folder `auth_state/`; daftar pesan yang sudah dikirim
  (pencegah kirim ganda) di folder `data/`. Keduanya ada di sisi gateway.
- Aturan pengiriman (jendela jam, batas harian, jeda, cek ulang sebelum kirim) dijelaskan di
  [`kampusping-backend/docs/messaging.md`](../kampusping-backend/docs/messaging.md) (Inggris).

Catatan: berkas Docker (`docker-compose.yml`, Dockerfile) **belum pernah dibangun atau dijalankan**.
Perintah di bawah memakai PM2 seperti di folder `deploy/` tiap repo; padanan Docker dicatat bila ada.

## 2. Status koneksi dan artinya

Dilihat di **Pengaturan → Koneksi WhatsApp** (halaman diperbarui otomatis tiap beberapa detik).

| Status di layar | Artinya | Pengiriman |
| --- | --- | --- |
| **Terhubung** | Sesi aktif dan siap mengirim. | Berjalan sesuai jadwal. |
| **Menyambungkan…** | Gateway sedang menyambung atau menyambung ulang ke WhatsApp. | Menunggu. |
| **Menunggu pemindaian** | Belum ada sesi tertaut; kode QR tampil. | Tidak mengirim. |
| **Terputus** | Tidak ada sambungan (jaringan, gateway mati, perangkat dilepas, nomor dibatasi). | Tidak mengirim. |
| "Tidak dapat memuat status WhatsApp" | API tidak bisa menghubungi gateway (gateway mati, kunci API salah). | Tidak mengirim. |

Selama status bukan **Terhubung**, worker melewati tahap kirim; pesan tetap berstatus **Antre** dan
akan dikirim otomatis setelah sambungan pulih. Namun pesan yang tertunda lebih dari 3 hari dari
tanggal jadwalnya menjadi **Dibatalkan (Kedaluwarsa)** dan tidak dikirim lagi, jadi gangguan yang
lama berarti sebagian pengingat hilang (staf perlu menagih manual).

## 3. Menautkan nomor (pertama kali atau ganti nomor)

**Gunakan nomor KHUSUS**, bukan nomor utama kampus atau nomor pribadi yang penting. Bila nomor
diblokir, hanya nomor khusus itu yang hilang.

1. Siapkan ponsel dengan nomor khusus dan WhatsApp aktif (nomor sudah terverifikasi di ponsel itu).
2. Pastikan gateway berjalan (`pm2 status` menampilkan `kampusping-wa-gateway` online) dan API
   serta worker memakai `WA_PROVIDER=gateway` dengan `WA_GATEWAY_URL`, `WA_GATEWAY_API_KEY` dan
   `WA_WEBHOOK_SECRET` yang sama dengan `.env` gateway.
3. Masuk sebagai pengguna dengan izin `settings:update` (admin atau staf keuangan), buka
   **Pengaturan → Koneksi WhatsApp**. Status menjadi **Menunggu pemindaian** dan kode QR tampil
   (kode berganti sekitar tiap 20 detik).
4. Di ponsel: **WhatsApp → Perangkat tertaut → Tautkan perangkat**, lalu pindai kode QR di layar.
5. Status berubah ke **Menyambungkan…** lalu **Terhubung**. Jangan memindai berulang kali dan jangan
   menekan **Putuskan sesi** berulang: login yang cepat dan berulang adalah salah satu pemicu blokir.
6. Sebelum mengaktifkan pengiriman otomatis, jalankan [uji manual](manual-smoke-test.md).

Tanpa antarmuka web, kode QR mentah ada di gateway: `GET http://127.0.0.1:8095/status` dengan header
`Authorization: Bearer <WA_GATEWAY_API_KEY>` (nilai `qr` adalah teks yang dirender sebagai kode QR).

## 4. Bila terputus, kode 440, 403 atau diblokir

Mulai dari log gateway: `pm2 logs kampusping-wa-gateway` (tidak memuat nomor lengkap, isi pesan,
kunci API atau rahasia webhook).

| Gejala | Kemungkinan penyebab | Tindakan |
| --- | --- | --- |
| **Terputus** sebentar lalu **Terhubung** sendiri | Gangguan jaringan. Gateway menyambung ulang dengan jeda yang makin lama (2 detik, 4, 8, … hingga 5 menit). | Tunggu. Jangan restart berulang. |
| **Terputus** terus, log gateway berisi satu peringatan "WhatsApp session was logged out" | Perangkat dilepas dari ponsel (WhatsApp → Perangkat tertaut) atau sesi dicabut. Kondisi ini **final**: gateway tidak mencoba lagi. | **Pengaturan → Putuskan sesi**, lalu pindai QR baru. Hapus perangkat lama di ponsel bila masih tampil. |
| **Terputus**, log berisi "taken over by another connection" (kode **440**, connection replaced) | Ada proses lain yang memakai sesi yang sama (gateway kedua, salinan cadangan yang dijalankan, atau penaut lain dengan sesi itu). Final. | Hentikan proses lain itu. Pastikan hanya satu gateway. Lalu restart gateway (`pm2 restart kampusping-wa-gateway`). Bila tetap gagal, **Putuskan sesi** dan pindai ulang. |
| **Terputus**, log berisi "WhatsApp refused the session (the number may be restricted or banned)" (kode **403**, forbidden) | Nomor dibatasi atau diblokir WhatsApp. Final. | Lihat bagian "Nomor diblokir atau dibatasi" di bawah. Jangan menautkan ulang berkali-kali. |
| "Tidak dapat memuat status WhatsApp" | Gateway mati atau tidak terjangkau, atau `WA_GATEWAY_API_KEY` tidak sama (log API: "Gateway rejected the API key"). | `pm2 status`, nyalakan gateway, samakan kunci di API/worker dan gateway. |
| **Terputus** dan tombol **Putuskan sesi** gagal | Gateway tidak bisa memindahkan folder sesi (izin berkas). | Periksa pemilik dan izin folder `auth_state/` (pemilik pengguna PM2, mode `700`); lihat log gateway. |

Setelah penutupan "final" tidak ada soket yang terhubung, jadi **Putuskan sesi** hanya mereset sesi
secara lokal (memindahkan folder lama dan menampilkan QR baru). Perangkat lama di ponsel perlu
dilepas sendiri lewat WhatsApp → Perangkat tertaut.

### Nomor diblokir atau dibatasi

1. **Matikan pengiriman otomatis** ([bagian 6](#6-mematikan-pengiriman-otomatis)) agar tidak ada
   percobaan kirim lagi.
2. Periksa ponsel: apakah WhatsApp menampilkan pesan pembatasan atau permintaan verifikasi. Ikuti
   prosedur banding di aplikasi WhatsApp bila ada. Hasilnya tidak dapat dijamin.
3. Jangan menautkan, memutus dan menautkan ulang berkali-kali. Itu memperburuk keadaan.
4. Bila nomor tidak pulih, siapkan **nomor khusus pengganti**: **Putuskan sesi**, pindai QR dengan
   ponsel baru, jalankan uji manual, baru aktifkan pengiriman lagi. Pertimbangkan menurunkan
   **Batas harian** dan memperlebar jeda antar pesan di Pengaturan.
5. Selama menunggu, staf keuangan menagih lewat jalur lain. Pesan yang tertunda lebih dari 3 hari
   menjadi Kedaluwarsa, jadi tinjau tagihan yang jatuh tempo pada masa gangguan.
6. Laporkan kejadian ke atasan Bagian Keuangan dan pengembang (lihat [eskalasi](#12-kontak-eskalasi)).

## 5. Menjeda dan melanjutkan pengiriman

Sistem berhenti sendiri dalam dua keadaan yang berbeda:

- **WhatsApp tidak Terhubung:** pengiriman terlewati dan **pulih otomatis** begitu status kembali
  **Terhubung**. Tidak ada yang perlu ditekan.
- **Pemutus sirkuit (circuit breaker):** bila pengiriman gagal **berturut-turut** sebanyak
  **Batas kegagalan beruntun** (bawaan 5), seluruh pengiriman otomatis dijeda. Di **Dasbor** dan
  **Pengaturan** muncul peringatan "Pengiriman otomatis dijeda: terlalu banyak kegagalan beruntun".
  Pemutus ini **tidak pulih sendiri**.

Untuk melanjutkan setelah pemutus sirkuit:

1. Cari tahu penyebabnya dulu: lihat **Pengiriman** (kolom Alasan pada baris Gagal), `pm2 logs
   kampusping-worker` dan log gateway. Penyebab umum: gateway terputus saat mengirim, kunci API
   salah, atau nomor dibatasi.
2. Perbaiki penyebabnya (status harus **Terhubung**).
3. Di **Pengaturan**, tekan **Lanjutkan pengiriman** pada peringatan (perlu izin `settings:update`).
   Penghitung kegagalan di-reset dan tindakan ini tercatat di audit.

Satu pesan yang gagal tidak menghentikan antrean. Pesan gagal dicoba ulang dengan jeda 5 lalu 15
menit (bawaan **Maksimum percobaan** = 3 percobaan *total*), lalu berstatus **Gagal**. Nomor yang
tidak terdaftar di WhatsApp langsung **Gagal** dan nomor mahasiswa ditandai tidak valid.

## 6. Mematikan pengiriman otomatis

- **Cara normal:** **Pengaturan → Pengiriman otomatis** dimatikan, lalu **Simpan pengaturan**. Worker
  tetap berjalan tetapi tidak mengirim. Pesan yang sudah dibuat tetap **Antre** (jangan lupa batas
  kedaluwarsa 3 hari).
- **Membatalkan satu pesan antre:** menu **Pengiriman**, ikon Batalkan pada barisnya (hanya pesan
  berstatus Antre).
- **Darurat:** `pm2 stop kampusping-worker`. Pesan yang sedang dikirim saat itu dipulihkan otomatis
  saat worker hidup lagi (lihat messaging.md, "stale recovery").
- Pengiriman otomatis **mati** secara bawaan pada database baru dan harus diaktifkan staf dengan
  konfirmasi.

## 7. Rotasi rahasia

Ada dua rahasia bersama antara gateway dan backend, masing-masing minimal 16 karakter (buat dengan
`openssl rand -hex 32`); gateway menolak nilai kosong, pendek atau berawalan `change-me`:

| Rahasia | Fungsi | Dipakai oleh |
| --- | --- | --- |
| `WA_GATEWAY_API_KEY` | Kunci Bearer untuk memanggil gateway | gateway, API dan worker |
| `WA_WEBHOOK_SECRET` | Tanda tangan HMAC webhook gateway → API | gateway dan API |

Langkah:

1. **Matikan pengiriman otomatis** ([bagian 6](#6-mematikan-pengiriman-otomatis)) atau hentikan
   worker. Selama nilai belum sama di semua proses, panggilan ditolak dan kegagalan beruntun bisa
   memicu pemutus sirkuit.
2. Ganti nilai di `.env` gateway **dan** `.env` backend (backend dipakai API dan worker).
3. Restart ketiganya: `pm2 restart kampusping-wa-gateway kampusping-backend kampusping-worker`.
4. Periksa **Pengaturan → Koneksi WhatsApp**: harus **Terhubung** (bukan "Tidak dapat memuat").
   Sesi WhatsApp tidak terpengaruh, tidak perlu pindai ulang.
5. Aktifkan lagi pengiriman otomatis, dan **Lanjutkan pengiriman** bila muncul peringatan jeda.
6. Jangan simpan nilai lama; jangan taruh rahasia di berkas yang masuk git.

Rahasia lain (`SECRET_KEY` JWT, kata sandi database) diganti menurut panduan deploy backend.

## 8. Cadangan `auth_state/` dan `data/`

| Folder (di sisi gateway) | Isi | Bila hilang |
| --- | --- | --- |
| `auth_state/` | Kunci sesi WhatsApp (setara login). **Rahasia.** | Pindai QR ulang. Bila salinan jatuh ke orang lain, ia dapat mengirim atas nama nomor itu. |
| `data/` | Penyimpanan `client_ref` (pencegah kirim ganda, disimpan 14 hari). | Percobaan ulang pesan terbaru dapat terkirim **ganda** selama 14 hari. |

Untuk instalasi PM2 folder-folder ini berada di folder kerja gateway (`./auth_state`, `./data`)
kecuali diubah lewat `WA_AUTH_DIR` dan `WA_DEDUPE_FILE`. Di Docker keduanya ada di volume `wa-auth`
(`/app/session`, sesi di subfolder `auth_state`) dan `wa-data` (`/app/data`).

- Cadangkan **keduanya bersama-sama**, terenkripsi, dengan perlindungan seperti kata sandi.
- **Hentikan gateway dulu** (`pm2 stop kampusping-wa-gateway`) lalu salin, atau pakai snapshot
  sistem berkas yang atomik. Baileys menulis ulang berkas kunci saat berjalan, jadi menyalin berkas
  dari gateway yang hidup dapat menghasilkan kunci yang tidak konsisten.
- Izin: pemilik pengguna PM2, mode `700` (`chmod -R go-rwx auth_state data`). Jangan taruh di web
  root, jangan commit ke git, simpan di disk lokal (bukan folder jaringan).
- **Salinan pulihan tidak boleh berjalan bersamaan dengan produksi** (di server lain atau mesin uji):
  dua pemegang sesi yang sama saling menendang, dan gateway berhenti permanen dengan status
  "connection replaced" (440). Pulihkan hanya setelah gateway produksi dihentikan, atau bila memang
  menggantikannya.
- Memulihkan `auth_state/` mengembalikan sesi tanpa QR baru, kecuali WhatsApp sudah melepas perangkat.

## 9. Menghapus salinan `auth_state.old-*`

**Putuskan sesi** tidak menghapus sesi lama, melainkan memindahkannya ke
`auth_state.old-<angka>` (hanya salinan terbaru yang disimpan). Salinan itu **masih bisa berisi login
yang hidup**, sama sensitifnya dengan `auth_state/`.

- Gateway menghapusnya otomatis setelah sesi baru tersambung stabil selama 60 detik.
- Bila gateway tidak pernah tersambung stabil, hapus manual di folder gateway setelah sesi baru
  berfungsi: `rm -rf auth_state.old-*` (di Docker: hapus di dalam volume `wa-auth`).
- Pastikan perangkat lama juga dilepas di ponsel (WhatsApp → Perangkat tertaut).
- Folder ini sudah masuk `.gitignore`; jangan ikut dicadangkan ke tempat yang tidak aman.

## 10. Memantau log dan batas pengiriman

Log: `pm2 logs kampusping-wa-gateway`, `pm2 logs kampusping-worker`, `pm2 logs kampusping-backend`
(di Docker: `docker compose logs -f worker api wa-gateway`).

- Log tidak memuat isi pesan, kunci API, rahasia webhook maupun nomor telepon lengkap. Nomor hanya
  tampil sebagai **empat digit terakhir**. Bila Anda melihat nomor lengkap di log, laporkan sebagai
  insiden privasi (UU PDP).
- Tanda sehat: worker mencatat ringkasan tiap menit (`Worker tick: created=… handled=…`); gateway
  mencatat koneksi dan jumlah pengiriman tanpa isi.
- **Jendela kirim:** pesan hanya dikirim pada **hari kerja** dan jam yang diatur di
  **Pengaturan → Jendela kirim** (bawaan Senin-Jumat 08:00-17:00 WIB, zona `APP_TIMEZONE`). Di luar
  itu worker menunggu; pesan yang jadwalnya jatuh di akhir pekan dikirim hari kerja berikutnya
  (selama belum lewat 3 hari).
- **Batas harian:** bawaan 200 pesan per hari kalender lokal. Setelah tercapai worker berhenti
  sampai hari berikutnya; sisanya tetap **Antre** (ingat kedaluwarsa 3 hari).
- **Jeda antar pesan:** acak 8-20 detik (bawaan), jadi 200 pesan memakan sekitar 30-70 menit.
- **Satu pesan otomatis per mahasiswa per hari.** Tagihan kedua milik mahasiswa yang sama menunggu
  hari kerja berikutnya.
- Dasbor menampilkan jumlah Pesan terkirim, Diterima, Dibaca, Gagal dan Antre.

## 11. Yang TIDAK terjadi otomatis

- **Hari libur nasional tidak dikenali.** Pesan tetap dikirim pada hari kerja yang jatuh di hari
  libur (**Hari kerja** di Pengaturan hanya mengenal hari dalam sepekan, bukan tanggal tertentu).
  Matikan pengiriman otomatis sendiri pada hari libur bila tidak ingin pesan keluar, dan hidupkan
  lagi sesudahnya.
- **Balasan mahasiswa belum ditangani** (milestone M3). Balasan ke nomor pengirim tidak dibaca oleh
  sistem. **Permintaan "STOP" belum diproses**: sistem belum menghentikan pesan ke mahasiswa yang
  membalas STOP. Pantau ponsel pengirim secara berkala dan tangani permintaan berhenti secara manual
  (misalnya koreksi nomor mahasiswa di menu Mahasiswa atau matikan pengiriman otomatis).
  Pengecualian keringanan/cicilan juga belum punya layar (M3).
- **Tidak ada kirim manual atau massal**, tidak ada ekspor Excel/PDF (M3).
- **Pembayaran setelah impor terakhir tidak terlihat.** Cek ulang sebelum kirim hanya melihat data
  impor terakhir; impor ulang sebelum tiap siklus penagihan.
- **Pemulihan sesi setelah penutupan final** (perangkat dilepas, 440, 403) tidak otomatis; perlu
  tindakan manusia (bagian 4).
- **Tanda terima** (Diterima/Dibaca) bisa hilang: antrean webhook di gateway ada di memori, dan
  tanda terima dibuang bila API terlalu lambat mencatat pengiriman. Akibatnya pesan tetap
  **Terkirim** padahal sudah sampai. Ini tidak berarti pesan tidak terkirim.
- **Cadangan dan pemulihan tidak otomatis.** Backup database (NFR-09) dan `auth_state/` harus
  dijadwalkan sendiri.

## 12. Kontak eskalasi

Isi oleh Bagian Keuangan dan IT sebelum dipakai:

| Peran | Nama | Kontak |
| --- | --- | --- |
| Penanggung jawab Bagian Keuangan (penyetuju) | | |
| Staf IT yang mengoperasikan server | | |
| Pengembang / pemelihara sistem | | |
| Pemegang ponsel dan nomor khusus WhatsApp | | |

Eskalasi segera bila: nomor diblokir, kode QR diminta berulang tanpa sebab, pesan terkirim ke
mahasiswa yang sudah lunas, pesan terkirim ganda, nomor lengkap muncul di log, atau `auth_state/`
mungkin diakses pihak lain (putuskan sesi dari ponsel, lalu Putuskan sesi di aplikasi).
