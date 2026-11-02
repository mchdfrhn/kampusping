# Uji manual KampusPing dengan ponsel sungguhan

Pengiriman lewat Baileys (gateway WhatsApp) **tidak bisa diuji otomatis**: tes otomatis memakai
gateway palsu. Dokumen ini adalah daftar periksa yang dijalankan **manusia** pada ponsel asli,
sebelum pengiriman otomatis dipakai untuk mahasiswa. Ulangi setiap kali gateway berubah (rencana M1
Task 19 langkah 5, ADR 0002).

> **PERINGATAN RISIKO DIBLOKIR.** Baileys adalah klien WhatsApp **tidak resmi** dan melanggar
> ketentuan WhatsApp. Nomor yang dipakai mengirim dapat **diblokir, bahkan permanen**. Karena itu uji
> ini **hanya** memakai **nomor khusus yang rela diambil risikonya**, dan pesan hanya dikirim ke
> **nomor ponsel Anda sendiri**. Jangan pernah memakai nomor utama kampus, dan jangan menjalankan
> uji ini dengan data mahasiswa sungguhan.

Perkiraan waktu: 45-60 menit. Catat hasil tiap langkah di [tabel hasil](#9-tabel-hasil-yang-dilaporkan-kembali).

## 0. Prasyarat

- [ ] **Nomor khusus pengirim** (kartu SIM + ponsel dengan WhatsApp aktif) yang boleh berisiko
      diblokir. Ponsel ini akan "menautkan" gateway sebagai perangkat.
- [ ] **Nomor ponsel pribadi Anda** sebagai "mahasiswa" uji (ponsel kedua, atau nomor lain). Pesan uji
      akan masuk ke sini. Pastikan nomor ini berbeda dari nomor pengirim.
- [ ] **Database uji terpisah.** Di bawah dipakai berkas SQLite sementara di luar repo. **JANGAN
      memakai database produksi** atau database jarak jauh. File `kampusping-backend/.env` Anda
      mungkin menunjuk ke database jarak jauh: semua perintah di bawah menimpa `DATABASE_URL`
      lewat variabel lingkungan, dan Anda harus memeriksanya (langkah 1.2) sebelum menjalankan apa pun.
- [ ] Python 3.11+ dengan virtualenv backend terpasang (`pip install -r requirements-dev.txt`), Node
      20.19+ dengan `npm install` di `kampusping-frontend` dan `kampusping-wa-gateway`.
- [ ] Akses internet untuk gateway (WhatsApp, dan satu panggilan ke GitHub untuk versi WhatsApp Web
      kecuali `WA_FETCH_WA_VERSION=false`).
- [ ] Port bebas: contoh di bawah memakai API `8100`, web `3100`, gateway `8095`. Bila Anda punya
      `npm run dev` atau `uvicorn --reload` yang sedang berjalan di 3000/8000, biarkan saja, tetapi
      jangan membuka aplikasi itu untuk uji ini (mungkin tersambung ke data sungguhan).
- [ ] Dua rahasia acak (16+ karakter), mis. `openssl rand -hex 32` dua kali. Di bawah disebut
      `KUNCI_API` dan `RAHASIA_WEBHOOK`.

Perintah ditulis untuk PowerShell di Windows. Di Git Bash/Linux ganti `$env:NAMA="nilai"` dengan
`export NAMA=nilai`.

## 1. Siapkan dan jalankan semua bagian

Buka empat terminal. Gunakan **`localhost`** (bukan `127.0.0.1`) untuk web dan API agar cookie sesi
berfungsi.

### 1.1 Gateway (terminal 1)

```powershell
cd kampusping-wa-gateway
copy .env.example .env
# Ubah di .env (jangan commit):
#   WA_GATEWAY_API_KEY=KUNCI_API
#   WA_WEBHOOK_SECRET=RAHASIA_WEBHOOK
#   WA_WEBHOOK_URL=http://127.0.0.1:8100/api/v1/webhooks/whatsapp
npm install
npm run dev
```

Gateway menolak nilai kosong, pendek, atau berawalan `change-me`. Biarkan terminal ini terbuka.

### 1.2 Variabel lingkungan backend (terminal 2, 3 dan 4 yang memakai backend)

Setiap terminal backend (API dan worker) harus memakai **nilai yang sama**. Siapkan satu blok yang
Anda tempel di tiap terminal (ganti `KUNCI_API` dan `RAHASIA_WEBHOOK`):

```powershell
cd kampusping-backend
.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force C:\tmp | Out-Null
$env:DATABASE_ENGINE="sqlite"
$env:DATABASE_URL="sqlite+aiosqlite:///C:/tmp/kampusping-smoke.db"
$env:BACKEND_CORS_ORIGINS="http://localhost:3100"
$env:INITIAL_ADMIN_EMAIL="admin@example.com"
$env:INITIAL_ADMIN_PASSWORD="UjiCoba-Kampus-123"
$env:WA_PROVIDER="gateway"
$env:WA_GATEWAY_URL="http://127.0.0.1:8095"
$env:WA_GATEWAY_API_KEY="KUNCI_API"
$env:WA_WEBHOOK_SECRET="RAHASIA_WEBHOOK"
# Pemeriksaan wajib: harus mencetak sqlite, bukan alamat server
python -c "from app.core.config import settings; print(settings.database_engine.value, settings.database_url)"
```

Keluaran harus `sqlite sqlite+aiosqlite:///C:/tmp/kampusping-smoke.db`. **Bila bukan, berhenti.**

### 1.3 Migrasi dan API (terminal 2)

```powershell
python -m alembic upgrade head
python -m app.cli create-admin
python -m uvicorn app.main:app --port 8100 --host localhost
```

`create-admin` juga mengisi peran, dua template contoh, dan enam aturan jadwal (H-7 sampai H+7).
Biarkan terminal ini terbuka.

### 1.4 Aplikasi web (terminal 3)

```powershell
cd kampusping-frontend
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8100/api/v1"
npm run build
npm start -- -p 3100
```

(`npm run dev` bisa dipakai, tetapi Next.js menolak dua server dev di folder yang sama; jika `npm run
dev` Anda sendiri masih berjalan, pakai `build` + `start` seperti di atas.) Buka
<http://localhost:3100> dan masuk dengan `admin@example.com` / `UjiCoba-Kampus-123`.

- [ ] Halaman web terbuka dan Anda berhasil masuk (mendarat di **Dasbor**).

### 1.5 Terminal 4 (worker)

Siapkan blok variabel di 1.2 di terminal ini. **Jangan** menjalankan worker dulu.

## 2. Tautkan nomor khusus (QR)

1. Di web: **Pengaturan → Koneksi WhatsApp**. Status harus **Menunggu pemindaian** dan kode QR tampil.
   Bila tertulis "Tidak dapat memuat status WhatsApp", periksa kunci/rahasia di gateway dan backend.
2. Di ponsel **pengirim**: **WhatsApp → Perangkat tertaut → Tautkan perangkat**, pindai kode QR.
3. Status berubah ke **Menyambungkan…** lalu **Terhubung**.

- [ ] Status **Terhubung** dan perangkat tertaut tampil di ponsel pengirim.

Jangan memindai berulang-ulang. Bila gagal beberapa kali, tunggu beberapa menit (lihat
[runbook](runbook-whatsapp.md)).

## 3. Isi pengaturan dan impor dua tagihan uji

1. **Pengaturan**: isi **Nama kampus** ("Kampus Uji"), **Kontak keuangan** (mis. nomor Anda),
   **Tautan pembayaran SIAKAD/Civitas** (mis. `https://contoh.ac.id/bayar`). **Simpan pengaturan**.
2. Buat berkas `uji-tagihan.csv`. Ganti `0812XXXXXXXX` dengan **nomor ponsel pribadi Anda** (bukan
   nomor pengirim), dan `BESOK` dengan **tanggal besok** (format `YYYY-MM-DD`) serta `KEMARIN` dengan
   tanggal kemarin:

   ```csv
   NIM,Nama,Prodi,Angkatan,No WA,Kode Tagihan,Nominal,Jatuh Tempo,Status,Tanggal Bayar,Kanal Pembayaran,Semester
   UJI0001,Uji Belum Lunas,Uji Coba,2024,0812XXXXXXXX,UJI-INV-0001,1500000,BESOK,Belum lunas,,,Uji 2026
   UJI0002,Uji Sudah Lunas,Uji Coba,2024,0812XXXXXXXX,UJI-INV-0002,1500000,BESOK,Lunas,KEMARIN,siakad,Uji 2026
   ```

   Dua mahasiswa memakai nomor yang sama (nomor tidak harus unik). Hanya yang **belum lunas**
   boleh menerima pesan.
3. **Impor Data**: pilih sumber **SIAKAD**, pilih berkas, **Unggah dan pratinjau**. Pratinjau harus menunjukkan 2
   baris valid, 0 galat, 2 mahasiswa baru, 2 tagihan baru.
4. Tekan **Terapkan**.
5. Periksa **Mahasiswa** (dua baris, nomor tampil sebagai `+62…`, status nomor Valid) dan **Tagihan**
   (UJI-INV-0001 Belum lunas, UJI-INV-0002 Lunas).

- [ ] Pratinjau 2 valid / 0 galat; setelah Terapkan, 2 mahasiswa dan 2 tagihan tampil dengan status benar.

## 4. Periksa template dan jadwal

1. **Template Pesan**: ada "Pengingat sebelum jatuh tempo" dan "Tunggakan setelah jatuh tempo". Buka
   salah satu, lihat pratinjau. (Footer "Balas STOP untuk berhenti." ditambahkan otomatis saat
   pesan dibuat dan tidak tampil di editor.)
2. **Jadwal**: enam aturan H-7, H-3, H-1, H, H+3, H+7, semuanya aktif.

- [ ] Template dan keenam aturan ada dan aktif.

## 5. Atur jendela kirim agar mencakup waktu sekarang

Pengiriman hanya berjalan di dalam jendela kirim (bawaan Senin-Jumat 08:00-17:00 WIB).

1. **Pengaturan → Jendela kirim**. **Catat nilai asli** (Jam mulai ____, Jam selesai ____, hari kerja
   ____) di tabel hasil.
2. Ubah **Jam mulai** menjadi sebelum jam sekarang, **Jam selesai** menjadi sesudah jam sekarang
   (selisih minimal 1 jam), dan pastikan **hari ini** tercentang di **Hari kerja**. Simpan.

- [ ] Jendela kirim mencakup waktu sekarang. **Nilai asli sudah dicatat dan akan dikembalikan di bagian 8.**

## 6. Aktifkan pengiriman otomatis (hati-hati)

> Dari titik ini sistem dapat benar-benar mengirim WhatsApp lewat nomor khusus. Pastikan database
> hanya berisi dua mahasiswa uji di atas.

1. **Pengaturan → Pengiriman otomatis**: nyalakan. Dialog "Aktifkan pengiriman otomatis?" menjelaskan
   risiko diblokir. Tekan **Aktifkan pengiriman otomatis**, lalu **Simpan pengaturan**.
2. Pastikan status WhatsApp masih **Terhubung**.

## 7. Jalankan worker dan periksa hasil

Di terminal 4 (blok variabel 1.2 sudah ditempel):

```powershell
python -m app.cli run-worker --once
```

Perintah berjalan satu putaran lalu keluar. Karena ada jeda acak 8-20 detik setelah mengirim, perintah
bisa memakan sampai sekitar 20 detik. Keluaran yang diharapkan:

```text
Worker tick done: created=2 expired=0 superseded=1 escalated=0 handled=1
```

(`created=2`: dua aturan jadwal untuk tagihan belum lunas yang jatuh tempo besok; `superseded=1`:
hanya aturan terbaru yang dikirim; `handled=1`: satu pesan dikirim. Angka `created` dan
`superseded` bisa berbeda sedikit bila Anda memakai tanggal jatuh tempo lain; yang penting
`handled=1`. Keluar kode 1 dan teks "failed" berarti ada galat, lihat log.)

Hasil yang diharapkan:

- [ ] **Ponsel pribadi Anda menerima satu pesan** dari nomor pengirim, berisi: "Selamat siang, Uji Belum
      Lunas (NIM UJI0001)…", nominal `Rp1.500.000`, tanggal jatuh tempo ditulis dalam bahasa Indonesia,
      tautan pembayaran, dan di baris terakhir **"Balas STOP untuk berhenti."**
- [ ] **Tidak ada pesan** untuk tagihan UJI-INV-0002 yang sudah lunas.
- [ ] Di web **Pengiriman**: satu pesan berstatus **Terkirim** (lalu **Diterima**, lalu **Dibaca**
      setelah Anda membukanya di ponsel; segarkan halaman; tanda terima bisa tertunda beberapa
      detik, dan "Dibaca" hanya muncul bila konfirmasi baca aktif di ponsel penerima). Pesan aturan
      lain untuk tagihan itu berstatus **Dibatalkan** dengan alasan "Digantikan pesan yang lebih
      baru". Tidak ada baris untuk tagihan lunas.
- [ ] Di **Dasbor**: Total tagihan 2, Lunas 1, Belum lunas 1, Tunggakan 0, Pesan terkirim 1,
      Antre 0 (Diterima dan Dibaca tampil sebagai persentase dari pesan terkirim, mis. 100%).

### 7.1 Uji ketahanan

1. **Worker lagi.** Jalankan `python -m app.cli run-worker --once` sekali lagi.
   - [ ] Keluaran `created=0 … handled=0`; **tidak ada pesan kedua** di ponsel; **Pengiriman**
         tidak bertambah baris terkirim.
2. **Restart gateway lalu worker.** Hentikan gateway (Ctrl+C di terminal 1) dan jalankan lagi
   (`npm run dev`). Sesi dipulihkan dari folder `auth_state` tanpa QR baru; tunggu status
   **Terhubung**. Lalu jalankan worker `--once`.
   - [ ] Status kembali **Terhubung** tanpa memindai ulang; worker `handled=0`; ponsel tidak menerima
         pesan ganda.
   - [ ] *(Opsional, untuk IT)* Uji pencegah kirim ganda: pada database **uji** itu, kembalikan pesan
         terkirim ke antre dengan `UPDATE messages SET status='queued', sent_at=NULL, attempts=0
         WHERE provider_message_id IS NOT NULL;` (mis. lewat `sqlite3 C:/tmp/kampusping-smoke.db`),
         lalu jalankan worker `--once`. Gateway harus menjawab dengan id lama tanpa mengirim
         lagi: ponsel **tidak** menerima pesan kedua dan pesan kembali **Terkirim**. (Langkah SQL ini
         belum pernah dijalankan oleh penyusun dokumen; jika hasilnya berbeda, laporkan.)
3. **Cabut perangkat tertaut di ponsel.** Di ponsel pengirim: **WhatsApp → Perangkat tertaut** →
   pilih perangkat KampusPing → **Keluar**. Di web segarkan **Pengaturan**.
   - [ ] Status menjadi **Terputus** (dalam beberapa detik sampai semenit) dan tidak kembali sendiri.
   - Impor satu tagihan belum lunas lagi (mis. UJI0003, nomor Anda, jatuh tempo besok), jalankan
     worker `--once`.
   - [ ] Worker `handled=0`, ponsel tidak menerima pesan baru, dan pesan baru berstatus **Antre** di
         **Pengiriman** (tidak terkirim dan tidak ada galat).
4. **Tombol Putuskan sesi.** Di **Pengaturan → Koneksi WhatsApp** tekan **Putuskan sesi** dan
   konfirmasi.
   - [ ] Muncul "Sesi WhatsApp diputus." dan status menjadi **Menunggu pemindaian** dengan kode QR baru.
   - Bila Anda ingin melanjutkan uji pesan, pindai QR itu lagi (ulangi bagian 2) dan jalankan worker
     `--once` sekali untuk melihat pesan Antre terkirim.

## 8. Pemulihan dan pembersihan

- [ ] **Matikan pengiriman otomatis**: Pengaturan → Pengiriman otomatis dimatikan → Simpan.
- [ ] **Kembalikan jendela kirim** ke nilai asli yang Anda catat di bagian 5 → Simpan.
- [ ] **Putuskan sesi** dari Pengaturan, lalu pastikan di ponsel pengirim tidak ada lagi perangkat
      KampusPing di **Perangkat tertaut**.
- [ ] Hentikan semua proses (gateway, API, web, worker) dengan Ctrl+C.
- [ ] Hapus salinan sesi lama di folder gateway: `kampusping-wa-gateway\auth_state.old-*` (berisi
      kredensial yang bisa masih hidup). Jika nomor khusus ini tidak akan dipakai produksi dari
      mesin ini, hapus juga `auth_state\` dan `data\` milik uji.
- [ ] Hapus data uji: berkas `C:\tmp\kampusping-smoke.db`, dan file `.env` gateway yang berisi
      rahasia uji bila tidak dipakai lagi. Hapus berkas `uji-tagihan.csv`.
- [ ] Bersihkan variabel lingkungan terminal (tutup terminalnya).
- [ ] Pastikan tidak ada mahasiswa uji yang tertinggal di database sungguhan (database sungguhan
      tidak pernah disentuh oleh uji ini).

## 9. Tabel hasil yang dilaporkan kembali

Salin tabel ini, isi, dan laporkan ke pengembang bersama keluaran `Worker tick done: …` dan potongan
log gateway/worker bila ada kegagalan (log tidak memuat nomor lengkap atau isi pesan).

| # | Langkah | Hasil (OK / Gagal) | Catatan (waktu, keluaran, tangkapan layar) |
| --- | --- | --- | --- |
| 1 | Semua bagian berjalan; pemeriksaan database uji mencetak `sqlite` | | |
| 2 | QR dipindai, status **Terhubung** | | |
| 3 | Impor 2 baris valid, Terapkan, data benar | | |
| 4 | Template dan 6 aturan ada | | |
| 5 | Jendela kirim diubah; nilai asli: mulai ____ selesai ____ hari ____ | | |
| 6 | Pengiriman otomatis diaktifkan (konfirmasi tampil) | | |
| 7a | Worker `--once`: keluaran persis | | |
| 7b | Ponsel menerima **1** pesan untuk yang belum lunas, ada footer STOP | | |
| 7c | **Tidak** ada pesan untuk yang lunas | | |
| 7d | Pengiriman: Terkirim → Diterima → Dibaca; aturan lain Dibatalkan (Digantikan) | | |
| 7e | Dasbor: Total 2 / Lunas 1 / Belum lunas 1 / Tunggakan 0 / Pesan terkirim 1 / Antre 0 | | |
| 8 | Worker kedua: tidak ada pesan ganda | | |
| 9 | Restart gateway lalu worker: tanpa QR baru, tidak ada ganda | | |
| 10 | Perangkat dicabut: **Terputus**, pesan baru tetap **Antre**, tidak terkirim | | |
| 11 | **Putuskan sesi**: QR baru muncul | | |
| 12 | Pembersihan selesai (pengiriman otomatis mati, jendela dikembalikan, sesi diputus, `auth_state.old-*` dihapus, data uji dihapus) | | |
| 13 | Apakah nomor pengirim mendapat peringatan/pembatasan dari WhatsApp selama uji? | | |

Hal lain yang perlu dilaporkan: pesan galat di layar, perbedaan antara yang diharapkan dan yang
terjadi, berapa lama tanda terima (Diterima/Dibaca) muncul, dan apakah ada nomor lengkap di log.

> Ingat: lulus uji ini tidak menghilangkan risiko blokir. Untuk pemakaian sungguhan, baca
> [runbook](runbook-whatsapp.md) (terutama bagian nomor diblokir dan yang tidak terjadi otomatis) dan
> tetap awasi ponsel pengirim.
