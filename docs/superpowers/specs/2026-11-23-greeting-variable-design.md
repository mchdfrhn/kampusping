# Variabel `{{salam}}` mengikuti jam kirim

Status: disetujui 2026-11-23 (ukuran: perubahan kecil).

## Maksud

Staf ingin template penagihan bisa membuka pesan dengan "Selamat pagi/siang/sore" yang sesuai
dengan jam pesan **benar-benar terkirim**, supaya pesan terasa wajar dan sopan (AB-08).

## Tujuan / bukan tujuan

- Tujuan: variabel baru `{{salam}}` di template pesan (otomatis dan Kirim Manual).
- Tujuan: teks salam ditentukan dari jam kirim dalam `APP_TIMEZONE` (WIB), bukan jam perencanaan.
- Tujuan: Log Pengiriman menampilkan teks persis seperti yang diterima mahasiswa.
- Bukan tujuan: merender ulang variabel lain saat kirim; salam yang bisa diatur staf.
- Anti-tujuan: mahasiswa menerima `{{salam}}` mentah, atau salam yang salah waktu.

## Kendala

- `messages.body` dirender saat perencanaan dan disimpan; pesan bisa menunggu berjam-jam
  (throttle, batas harian, jendela kirim) sebelum terkirim.
- Jam diinjeksi (tes tidak bergantung jam sistem).

## Pendekatan

1. **Placeholder ditunda, diisi di sender (dipilih).** Saat perencanaan/Kirim Manual `{{salam}}`
   dibiarkan di `body`; sender menggantinya tepat sebelum `provider.send` memakai `now` langkah itu
   dan menyimpan teks final ke `body`. Perubahan kecil, kontrak "dirender saat planning" tetap
   berlaku untuk variabel lain.
2. Render ulang seluruh body saat kirim: mengubah kontrak untuk semua variabel padahal hanya salam
   yang bergantung waktu kirim; data tagihan bisa berubah antara rencana dan kirim.
3. Isi salam saat perencanaan: salah ketika pesan tertunda. Ditolak.

## Rincian

- Jam lokal: pagi `< 11:00`, siang `11:00–14:59`, sore `15:00–17:59`, malam `>= 18:00`.
  Teks: "Selamat pagi", "Selamat siang", "Selamat sore", "Selamat malam" (EYD).
- Pratinjau template memakai contoh "Selamat pagi".
- Teks final yang terkirim disimpan ke `messages.body` dalam transaksi pencatatan hasil kirim
  (keputusan builder: boleh juga saat klaim, asalkan yang dikirim = yang tersimpan).
- Frontend: tambahkan `salam` ke daftar variabel template.
- Tes: batas 10:59/11:00, 14:59/15:00, 17:59/18:00; pesan direncanakan pagi lalu terkirim sore.
