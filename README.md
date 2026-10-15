# Crypto Strategy Lab v8 — PAPER ONLY

![CI](https://github.com/0xzein-eth/crypto-strategy-lab/actions/workflows/ci.yml/badge.svg)

**Lab eksperimen strategi kripto otomatis, berjalan lewat GitHub Actions, tanpa transaksi riil.**

✅ [Hasil simulasi terakhir](data/report.json) · 📚 [Event ledger permanen](data/events/) · 📊 [Dashboard source](dashboard/index.html) · ⚙️ [Workflow otomatis](.github/workflows/lab.yml) · 🧪 [Pengujian](tests/)

## Status operasional

Eksekusi v8 pertama berhasil pada **8 Oktober 2026, pukul 10.18 WIB**, mencatat 6 eksperimen LAB-116–121 menggunakan snapshot **OKX USDT perpetual**; hash-chain ledger telah diverifikasi. Lihat [run pertama](https://github.com/0xzein-eth/crypto-strategy-lab/actions/runs/37722057618). Data terbaru selalu ada di `data/report.json`, bukan di teks README ini.

**Jadwal otomatis internal GitHub:** paper lab menit **04, 14, 24, 34, 44, dan 54 UTC** (setiap 10 menit), dengan **dua clock pemulihan terpisah** pada menit **02/12/22/32/42/52** dan **09/19/29/39/49/59**. Keduanya menggunakan `GITHUB_TOKEN` bawaan, memeriksa laporan resmi terbaru serta workflow yang sedang berjalan, dan baru meminta `workflow_dispatch` jika laporan berusia lebih dari 14 menit. Pemicu cadangan saling dikunci untuk membatasi duplikasi; jadwal GitHub tetap *best effort* dan tidak dijamin tepat waktu. [Dokumentasi dan keterbatasan](OPS_RELIABILITY.md). Laptop pengguna tidak perlu menyala. Pada kondisi normal engine mengupayakan hingga 14 eksperimen baru per run (hard cap 24), dengan batas **850 OPEN bersamaan**, **50 OPEN per aset** dan **1.400 OPEN baru per hari UTC**, tetapi **tanpa batas seumur hidup 80 record**. Ketika posisi jatuh tempo, penyelesaian dilakukan terlebih dahulu memakai snapshot segar; harga historis tidak dicari untuk menyamarkan keterlambatan.

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

The lab now scores a frozen set of **14 auditable paper-only strategy hypotheses** and continuously reallocates *future* experiments. The learner excludes late closes and spot proxies, retains precommitted controls, evaluates day-cluster lower bounds, and maintains a reproducible date-partitioned monitoring sample. Until strict training/monitoring/control thresholds are met, **no strategy is provisionally preferred**. A provisional leader is not proof of profitability. New signal families are versioned rather than generated through unreviewed arbitrary code.

- [Read the learning design](LEARNING.md)
- Dashboard now displays adaptive arm evidence, monitoring samples and provisional status.
- Normal target: **14 new experiments per scheduled run** (hard max 24; 850 OPEN overall; 50 OPEN per symbol; UTC day cap 1,400), if source and strategy filters allow.
- [Schedule guardian](.github/workflows/health.yml) dan [redundant clock](.github/workflows/rescue.yml) memeriksa integritas event, mencegah pemicu berulang, dan memicu pemulihan jika perlu. **Baru:** setelah run yang terlambat berhasil, [recovery_window.py](recovery_window.py) dapat mengambil maksimal enam snapshot baru dengan jarak nyata 10 menit, lalu berhenti. Indikator `estimated_10m_slot_coverage` dalam [report](data/report.json) memperlihatkan perkiraan slot yang berhasil dari 72 jeda observasi terakhir; perlu minimal 12 jeda untuk interpretasi. Semua tetap penelitian tanpa order riil; cron GitHub tidak menjamin 24/7.

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

## v9 — Historical Research Factory (terpisah dari paper ledger v8)

**Aktif:** [workflow riset v9](.github/workflows/research.yml) · [laporan hasil backtest terbaru](research_results/latest.json) · [metodologi dan cara menjalankan](RESEARCH_V9.md).

Research Factory otomatis mengumpulkan confirmed 15m OHLCV OKX perpetual dengan cache historis berintegritas, menguji sekitar **250 varian** aturan dan parameter terhadap **8 aset kandidat** (jika feed tersedia), dan menggunakan tiga validasi walk-forward terpisah secara kronologis dengan purge/embargo. Laporan dibuat setiap hari sekitar **10:19 WIB** oleh GitHub Actions (best effort). Siklus tambahan bisa dijalankan manual melalui tab Actions.

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


### Historical research v9.3 — 750 deterministic backtest hypotheses
The Research Factory increases its predeclared **historical-only** grid
from 500 to **750** independent *parameter variants* (not 750 proven
or executed strategies). The first 500 variant IDs and their ordering
remain byte-for-byte stable; beyond them the factory adds:
Donchian price-channel breakout plus historical-volume confirmation,
z-score continuation filtered by trailing SMA50/SMA20 trend, and
RSI-trend continuation gated on SMA50. All use confirmed 15-minute
OHLCV and enter at the **next** bar open in historical approximation;
same 8 OKX perpetual funding-aware symbols, 90-day common analysis
window, purged 96-candle walk-forward, fees/slippage stress and
unchanged manual-only promotion. 750 related hypotheses substantially
increase multiple-testing risk and do not establish profitability.

The canonical scheduled paper workflow and each bounded 10-minute observer
pass `--count 30`, but **the engine never actually opens 30** unless
the independent rolling sample coverage meets its predeclared
quality threshold and symbol/15m/day/source gates permit. Recovery
after a long scheduling gap still caps new entries at three.


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
The historical 750-variant walk-forward additionally publishes for each
training fold the count of candidates failing sample/day/positive-day-bound
requirements plus up to ten highest-scoring **disqualified training-only**
variants. These are explicitly NOT selected for validation, promotion,
or live trading; the previous positive-bound selection criterion is
unchanged.


### Shadow validation of rejected historical hypotheses

V9 historical research can validly report **zero** positively selected
strategy variants after 750 tests. Instead of claiming the least-bad
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
