# Crypto Strategy Lab — Peta Jalan Induk 2026–2027

**Status:** rencana teknis dan kriteria penerimaan yang dapat diaudit, bukan janji untung. Sistem ini **PAPER ONLY**, tidak mengirim order asli. Seluruh hasil observasi pada `data/events/` adalah ledger append-only; tidak boleh ditulis ulang untuk memperbaiki statistik. Kebijakan exit tetap **1/2/4/8/12/24 jam fixed-horizon**, TANPA SL, TP, trailing stop, backfill harga atau entry retroaktif.

## Sasaran yang terukur

1. **Keandalan data**: harga publik segar, instrumen dan venue sama ketika OPEN/CLOSE; asal candle dan status konfirmasi dapat diuji; semua observasi terlambat diberi label dan tidak diperlakukan seolah tepat waktu.
2. **Kuantitas yang benar**: lebih banyak **slot instrumen × 15 menit unik, hari entry, pekan, rezim, dan pasangan kontrol**; bukan menghitung ribuan perdagangan berkolerasi sebagai bukti independen.
3. **Kualitas penelitian**: nilai harapan (net R) setelah fee dan secara terpisah biaya stress, pembandingan kontrol setara, ketidakpastian berkelompok berdasarkan hari/pekan dan pengujian yang tidak bocor.
4. **Strategi yang falsifiable**: setiap varian punya syarat konkret, sumber data entry nyata, versi sinyal, uji lookahead/duplikasi, evaluasi beberapa horizon, dan status eksperimen yang jelas.
5. **Operasional GitHub**: bisa dipelihara tanpa API trading, memakai Actions GitHub bawaan; biaya runner, storage dan kuota diperhatikan.

## Arsitektur dan pekerjaan yang dipetakan

| Lapisan | Implementasi | Ukuran kualitas |
| --- | --- | --- |
| Market data | `engine.quote`, `signals.parse_okx_candles` | jumlah quote perpetual valid, status 403/451/timeout, stale/rejected candle, cakupan instrumen |
| Ledger / simulasi | `engine.py`, `audit.py` | seluruh hash-chain terverifikasi, ZERO synthetic OPEN/CLOSE, durasi fixed-horizon tepat |
| Scheduler | `lab.yml`, `recovery_window.py`, `scheduler_guard.py` | rasio slot 10 menit tercakup, jeda terburuk, pos yang melewati 30 menit |
| Intake / sampling | `universe.py`, `learner.py`, `entry_sampling.py` | entry per simbol-slot; *confirmed signal opportunities* dan entry aktual, 7-day original OPEN counts |
| Strategy catalogue | `signals.py`, `regime_hypotheses.py` | confirmed 15m candle, entry-frozen regime, no lookahead, pre-registered label |
| Prospective outcomes | `outcome_stats.py`, `temporal_evidence.py` | eligible closed per arm/horizon, distinct UTC days/weeks, concentration, P&L fee-only |
| Independent comparisons | `matched_controls.py`, `negative_edge_diagnostic.py`, `regime_evidence.py` | strict one-to-one controls, actual matched fraction, training-only negative warnings |
| Statistical gates | `research_quality.py`, final future test protocol | readiness, paired day clusters, family-wise multi-test correction; NO auto promotion |
| Historical factory | `research_results/latest.json` / v9 | historical walk-forward, funding gaps, holdout sensitivity; **never counted as forward paper** |
| CI and reporting | `.github/workflows/`, `data/report.json` | test + audit success, tip SHA, coherent evidence interpretation |

## Fase 0 — utamakan kejujuran dan integritas (selesai; dijaga selamanya)

- Tidak pernah merekayasa harga, mengubah timestamp, menutup posisi sebelum evaluate_at, atau melompat penyedia dari OPEN ke CLOSE.
- Dataset terbagi jelas: quote sesungguhnya yang diamati, ledger OPEN/CLOSE prospektif, dan 1.600 varian *historical backtest* hipotetis.
- Menolak klasifikasi sebagai "champion" hanya karena win rate tertinggi, banyak trade, atau hasil 1–2 minggu.
- Setiap perubahan terhadap kontrak fixed-horizon atau live trading di luar cakupan roadmap ini, memerlukan persetujuan pengguna tersendiri.

## Fase 1 — ketahui berapa sinyal yang *benar-benar tersedia* (dikerjakan sekarang)

**Kesenjangan:** BRREG-v1/TPREG-v1 memiliki terlalu sedikit CLOSE; belum diketahui apakah sinyal jarang muncul, jarang dipilih, atau entry ditolak karena quote baru berbeda/tidak segar.

**Implementasi:** satu audit kesempatan pada setiap tick:
- jumlah simbol ber-quote valid; simbol-slot yang benar-benar dipertimbangkan;
- jumlah deteksi masing-masing strategi berdasarkan candle OKX 15m konfirmasi dan ticker benar;
- terpilihnya strategi ke OPEN nyata dan reject karena fresh reobservation;
- jumlah entry strategi selama 7 hari terakhir, termasuk yang kalah atau terlambat, berdasarkan metadata OPEN saja.
- *Coverage-first sampling*: maksimal 25 dari 100 bucket deterministik khusus kandidat ADVANCED yang benar-benar tersedia dapat memilih arm yang paling kurang terwakili; hak CTRL minimal 20% bucket dipertahankan. Tidak ada strategi palsu, bypass 1 OPEN per simbol per 15m, atau reward-based promotion.

**Gate sukses:** CI & hash-chain audit lulus; pada tick yang belum ada confirmed signal, audit menampilkan nol peluang dan tidak menciptakan advanced arm; ubah P&L historis secara arbitrer tidak mengubah entry counts / probabilitas pilihan.

**Peringatan:** pilihan coverage-first meningkatkan kesempatan *mengukur* arm langka, **tidak membuktikan arm itu menguntungkan** dan dapat mengubah distribusi sampel (wajib dibedakan sebelum/ sesudah versi).

## Fase 2 — transparansi underperformers & biaya (sekarang, read-only)

- Terbitkan dua label training-only secara **terpisah**: (a) expectancy absolut konsisten negatif menurut hari entry, (b) perbedaan *matched* terhadap CTRL-v1 negatif dengan jumlah pasangan dan hari mencukupi.
- Arm tanpa kontrol sebanding berstatus **belum dapat dibandingkan**, bukan strategi lebih baik/buruk dari kontrol.
- Segregasikan `normalized_R` berbasis fee dari `stress_normalized_R` berbasis spread/impact asumsi tambahan. Jangan menjumlahkan biaya dua kali.
- Monitoring 20% UTC-day tidak ikut keputusan alokasi, dan monitoring lama tidak dianggap holdout akhir yang sepenuhnya baru.

**Gate sukses:** laporan menyertakan kontrol pasangan benar-benar tercocok, fraction, training days dan sifat deskriptif; tidak pernah mematikan strategi atau mengubah trade CLOSED secara otomatis.

## Fase 3 — sampel independen lintas kalender (4–12 minggu aktual, belum selesai)

Ambang **readiness**, bukan bukti alpha:
- minimal **20 UTC entry days**, **4 ISO weeks**, setidaknya 5 weekday;
- minimal 10 hari dengan rezim rising/falling tercakup, 6 hari dengan keempat band waktu UTC 6 jam;
- minimal 100 pasangan CTRL untuk arm yang diuji, setidaknya 25 matched holdout pairs dari beberapa hari dan >=50% pencocokan bila realistis;
- pastikan sumber perpetual, tanggal OPEN, durasi horizon, dan kelompok biaya cocok;
- cakupan jadwal >=90% sebagai syarat riset temporal, sambil menampilkan missed slots; target ini tidak mengubah keterlambatan lama.

Tidak ada cara sah memadatkan **4 pekan kalender** menjadi satu jam atau menggandakan trade simbol berkorelasi untuk menggantikannya.

## Fase 4 — validasi falsifikasi strategi (mulai setelah Fase 3)

1. Bekukan keluarga hipotesis (termasuk horizon 1/2/4/8/12/24 jam), filter, tanggal mulai dan metrik primer **paired net R after fees / stres terpisah**.
2. Bandingkan pada stratum sama: simbol, hari UTC entry, LONG/SHORT, regime, horizon, gap <=120 menit; tidak pakai pasangan kontrol ulang **di dalam satu arm**.
3. Kelompokkan interval ketidakpastian menurut hari/pekan, koreksi banyak pengujian (Holm atau simultan block bootstrap berasumsi terjelaskan).
4. Uji ketahanan pada aset dan hari dominan, fee/slippage stress, perubahan volatilitas, hari libur dan berkurangnya uptime cron.
5. Setelah seleksi apa pun, mulai **periode final prospektif baru yang belum diintip sama sekali**. Tidak ada parameter/threshold/strategi yang di-tune di tengah periode validasi.

**Kelulusan:** hasil positif vs kontrol pada beberapa pekan dan rezim + setelah stress asumsi wajar + ketidakpastian memadai; tidak boleh menjanjikan untung trading sungguhan.

## Fase 5 — kebijakan alokasi kandidat pemenang (hanya setelah terbukti dan disetujui)

- Buat PR versi allocator berikutnya; test invariants, pembanding kontrol tetap, eksplorasi wajib, limit exposure/slot dan intake throttling.
- Hanya berlaku pada **OPEN di masa depan**; data lama tak bisa mengganti nama strategi atau harga.
- Tetap tidak mengaktifkan *live orders*, leverage nyata, ataupun SL/TP/trailing.

## Pengukuran harian, mingguan, bulanan

| Frekuensi | Deliverable | Tindakan bila gagal |
| --- | --- | --- |
| Setiap tick | `data/report.json` dengan status data, opportunities, OPEN, CLOSE, due, sampel kualitas | fail closed pada integritas, tidak buat entry dari data tidak segar |
| Harian | Hash ledger, warnings expectancy, input/entry/source coverage dan artifact dari Actions | periksa missing source, scheduler gap, matching rendah |
| Mingguan | Kelompok arm × rezim × horizon; pemisahan training/monitoring, matched fraction, biaya | jangan promosi hanya karena WR atau hasil positif sesaat |
| Bulanan | Evaluasi jendela kalender 4 pekan, jumlah arm dan biaya CI/storage, drift market | revisi calon hipotesis melalui PR baru dan test |
| 3/6/12 bulan | Review efektivitas sistem, kebutuhan infrastruktur terpisah, ketahanan statistik | tetap paper-only sampai standar dan persetujuan terpenuhi |

## Prioritas sprint setelah merge

1. Verifikasi *forward* opportunity-audit di tick GitHub nyata setelah code merge; ukur BRREG/TPREG: **candidate opportunities vs selected OPENs vs eligible CLOSEs**.
2. Stabilkan scheduler hanya bila data menunjukkan gap; **jangan** memalsukan missing ten-minute slots. Tinjau kemampuan kuota GitHub Actions 3 jam runner serta storage ledger yang membesar.
3. Tambahkan laporan kesehatan data per-strategy/horizon (source failure, lateness, control match rate, stress costs) bila belum tertangkap oleh report saat ini.
4. Setelah minggu baru benar-benar berlalu, nilai konsentrasi dan kesiapan validasi; buat threshold changes **versi baru**, tidak berdasarkan trade pemenang kebetulan.

**Definisi selesai untuk sprint saat ini:** kode dan fixture tests lulus, PR ter-merge, source ledger terbukti tetap utuh, peluang dan hasil bisa dibedakan, roadmap di-repository. **Definisi selesai untuk menemukan strategi terbaik:** belum dapat dipenuhi tanpa masa depan prospektif dan pembuktian statistik.
