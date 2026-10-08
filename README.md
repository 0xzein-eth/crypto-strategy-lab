# Crypto Strategy Lab v8 — PAPER ONLY

![CI](https://github.com/0xzein-eth/crypto-strategy-lab/actions/workflows/ci.yml/badge.svg)

**Lab eksperimen strategi kripto otomatis, berjalan lewat GitHub Actions, tanpa transaksi riil.**

✅ [Hasil simulasi terakhir](data/report.json) · 📚 [Event ledger permanen](data/events/) · 📊 [Dashboard source](dashboard/index.html) · ⚙️ [Workflow otomatis](.github/workflows/lab.yml) · 🧪 [Pengujian](tests/)

## Status operasional

Eksekusi v8 pertama berhasil pada **8 Oktober 2026, pukul 10.18 WIB**, mencatat 6 eksperimen LAB-116–121 menggunakan snapshot **OKX USDT perpetual**; hash-chain ledger telah diverifikasi. Lihat [run pertama](https://github.com/0xzein-eth/crypto-strategy-lab/actions/runs/37722057618). Data terbaru selalu ada di `data/report.json`, bukan di teks README ini.

**Jadwal otomatis:** menit **13 dan 43 setiap jam**, menggunakan `schedule` GitHub Actions. Jadwal bersifat best effort; eksekusi dapat terlambat atau sesekali terlewat. Laptop pengguna tidak perlu menyala. Pada kondisi normal engine membuat hingga 6 kandidat baru per run (maksimum 10 bila parameter kode diubah), dengan batas **120 OPEN bersamaan**, **12 OPEN per aset**, tetapi **tanpa batas seumur hidup 80 record**. Ketika posisi jatuh tempo, penyelesaian dilakukan terlebih dahulu memakai snapshot segar; harga historis tidak dicari untuk menyamarkan keterlambatan.

## Struktur repository

| File | Fungsi |
|---|---|
| `engine.py` | Mesin prospektif event-sourcing v8; harga publik, buka/tutup simulasi, audit |
| `signals.py` | Hipotesis TP-v3, BR-v3, MR-v3, LS-v3, FB-v3 dengan OHLCV **15m confirmed** |
| `data/events/YYYY-MM.jsonl` | **Sumber kebenaran tunggal**: OPEN & CLOSE record **lengkap**, baris append-only, rantai SHA-256 |
| `data/report.json` | Seluruh statistik hasil observasi dan peringatan kualitas |
| `data/state.json` | Semua posisi OPEN dan 80 CLOSED terbaru untuk dashboard |
| `dashboard/index.html` | Dashboard mandiri yang membaca data publik langsung dari GitHub |
| `.github/workflows/lab.yml` | Pengambilan harga, tes, eksekusi, validasi, dan atomic Git commit |
| `.github/workflows/ci.yml` | Pengujian lokal-lingkungan runner otomatis |
| `lab.py`, `data/ledger.json` | **Legacy v7 (non-operasional)**; tidak dipakai v8 dan tidak boleh dihitung ganda |

Strategi berbasis candle aktif **hanya jika** data OHLCV dari **instrumen OKX perpetual yang sama** tersedia dan candle telah dikonfirmasi selesai. Jika tidak, mesin mencoba baseline BR-proxy, MR-proxy dan CTRL-v1, selalu diberi label sebagai hipotesis sederhana. Strategi yang tidak memenuhi sinyal tidak direkayasa.

## Sumber harga & aturan integritas

Prioritas data: Bybit linear → OKX USDT swap → Binance Futures → Kraken USD spot proxy → Coinbase USD spot proxy. Beberapa penyedia bisa memblokir runner GitHub berdasarkan wilayah; kode membedakan kesalahan HTTP 403/451 dan mencoba sumber alternatif. **Harga exit selalu harus dari provider, tipe pasar, dan instrumen yang sama dengan entry.** Spot proxy tidak pernah dihitung sebagai sampel valid untuk bukti edge perpetual.

- Simulasi `$10,000` notional per eksperimen, leverage hipotesis `3x`, fee `0,05%` per sisi.
- `normalized_R = (signed_return_pct − 0,10%) / research_risk_pct`. Risk denominator riset awal `1,5%`, **bukan stop-loss aktual**.
- Keterlambatan exit dihitung nyata; **lebih dari 30 menit** masuk kelompok `late_excluded`, bukan performa eligible tepat waktu.
- Jika harga tidak tersedia, trade tetap OPEN dan menjadi DUE/PENDING; tidak boleh di-backfill.
- Event OPEN/CLOSE yang sudah disimpan tidak diedit, disingkat, atau dihapus. Semua hash event diverifikasi setiap run.
- Perubahan merusak hash, hilangnya source-of-truth, atau ketidaksesuaian laporan menyebabkan `INTEGRITY_FAILURE` (fail-closed).
- Jika tak ada feed harga valid, workflow gagal dengan `DATA_UNAVAILABLE`, bukan sukses palsu.
- Arsip **LAB-074–115** dari scheduler lama **belum dimigrasi**: record asli lengkap belum direkonsiliasi. Statistiknya **tidak dicampur** dengan v8.

## Menjalankan dan memantau

Otomatisasi telah terpasang; untuk inspeksi buka [GitHub Actions](https://github.com/0xzein-eth/crypto-strategy-lab/actions) dan pilih **Continuous paper strategy lab**. Setiap run yang berhasil akan memperbarui [report](data/report.json) dan [individual events](data/events/). Run hijau tetap perlu dicek `added`, `provider_observations`, `closed_this_run`, `pending` agar tidak salah membaca kegiatan.

Untuk menjalankan secara lokal tanpa dependensi pihak ketiga:

```sh
python -m unittest discover -s tests -v
python engine.py --verify-only
python engine.py --count 6
```

Dashboard disimpan di `dashboard/index.html` dan dapat diperoleh sebagai artifact workflow `Validate dashboard`. **GitHub Pages belum dianggap aktif** sampai Pages dikonfigurasi/berhasil diterbitkan.

[Lihat metodologi & keterbatasan](METHODOLOGY.md) · [Lihat troubleshooting](RUNBOOK.md)

> **Penting:** Ini simulasi penelitian, bukan sistem trading real. Tidak ada API key exchange, order, wallet, deposit, atau posisi asli. Performa simulasi tidak memodelkan pendanaan variabel, slippage, spread, order fill dan likuidasi. **Tidak ada bukti strategi menguntungkan secara riil.**
