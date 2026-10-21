# Crypto Strategy Lab v8 — PAPER ONLY

![CI](https://github.com/0xzein-eth/crypto-strategy-lab/actions/workflows/ci.yml/badge.svg)

**Lab eksperimen strategi kripto otomatis, berjalan lewat GitHub Actions, tanpa transaksi riil.**

**Prioritas kebenaran:** `data/events/` = ledger asli; `data/report.json` = metrik terbaru; `engine.py`, `learner.py` dan `signals.py` = aturan berjalan. Bagian kronologi upgrade di bawah memuat angka versi lama yang tidak lagi menjadi kuota aktif. [**Crypto Lab v2: audit kegagalan dan roadmap pembangunan ulang**](docs/CRYPTO_LAB_V2_REBUILD_PLAN_20261019.md) · [Roadmap induk 2026–2027](docs/MASTER_ROADMAP_2026_2027.md) · [Program riset jangka panjang](docs/LONG_TERM_RESEARCH_PROGRAM.md) · [Pemetaan validasi](docs/RESEARCH_DEVELOPMENT_MAP.md).\n\n✅ [Hasil simulasi terakhir](data/report.json) · 📚 [Event ledger permanen](data/events/) · 📊 [Dashboard source](dashboard/index.html) · ⚙️ [Workflow otomatis](.github/workflows/lab.yml) · 🧪 [Pengujian](tests/)

**Peringatan metodologi (19 Oktober 2026):** ledger v8 adalah eksperimen
PAPER dengan notional $10.000 berulang, **bukan rekening portofolio yang
mencukupi modal/margin**. Total fee round-trip pada laporan canonical
12.231 CLOSED adalah $122.310 vs P&L net -$117.333,40, sehingga
keunggulan harga sebelum fee hanya +$4.976,60 (+0,00407% rata-rata
notional). v9 memiliki 2.000 backtest varian tetapi jendela bersama hanya
90 hari; tidak ada champion terverifikasi. Rencana v2 memprioritaskan
riwayat pasar lebih panjang, *backtest-forward parity*, akuntansi portofolio
yang realistis, model biaya, serta validasi final independen. **Tidak ada
strategi saat ini yang dibuktikan aman/untung untuk trade riil.**

## Active Stock Strategy Lab — Nasdaq + LQ45 (IHSG benchmark)

**Berlaku mulai 21 Oktober 2026:** Trading lab saham pindah ke
[`equity_lab/`](equity_lab/README.md): **25 saham tercatat di Nasdaq AS**
dan **45 saham konstituen LQ45 periode Agustus–Oktober 2026**. IHSG
(`^JKSE`) adalah benchmark Indonesia dan Nasdaq-100 (`^NDX`)
benchmark AS; bukan saham dan tidak dapat dijadikan fill.
Masing-masing memiliki jurnal hash, saldo dan biaya simulasi terpisah:
USD $10.000 serta IDR Rp10 juta, tanpa konversi mata uang.
Ada **14 keluarga strategi** dievaluasi dengan harga harian autentik,
riset historis purged/walk-forward, serta simulated prospective paper
account yang tidak bisa ditulis mundur. Data LQ45 berhenti otomatis
ketika membership snapshot kedaluwarsa 30 Oktober 2026.

**Riwayat sebelum migrasi:** `stock_lab/` dan `stock_lab_state/`
adalah **arsip IDX enam saham**, bukan sistem saham yang masih
mengambil trade terjadwal. Workflow lama sekarang read-only, dijalankan
secara manual untuk audit histori. Jurnal yang sudah dibuat tidak
ditimpa/dihapus dan performa arsip tidak digabung dengan epoch baru.

## Arsip Stock Strategy Lab IDX — era lama enam saham

Repo ini juga memuat **[Stock Strategy Lab](stock_lab/README.md)** untuk
riset saham reguler Indonesia BBCA, BBRI, BMRI, TLKM, ASII dan ICBP,
berbeda sepenuhnya dari crypto futures. Empat strategi harian
trading long-only diuji dengan **satu saldo simulasi Rp10 juta**,
maksimum tiga saham dan pembelian 100 lembar/lot, tanpa leverage
atau short. Jurnal cash/EOD hash-chain, equity dan penelitian
bayangan terpisah ada di `stock_lab_state/` setelah sumber IDX
publik menghasilkan observasi sungguhan. Sumber adalah Yahoo
Finance chart *tidak resmi*, harga OPEN harian hipotetis baru
diketahui setelah EOD (bukan fill nyata), dividen/aksi korporasi
belum lengkap. Otomatisasi GitHub
[Stock Lab](.github/workflows/stock-lab.yml) nominal Senin–Jumat
setelah pukul 18 WIB. *Penelitian ini bukan sinyal profit
terjamin dan tidak mengaktifkan order broker.*

## Eksperimen historis tambahan — crypto v9 dan IDX

Pada 21 Oktober 2026, jalur riset historis crypto v9 diperluas dari
**2.000 menjadi 2.400 hipotesis** termasuk empat keluarga baru:
`range_failure_revert`, `momentum_acceleration`,
`volume_followthrough` dan `pullback_channel`.
Target sumber 15-menit historis diperluas dari 12 ke **hingga 16**
perpetual OKX yang terverifikasi. Seluruh 2.000 ID lama tetap berada
pada urutan semula. Ketersediaan dan completeness funding dicatat;
sumber yang tidak tersedia **tidak** digantikan harga sintetis atau
funding 0%. Validasi meliputi trailing confirmed candles, pemisahan
train dan tiga fold kronologis, biaya dasar, tambahan stress 25bp,
dan pengamatan yang eksplisit **bukan** forward paper profit.

Di saham, enam ticker/four-arm **cash wallet tidak berubah**.
Sebagai riset historis terpisah, hingga **18 saham IDX** dan
**10 strategi baru** diuji pada dua tahun data Yahoo EOD publik
dengan 60/20/20 split, purge, stress fee, dan cohort
non-overlap. [Metodologi tambahan](stock_lab/README.md).
Kedua perluasan ini **tidak mengaktifkan pemilihan juara otomatis,
membuktikan ROI, memprediksi win rate, atau mengirim order nyata**.
Data historis dan penelitian prospektif tetap dipisahkan.

## Pembangunan v2 — audit biaya dan modal (fase P0)

Modul `v2/legacy_audit.py` sekarang membongkar secara **read-only**
kontribusi harga sebelum fee, fee round-trip, net P&L, distribusi
per strategi, dan **eksposur notional/margin hipotetis** dari event
ledger asli. Ini **bukan saldo modal atau equity akun futures**.
GitHub CI memverifikasi identitas penjumlahan terhadap laporan resmi.
Jalankan `python -m v2.legacy_audit --verify-main`.
Akan ada fase lanjutan untuk model eksekusi dan portofolio baru;
**belum ada strategi layak trade riil yang dibuktikan**.

## Crypto Lab v2 — data & sinyal tanpa kebocoran (fase P1/P2)

- `v2/data_contract.py` membuat manifest **read-only** untuk cache
  candle OKX perpetual 15m: hash, tanggal asli, panjang jendela,
  kontinuitas bar, dan status funding **belum terbukti lengkap**.
  Cache 90–125 hari **tidak** diubah menjadi klaim data dua tahun.
- `v2/signal_parity.py` memanggil aturan `signals.classify`
  yang benar-benar sedang berjalan dari satu sumber fitur, lalu
  membandingkannya dengan jalur parsing sinyal `signals.from_okx`
  pada *as-of* sama. Candle masa depan tidak boleh memengaruhi sinyal.
  **Ini belum membuktikan kesetaraan fill** dengan v9 historical
  next-bar open; perbedaannya dilaporkan secara eksplisit.
- Workflow [inventaris v2](.github/workflows/v2-data-inventory.yml)
  menyimpan laporan kualitas sumber tanpa mengirim order atau
  mengisi bagian data yang hilang dengan angka perkiraan.

## Crypto Lab v2 — rekening PAPER bermodal terbatas (P3 awal)

`v2/paper_portfolio.py` sekarang menyediakan prototipe saldo USDT
**PAPER** (default 1.000 USDT), *free collateral*, jaminan margin,
batas gross notional terhadap equity, harga bid/ask dan ukuran book
yang **benar-benar disuplai** untuk entry/exit hipotetis. Sistem
menolak quote stale, venue salah, kedalaman kurang, dan kekurangan margin;
jika disetujui, partial fill diberi label eksplisit. Fee, funding settled
dan likuidasi (berdasarkan asumsi) dicatat melalui jurnal kejadian ber-hash.
Semua data masuk ke simulasi **terpisah** dari ledger v8. Tidak ada
credential atau konektor order di modul ini; penggunaan harga best-bid/ask
bukan bukti order riil akan terisi. Modul ini masih **in-memory
prototype**, bukan portofolio live atau sistem produksi persisten.

## Crypto Lab v2 — economic edge dan review strategi (fase P4 awal)

`v2/cost_gate.py` menghitung kebutuhan pergerakan harga minimum
untuk membayar fee, selisih bid/ask, asumsi funding, impact/latency,
dan buffer. Tanpa model perkiraan harga yang memang sudah dibekukan
sebelum sinyal, keputusannya adalah **NO FORECAST / NO TRADE**.
Sinyal yang melebihi biaya pun hanya bisa masuk *shadow research*,
BUKAN strategi pemenang atau order riil.

`v2/research_review.py` menelaah seluruh data CLOSED perpetual
tepat waktu, statistik **hari training**, kelompok kontrol
exact-stratum, dan hambatan kesiapan. Hasil monitoring dilarang
mengubah status triase training; tidak ada auto-promotion.
[Workflow laporan harian v2](.github/workflows/v2-research-review.yml)
menerbitkan artifact read-only. Seluruh evaluasi masih belum lolos
validasi independen jangka panjang.

## Crypto Lab v2 — observer dan equity curve persisten (fase P5 awal)

**Mulai 20 Oktober 2026, v2 memiliki prototipe pengamat PAPER otomatis
yang dapat menyimpan simulasi satu akun dari observasi asli secara
prospektif.** Skrip `v2/okx_observer_source.py` mengambil data publik
OKX USDT-SWAP BTC/ETH/SOL: bid/ask, ukuran kedalaman book
yang **dikonversi dari kontrak ke unit aset** memakai metadata
`ctVal`, serta sinyal candle 15 menit yang sudah confirmed melalui
aturan persis `signals.from_okx`.

`v2/forward_paper.py` memverifikasi dan me-replay
`v2_state/observations.jsonl` dengan hash SHA256, lalu memakai satu
`PaperWallet` berawal 1.000 USDT **simulasi** (maksimum 2 posisi
200 USDT, batas gross exposure 1,25× equity, leverage maksimum 2×),
pilihan riset FB-v3/VWAP-v1, penilaian biaya/spread, dan exit
fixed-horizon 4 jam pada observasi asli berikutnya. File
`v2_state/report.json` dan `v2_state/equity_curve.json` berasal
dari replay yang bisa diuji, bukan angka rekayasa. Jurnal v8
`data/events/` tidak diubah. Penerusan observasi menggunakan
[GitHub workflow v2](.github/workflows/v2-forward-paper.yml)
nominal setiap 30 menit; keterlambatan cron tetap mungkin. Setiap
`--verify-only` memeriksa input historis dan hasil turunan.

**Peringatan penting:** strategi pilihan sebelumnya telah diperiksa,
jadi ini **uji plumbing eksploratoris, bukan final untouched
out-of-sample**. Price crossing bid/ask adalah hipotesis eksekusi,
tidak ada bukti fill, funding belum lengkap, dan slippage/impact
belum terselesaikan. Equity curve sementara hanya setelah
**bid/ask dan fee simulasi**, belum layak diterjemahkan sebagai
hasil akun riil ataupun strategi menguntungkan. Workflow tidak
memiliki endpoint order dan tidak memakai kunci akun trading.
Ketiga pasar harus punya quote segar agar sebuah equity mark baru
dicatat; source gagal berarti run berhenti, tidak memalsukan
harga atau waktu.

## Crypto Lab v2 — semua strategi diamati, modal paper tetap terbatas

**Pembaruan 20 Oktober — studi shadow prospektif 26 strategi confirmed.**
`v2/shadow_research.py` mencatat semua sinyal valid dari katalog
*beku*, menghitung peluang → kelayakan depth/spread → hasil 4 jam pada
quote asli berikutnya, dan membandingkan **kontrol arah deterministik
pada waktu/aset sama** yang ditetapkan sebelum hasil diketahui.
Aturan wallet **tidak diubah**: hanya FB-v3/VWAP-v1 yang berhak
mengusulkan posisi paper, maksimum 2 × 200 USDT dari satu saldo
1.000 USDT simulasi. Ada tidaknya sinyal shadow bukan perintah order.

Hasil baru hanya boleh berasal dari event hash
`v2_state/observations.jsonl`, dipublikasikan secara terpisah pada
`v2_state/shadow_report.json`; equity akun tetap pada
`v2_state/equity_curve.json`. Tidak ada data OHLCV masa depan,
interpolasi CLOSE atau perubahan ledger v8. Workflow peneliti
dapat terpicu oleh cron 30 menit **dan** run v8 sukses; setiap
gagal sumber dapat diperiksa lewat artefak kesehatan workflow,
tanpa memalsukan tick.

**Peringatan:** biaya funding dan eksekusi sesungguhnya belum
terukur lengkap; tambahan biaya 30bps adalah *stress asumsi*.
Kontrol bayangan bukan eksperimen acak dengan uang.
Hasil lama sudah berulang kali diinspeksi sehingga **tidak ada
strategi juara tervalidasi**. Baca
[protokol studi forward 26-arm](docs/V2_PROSPECTIVE_SHADOW_RESEARCH_20261020.md).

## Crypto Lab v2 — pengumpulan data historis hingga 2 tahun

`v2/history_warehouse.py` membuat warehouse sendiri yang hanya
menerima OHLCV OKX **15m confirmed** yang benar-benar diperoleh
melalui API resmi, atau berasal dari cache v9 dengan integritas valid.
Perluasan data dilakukan dalam halaman API terbatas setiap run dan
dilanjutkan pada run berikutnya sampai maksimum **730 hari** jika
sumber mendukung. Candle yang hilang, berubah, terduplikasi, tidak
berurutan, atau berada di masa depan akan menyebabkan kegagalan, bukan
interpolasi. Ada hash SHA256, tanggal UTC asli, jumlah candle asli dan
status kecukupan 365/730 hari per aset. BTC/ETH/SOL dipilih sebagai
subset awal; ini **bukan** bukti seluruh 12 aset atau 2 tahun tersedia.

Data pendanaan `realizedRate` yang **sudah diselesaikan**
oleh bursa dikumpulkan dan disimpan **terpisah**. Status funding yang
tidak lengkap tidak boleh diubah menjadi anggapan nol biaya.
Workflow [v2 historical warehouse](.github/workflows/v2-history-warehouse.yml)
berjalan batch terjadwal/dispatch dan menyimpan data terverifikasi di
`v2_history/`. **Data historis tidak digunakan untuk mengarang
transaksi forward ataupun untuk menyetujui trading riil.**

## Crypto Lab v2 — kontrol bias dari banyak strategi

`v2/evidence_gate.py` menilai 26 strategi berdasarkan hasil
shadow dengan pasangan kontrol pada aset dan waktu yang sama,
**mengelompokkan trade berdasarkan hari UTC** alih-alih menganggap
ribuan transaksi independen. Menggunakan koreksi pengujian bersama
dengan 2.048 *shared-day sign-flip permutations*. Baru memberi
statistik eksploratoris ketika ada minimal 100 pasangan valid,
20 hari entry terpisah dan 4 minggu ISO. Hasil tetap **tidak
memperbolehkan promosi strategi otomatis** karena data telah
sering diperiksa dan funding serta eksekusi riil belum lengkap.
Laporan terbuka sebagai artefak GitHub Actions melalui
[workflow evidence gate](.github/workflows/v2-evidence-gate.yml).
[Baca protokolnya](docs/V2_MULTIPLE_TESTING_EVIDENCE_20261020.md).

## Crypto Lab v2 — prospektif 90 hari terkunci

Modul `v2/frozen_trial.py` memulai protokol periode masa depan
**21 Oktober 2026 sampai 19 Januari 2027 UTC**, dengan
versi kode strategi, wallet, dan penelitian yang dikunci
berdasarkan Git blob SHA. Kandidat FB-v3 dan VWAP-v1 sudah
pernah diperiksa sebelumnya, jadi bukan strategi terbukti.
Selama 90 hari, tracker hanya mengumumkan progres dan integritas
sumber, bukan win rate atau pemeringkatan kandidat. Kelengkapan
funding/eksekusi, kontrol risiko akun, koreksi pengujian,
dan izin pengguna adalah syarat terpisah. Tidak ada order riil.
[Protokol beku](docs/V2_FROZEN_90DAY_TRIAL_20261020.md).

## Status operasional

Eksekusi v8 pertama berhasil pada **8 Oktober 2026, pukul 10.18 WIB**, mencatat 6 eksperimen LAB-116–121 menggunakan snapshot **OKX USDT perpetual**; hash-chain ledger telah diverifikasi. Lihat [run pertama](https://github.com/0xzein-eth/crypto-strategy-lab/actions/runs/37722057618). Data terbaru selalu ada di `data/report.json`, bukan di teks README ini.

**Jadwal otomatis internal GitHub:** paper lab menit **04, 14, 24, 34, 44, dan 54 UTC** (setiap 10 menit), dengan **dua clock pemulihan terpisah** pada menit **02/12/22/32/42/52** dan **09/19/29/39/49/59**. Keduanya menggunakan `GITHUB_TOKEN` bawaan, memeriksa laporan resmi terbaru serta workflow yang sedang berjalan, dan baru meminta `workflow_dispatch` jika laporan berusia lebih dari 14 menit. Pemicu cadangan saling dikunci untuk membatasi duplikasi; jadwal GitHub tetap *best effort* dan tidak dijamin tepat waktu. [Dokumentasi dan keterbatasan](OPS_RELIABILITY.md). Laptop pengguna tidak perlu menyala. Pada kondisi normal mesin memiliki batas **hingga 44 eksperimen baru per run** (tetap bergantung pada kuota aktual, sinyal, sumber publik dan kualitas jadwal), batas **1.050 posisi OPEN bersamaan**, **50 OPEN per aset** dan **1.750 OPEN baru per hari UTC**, tetapi **tanpa batas seumur hidup 80 record**. Ketika posisi jatuh tempo, penyelesaian dilakukan terlebih dahulu memakai snapshot segar; harga historis tidak dicari untuk menyamarkan keterlambatan.

**Penyempurnaan reliabilitas 19 Oktober:** setelah run `lab.yml` sukses,
`health.yml` kini melakukan handoff ke sesi observer baru yang tetap berbatas,
meskipun cakupan sebelumnya telah pulih. Guard mengecek antrean dua kali
untuk mencegah penulis ledger paralel. Ini mengurangi ketergantungan
pada cron GitHub yang bisa terlambat, tetapi tidak menjadi SLA.
Repository variable `PAPER_CONTINUOUS_HANDOFF=off` dapat menonaktifkan
penerus otomatis jika ingin membatasi menit runner; jadwal/guardian lain
tetap aktif. Lihat [catatan operasional](OPS_RELIABILITY.md).

**Peningkatan kebijakan eksperimen 19 Oktober:** `learner-v8` sekarang
membatasi *24h-only directional proxy* ketika pemeriksaan OKX 15m sungguhan
tidak memberikan kandidat confirmed: hanya 12% slot simbol unik yang
dicatat sebagai baseline probe teracak deterministik. Jika sinyal confirmed
ada, 20% hash band CTRL tetap dipertahankan. Strategi advanced yang
secara konsisten negatif di **training-only** (>=50 CLOSE; >=7 UTC days,
day-cluster UCB <-0.05 R dan lebih buruk daripada CTRL) dapat dikurangi
bobotnya 4:1 **hanya di satu band eksplorasi**, tanpa dihentikan atau
dipilih berdasarkan monitoring. Ini mengurangi eksperimen baseline
tanpa sinyal, bukan jaminan keuntungan. Auditor dapat melihat jumlah
slot yang dilewati dan dampak policy cohort baru melalui
[protokol dan batas validitas](docs/STRATEGY_QUALITY_SPRINT_20261019.md).

## Struktur repository

| File | Fungsi |
|---|---|
| `engine.py` | Mesin prospektif event-sourcing v8; harga publik, buka/tutup simulasi, audit |
| `signals.py` dan `regime_hypotheses.py` | Katalog sinyal 15m terkonfirmasi dan varian BRREG-v1/TPREG-v1 khusus paper entry baru |
| `learner.py` | Alokasi eksperimen dan kelompok kontrol, pemantauan berbasis hari |
| `universe.py` | Katalog kandidat aset dengan strata sektor/arah/volatilitas; instrumen tanpa kontrak terverifikasi dilewati |
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

Prioritas data untuk eksperimen baru: OKX USDT swap → Bybit linear → Binance Futures → Kraken USD spot proxy → Coinbase USD spot proxy. Harga keluar posisi lama tetap diwajibkan berasal dari venue serta instrumen entry yang sama. Beberapa penyedia bisa memblokir runner GitHub berdasarkan wilayah; kode membedakan kesalahan HTTP 403/451 dan mencoba sumber alternatif. **Harga exit selalu harus dari provider, tipe pasar, dan instrumen yang sama dengan entry.** Spot proxy tidak pernah dihitung sebagai sampel valid untuk bukti edge perpetual.

- Simulasi `$10,000` notional per eksperimen, leverage hipotesis `3x`, fee `0,05%` per sisi.
- `normalized_R = (signed_return_pct − 0,10%) / research_risk_pct`. Risk denominator riset awal `1,5%`, **bukan stop-loss aktual**.
- Keterlambatan exit dihitung nyata; **lebih dari 30 menit** masuk kelompok `late_excluded`, bukan performa eligible tepat waktu.
- Jika harga tidak tersedia, trade tetap OPEN dan menjadi DUE/PENDING; tidak boleh di-backfill.
- Event OPEN/CLOSE yang sudah disimpan tidak diedit, disingkat, atau dihapus. Semua hash event diverifikasi setiap run.
- Perubahan merusak hash, hilangnya source-of-truth, atau ketidaksesuaian laporan menyebabkan `INTEGRITY_FAILURE` (fail-closed).
- Jika tak ada feed harga valid, workflow gagal dengan `DATA_UNAVAILABLE`, bukan sukses palsu.
- Arsip **LAB-074–115** dari scheduler lama **belum dimigrasi**: record asli lengkap belum direkonsiliasi. Statistiknya **tidak dicampur** dengan v8.

## Adaptive continuous research (v1)

The lab evaluates a **versioned, pre-registered catalogue of paper-only hypotheses**. Current allocation is **performance-neutral**, maintaining CTRL and exploration; descriptive research rankings do not preferentially select future trades. The learner excludes late closes and spot proxies, retains precommitted controls, evaluates day-cluster lower bounds, and maintains a reproducible date-partitioned monitoring sample. Until strict training/monitoring/control thresholds are met, **no strategy is provisionally preferred**. A provisional leader is not proof of profitability. New signal families are versioned rather than generated through unreviewed arbitrary code.

- [Read the learning design](LEARNING.md)
- Dashboard now displays adaptive arm evidence, monitoring samples and provisional status.
- Normal healthy target: **up to 44 new paper experiments per observation** (1,050 OPEN overall; 50 OPEN per symbol; UTC day cap 1,750), if source and strategy filters allow.
- [Schedule guardian](.github/workflows/health.yml) dan [redundant clock](.github/workflows/rescue.yml) memeriksa integritas event, mencegah pemicu berulang, dan memicu pemulihan jika perlu. **Baru:** setelah run yang terlambat berhasil, [recovery_window.py](recovery_window.py) dapat mengambil maksimal enam snapshot baru dengan jarak nyata 10 menit, lalu berhenti. Indikator `estimated_10m_slot_coverage` dalam [report](data/report.json) memperlihatkan perkiraan slot yang berhasil dari 72 jeda observasi terakhir; perlu minimal 12 jeda untuk interpretasi. Semua tetap penelitian tanpa order riil; cron GitHub tidak menjamin 24/7.

## Peningkatan kapasitas dan kualitas sampel (Oktober 2026)

- **48 pasar kandidat** lintas kelompok aset; sistem hanya menerima harga dari instrumen yang sungguh tersedia, tidak menciptakan harga atau memaksa aset tidak terdaftar.
- **Observasi terjadwal sekitar setiap 10 menit** secara best-effort; kapasitas mesin maksimal **44 eksperimen baru per observasi** ketika kondisi sehat, dengan satu OPEN per aset/slot sinyal 15 menit. Batas 1.750 entri baru per hari UTC mencegah lonjakan tidak sengaja.
- **Stratifikasi** berdasarkan sektor, arah pasar dan band volatilitas agar tidak seluruh eksperimen mengejar aset paling volatil; hasil tetap saling berkorelasi dan tidak otomatis independen.
- **Kapasitas 1.050 posisi simulasi OPEN**, 50 OPEN per simbol. Berbagai horizon 1/2/4/8/12/24h tetap digunakan; duplikat aktif strategi×horizon pada venue yang sama dihindari.
- **Skenario friction-stress** memakai bid/ask entry jika ada dan estimasi dampak pasar; dilaporkan terpisah dari P&L lama berbasis fee sehingga rekam historis tidak diubah.
- **Katalog strategi berversi** mencakup tiga baseline, kelompok sinyal berbasis candle, dan BRREG-v1/TPREG-v1 khusus eksperimen masa depan. Daftar otoritatif berada di `learner.py`, bukan angka statis README; tidak ada strategi yang dinyatakan terbukti unggul.
- **Biaya Git storage** bisa bertambah besar pada throughput tinggi. Ini rancangan riset gratis selama masih dalam batas layanan; tidak dijamin tanpa batas waktu atau kapasitas.

[Lihat rancangan learner](LEARNING.md) · [Lihat workflow kesehatan](.github/workflows/health.yml)

## Peningkatan representasi sampel dan audit kesempatan sinyal\n\n`entry_sampling.py` dan allocator baru memakai hanya **jumlah OPEN asli sepanjang tujuh hari** (termasuk yang kalah, menang, atau masih terbuka) untuk membantu memilih arm terkonfirmasi yang benar-benar tersedia tetapi kurang terkumpul. Sekitar 35% bucket alokasi disediakan untuk sampling berbasis jumlah entry, tanpa melihat profit/loss. Kelompok CTRL-v1 20% tidak diubah. `data/report.json → entry_opportunity_audit` menampilkan peluang kandidat per arm, OPEN sesungguhnya, penolakan quote baru, dan kondisi kapasitas. Peluang yang belum tercatat bukan bukti pasar tanpa sinyal; jika kapasitas penuh, modul tidak mensimulasikan candle yang tidak diamati. Diagnostik rugi kini juga membandingkan **TRAINING matched controls** secara terpisah, tanpa otomatis mematikan atau mempromosikan strategi.\n\n## Diversifikasi strategi terkonfirmasi — 19 Oktober 2026

Empat arm paper baru (`IBREAK-v1`, `BANDREV-v1`, `VWAPTR-v1`, `EFFTREND-v1`) menguji **inside-bar breakout**, **dua-bar z-band re-entry**, **VWAP reclaim dengan konfirmasi tren/RSI**, dan **efisiensi pergerakan enam candle**. Semua hanya menggunakan candle OKX perpetual 15m yang sudah dikonfirmasi, tidak melakukan trading riil, tidak mewarisi histori profit arm sebelumnya, dan menjaga exit fixed-horizon. Katalog terdiri atas 25 arm confirmed ditambah tiga baseline. [Preregistrasi penuh](docs/DIVERSE_PROSPECTIVE_HYPOTHESES_20261019.md).

Jatah alokasi paper yang **bersyarat pada ketersediaan sinyal asli** diubah menjadi 35% bucket untuk arm confirmed yang kurang tersampel, 35% eksplorasi confirmed biasa, 20% untuk kontrol CTRL-v1 (bila tersedia), 5% baseline proxy dan 5% netral. Perubahan **berbasis kualitas asal sinyal, bukan P&L**; tidak mengklaim profit atau menghentikan eksperimen lama. Jika tidak ada sinyal terkonfirmasi, hanya baseline/kontrol yang sah bisa dipilih. `entry_opportunity_audit` kini menunjukkan jumlah OPEN hari UTC sebelumnya, sisa kuota, kapasitas OPEN, dan `no_new_entry_reason` untuk membedakan kuota habis vs sinyal tidak muncul.

## Strategi baru dan validasi prospektif\n\nDua hipotesis v1 hanya berlaku untuk **OPEN baru**: BRREG-v1 (breakout terkonfirmasi dengan rezim 24 jam searah) dan TPREG-v1 (pullback terkonfirmasi dengan rezim searah). Mereka memerlukan candle OKX USDT perpetual yang telah selesai, SMA20/SMA50 yang mendukung arah posisi, serta perubahan 24 jam >=1% searah dari ticker publik instrumen yang sama. Bukti asal, versi dan timestamp observasi dibekukan pada OPEN. Data hilang/salah instrumen/tidak segar => tidak ada sinyal tambahan. **Ini bukan strategi unggulan yang telah terbukti.** Lihat [preregistration dan milestone penelitian](docs/LONG_TERM_RESEARCH_PROGRAM.md).\n\n[Audit kesehatan dataset per horizon](.github/workflows/dataset-health.yml) menampilkan rasio penutupan tepat waktu, jumlah OPEN jatuh tempo, spread terobservasi (bukan fill riil), serta jumlah pasangan kontrol yang benar-benar tercocok. Hasil lengkap ada di artifact harian `prospective-cohort-health-paper-only`, dengan hash ledger dan timestamp sumber. Pengujian kode tetap wajib lulus.\n\nResearch quality gates, [matched-control dashboard](.github/workflows/matched-controls.yml), [negative expectancy diagnostics](.github/workflows/negative-edge.yml), dan [frozen regime evidence](.github/workflows/regime-evidence.yml) adalah jalur baca-saja: tidak otomatis mempromosikan strategi dan tidak mengubah ledger. Keunggulan memerlukan pekan prospektif mendatang dan validasi kontrol independen.\n\n## Model evaluasi yang dipertahankan: fixed-horizon TANPA SL/TP

Setiap paper-trade `OPEN` mempunyai harga/timestamp masuk, arah LONG/SHORT, serta `evaluate_at` di horizon 1, 2, 4, 8, 12, atau 24 jam. **Tidak ada stop-loss, take-profit, trailing-stop, atau exit intrahorizon.** Ketika waktu evaluasi telah lewat, workflow memakai **harga segar yang benar-benar teramati dari venue dan kontrak yang sama, pada atau setelah `evaluate_at`**. Jika terhambat, posisi tetap `OPEN` dan ditandai `DUE/PENDING`; saat harga tersedia, keterlambatan tercatat dan hasil yang terlalu terlambat dipisahkan dari kelompok penilaian tepat waktu.

Laba/rugi simulasi setelah fee hanya diakui untuk eksperimen berstatus `CLOSED`, bukan sebagai floating P&L dari posisi `OPEN`. Ini penelitian berdasarkan titik waktu, **bukan simulasi order TP/SL atau fill persis di detik evaluasi**. Perbedaan harga akibat keterlambatan GitHub Actions tercatat secara eksplisit.

Laporan kini menyediakan `data/report.json → fixed_horizon_outcomes` untuk **statistik LONG vs SHORT, tiap horizon, strategi, aset, jatuh tempo, profit/loss dan P&L simulasi**. Dashboard menampilkan tabel ringkasnya. Notional untuk banyak posisi eksperimen yang saling tumpang-tindih bukan modal portofolio sungguhan.

## Menjalankan dan memantau

Otomatisasi telah terpasang; untuk inspeksi buka [GitHub Actions](https://github.com/0xzein-eth/crypto-strategy-lab/actions) dan pilih **Continuous paper strategy lab**. Setiap run yang berhasil akan memperbarui [report](data/report.json) dan [individual events](data/events/). Run hijau tetap perlu dicek `added`, `provider_observations`, `closed_this_run`, `pending` agar tidak salah membaca kegiatan.

Untuk menjalankan secara lokal tanpa dependensi pihak ketiga:

```sh
python -m unittest discover -s tests -v
python engine.py --verify-only
python audit.py
```

Dashboard disimpan di `dashboard/index.html` dan dapat diperoleh sebagai artifact workflow `Validate dashboard`. **GitHub Pages belum dianggap aktif** sampai Pages dikonfigurasi/berhasil diterbitkan.

[Lihat metodologi & keterbatasan](METHODOLOGY.md) · [Lihat troubleshooting](RUNBOOK.md)

> **Penting:** Ini simulasi penelitian, bukan sistem trading real. Tidak ada API key exchange, order, wallet, deposit, atau posisi asli. Performa simulasi kini menyediakan skenario perkiraan dampak spread dan slippage **terpisah**, tetapi tidak mencerminkan fill sesungguhnya, funding variabel, atau likuidasi. **Tidak ada bukti strategi menguntungkan secara riil.**

New writes use `data/events/YYYY-MM_daily_DD.jsonl` per UTC day. Prior `YYYY-MM.jsonl` is preserved verbatim, and the hash chain is continuous across both formats; the loader verifies files in deterministic chronological order. Daily sharding mitigates growth of each individual Git blob but is not unlimited storage.

## Historical Factory v9.6 — 2.000 varied strategies

V9.6 menguji **2.000 varian backtest deterministik** termasuk 400 tambahan dari empat keluarga yang berbeda (inside-bar release, band re-entry, VWAP-trend reclaim, efficient trend). Validasi per-fold tidak lagi memilih empat kombinasi terbaik yang bisa saja dari satu keluarga: *training-only family diversity* diutamakan, dengan chronological purge/embargo, kontrol, funding teramati, fee/stress sensitivitas dan tanpa auto-deploy ke paper v8. Ke-1.600 identitas varian sebelumnya tetap sama. Bertambahnya strategi meningkatkan **beban multiple testing**, bukan jaminan kenaikan profit. <Link to? no>Rincian: [Historical factory](RESEARCH_V9.md).

## v9 — Historical Research Factory (terpisah dari paper ledger v8)

**Aktif:** [workflow riset v9](.github/workflows/research.yml) · [laporan hasil backtest terbaru](research_results/latest.json) · [metodologi dan cara menjalankan](RESEARCH_V9.md).

Research Factory otomatis mengumpulkan confirmed 15m OHLCV OKX perpetual dengan cache historis berintegritas, menguji hingga **2.000 varian** aturan dan parameter terhadap **8 aset kandidat** (jika feed tersedia), dan menggunakan tiga validasi walk-forward terpisah secara kronologis dengan purge/embargo. Laporan dibuat setiap hari sekitar **10:19 WIB** oleh GitHub Actions (best effort). Siklus tambahan bisa dijalankan manual melalui tab Actions.

**Penting:** ini adalah backtest historis, bukan trading sungguhan atau hasil paper trade prospektif; asumsi biaya dan likuiditas tetap terbatas. **Tidak ada strategi yang otomatis dianggap terbukti profitable.** File v9 di `research_cache/` dan `research_results/` tidak dimasukkan ke `data/events/` atau statistik paper-trading v8. Mesin v8 berjalan terpisah sesuai jadwal dan aturan integritasnya.


### Quality-first reliability / funding policy (10 October 2026)

Until the GitHub-only observation clock is more reliable, the lab
automatically **throttles new paper entries** based on a minimum
12-observation rolling schedule sample: <40% coverage → max 3 new
positions/run, 40–75% → max 7, otherwise normal requested budget.
An immediate >45-minute recovery gap still caps to 2. Due exits are
always attempted before new entries. Guardian status is now reported as
`DEGRADED_RECOVERING` rather than pretending an accepted retry has
already restored fresh data.

The historical research separately uses a 90-day trailing **funding-aware
window** while preserving longer OHLCV source caches. Settlement gaps
remain missing, never silently treated as 0% funding. Historical
research candidates are not automatically activated or traded live.


### October 2026 research quality upgrade

The ten-minute coverage estimate now treats rapid consecutive reports
less than five minutes apart as **additional snapshots, not distinct
covered ten-minute slots**. The dashboard exposes the number of near
duplicates alongside missed slots. This corrects an optimistic artifact
of schedule guardians and long recovery windows; it is not a promise
that GitHub cron will achieve the nominal cadence.

The derived v3 fixed-horizon report additionally compares outcomes
across **entry-time precommitted rising/falling regimes** and UTC
dayparts, with distinct entry-day counts and late sample shares.
These descriptive breakdowns cannot prove profitability, and no
new strategy receives automatic promotion or real-money access.


### New future-only horizon quality policy

Under poor observed GitHub schedule reliability, the lab is still free
to open **paper** hypotheses but automatically reduces exposure to
evaluation times that would likely be missed. New entries use
4/8/12/24-hour horizons below 40% observed 10-minute slot coverage;
2/4/8/12/24-hour horizons from 40% to under 75%; and all six horizons
when coverage reaches 75%. The policy and allowed horizons are saved in
each new experiment, without touching any previously recorded OPEN or
CLOSE. A prolonged recovery run exits early if another independent
committer advances the canonical market report on two consecutive
checks, saving Actions compute. Research conclusions remain unproven.


### New v4 post-friction horizon diagnostics

The read-only fixed-horizon cohort report now displays the hypothetical
**after-friction average R and UTC-day-cluster lower bound** across
timely, same-venue perpetual CLOSE observations. The same conservative
predeclared stress-funding-agnostic fallback as the learner applies:
frozen recorded extra friction when present or a 0.12%-of-notional
haircut to legacy experiments. All unobserved actual order fills, funding
and margin remain excluded and unproven.

Clustering outcomes by distinct OPEN UTC days, clipping per-trade R in
the *diagnostic lower bound* and requiring at least seven independent
entry days and 30 valid closes are minimum screening checks. They
are **not** a statistical confirmation or automatic strategy selection.
Version `fixed_horizon_v4` permits a one-time additive derived-report
upgrade while the original event source, old outcomes and hash chain
remain unchanged.


### October 2026 cadence and evidence-volume upgrade

Every successful paper workflow now extends into an adaptive,
serialized observation window, publishing a verified fresh observation
every ten minutes for up to 6 / 12 / 18 later real-time intervals
according to measured coverage. This is no longer restricted to the
first recovery after a long scheduling gap. The target of **near 100%
ten-minute interval coverage** is aspirational: GitHub cron has no
timeliness SLA, and the lab measures, rather than fabricates, uptime.
Runner time and repo size must be monitored as the ledger expands.

New paper experiment capacity is now up to 20 per healthy interval,
reduced automatically to 10 / 5 under degraded schedules and to 3
immediately after a long gap, always resolving existing due trades
first. The quality-aware future-only horizon rule continues to protect
short fixed-horizon studies from known poor scheduler conditions.
The independent historical factory runs twice per day with up to
400 deterministic parameter variants; none is promoted automatically.


**Research grid details:** v9 now explicitly covers 1/2/4/8/12/24-hour
hypothetical exit horizons and a wider pre-registered trend, momentum,
mean-reversion, breakout and RSI parameter grid. The deterministic
factory has 420 possible configured combinations and tests the
requested first 400, including controls. Increasing the number of
backtested rules materially increases the risk of selection overfitting:
the review gate still requires independent chronological validation,
settled funding and controls, and no variant is auto-enabled.


### Signal-slot independence and sustained observation (13 October 2026)

The 10-minute real-time market-observation cadence and due-position
closure logic remain unchanged. New paper OPEN experiments are now
bounded to **one per asset per frozen 15-minute signal decision slot**,
even when earlier experiments on that asset were already closed. New
OPEN evidence stores its precommitted `signal_slot_utc` and
`independent_symbol_slot_policy`. This prevents 10-minute observer
overlap from creating nearly identical correlated research samples.
Historic entries and exits are never touched. Current active-trade
signature checks are also pre-indexed instead of repeatedly scanning
the growing ledger for each market/horizon combination.

For rolling scheduling coverage below 75% (once at least 12 intervals
exist), each healthy or recovery-triggered 10-minute observation window
now requests **up to 18 real future snapshots over approximately 3
hours** instead of two hours in the intermediate degraded band. At
75%+ it remains six pulses/one hour. This avoids reliance on an
additional Github cron start midway through an unstable interval;
it can increase Actions compute use and still cannot guarantee
100% scheduling or repair historical missing observations.


### Research and sampling upgrade (2026-10-13)

The continuous GitHub-hosted observer now takes up to 18 authentic
ten-minute samples while estimated rolling observation coverage is
below 95%; after reaching 95% it takes 12. Longer bounded runner
windows reduce dependence on best-effort cron restarts. This is
**not a 90% uptime guarantee**: actual coverage is measured in the
canonical report and missing slots are never fabricated.

Healthy, prospective paper observations request up to 24 NEW
experiments per tick, subject to one-asset-per-frozen-15m-signal-slot,
market-source, daily and open-position quality gates. Existing
due exits run first, never blocked by new-entry throttling.

Historical Research Factory v9 now examines 500 deterministic
fixed-parameter variants per scheduled run, up from 400, and
includes a stress sensitivity for another 25bp of round-trip
execution impact above existing 22bp estimated base trading costs.
The promotion gate demands positive stressed daily-clustered
confidence bound and fully-funded stressed mean. None of these
results represents live execution or verified profitability.


### Training-only risk-aware research triage and coverage relay (2026-10-14)

The guardian can send **one authenticated handoff dispatch** when the
completed successful canonical lab run has no queued or running successor
and measured rolling 10-minute observation coverage is below **90%**.
The completed-run identity, fresh canonical report, status and cadence
are verified twice against GitHub's workflow-specific API. Competing
runners, failed jobs, older completion receipts, adequate coverage and
absent schedule history are rejected. GitHub cron/dispatch remains
best-effort; this does not guarantee a 90% SLA or permit fabricated
quotes, and longer runner continuity consumes hosted compute.

All new experimental candidate sorting now favors **less frequently
sampled sector/direction/volatility groups within the same UTC day**.
These counts use only precommitted entry labels, never outcomes.
The reported evidence quality includes authentic eligible entry-day
coverage, positive/negative 24h regimes, sector breadth and sampled
six-hour UTC windows. Historical dates remain unchanged and a seventh
distinct day cannot be manufactured in one run.

Arms with **>=50 training-only valid closes across >=7 training days**
may be downweighted only when their clipped daily **upper** confidence
bound is below -0.05R and the training mean trails the control by
more than 0.05R. The 20% control branch remains intact; unfavored
strategies retain a positive exploration weight and may be re-evaluated
on future regimes. The holdout/monitoring partition is NEVER used in
the allocation decision. This is allocation triage, not evidence of
trading profitability, and no rule can enable real trading.


### Idle market heartbeat and resilient paper observation (October 2026)

An empty/no-new-signal tick must not be mislabeled an exchange outage.
When the normal OPEN/CLOSE path did not read any valid quote, `engine.py`
now independently probes **actual current quotes** from BTC, ETH, SOL and
XRP until at least one properly validated public venue observation is
available. A heartbeat is **not** a fill, simulated trade, or an OPEN/CLOSE
event: it only refreshes the persisted quote-observation report at its real
time. If all providers fail, the engine still refuses to claim a new tick;
its source errors and attempted symbols are explicit.

The long GitHub runner now exposes Python engine failures in GitHub
Actions logs instead of hiding their stderr behind a generic
`CalledProcessError`. On a confirmed `DATA_UNAVAILABLE` outage, it
skips that actual ten-minute sampling slot rather than fabricating a
quote, sleeps before its next attempt and stops after three consecutive
outages for incident triage. Integrity and programming errors remain
fatal; all prior events are preserved. This improves observability and
transient outage tolerance, not guaranteed GitHub cron delivery.


### Periodic independently replayed evidence checks and venue-health provenance

The read-only **Research quality gates** workflow now evaluates the
canonical SHA-chained event ledger automatically twice daily on a
best-effort GitHub schedule, and on successful completion of the
historical Research Factory. It continues running on pull requests.
Each 30-day GitHub artifact contains the source report observation
timestamp and exact ledger-tip SHA; no previous events are changed.
All gates remain descriptive and do not establish tradeable profits.

Every genuine prospective tick also reports counts of successful real
perpetual public quotes, successful spot-proxy quotes, failed
symbol/venue requests, and the sources that actually provided usable
fresh prices. **Spot-proxy quotes do not qualify as perpetual-market
evidence.** This distinguishes heartbeat liveness from the reliability
of derivative-instrument pricing.


### Cadence target and quality-gated prospective throughput (2026-10-15)
The strict 72-real-gap rolling cadence ratio is **not** smoothed or
retroactively rewritten. Extra recent-12 and recent-36 gap metrics are
separate diagnostics only: old outages remain in the headline metric until
the actual rolling window advances. On a successful completed run with no
active successor the audited guardian may hand off below **95%** (a buffer
above the 90% operating target), still requiring a fresh main report and
two independent GitHub queue reads. These triggers cost GitHub runner minutes
and cannot guarantee a 90% SLA.
The prospective intake is capped at 5 if coverage <40%, 12 at <75%,
20 at <90%, and up to 30 at >=90% with at least 12 observed intervals.
The recovery-gap throttle remains 3; all sector/15-minute duplicate,
source, open-position and UTC-day caps and control-policy gates remain
unchanged. More hypotheses are not more statistically independent trials.


### Prospective confirmed-candle hypothesis expansion (October 2026)
Three new predeclared paper-only 15m OKX swap hypotheses are now
available **only** when the OHLCV source sequence has genuine confirmed,
gap-free candles: `DC-v1` (Donchian break of the *prior* 20 bars with
volume/ATR buffer), `RSITREND-v1` (RSI continuation filtered by the
trailing SMA50 and SMA20 slope), and `ATRCHAN-v1` (directional ATR
channel breakout around SMA20 with volume). The unchanged CTRL-v1
control branch, one asset/15-minute decision slot, same venue fills,
stress-friction and no-lookahead checks still apply.
These arms may have substantial correlation with existing hypotheses,
so paper volume is never presented as independent statistical evidence.


### Historical research v9.4 — 1,200 deterministic backtest variants

The independent historical Research Factory now tests up to **1,200
parameterized hypotheses**, up from 750, with the exact original 750
experiment IDs and their order unchanged. Three additional families
are **compression-breakout**, **volatility-impulse**, and **trend-reclaim**.
They use closed 15-minute candles and hypothetical next-bar entry only;
historical fills are estimates, not observed executed trades.

The requested price-history universe expands from 8 to **10** predeclared
OKX USDT-perpetual instruments: BTC, ETH, SOL, LINK, XRP, ADA, AVAX,
DOGE, DOT, NEAR. Actual dataset and *complete settled funding*
availability are independently audited in every run: missing instruments
are omitted, missing funding is never treated as zero, and data cannot
be backfilled with imagined prices. The analysis window remains
90 days. Tests retain purged chronological walk-forward, explicit
fee/impact sensitivity and non-promotion of rejected shadow candidates.
Testing 1,200 overlapping variants magnifies multiple-comparison risk;
the report always remains exploratory, with no proven edge.

### Prospective paper experiment capacity and neutral allocation

The canonical GitHub Actions observer now requests at most **36 new
paper OPENs per observation**, formerly 30. This is only a
**requested maximum**: actual new positions require qualifying current
quotes, instrument checks, independent 15m symbol slots, distinct open
signatures, daily/total capacity and real rolling scheduling coverage.
The guard still limits recovery runs to three; missed ticks are never
retroactively filled. Every position remains paper-only and has a
separately observed current entry and due exit quotation.

Prospective confirmed-candle testing also includes
`COMPBR-v1`, `IMPULSE-v1`, and `TRECLAIM-v1`. The control allocation
is reserved at >=20% where CTRL is offered. All available hypothesis
arms are chosen with deterministic *equal weights within each sampling
branch*, based on availability and precommitted keys, **not**
provisional win rates, training ranks, losses or viewed holdout returns.
Training leaderboards remain research diagnostics; `champion` stays
null and **no strategy is automatically promoted** until a separately
verified independent eligibility policy is explicitly deployed.
Confirmed OKX candles older than 25 minutes are rejected, including
after scheduler delays.

### Evidence-first automatic ranking and failure diagnosis (2026-10-15)
The separate **Matched controls research** workflow now runs automatically
four times daily in GitHub Actions. Its read-only 30-day artifacts contain
both `matched-controls-report.json` and `strategy-leaderboard.json`,
which report all eligible paper strategies with frozen entry-day one-to-one
matched CTRL differences, **separately computed paired training and paired
monitoring** (20% day-partition) and original source ledger-tip hash.
A positive raw strategy expectancy is only descriptive; the quality gate
also requires genuinely matched *positive day-cluster bounds in both
partitions*, not merely unmatched profitable trades. This partition has
been inspected repeatedly; it is **not** untouched independent validation
and it never changes the online learner's allocations.
The historical 1,200-variant walk-forward additionally publishes for each
training fold the count of candidates failing sample/day/positive-day-bound
requirements plus up to ten highest-scoring **disqualified training-only**
variants. These are explicitly NOT selected for validation, promotion,
or live trading; the previous positive-bound selection criterion is
unchanged.


### Shadow validation of rejected historical hypotheses

V9 historical research can validly report **zero** positively selected
strategy variants after 1,200 tests. Instead of claiming the least-bad
training result is an edge, each expanding chronological fold now
preselects **up to four training-rejected** parameter variants (preferring
different families) and evaluates them descriptively on the next purged
validation fold. Every shadow result includes the frozen training
rejection, subsequent held-out descriptive P&L, stress metrics, and a
same-horizon two-control comparison when sample sizes permit.
`SHADOW_EXPLORATORY_ONLY` results **never** enter
`walk_forward_selected`, `eligible_for_forward_code_review`,
a prospective paper trade, or an order. Validation is repeatedly
inspected and is NOT a clean confirmatory holdout.


### Transparent recovery ETA expressed in NEW actual 10-minute intervals

The unchanged canonical 72-gap coverage metric now exposes an
**explicitly counterfactual** count of future real on-time 10-minute
observations required to reach 90% or 95%, *assuming every upcoming
interval succeeds and no slots are missed*. It slides historical gaps
out of the fixed-size window; it never adds synthetic gap entries to
the actual ledger, updates the headline metric, requests trades based
on projected coverage, or guarantees a time-to-recovery SLA.

## Research scale v11 (2026-10-16, paper only)

**Scope:** The prospective candidate universe expands from 38 to 48 versioned
symbols, with no assertion that every symbol is supported on every exchange.
Unlisted/stale/illiquid assets fail closed: only real, matching provider quotes
may result in a new paper OPEN. The guarded healthy-run request rises from 36 to
44; real 15-minute symbol-slot uniqueness, maximum 1,750 new/day, 1,050
simultaneous OPEN and 50 concurrent per symbol remain enforced. A market
outage or low scheduler coverage always reduces, rather than inflates, trades.

**Historical research:** 1,600 parameterized variants (previously 1,200) on
12 requested OKX USDT perpetual symbols, with the original first 1,200 IDs in
exact historical order. Two genuinely separate exploratory families are
volume-climax wick rejection and RSI oversold/overbought recovery. Their
prospective 15-minute counterparts use only confirmed and timely OKX candles.

**Memory and data accounting:** Each variant's synthetic trades are processed
into training-fold statistics then released before examining another variant;
validation rows are recomputed only for variants frozen by training-only
selection and a small labeled exploratory shadow sample. Derived reports include
cumulative counts by variant family and market, **not** claims of unique
observations or actual paper executions. Raw confirmed OHLCV cache capacity
increases to 18,000 candles per instrument. Settled funding is never fabricated:
comparison windows remain constrained to periods with real funding coverage.

**Evidence:** No allocation based on performance or automatic promotion; keep
the controls and realistic fee, extra friction, day-cluster, no-lookahead and
source-provenance checks. More overlapping hypotheses increases multiple-testing
risk and cannot establish profitability. GitHub Actions remains best effort and
may incur runner usage charges.

## Prospective temporal maturity and seven-day neutral coverage (2026-10-16)

The research bottleneck is now **different, real UTC days and market
regimes**, not raw overlapping hypothetical trade count. This release does
not change the ten-minute observer cadence or claim that trading more
positions in one price regime creates independent evidence.

- New OPEN selection balances **frozen market sector/direction/volatility
  strata across the preceding seven calendar days**, breaking ties using
  the pre-existing same-day balance. It reads only original OPEN-time
  metadata of both winning and losing records; no strategy PnL, later CLOSE,
  adaptive leaderboard or future information can influence the weighting.
- The canonical derived `data/report.json` includes an
  `evidence_quality.temporal_maturity` summary by arm and overall:
  distinct observed UTC entry days, ISO weeks, weekdays, six-hour dayparts,
  precommitted direction regimes, 7/14/30-calendar-day activity, and the
  largest day's share of eligible CLOSEs. Day concentration effective
  count is a descriptive **upper bound**, never an iid or alpha sample size.
- Read-only [research quality gates](research_quality.py) now require
  four real ISO calendar weeks and five weekdays on top of existing
  minimum matched days, strictly paired controls, funding/friction
  safeguards and prospective scheduler quality. The [quality workflow]
  (.github/workflows/research-quality.yml) saves an independent ledger-tip
  linked maturity snapshot as an artifact; no extra order automation.
- **Twenty separate eligible entry days and four ISO weeks** are
  minimum *data maturity* targets, not a claim that strategy performance
  becomes statistically valid after twenty days. Until measured reality
  supplies the days, the status remains `NOT_PROVEN` and all experimental
  strategies stay performance-neutral.
- Historic day counts are never fabricated or interpolated; historical
  backtests cannot be counted as future observed paper entry dates.

## Cadence gap early warning and daily evidence coverage (2026-10-16)

The independent GitHub-native clocks cannot guarantee time-to-run; a continuous
observer can remain **running while the actual market report is stale**.
The guardian now emits `PAPER_OBSERVATION_GAP` immediately after the authoritative
report crosses the configured freshness threshold *even if the worker is
IN_FLIGHT*. It does **not** queue a duplicate ledger writer, cancel a possibly
healthy observation runner, create fake historical ticks, or bypass venue data
validation. The 95% rolling-slot goal is monitored separately from the 90%
entry-throttling safety threshold.

The read-only `temporal_evidence` quality artifact and canonical derived
report now distinguish **today's incomplete UTC day** from the **last seven
fully completed UTC days**. A missing day appears explicitly (no filled
dates), alongside coverage breadth targets: >=10 genuine bidirectional-regime
days and >=6 genuine full four-daypart days. Targets measure diversity, NOT
statistical independence or evidence of profit. The preexisting 20-day /
4-week quality gate and performance-neutral seven-day OPEN sampling remain.
