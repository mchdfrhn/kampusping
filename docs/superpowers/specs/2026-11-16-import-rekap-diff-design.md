# KampusPing: desain deteksi lunas dan tagihan baru pada impor Rekap Tunggakan

- Tanggal: 2026-11-16
- Status: disetujui (2026-11-16), belum diimplementasikan
- Kebutuhan induk: FR-01 di [`docs/BRD-penagihan-uang-kuliah-whatsapp.md`](../../BRD-penagihan-uang-kuliah-whatsapp.md); desain induk di [`2026-10-31-kampusping-design.md`](2026-10-31-kampusping-design.md); rollback impor di [`2026-11-10-import-rollback-design.md`](2026-11-10-import-rollback-design.md)
- Aturan bisnis yang tidak boleh melemah: AB-01 / FR-06 (hanya tagihan belum lunas yang ditagih; lunas bersifat sticky), AB-03, AB-05, NFR-07 (audit), NFR-08 (data hanya masuk lewat berkas)

## 1. Latar belakang dan tujuan

Staf Keuangan mengunggah **Laporan Rekap Tunggakan Mahasiswa** dari SIAKAD (xlsx). Laporan ini hanya berisi
mahasiswa yang **masih menunggak**; satu baris per mahasiswa per semester, nominal pada kolom *Rekap*.
Staf mengekspornya untuk **semua prodi dan semua kelas, satu semester, dengan filter Status = Aktif**.

Hasil penyelidikan (2026-11-16) atas impor ulang (file lama vs file "Update"):

1. Parser rekap (`_try_parse_siakad_rekap`) memberi semua baris status `belum lunas`. Lunas berarti
   mahasiswa **hilang dari file**, dan tidak ada kode yang membaca hilang sebagai lunas. Dari 226 tagihan
   2026/2027 Ganjil di file lama, 23 tidak ada di file Update dan tetap `unpaid`.
2. Preview hanya menampilkan angka. "Tagihan diperbarui" menghitung semua kode yang sudah ada, berubah
   atau tidak (206 padahal hanya 53 yang nominalnya berubah: 30 turun, 23 naik). Tidak ada daftar siapa yang baru, berubah
   atau diduga lunas, sehingga staf tidak bisa memeriksa sebelum Terapkan.
3. Aturan "mahasiswa yang menerima tagihan baru: tagihan lama yang belum lunas otomatis ditandai lunas"
   (`apply_rows`, `_predict`) salah untuk laporan tunggakan: tunggakan semester lama yang nyata ikut
   ditandai lunas. Pada data Anda, 2 dari 4 tagihan baru milik mahasiswa yang punya tunggakan semester
   lama (`TGK-202355079-20252`, `TGK-202311388-20252`).
4. Jatuh tempo diisi `date.today()` dan ditimpa di setiap impor ulang, sehingga jadwal H-7/H-3/H+3
   bergeser tiap impor.

**Tujuan.** Setelah mengimpor Rekap Tunggakan yang baru, staf melihat di preview (a) tagihan baru,
(b) tagihan yang nominalnya berubah, (c) tagihan yang **diduga lunas** karena hilang dari file, lalu
menyetujui daftar (c) sebelum Terapkan. Pengingat WhatsApp berhenti untuk yang disetujui lunas.

**Kriteria berhasil**
1. Impor file Update atas data dari file lama menampilkan 23 tagihan diduga lunas, 4 tagihan baru,
   53 nominal berubah dan 150 tidak berubah (angka dari dua berkas nyata; builder memverifikasi dengan fixture yang mirip).
2. Tagihan yang tidak dipilih staf tetap `unpaid`. Tidak ada yang ditandai lunas tanpa terlihat di preview.
3. Tunggakan semester lama tidak pernah ditandai lunas hanya karena mahasiswanya menerima tagihan baru.
4. Impor ulang tidak menggeser jatuh tempo tagihan yang sudah ada.
5. Rollback impor (`imports:rollback`) mengembalikan tagihan yang ditandai lunas lewat mekanisme ini.

## 2. Di luar cakupan (non-goal)

- Mengubah AB-01. Lunas tetap sticky: tagihan yang sudah `paid` tidak kembali `unpaid` oleh file.
- Mengganti cara staf mengunggah (tetap satu file xlsx/csv per impor, tanpa langkah unggah tambahan).
- Deteksi mahasiswa nonaktif secara otomatis (lihat batasan 6).
- Bagaimana planner memperlakukan tagihan yang jatuh temponya sama dengan tanggal impor (tunggakan
  sudah lewat tempo). Itu perilaku penjadwalan yang berbeda dan tidak disentuh di sini.
- Riwayat rincian setelah diterapkan. Daftar rincian dibuang setelah Terapkan/Batalkan seperti `rows`;
  jejaknya tinggal di `import_changes` dan audit.
- Format impor selain Rekap Tunggakan (perilakunya tidak berubah kecuali penghitungan di bagian 4.4).

**Anti-goal (kegagalan walau tampak berfungsi):** tagihan yang masih menunggak ditandai lunas tanpa
terlihat staf, atau pengingat berhenti karena ekspor yang tidak lengkap.

## 3. Pendekatan yang dipertimbangkan

- **A. Otomatis tanpa konfirmasi:** yang hilang dari file langsung lunas. Sederhana, tetapi mahasiswa
  nonaktif atau ekspor tidak lengkap langsung berhenti ditagih tanpa diketahui. Ditolak.
- **B. Diduga lunas ditinjau di preview (dipilih):** preview punya daftar Tagihan baru, Nominal
  berubah, Diduga lunas. Hanya yang dipilih staf saat Terapkan yang ditandai lunas.
- **C. Berkas lunas terpisah:** menambah pekerjaan padahal laporan tunggakan sudah cukup. Ditolak.

Keputusan: **B**, dipilih oleh pemilik produk.

## 4. Desain

### 4.1 Mengenali format rekap

`ParsedSheet` mendapat field `kind: Literal["standard", "rekap"]` (default `standard`).
`_try_parse_siakad_rekap` mengembalikan `kind="rekap"`. `ImportBatch` mendapat kolom `kind`
(`varchar(10)`, default `standard`). Semua aturan baru di bawah berlaku **hanya untuk `kind="rekap"`**,
kecuali 4.4.

Kode tagihan rekap tetap `TGK-{nim}-{semester}` (tidak berubah).

### 4.2 Menghitung kandidat diduga lunas (saat preview)

Kandidat = tagihan di database yang memenuhi semua:
- `deleted_at IS NULL` dan `status = unpaid`
- `invoice_code` berawalan `TGK-` (dibuat format rekap; tagihan dari format lain tidak disentuh)
- `semester` sama persis dengan salah satu semester yang **muncul di baris valid file** ini
- `invoice_code` tidak ada di kode file

Semester yang tidak ada di file tidak pernah menghasilkan kandidat (file Update hanya 2026/2027 Ganjil,
jadi tunggakan 2025/2026 dan sebelumnya aman).

**Peringatan ekspor tidak lengkap.** Jika kandidat lebih dari **30%** dari seluruh tagihan unpaid
berkriteria di atas (semester dalam file), `summary.incomplete_warning = 1`. Ambang adalah konstanta
backend (`INCOMPLETE_EXPORT_THRESHOLD = 0.30`), bukan pengaturan.

### 4.3 Rincian preview

Kolom baru `import_batches.details` (JSON, deferred, `none_as_null=True`, NULL setelah Terapkan/Batalkan
seperti `rows`). Isinya tiga daftar:

| Daftar | Isi per item |
| --- | --- |
| `new` | `invoice_code`, `nim`, `name`, `semester`, `amount` |
| `changed` | `invoice_id`, `invoice_code`, `nim`, `name`, `semester`, `fields` (mis. `amount: [lama, baru]`) |
| `suspected_paid` | `invoice_id`, `invoice_code`, `nim`, `name`, `study_program`, `semester`, `amount` |

Tanpa nomor telepon. `changed` dan `new` dibuat untuk semua format; `suspected_paid` hanya untuk rekap.

Endpoint baru `GET /api/v1/imports/{id}/details?category=new|changed|suspected_paid&page=&page_size=`
(permission `imports:read`, bentuk `{items, total, page, page_size}`). Batch non-preview mengembalikan 409
seperti operasi preview lain.

`summary` (angka) bertambah: `invoices_unchanged`, `paid_suspected`, `incomplete_warning`
(0/1). Arti baru `invoices_updated`: **hanya** tagihan yang ada dan benar-benar berubah (nominal,
jatuh tempo bila boleh berubah, semester, sumber, restore, atau menjadi lunas). Sisanya
`invoices_unchanged`. Preview dan apply memakai satu fungsi pembanding supaya angkanya sama.

### 4.4 Aturan apply

Perubahan pada `apply_rows` dan `build_preview`:

1. **Aturan supersede dimatikan untuk rekap.** `students_with_new_invoice` / `superseded_invoices`
   kosong bila batch `rekap`. Format standar tidak berubah.
2. **Jatuh tempo stabil.** Untuk rekap, `due_date` hanya diisi saat tagihan **dibuat** (nilai: tanggal
   hari ini zona `APP_TIMEZONE`, bukan `date.today()` server) dan tidak ditimpa pada tagihan yang sudah ada.
   Tagihan yang di-restore tetap diperlakukan sebagai baru.
3. **Tandai lunas terpilih.** `POST /imports/{id}/apply` menerima body opsional
   `{"mark_paid_invoice_ids": [int]}` (default kosong, artinya tidak ada yang ditandai lunas). Untuk
   tiap id yang ada di `details.suspected_paid`, tagihan yang **masih** aktif dan `unpaid` saat apply:
   `status=paid`, `paid_at=hari ini (APP_TIMEZONE)`, `paid_via=source batch`. Pesan antre ikut
   dibatalkan lewat `cancel_pending_messages_for_invoices(reason=CancelReason.PAID)`. Id di luar
   `suspected_paid`, atau tagihan yang berubah sejak preview, diabaikan (tidak error) dan tidak dihitung.
4. **Log perubahan.** Tagihan yang ditandai lunas di-`snapshot` sebelum diubah, jadi `ChangeRecorder` dan
   rollback bekerja tanpa perubahan di `rollback.py`.
5. `summary` setelah apply: `invoices_paid_by_absence` (jumlah yang benar-benar ditandai lunas), di samping
   hitungan yang ada.

Perubahan penghitungan `invoices_updated`/`invoices_unchanged` berlaku juga untuk format standar
(satu fungsi pembanding). Tes yang menegaskan hitungan lama diperbarui.

### 4.5 Migrasi

Revisi `011`: `import_batches.kind varchar(10) NOT NULL DEFAULT 'standard'` dan
`import_batches.details JSON NULL`. Batch lama menjadi `standard` dan `details` NULL; tidak perlu backfill.
Tidak ada permission baru (memakai `imports:read` dan `imports:create`).

### 4.6 Tampilan (frontend, `ImportPreview.tsx`)

Teks Indonesia, komponen `App*`, token tema. Sketsa untuk batch rekap:

```
Pratinjau impor
Laporan Rekap Tunggakan Mahasiswa - Update.xlsx · SIAKAD/Civitas · 16 Nov 2026

 Baris dibaca 207   Baris valid 207   Baris bermasalah 0   Mahasiswa baru 1
 Tagihan baru 4     Tagihan berubah 53  Tagihan tidak berubah 150  Diduga lunas 23

 [!] (hanya bila incomplete_warning) Lebih dari 30% tagihan semester ini hilang dari berkas.
     Kemungkinan ekspor tidak lengkap. Tidak ada yang dipilih; periksa daftar sebelum menandai lunas.

 [ Tagihan baru (4) ] [ Nominal berubah (53) ] [ Diduga lunas (23) ] [ Masalah (0) ]
 ┌──┬─────────────┬──────────────┬──────────────────┬──────────────┐
 │☑ │ NIM         │ Nama         │ Semester         │ Nominal      │
 │☑ │ 202311388   │ HENDDY ...   │ 2026/2027 Ganjil │ Rp 1.412.000 │
 └──┴─────────────┴──────────────┴──────────────────┴──────────────┘
 Dipilih 23 dari 23 · [Pilih semua] [Kosongkan]
                                              [Batalkan]  [Terapkan]
```

- Tab "Diduga lunas" punya kotak centang; **default semua terpilih**, kecuali `incomplete_warning`
  (default tidak ada yang terpilih). Pilihan bertahan lintas halaman dan lintas tab.
- Teks info `Alert` diganti untuk rekap: "Tagihan yang hilang dari berkas ditampilkan sebagai Diduga lunas
  dan hanya ditandai lunas bila dipilih. Tunggakan semester yang tidak ada di berkas tidak diubah."
  Format standar tetap memakai teks lama (tanpa kalimat supersede untuk rekap).
- Dialog konfirmasi Terapkan menyebut jumlah yang akan ditandai lunas.
- Tab Masalah memakai tabel yang sekarang. Tab tanpa isi menampilkan empty state eksplisit
  ("Tidak ada tagihan baru"), bukan grid kosong.
- Tab rincian diambil dari `GET /imports/{id}/details`; pilihan dikirim sebagai `mark_paid_invoice_ids`.
  Tipe di `types.ts` dan `import.service.ts` ditambah.

## 5. Batasan yang diketahui

1. Mahasiswa nonaktif ikut hilang dari file berfilter Aktif, jadi muncul di Diduga lunas. Staf melihat
   nama dan prodi di daftar dan melepas centang yang tidak sesuai. Tidak ada deteksi otomatis.
2. Lunas sticky: tagihan yang terlanjur ditandai lunas keliru tidak kembali `unpaid` lewat impor berikutnya.
   Jalan keluarnya: **Rollback Impor** (hanya impor terbaru, admin) atau ubah status manual di halaman Tagihan.
3. Penanda lunas ini hanya sebaik laporan terakhir (sama seperti batasan "payments after the last import").
4. Ambang 30% adalah tebakan awal; sesuaikan dari pengalaman nyata.
5. Pembaruan `CLAUDE.md` (daftar tabel/migrasi dan status) dilakukan bersama implementasi.

## 6. Rencana pengujian

Backend (`pytest`, `WA_PROVIDER=fake`, SQLite di luar repo, jam disuntikkan):
- Parser mengembalikan `kind="rekap"`; file standar `standard`.
- Preview rekap: tagihan baru / berubah / tidak berubah / diduga lunas dihitung benar, termasuk daftar
  `details`; hanya semester yang ada di file; hanya kode `TGK-`; tagihan paid, deleted, atau format lain
  tidak jadi kandidat.
- `incomplete_warning` di atas dan di bawah ambang.
- Supersede mati untuk rekap (mahasiswa dengan tunggakan lama + tagihan baru: tunggakan lama tetap unpaid)
  dan tetap berlaku untuk format standar.
- Jatuh tempo tidak ditimpa pada impor ulang; tagihan baru memakai tanggal `APP_TIMEZONE`.
- Apply dengan `mark_paid_invoice_ids`: hanya yang dipilih menjadi lunas, pesan antre dibatalkan,
  id tak dikenal / sudah berubah diabaikan, tanpa daftar tidak ada yang lunas; audit dan `import_changes` ada.
- Rollback mengembalikan tagihan yang ditandai lunas; 401/403 untuk endpoint `details`.
- Skenario data nyata: dua fixture (lama 226 tagihan 2026/2027 + tunggakan lama, update 207) menghasilkan
  23 diduga lunas / 4 baru / 53 berubah / 150 tidak berubah.
- Tes lama yang menegaskan arti lama `invoices_updated` dan `SUMMARY_KEYS` diperbarui.

Frontend (Vitest): render tab, empty state, pilihan default (termasuk mode peringatan), pilihan lintas
halaman, body `mark_paid_invoice_ids`, teks konfirmasi. E2E (`WA_PROVIDER=fake`): impor rekap dua kali,
terapkan dengan sebagian dipilih.

## 7. Diserahkan ke builder

- Bentuk grid pilihan lintas halaman (server atau client pagination) dan nama komponen.
- Struktur modul untuk fungsi pembanding tagihan (satu fungsi untuk preview dan apply).
- Ukuran batas `details` untuk 20.000 baris (JSON di satu kolom dipilih agar sederhana; pindah ke tabel
  bila terlalu lambat).
- Teks Indonesia final untuk label dan empty state, mengikuti gaya UI yang ada.

## 8. Keputusan yang saya ambil sendiri (periksa saat membaca)

- Kandidat dibatasi pada kode berawalan `TGK-` dan semester yang ada di file.
- Ambang peringatan 30%, dan pilihan default kosong saat peringatan aktif.
- Pilihan dikirim sebagai daftar id yang disertakan (bukan daftar yang dikecualikan), supaya lupa mengirim
  berarti tidak ada yang ditandai lunas.
- `details` disimpan sebagai kolom JSON di batch, bukan tabel baru.
- `invoices_updated` berubah arti untuk semua format (hanya yang benar-benar berubah).
- Jatuh tempo baru memakai tanggal `APP_TIMEZONE`, bukan `date.today()` server.
