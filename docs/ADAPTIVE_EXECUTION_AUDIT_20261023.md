# Audit pelaksanaan roadmap — 23 Oktober 2026

Audit mencakup roadmap/issue GitHub, implementasi lokal sebelumnya, perubahan
upstream sampai `f2bd138261cf1d115a579512912d52d547ceb732`, serta epoch adaptif
baru. [Rencana kasta dan retest](CRYPTO_ADAPTIVE_RESEARCH_PLAN.md) menjelaskan
aturan yang didaftarkan sebelum klasifikasi. Semua tetap SHADOW/PAPER ONLY.

## Hasil nyata, bukan proyeksi

- API publik OKX berhasil untuk **16 instrumen**, 128 candle 15m confirmed
  per capture, bid/ask/depth yang dikonversi dari kontrak dengan ctVal, dan
  settled funding. Tidak ada kegagalan sumber pada capture pertama.
- Penyimpanan terpisah `adaptive_history/`: **301.606 candle asli**, sekitar
  129,58–129,59 hari untuk 13 instrumen dan 485,70 hari BTC/ETH/SOL. Batch
  pertama menambah 300 candle lebih tua per instrumen. Gzip total sekitar
  4,99 MB. Target 730 hari belum tercapai; funding lama tidak dipalsukan.
- Historical screen menguji **144 hipotesis** pada tiga blok 14 hari dan
  menghitung **265.224 hasil hipotetis**. Semua memiliki funding yang
  dapat diperiksa pada jendela yang dipakai. Angka ini trade berkolerasi,
  bukan 265.224 observasi independen, bukan PnL rekening.
- Epoch prospektif terpisah merekam satu observasi autentik, membuka
  **32 pasangan shadow** (8 eksplorasi + 24 prioritas), dan lolos replay.
  Pemanggilan ulang pada slot sama menghasilkan `SLOT_ALREADY_OBSERVED`.
  Belum ada CLOSED atau blok prospektif selesai; **144 hipotesis aktif
  masih WARMUP**, 30 keturunan cadangan belum diaktifkan. Tidak ada kasta
  tinggi atau calon pemenang yang dikarang dari backtest.

## Temuan yang diperbaiki

1. Konflik namespace quality API disatukan dengan modul upstream
   `research_quality.legacy_quality`; alias kompatibilitas tetap tersedia.
2. Entry saham v2 menggunakan modal/drawdown/volume sesi sebelumnya,
   tidak memakai CLOSE atau volume yang baru diketahui setelah OPEN.
   Kebijakan replay v1 dipertahankan untuk event lama.
3. Verifikasi saham mencocokkan report **dan** equity curve dengan sumber,
   menolak file hilang/berbeda. Timestamp, OHLCV, expiry dan downgrade
   kebijakan diperiksa. Observasi baru append-only dengan fsync.
4. Jalur eksplorasi memiliki non-overlap terpisah dari prioritas. Posisi
   prioritas tidak dapat memblokir sampel untuk menentukan kasta.
5. Funding pada epoch baru memakai jadwal teramati sebelum entry dan
   memeriksa semua settlement yang diharapkan. Pembayaran hilang, interval
   berubah atau histori jadwal kurang menghasilkan UNKNOWN, bukan nol.
   Model tetap constant-notional dan belum merupakan akun bursa.
6. Exit liquidity dihitung dari kuantitas asli saat entry, bukan sekadar
   notional 200 USDT dibagi harga exit yang bisa memberi ukuran keliru.
7. Kalender statistik memeriksa tanggal valid dan cluster UTC; NaN,
   boolean threshold, fractional/negative trade counts ditolak. Composite
   saham memveto EXIT yang berlawanan meskipun dua komponen BUY.
8. Dashboard memisahkan allocator v8 dari kasta adaptif, menampilkan
   WARMUP/tinggi/sedang/rendah, sampel eksplorasi, retest, sumber gagal,
   data stale dan kebutuhan review. Missing report tidak diartikan sukses.
9. CI/Actions mencakup modul baru, diagnostik forensik, audit readiness,
   pengambilan slot 15m, historical refresh dua kali sehari, dan artifacts.
   Jadwal baru aktif setelah kode masuk default branch; bukan SLA uptime.

## Bukti pengujian

- **416 tes lokal lulus**, termasuk counterexample no-lookahead,
  funding hilang/berubah, klasifikasi minimum, tiga/five retest, repeated
  checkpoint, multiple testing, priority/exploration separation, child
  activation tanpa inherited results, integritas journal dan report.
- Audit readiness memverifikasi v8, v2, Nasdaq, LQ45, warehouse dan epoch
  adaptif. Forensics fee/PnL dan composite diagnostics dijalankan.
- Script dashboard lolos `node --check` dan functional rendering dengan
  report asli (144 baris aktif) serta fallback saat report tidak tersedia.
- YAML workflow diparse, shell persistence lolos `bash -n`, dan
  `git diff --check` berhasil. Ini bukti lokal; CI GitHub dinilai terpisah.
- Sebelum mengintegrasikan data upstream, **76 berkas evidence awal identik
  SHA256**. Seluruh **19 jurnal awal** telah dipastikan merupakan awalan
  identik jurnal fetched main. Observasi upstream yang lebih baru tidak
  mengganti event lama; original baseline tetap dapat dipulihkan dari Git.

## Status roadmap yang masih memerlukan bukti

| Kebutuhan | Status dan tindakan berikutnya |
|---|---|
| Tiga kasta adaptif | Implementasi dan fixture lulus; klasifikasi nyata menunggu >=3 blok 14 hari valid dan minimum sampel |
| Calon review peluang tinggi | Perlu >=5 blok positif dan gate; tidak otomatis masuk wallet/live |
| Parent rugi berkepanjangan | Diagnosis otomatis setelah >=28 hari kasta rendah; aktivasi maksimal 30 resep anak baru yang didaftarkan |
| Issue #65 | First tick/26-arm plumbing tersedia; syarat >=48 slot nyata dan cakupan >=2 hari harus dinilai dari jurnal, jangan menutup issue dari fixture |
| Issue #55 | Harga >365 hari terbukti untuk subset 3 aset; target730/funding lengkap masih bertahap |
| Scheduler | Best effort; cakupan crypto lama di bawah target, tidak memalsukan slot yang hilang |
| LQ45 | Membership lama berhenti setelah 30 Okt; butuh sumber snapshot efektif berikutnya |
| Trial v2 | Tetap dibekukan sampai 19 Jan 2027 UTC dan exit terakhir; tidak diubah menjadi allocator adaptif |
| Kalender/corporate actions/impact | Masih memerlukan data dan model yang dapat direkonsiliasi; belum ada klaim return sesudah seluruh biaya riil |
| Storage dan kuota Actions | Review mingguan; pindahkan raw capture ke object storage/checkpoint tervalidasi sebelum ukuran/replay melampaui budget runner |

**Reproduksi** dari checkout Python 3.12:

```bash
python -m unittest discover -s tests -v
python -m adaptive_lab.engine --verify-only
python -m research_quality.readiness --output /tmp/roadmap-readiness.json
python -m research_quality.crypto_forensics --output /tmp/crypto-forensics.json
# Permintaan eksplisit pengambilan data nyata:
python -m adaptive_lab.engine --observe
python -m adaptive_lab.history --refresh --pages 5 --screen
```

Perubahan kode epoch adaptif yang memengaruhi fingerprint harus memakai
registrasi/path epoch baru. Jangan mengubah hash lama agar verifikasi lewat.
Tidak ada strategi yang saat ini dibuktikan memberi profit trading nyata.
