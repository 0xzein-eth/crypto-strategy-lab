# Crypto Strategy Lab v8 — PAPER ONLY

![CI](https://github.com/0xzein-eth/crypto-strategy-lab/actions/workflows/ci.yml/badge.svg)

**Lab eksperimen strategi kripto otomatis, berjalan lewat GitHub Actions, tanpa transaksi riil.**

✅ [Hasil simulasi terakhir](data/report.json) · 📚 [Event ledger permanen](data/events/) · 📊 [Dashboard source](dashboard/index.html) · ⚙️ [Workflow otomatis](.github/workflows/lab.yml) · 🧪 [Pengujian](tests/)

## Status operasional

Eksekusi v8 pertama berhasil pada **8 Oktober 2026, pukul 10.18 WIB**, mencatat 6 eksperimen LAB-116–121 menggunakan snapshot **OKX USDT perpetual**; hash-chain ledger telah diverifikasi. Lihat [run pertama](https://github.com/0xzein-eth/crypto-strategy-lab/actions/runs/37722057618). Data terbaru selalu ada di `data/report.json`, bukan di teks README ini.

**Jadwal otomatis:** menit **07, 22, 37, dan 52 setiap jam** (setiap 15 menit), menggunakan `schedule` GitHub Actions. Jadwal bersifat best effort; eksekusi dapat terlambat atau sesekali terlewat. Laptop pengguna tidak perlu menyala. Pada kondisi normal engine mengupayakan hingga 14 eksperimen baru per run (hard cap 24), dengan batas **850 OPEN bersamaan**, **50 OPEN per aset** dan **1.400 OPEN baru per hari UTC**, tetapi **tanpa batas seumur hidup 80 record**. Ketika posisi jatuh tempo, penyelesaian dilakukan terlebih dahulu memakai snapshot segar; harga historis tidak dicari untuk menyamarkan keterlambatan.

## Struktur repository

| File | Fungsi |
|---|---|
| `engine.py` | Mesin prospektif event-sourcing v8; harga publik, buka/tutup simulasi, audit |
| `signals.py` | 11 aturan berbasis OHLCV 15 menit yang telah dikonfirmasi, termasuk RSI/SMA/VWAP |
| `learner.py` | Alokasi eksperimen dan kelompok kontrol, pemantauan berbasis hari |
| `universe.py` | Katalog 38 aset dengan strata sektor/arah/volatilitas; aset tanpa kontrak terverifikasi dilewati |
| `friction.py` | Skenario spread/impact hipotesis yang disimpan pada eksperimen baru |
| `data/events/YYYY-MM.jsonl or YYYY-MM_daily_DD.jsonl` | **Sumber kebenaran tunggal**: OPEN & CLOSE record **lengkap**, baris append-only, rantai SHA-256 |
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

## Adaptive continuous research (v1)

The lab now scores a frozen set of **14 auditable paper-only strategy hypotheses** and continuously reallocates *future* experiments. The learner excludes late closes and spot proxies, retains precommitted controls, evaluates day-cluster lower bounds, and maintains a reproducible date-partitioned monitoring sample. Until strict training/monitoring/control thresholds are met, **no strategy is provisionally preferred**. A provisional leader is not proof of profitability. New signal families are versioned rather than generated through unreviewed arbitrary code.

- [Read the learning design](LEARNING.md)
- Dashboard now displays adaptive arm evidence, monitoring samples and provisional status.
- Normal target: **14 new experiments per scheduled run** (hard max 24; 850 OPEN overall; 50 OPEN per symbol; UTC day cap 1,400), if source and strategy filters allow.
- [Read-only health watchdog](.github/workflows/health.yml) checks event integrity every two hours and whether updates are more than 2.5 hours old. Liveness cannot be guaranteed when GitHub Actions or exchanges are unavailable.

## Peningkatan kapasitas dan kualitas sampel (Oktober 2026)

- **38 pasar kandidat** lintas kelompok aset; sistem hanya menerima harga dari instrumen yang sungguh tersedia, tidak menciptakan harga atau memaksa aset tidak terdaftar.
- **4 pemindaian per jam** secara best-effort (sebelumnya dua), target **14 eksperimen per run**, sampai 24 bila dikonfigurasi manual. Batas 1.400 entri baru per hari UTC mencegah lonjakan tidak sengaja.
- **Stratifikasi** berdasarkan sektor, arah pasar dan band volatilitas agar tidak seluruh eksperimen mengejar aset paling volatil; hasil tetap saling berkorelasi dan tidak otomatis independen.
- **Kapasitas 850 posisi simulasi OPEN**, 50 OPEN per simbol. Berbagai horizon 1/2/4/8/12/24h tetap digunakan; duplikat aktif strategi×horizon pada venue yang sama dihindari.
- **Skenario friction-stress** memakai bid/ask entry jika ada dan estimasi dampak pasar; dilaporkan terpisah dari P&L lama berbasis fee sehingga rekam historis tidak diubah.
- **14 hipotesis terdaftar**, meliputi tiga baseline serta 11 sinyal berbasis candle. Metode terbaik baru dapat memperoleh alokasi tambahan setelah hasil prospektif memadai.
- **Biaya Git storage** bisa bertambah besar pada throughput tinggi. Ini rancangan riset gratis selama masih dalam batas layanan; tidak dijamin tanpa batas waktu atau kapasitas.

[Lihat rancangan learner](LEARNING.md) · [Lihat workflow kesehatan](.github/workflows/health.yml)

## Model evaluasi yang dipertahankan: fixed-horizon TANPA SL/TP

Setiap paper-trade `OPEN` mempunyai harga/timestamp masuk, arah LONG/SHORT, serta `evaluate_at` di horizon 1, 2, 4, 8, 12, atau 24 jam. **Tidak ada stop-loss, take-profit, trailing-stop, atau exit intrahorizon.** Ketika waktu evaluasi telah lewat, workflow memakai **harga segar yang benar-benar teramati dari venue dan kontrak yang sama, pada atau setelah `evaluate_at`**. Jika terhambat, posisi tetap `OPEN` dan ditandai `DUE/PENDING`; saat harga tersedia, keterlambatan tercatat dan hasil yang terlalu terlambat dipisahkan dari kelompok penilaian tepat waktu.

Laba/rugi simulasi setelah fee hanya diakui untuk eksperimen berstatus `CLOSED`, bukan sebagai floating P&L dari posisi `OPEN`. Ini penelitian berdasarkan titik waktu, **bukan simulasi order TP/SL atau fill persis di detik evaluasi**. Perbedaan harga akibat keterlambatan GitHub Actions tercatat secara eksplisit.

Laporan kini menyediakan `data/report.json → fixed_horizon_outcomes` untuk **statistik LONG vs SHORT, tiap horizon, strategi, aset, jatuh tempo, profit/loss dan P&L simulasi**. Dashboard menampilkan tabel ringkasnya. Notional untuk banyak posisi eksperimen yang saling tumpang-tindih bukan modal portofolio sungguhan.

## Menjalankan dan memantau

Otomatisasi telah terpasang; untuk inspeksi buka [GitHub Actions](https://github.com/0xzein-eth/crypto-strategy-lab/actions) dan pilih **Continuous paper strategy lab**. Setiap run yang berhasil akan memperbarui [report](data/report.json) dan [individual events](data/events/). Run hijau tetap perlu dicek `added`, `provider_observations`, `closed_this_run`, `pending` agar tidak salah membaca kegiatan.

Untuk menjalankan secara lokal tanpa dependensi pihak ketiga:

```sh
python -m unittest discover -s tests -v
python engine.py --verify-only
python engine.py --count 14
```

Dashboard disimpan di `dashboard/index.html` dan dapat diperoleh sebagai artifact workflow `Validate dashboard`. **GitHub Pages belum dianggap aktif** sampai Pages dikonfigurasi/berhasil diterbitkan.

[Lihat metodologi & keterbatasan](METHODOLOGY.md) · [Lihat troubleshooting](RUNBOOK.md)

> **Penting:** Ini simulasi penelitian, bukan sistem trading real. Tidak ada API key exchange, order, wallet, deposit, atau posisi asli. Performa simulasi kini menyediakan skenario perkiraan dampak spread dan slippage **terpisah**, tetapi tidak mencerminkan fill sesungguhnya, funding variabel, atau likuidasi. **Tidak ada bukti strategi menguntungkan secara riil.**

New writes use `data/events/YYYY-MM_daily_DD.jsonl` per UTC day. Prior `YYYY-MM.jsonl` is preserved verbatim, and the hash chain is continuous across both formats; the loader verifies files in deterministic chronological order. Daily sharding mitigates growth of each individual Git blob but is not unlimited storage.
