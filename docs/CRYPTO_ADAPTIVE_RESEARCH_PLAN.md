# Rencana kasta dan retest crypto — epoch riset adaptif v1

Tanggal registrasi kode: 22 Oktober 2026. Berlaku hanya pada observasi
prospektif epoch `adaptive_lab`, terpisah dari v8, trial v2 yang dibekukan,
Nasdaq, LQ45, dan backtest v9. Tidak ada order bursa atau klaim probabilitas
profit. Kasta adalah prioritas pengujian menurut bukti yang terukur.

## Audit kebutuhan

Baseline sudah memiliki 2.400 varian historical v9, 26 arm shadow v2, tetapi
observer v2 dibatasi BTC/ETH/SOL, slot 30 menit dan kebijakan trial beku.
Mengubah trial menjadi allocator adaptif akan merusak eksperimennya.
Mengulang backtest yang sama atau menaikkan trade yang bertumpuk tidak
menambah periode validasi independen. Funding dan spread harus terukur,
biaya impact tetap skenario, bukan angka fill bursa.

## Desain dan batas penerimaan

- Epoch baru mengamati hingga 16 kontrak OKX USDT-SWAP, candle 15m confirmed,
  best bid/ask beserta depth dalam unit aset, metadata ctVal, dan settled
  funding. Metadata kontrak wajib linear/live/USDT dan cocok dengan simbol.
  Tidak memakai harga spot sebagai pengganti perpetual. Partial source
  outage boleh dilaporkan; posisi tanpa quote exit tetap pending dan exit
  terlambat tidak layak mengubah kasta.
- Katalog berisi 24 spesifikasi tunggal dari beberapa keluarga dan enam
  horizon 1/2/4/8/12/24 jam: **144 hipotesis baru**. Lima resep gabungan
  2-dari-3 dengan veto konflik × enam horizon memberi **30 hipotesis
  cadangan**; aktivasi keturunannya hanya setelah diagnosis parent rendah.
  Seluruh 174 identitas, aturan, dan horizon didaftarkan sebelum hasilnya.
- Candle sumber dan metadata observasi disimpan gzip, hash-chain dengan
  sequence dan fingerprint kode. Semua hasil/keputusan direplay dari sumber.
  Perubahan aturan memerlukan epoch/path baru; histori tidak direlabel.

| Status | Syarat | Kesempatan jalur prioritas |
|---|---|---|
| BELUM CUKUP BUKTI | Belum memenuhi seluruh minimum | Setiap 30 menit |
| RENDAH | Tiga blok uji berturut-turut net stress negatif | Setiap 4 jam |
| SEDANG | Minimum terpenuhi tetapi hasil campuran atau gate tinggi belum lolos | Setiap 1 jam |
| TINGGI | Tiga blok berturut-turut positif setelah biaya dan vs kontrol, LCB harian positif, serta koreksi pengujian lolos | Setiap 15 menit |

Ini kesempatan maksimum saat ada sinyal autentik, bukan kewajiban membuka
trade. Maksimum satu hipotesis aktif per strategy×symbol **per jalur**; fixed horizon,
tidak ada SL/TP atau entry retroaktif. Cadence GitHub best effort.

## Retest yang dihitung

Satu blok = 14 hari UTC sejak observasi pertama epoch; klasifikasi hanya
dievaluasi saat blok selesai. Entry pada 24 jam terakhir blok tidak masuk
sampel klasifikasi sehingga exit tidak menyeberang blok. Setiap blok valid
per strategi perlu >=30 pasangan CLOSED tepat waktu, >=10 hari entry dan
>=2 instrumen. Sebelum memperoleh kasta: >=100 pasangan, >=20 hari entry,
>=4 ISO weeks, dan tiga blok berurutan yang valid. Tidak ada kasta yang
dibentuk dari seed backtest lama, data sintetis, atau jumlah run workflow.

Setiap pasangan membandingkan sinyal dengan arah netral deterministik
pada simbol, waktu, horizon dan book yang sama. Biaya mencakup bid/ask,
fee taker kedua sisi, funding settled yang cakupannya diperiksa, serta
stress tambahan 30bp. Unknown funding berarti hasil tidak layak untuk
klasifikasi. Model ini masih simulasi; impact/latency nyata belum terbukti.
Jadwal funding diinferensikan dari empat settlement terakhir yang teramati
sebelum entry dan dibekukan. Setiap pembayaran yang diharapkan harus muncul
pada timestamp yang tepat; interval berubah atau pembayaran hilang menjadi
UNKNOWN. Ini skenario constant-notional, bukan rekonsiliasi akun bursa.

Maksimum 32 admissions per tick: **8 eksplorasi outcome-neutral** dan 24
prioritas. Pemeringkatan kasta hanya memakai sampel jalur eksplorasi;
hasil jalur prioritas dilaporkan terpisah. Dengan demikian memperbesar
frekuensi strategi tinggi tidak otomatis memperbesar bukti klasifikasinya.
Posisi jalur prioritas tidak boleh memblokir slot jalur eksplorasi. Masing-
masing memiliki aturan non-overlap sendiri; keduanya bukan akun bermodal.
Weighted sampling prioritas memakai bobot tinggi/sedang/belum cukup/rendah
12/4/2/1, tetap dengan batas per instrumen dan keluarga.

Uncertainty memakai rata-rata harian, bukan menganggap semua trade iid.
Gate tinggi memakai one-sided day-sign test, Holm untuk seluruh 174
hipotesis termasuk yang gagal/diam, dan alpha budget 0,05/[k(k+1)] pada
checkpoint ke-k untuk membatasi repeated looks. Asumsi tanda harian
independen/simetris tetap terbatas oleh dependensi pasar; hasil adalah
triase eksploratoris, bukan alpha terjamin. Setelah lima blok berturut-turut
positif dan seluruh gate, strategi baru masuk **packet calon untuk review**;
tidak otomatis diaktifkan pada wallet atau dipromosikan ke trading nyata.

## Evaluasi kasta rendah dan strategi keturunan

Jika tetap rendah >=28 hari sejak klasifikasi rendah, buat diagnosis per
strategi: price edge vs fee/spread/funding/stress, match coverage, lateness,
peluang sinyal dan penolakan liquidity. Tidak membalik arah secara otomatis
hanya karena hasil rugi. Resep gabungan yang sudah didaftarkan dapat aktif
bila semua parent pada horizon yang sama memerlukan evaluasi tersebut.
Anak memiliki ID, lineage, waktu aktivasi dan sampel baru; tidak mewarisi
hasil parent, tidak masuk kasta tinggi secara otomatis, dan tidak mengubah
parent. Jumlah anak dibatasi 30 untuk mencegah pencarian tanpa batas.

## Operasional dan pengembangan lanjutan

1. Implementasi katalog, sumber, allocator, tier gate, replay, diagnosis,
   child activation, workflow, serta fixture negatif sebelum mulai epoch.
2. Jalankan capture publik nyata dan verifikasi replay; laporkan jumlah
   instrumen sukses, data gagal, peluang, admissions dan pending asli.
3. Workflow 15 menit mengumpulkan observasi; report/artifact menyimpan
   keputusan, hash, denominators, dan alasan belum cukup bukti. Jadwal baru
   aktif setelah perubahan diterapkan di GitHub.
4. Review kuota/storage mingguan. Gzip mengurangi duplikasi tetapi tidak
   menjamin skalabilitas bertahun-tahun; pindah ke object storage/checkpoint
   tervalidasi sebelum journal replay melampaui batas runner. Jangan hapus
   raw evidence diam-diam. Simulasi shadow tidak mengalokasikan modal nyata.
5. Setelah >=42 hari nyata, nilai checkpoint dengan bukti yang tersedia;
   >=70 hari diperlukan untuk lima blok calon review, lebih lama bila
   sampel kurang. Membership/source universe dan parameter baru memakai
   versi/epoch baru, bukan tuning pada periode yang sedang dinilai.

## Riset dan sumber

- Dokumentasi resmi OKX API v5, bagian candles, books, instruments dan
  funding-rate-history: https://www.okx.com/docs-v5/en/ — diakses 22 Okt
  2026, termasuk pemeriksaan respons publik nyata. Perhatikan ctVal dan
  funding history terbatas; tidak mengasumsikan funding lama tersedia.
- Bailey & López de Prado, *Deflated Sharpe Ratio* (2014):
  https://doi.org/10.3905/jpm.2014.40.5.094
- Bailey et al., *Probability of Backtest Overfitting* (2017):
  https://escholarship.org/uc/item/4w1110bb

Dua referensi metodologi terakhir sudah dirujuk blueprint repositori;
pengambilan halaman pada sesi ini ditolak proxy 403. Karena itu tidak
mengklaim melakukan pembacaan ulang teks penuh atau mengimplementasikan
DSR/PBO. Implementasi memakai kontrol eksplisit di atas, bukan nama metode
tersebut sebagai jaminan kelulusan.
