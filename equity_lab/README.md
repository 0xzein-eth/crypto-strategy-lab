# Nasdaq + IDX LQ45 Research Lab (21 October 2026)

**Two isolated cash-paper accounts. Zero broker orders.** Neither this
project nor a 14-arm stress test guarantees high WR, profitable ROI, or a
tradeable signal. It does not edit the original cryptocurrency v8/v2 paper
ledger or `stock_lab_state/` prior-epoch records.

## Current frozen research population

| Venue | Watchlist | Cash PAPER seed | Currency | Local EOD |
|---|---|---:|---|---|
| US Nasdaq | **25 specifically Nasdaq-listed liquid-company tickers** (NOT the complete Nasdaq-100 constituent registry) | 10,000 | USD | 19:00 ET |
| IDX LQ45 | **45-name LQ45 August–October 2026 snapshot** | 10,000,000 | IDR | 18:00 WIB |

All 45 LQ45 names are frozen from the published effective August 3–October
30 2026 list, including `INDY.JK` and `NCKL.JK`, but not departed
`SMGR.JK` or `TOWR.JK`. Relevant sources:
[IDX index landing page](https://www.idx.co.id/id/data-pasar/data-saham/indeks-saham/),
[dated constituent snapshot](https://www.investasiku.id/eduvest/saham/perusahaan-di-bei-yang-masuk-lq45),
[Aug 2026 rebalance](https://ajaib.co.id/belajar/saham/rebalancing-lq45-idx30-dan-idx80).
**LQ45 is fail-closed after October 30, 2026** pending next constituent
review. It is not silently assumed to contain the same 45 firms forever.
Nasdaq ticker cohort is 25 Nasdaq-listed equities rather than an assertion
that each is currently a Nasdaq-100 constituent or that they represent the
entire U.S. exchange. We do **not** convert USD equity into IDR or merge
account equity curves.

**Index benchmarks:** `^NDX` (Nasdaq-100, USA) and `^JKSE` (IHSG,
Indonesia). These are price-index **references, not shares** with executable
broker fills. No ETF proxy is silently substituted. On a missing benchmark,
the source outage is reported and relative assertions withheld.

## Data integrity / automatic scheduling

`equity_lab/source.py` fetches authentic provider daily bars from public
Yahoo chart endpoints for all frozen members independently with bounded
concurrency and explicit per-symbol error reporting. At least eight
synchronized **genuinely published completed** EOD stock bars are needed
per journal event. Data provider is NOT the exchange, and retrospective
`next session OPEN` is NOT an actual order fill. Dividends, FX,
delistings, total returns, true index membership as of every prior bar,
auction execution and market impact remain incompletely modeled.

[Dual Equity Lab workflow](../.github/workflows/dual-equity-lab.yml):

- **Nasdaq**: approximately 21:25/23:55 ET under daylight time,
  20:25/22:55 in standard time, Mon–Fri US local. Cron occurs Tue–Sat UTC
  and may be delayed/skipped by GitHub Actions.
- **IDX LQ45**: 19:35 and 21:20 WIB Mon–Fri (subject to exchange holidays
  and valid latest completed bar). A repeated session is not double-booked.
- Historical research and simulated forward wallet derive from one same
  public EOD source capture, avoiding unnecessary duplicate provider calls.
- Original IDX 6-symbol 4-arm workflow is **retired from automation**,
  preserved only for read-only archival audit and not rewritten.

## Strategy research

All 14 pre-existing rule names (`stock_lab.strategies` four families +
`stock_lab.experimental` ten families) now run as **NEW** research
identities in the dual-market epoch. They operate on last completed local
OHLCV and may only open an assumed **next observed session OPEN**. The
forward wallet picks among contemporaneous BUY proposals by a fixed hash
of symbol/arm/prior session, never the strategy with best P&L known
afterwards. It is one-wallet-per-venue, max three symbols, max 25% of
equity per entry, no shorts/leverage, USD single shares vs IDX 100-share
lots. There are separate modeled U.S. / Indonesian fees and conservative
one-/two-session sale settlement. Holdings have five session fixed exits.
New simulated entries stop after 10% observed peak drawdown. Corporate
actions while holding cause an explicit hard stop rather than a fake P&L.

`equity_lab/research.py` evaluates 14-arm hypothetical historical
five-session return cohorts with 60/20/20 chronological periods and
five-session purge, nonoverlap **per ticker+arm**, modeled brokerage fees
and adverse entry/exit plus **25bp additional roundtrip cost stress**.
Historical study outcomes are NOT credited as funded forward paper P&L.
Train-only descriptive research rankings NEVER auto-activate or pick a
champion. Reviewed historical holdouts are not clean independent data.

Actual per-market forward metrics are computed **only from replayed,
hash-linked, authentic future EOD journals** under `equity_state/NASDAQ/`
and `equity_state/LQ45/`:
`report.json`, `equity_curve.json`, and `observations.jsonl`.
Before there are genuinely completed trades, P&L is zero or unknown;
win rate / profit factor are `null`, not a fabricated 100%.

## Development / tests

**Policy v2 (22 October 2026):** new observations use prior-session volume,
prior observed equity and prior drawdown for hypothetical OPEN decisions.
The current day's CLOSE cannot change that OPEN allocation. A missed next
session or a signal recorded after its OPEN prevents a retroactive entry.
Existing v1 observations retain their original replay policy and hashes;
new records identify v2 explicitly, with policy downgrade rejected.
`--verify-only` reconciles both saved report and equity curve against the
source journal and refuses missing/divergent outputs. It never repairs or
rewrites evidence. Calendar holidays and corporate-action modeling remain
incomplete; weekday checks do not constitute an official exchange calendar.

```bash
python -m unittest discover -s tests -p 'test_equity_lab.py' -v
python -m unittest discover -s tests -p 'test_equity_audit_regression.py' -v
python -m equity_lab.forward --market NASDAQ --verify-only
python -m equity_lab.forward --market LQ45 --verify-only
# Only after each market's true daily close:
python -m equity_lab.forward --market NASDAQ --observe
python -m equity_lab.forward --market LQ45 --observe
```

The offline fixtures are synthetic and never used as results or written
to production state. Crypto stays independent and must establish positive
after-cost, independently forward-validated expectancy before any
performance claim.
