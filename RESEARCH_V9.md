# Crypto Strategy Lab v9 — Historical Research Factory

## Operational separation

Version 8 remains the immutable-source-of-truth *prospective* paper lab.
Version 9 is a **separate historical backtesting research lane**. Neither its
candles nor its simulated entries/exits are ever appended to data/events/,
data/state.json, data/report.json, or legacy data/ledger.json. It cannot place
real orders and requires no private exchange credentials.

Version 9 adds:

- Public OKX USDT swap 15-minute confirmed OHLCV history with bounded paging,
  exact derivative instrument identity, no silent gaps, and strict cross-run
  overlap checks. Compressed symbol-specific caches are capped at 6,000 bars.
- A deterministic, predeclared factory of up to 250 parameterized variants
  across trend, momentum, mean-reversion, breakout, RSI, plus long and
  deterministic directional controls. Example production setting: 250.
- Fixed-horizon 1, 2, 4, 8, 24-hour **historical** simulation. Signal at the
  most recently finished 15-minute candle, hypothetical entry at NEXT candle
  OPEN, hypothetical exit at the future candle OPEN, no SL/TP.
- Assumed trading cost of 0.05% per side, plus separate 0.12% hypothetical
  spread/impact haircut. Funding, liquidation, orders, actual bid/ask fills,
  leverage and execution latency are **not fully modeled**.
- Chronologically expanding training with 96-bar purge/embargo before each
  of three subsequent validation windows. Training alone chooses candidates
  in each fold; validation never influences selection *within the same fold*.
  The validation windows are repeatedly inspected on future runs, so this
  method does NOT deliver a pristine final holdout.
- Day-grouped descriptive lower bounds rather than miscounting hundreds of
  correlated trades as independently verified evidence.
- Daily scheduled GitHub Action plus manual trigger, regression tests, fail-
  closed provider handling, and isolated Git history commits for research
  cache/report only.

## Execution

CI: \`python -m unittest discover -s tests -p 'test_research_v9.py' -v\`

Daily (network): \`python run_research_v9.py --symbols BTC ETH SOL LINK XRP ADA AVAX DOGE --cold-pages 16 --update-pages 10 --backfill-pages 60 --max-variants 260\`

Offline (requires already-populated cache): \`python run_research_v9.py --symbols BTC ETH SOL LINK XRP ADA AVAX DOGE --offline --max-variants 260\`

Workflow: \`.github/workflows/research.yml\`. Scheduled 03:19 UTC daily
(10:19 WIB), with GitHub Actions best-effort delivery. Public endpoints may
block GitHub IPs; status should FAIL when less than two usable instruments are
available. No fabricated prices, interpolated candles, or retroactive paper
fills are permitted. Eight requested instruments can be degraded to two while
explicitly listing errors. Fresh confirmed candle staleness cannot exceed 3h.

For prospectively observed strategies and valid OPEN/CLOSE records, continue
using \`.github/workflows/lab.yml\` and the v8 paper ledger. The historical
factory does not automatically change v8 live-paper policies.

## Files

| Path | Meaning |
|---|---|
| \`research_v9/history.py\` | OKX history ingestion, price quality & cache integrity |
| \`research_v9/factory.py\` | Predeclared variant grid, signals and chronological evaluation |
| \`run_research_v9.py\` | CLI and reproducible data provenance |
| \`research_cache/okx_swap_15m/*.json.gz\` | Compressed capped historical dataset; never v8 event data |
| \`research_results/latest.json\` | Historical outcomes, caveats, validation folds and source digests |
| \`tests/test_research_v9.py\` | Independent offline regression/anti-leakage tests |
| \`.github/workflows/research.yml\` | Scheduled validation and publishing |

## Interpretation and next research stages

A factory-generated winning curve is **not** proof of edge, and historical
backtests are not actual fills. Every scored strategy is vulnerable to
multiple-testing bias, hidden regimes, and missing execution frictions.
Fields \`proven_edge=false\` and \`champion=null\` are intentional. Promotion
to additional v8 prospective paper experiments requires a separate versioned
strategy bridge that preserves v8 auditable signal evidence; it is not
silently enabled by this change.

Suggested next stages: additional independent venues, funding-rate snapshots,
contract-specific bid/ask cost modeling, global-date anchored walk-forward
comparison, and explicit promotion-gated forward paper candidates.

## V9.1: deeper market history, observed funding, and independent gate

**Daily deeper candle backfill:** \`refresh_symbol\` now extends cache
*backwards* by up to **60 older history pages** per scheduled execution (bounded by 12,000 cached candles),
preserving all existing confirmed data and refusing silent gaps or overlapping
values that change. The cache holds a bounded 12,000 continuous bars per asset,
about 125 days of 15m observations. This faster bootstrap can expand by about 6,000 15m candles (roughly 62.5 days) per successful run until the cap, if OKX serves continuous historical data. It does **not** fabricate missing bars or guarantee coverage. Endpoint
pagination uses \`after=oldest_seen_timestamp\` for strictly older records and
validates every added page. The 8-asset research universe is unchanged.

**Settled funding-rate history:** New \`research_v9/funding.py\` obtains OKX
USDT-swap settled history and considers **realizedRate**, excluding projected
rates without confirmed settlement. It persists a compressed, contract-keyed
cache. Funding coverage requires all source events to span the whole candle
research interval, with no settlement-time gap larger than 12h. If provider
history is unavailable or incomplete, the affected asset is still backtested
for the fee + spread/impact baseline, but **funding-adjusted metrics remain
unknown** and cannot contribute to an automatic candidate-review pass.
Hypothetical constant-notional funding cash flow is reported separately from
base P&L. Real position value and funding payments would vary.

**Liquidation barrier sensitivity:** A 3x leverage and assumed 0.5% of notional
maintenance-margin threshold yields a very rough adverse-move threshold of
32.833333%. Historical candle highs/lows are checked for touches while the
hypothetical position would have been open. This is **NOT exchange liquidation
modeling**: mark-price liquidation, tiered maintenance margins, fees, subbar
path, funding and partial liquidation are not established by OHLCV. A touch
is a risk *flag*, never assumed to be a fill or historical trade closure.
The user-selected fixed-horizon, no-stop/no-TP exit is unchanged.

**Prospective candidate gate:** \`research_v9/promotion.py\` creates the
read-only \`research_results/forward_candidates.json\`. It uses strict
walk-forward, distinct-day, repeated-fold, control-beating, settled-funding and
margin-proxy checks. This is a **review queue**, not a strategy implementation;
no v8 paper position is opened, and no parameter changes are automatically
applied to v8. Even a passed gate is *not proof of tradable alpha*:
independently frozen future-only tests and human-reviewed implementation are
required. Real order endpoints remain absent.

**Source-of-truth separation:** The v8 \`data/events/\` chain, state, report
and its workflow are unchanged. V9.1 commits only the historical cache and
separate research reports. Network outages fail or are explicitly marked as
funding coverage gaps instead of creating synthetic settled payments.

## V9.2: faster historical bootstrap, explicit coverage

The daily workflow now requests up to 60 *older* pages per instrument per run
(100 records per page), rather than 12. It keeps the same data integrity
checks, overlap validations and 12,000-bar cap. GitHub Actions remains
best-effort, and OKX can rate-limit or restrict access. Larger history is
intended to increase distinct market-day coverage, **not** imply profitable
strategies or independent sampling.

`research_results/latest.json` now reports `historical_overlap_days`,
`ninety_day_overlap_reached` and the cache cap; the Actions run summary shows
these alongside strategy-count statistics and the strict forward-review gate.
Backfill cannot alter `data/events/`, v8 paper P&L, or historical experiment
outcomes. All published v9 results remain purely hypothetical.

## Funding refresh and run diagnostics

Funding capture now refreshes recent settlements until it reaches the cached
newest timestamp, then uses a separate bounded backfill budget to extend toward
the oldest candle in each instrument's research window. Each budget uses
`--funding-pages`; missing rates still exclude that instrument from measured
funding analysis. Confirmed historical settlements remain immutable.

Every non-PR research run uploads the local research reports and caches as a
7-day Actions artifact, including after capture or Git persistence failure.
Artifacts are diagnostic snapshots and may contain the previous report if
capture failed; inspect report timestamps and run status before using them.
The canonical successful report remains the one committed on `main`.
