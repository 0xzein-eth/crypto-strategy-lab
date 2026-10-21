# Stock Strategy Lab — IDX cash equity (standalone PAPER ONLY)

**Independent subproject** inside [crypto-strategy-lab](../README.md).
This is **not** a branch of the cryptocurrency strategy simulator, a
registered broker, an actual order manager, a guaranteed signal, or a
promise of any level of win rate. Only fully funded, ordinary local
IDX cash equities are permitted. **No leverage, no futures, no short,
no real-money transactions, no API credentials and no account linkage.**

## Daily automated research

Source: anonymous public Yahoo Finance chart response with `.JK`
symbols, **unofficial** relative to IDX, availability and rate limits
NOT guaranteed. First fixed research universe:

| Symbol | Issuer | Research purpose |
|---|---|---|
| BBCA.JK | Bank Central Asia | liquid bank equity |
| BBRI.JK | Bank Rakyat Indonesia | liquid bank equity |
| BMRI.JK | Bank Mandiri | bank/market regime |
| TLKM.JK | Telkom Indonesia | telecom sector |
| ASII.JK | Astra International | diversified cyclical |
| ICBP.JK | Indofood CBP | consumer defensive |

A 2-year **historical** price window is loaded for computing features.
Historical candles supplied on first fetch are **not forward trades**.
Future-only observations start with the first successful completed
daily candle collected after deployment, using journal
`stock_lab_state/observations.jsonl`. Hash SHA256 verifies every
single record. Source market/currency/symbol/time/calendar conditions
fail closed when incomplete.

The machine runs best-effort at approximately **18:15 and 19:20 WIB
Monday–Friday** through [stock-lab.yml](../.github/workflows/stock-lab.yml).
Yahoo end-of-day publication can be delayed. Do NOT count cron success
as confirmed market availability. GitHub Actions stores a separate
source-health diagnostic on every run (even on failure). The effective
cash portfolio state, closed trade records, an EOD equity curve and a
**separate all-arm shadow research report** are replay-derived from
that hash-linked source, never from fabricated prices.

## Four fixed, distinct research hypotheses

| ID | Long-only prospective BUY proposal | EXIT research signal |
|---|---|---|
| TREND20_60 | SMA20 > SMA60 and completed close reclaims SMA20 after pullback | close below SMA20 |
| BREAKOUT20 | confirmed 20-session closing breakout on >=1.15× recent volume | bearish 10-session low or below SMA20 |
| RSI_REVERT | RSI14 oversold <=34, below SMA20 with broadly stable 60-day mean | RSI14 >=56 or mean reversion completed |
| LOWVOL_MOM | 20-session momentum 3–18%, low trailing daily volatility and positive trend | trend/momentum breaks |

Signals are computed only after the day is fully closed. A proposal from
session D is hypothetically priced at the next actually received
session D+1 **OPEN** with 10bp adverse friction, but this open is
known to this observer only AFTER the full D+1 EOD bar arrives.
**These are retrospective models of hypothetical execution, NOT
contemporaneously observed, executable bids/asks or broker fills.**
Any practical live implementation will require a dedicated licensed
data source and separately approved brokerage connectivity.

All four families receive future-only 5-session hypothetical
shadow markouts independent from the funded paper account.
The limited cash portfolio chooses its proposed family with a
fixed deterministic pre-outcome hash among eligible signals,
never according to recent winner rankings.

## Research expansion (21 October 2026) — HISTORICAL ONLY

The **original 6 stocks and 4 strategy IDs remain frozen** in the prospective
one-wallet paper journal. To increase independent research breadth *without
rewriting the past*, a **separate** `stock_lab/experimental.py` catalogue adds
10 predeclared daily-bar BUY hypotheses:

`TREND_RECLAIM30`, `DONCHIAN40`, `DONCHIAN60`, `RSI_RECOVERY35`,
`BOLLINGER_REENTRY20`, `VOLUME_SQUEEZE20`,
`VOLUME_CLIMAX_FADE`, `ATR_EXPANSION14`, `MOMENTUM60`,
`LOWVOL_PULLBACK60`.

The historical *research-only* sample targets 18 Indonesian shares. In
addition to the original six: BBNI, UNTR, INDF, KLBF, ANTM, PTBA, PGAS,
ISAT, SMGR, CPIN, MYOR and AMRT (Yahoo `.JK` tickers). This is NOT an
expansion of the funded paper wallet or a declaration that all tickers are
always available. An unavailable, stale, incorrect or partial provider
record is logged and skipped; the study requires **at least 6 authentic
tickers and 250 aligned EOD sessions**, otherwise results are withheld.

`stock_lab/expanded_research.py` computes historical five-session
next-open-to-next-open returns with existing brokerage fee/impact
assumptions **plus a further 25bp round-trip stress**. Chronological
60/20/20 training, validation and repeatedly-inspected historical
holdout periods have a 5-session purge. Same strategy / same ticker
overlapping returns are excluded. Reporting includes stressed win rate,
profit factor, average after-cost return, after-stress excess return
relative to a same-date survivor basket, worst trade and worst
signal-day average. The metrics are **not portfolio ROI**: overlapping
trades across multiple tickers do not imply a funded account.
Training-only descriptive rankings never promote an arm or overwrite
paper execution. No true, pristine independent holdout exists yet.

Results, or an explicit real-source rejection manifest, are uploaded
as GitHub workflow artifacts under
[Stock historical research](../.github/workflows/stock-lab-research.yml).
This broader *survivor-selected* universe increases data breadth but
does not remove dividends, delisting, vendor quality or unobserved
open-auction execution biases.

## Paper capital and costs

| Constraint | Frozen starting assumption |
|---|---|
| Initial capital | Rp10,000,000 PAPER (not deposited) |
| Instruments | 6 fixed Indonesian ordinary shares |
| Quantity | integer multiples of **100 shares** |
| Position count | max 3 different stocks at any time |
| Size | at most 30% current hypothetical account equity per entry |
| Volume | maximum 1% of **previously completed trading session** volume (no future same-day volume) |
| Buy fee | assumed 0.15% |
| Sell fee | assumed 0.25% |
| Additional buy/sell open friction | 0.10% each side |
| Cash recycling | sale proceeds unavailable until **third subsequent recorded trading session**, conservatively longer than IDX regular-market **T+2** |
| Trading directions | BUY, HOLD, SELL possessed shares only |
| Maximum position time | 15 genuinely observed trading sessions |
| Actual submitted broker orders | **Zero** |

The fee settings are assumptions and exclude changing brokerage tiers,
tax details, commissions and any tax/levy not represented by those
rates. Official IDX orders/trades use regular-board 100-share lots and
T+2 settlement, while the Yahoo source is not authoritative for
exchange calendar, bid/ask, opening auction fills or volumes.

The quantity proposed for the next session uses account equity from
the **previous fully observed session** and the previous session's
trading volume. Sizing from the upcoming same-day closing price or
same-day full trading volume would leak future data and is explicitly
prohibited by a no-lookahead regression test.

Cash + unsettled sale receivables + estimated after-sell-fee value of
held shares forms the simulated equity. It is not withdrawable
money. The closed paper P&L is not a complete **total return**:
declared dividends and payment dates are not reliably reconciled.
A split while holding causes a *hard failure* rather than inventing a
share adjustment or calling the resulting price move a market loss.

## Pelatihan dan validasi historis otomatis (tanpa data bocor)

`stock_lab/research.py` menggunakan **aturan sinyal persis sama** dari
`stock_lab/strategies.py` yang digunakan observer harian, tetapi dengan
dataset masa lalu berlabel **HISTORICAL BACKTEST**, tidak disulap
menjadi transaksi prospektif. Dataset enam saham diselaraskan hanya
pada hari perdagangan yang sama-sama tersedia, dengan periode awal
minimum 200 hari bersama. Sinyal hari D hanya dihitung dari candle
D dan sebelumnya; uji hypotetical entry pada OPEN berikutnya
dan exit pada OPEN sesudah **5 sesi**. Hasil harus sepenuhnya berada
dalam split data yang sama, dengan embargo minimal 5 sesi, dan
melewati biaya broker/slippage asumtif yang sama seperti simulator.
Dividend/split di sepanjang jendela tidak diisi return rekaan;
transaksi tersebut dikecualikan.

Data dibagi kronologis **60% training, 20% validation,
20% historical holdout**. Strategi eksploratoris dipilih dari
training saja; validation/holdout tidak digunakan memilih lagi.
Pembandingnya adalah sekeranjang enam saham dengan periode dan
biaya asumsi serupa—**bukan indeks IHSG resmi**. Historis tetap
sudah diketahui dan dapat diperiksa berkali-kali, sehingga
**holdout ini bukan bukti independen yang belum tersentuh**.
Perlu penelitian prospective baru sebelum klaim alpha atau real trading.
[Workflow training/validation otomatis](../.github/workflows/stock-lab-research.yml)
dipicu setelah observasi EOD berhasil.

## Rigor, model training, future roadmap

The project inherits the **scientific controls** from crypto research,
not crypto-specific indicators, leverage assumptions or the impossible
$10k per-trade aggregate P&L:

- precommitted strategy IDs/versions, identical frozen signal
  calculations on history and new daily observations;
- no future-label lookahead, outcome-driven automatic promotion or
  silently changing the strategy family based on inspected winnings;
- real prospective matched days vs BTC-style candle count inflation,
  source-integrity hashes, reproducible one-wallet equity, cash/lot
  discipline, fee/impact stress, separate shadow experiments;
- explicit daily sampling availability and missing-session flags,
  holiday/disruption recognition, corporate-action completeness,
  **survivorship bias** from the fixed 6-name universe;
- next: official/licensed consolidated IDX history including
  dividends/splits, delisted stocks, adjusted total returns,
  continuous instrument liquidity / bid-ask depth, IDX holidays;
  realistic open-auction venue order fills and security-level
  simulated exchange fees; chronological purged walk-forward model
  training, bootstrap/UTC-day clustering, multiple-testing correction,
  future independent 60–90 trading-session holdout and cap on
  absolute/relative drawdown;
- until these are delivered, even positive paper WR or P&L is
  **exploratory only and absolutely not permission to trade live**.

You can alter this project independently without mutating v8
`data/events`, crypto v2 `v2_state`, historical crypto source
`v2_history`, or frozen crypto future-policy fingerprints.
Future strategy experiments need **new versioned cohorts** so
earlier forward results remain immutable.

### Commands

```bash
python -m unittest discover -s tests -p 'test_stock_lab.py' -v
python -m stock_lab.engine --verify-only
python -m stock_lab.engine --observe
```

`--observe` requires fresh, fully completed, same-date six-symbol
IDX data after **18:00 WIB**; if it is unavailable, fails without
creating fake events. Under test, every market record is explicitly
labelled synthetic, never inserted into operational Git records.
