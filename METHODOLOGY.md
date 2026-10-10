# Research methodology and limitations (v8)

**All numbers are hypothetical and prospective paper-research only.** All original full records are stored in `data/events/YYYY-MM.jsonl or YYYY-MM_daily_DD.jsonl`, one JSON object per line. Avoid deriving strong market conclusions from a single period or from correlated crypto assets.

## Lifecycle

1. Start a GitHub Actions run. Replay every monthly event file in ascending order, verify sequence, previous-hash link, SHA-256 content digest, valid OPEN→CLOSE transitions, and cross-check the last persisted report's chain tip. The workflow refuses to run on an inconsistency.
2. Find all positions whose `evaluate_at` is on or before the current run start. Query a **fresh public last-traded ticker from the exact same provider, market type and contract/spot instrument** as the entry. No historical endpoint for exit, no interpolation and no simulated fill.
3. If an eligible observed snapshot exists, close the paper position and append a full CLOSE record with price source, timestamp, fee, signed return, net P&L, normalized R, delay and `late_excluded` marker. If not, keep the OPEN event unchanged; it shows up in `pending`.
4. Scan up to 38 predeclared market candidates. Filter invalid/stale prices, absolute 24h change <0.5%, and approximate 24h dollar turnover below USD 2 million; skip unsupported venue contracts. Determine **pre-committed strategy and horizon**, and (if available) use confirmed OKX 15-minute candles as evidence.
5. Immediately before committing a new trade, fetch a **second fresh ticker** from the same venue. The hypothetical entry timestamp must not predate the final observation or the decision.
6. Append all OPEN/CLOSE events to the current monthly JSONL, replay the entire chain, regenerate `data/report.json` and `data/state.json`, and atomically commit the files together in one Git commit.

The GitHub schedule targets **six times per hour**, at minutes 04, 14, 24, 34, 44 and 54. GitHub Actions is best effort and may be late or omitted. Time-sensitive exits can be missing or delayed. A close >1800 seconds after intended evaluation is **excluded from timely eligible evidence** but retained as a full actual observed paper outcome.

## Price and strategy evidence

Provider preference: Bybit USDT linear, OKX USDT swap, Binance USDT futures, Kraken USD spot proxy, Coinbase USD spot proxy. Geographically blocked feeds are skipped. Exit must match the entry venue and instrument. **Spot proxies are always segregated**; no cross-exchange exit mixing.

For OKX perpetual contracts, `signals.py` requests `bar=15m`, at most 120 candles. It considers **only complete, exchange-confirmed candles** (`confirm=1`) with correct timestamps and no gaps; no forming or future candle can generate a signal. Compute SMA20, SMA50, ATR14, z-score20, prior 20-candle high/low and last-bar volume relative to previous 20 bars.

**Advanced, conditional hypotheses (require confirmed candle evidence):**

- **BR-v3:** latest confirmed close outside previous 20-bar high/low by at least 0.1 ATR, with volume at least 1.2× prior 20-bar average; direction follows breakout.
- **TP-v3:** strong SMA20/SMA50 separation (more than 0.8 ATR), pullback through SMA20 and confirmed reclaim in trend direction, close within 0.65 ATR of SMA20.
- **MR-v3:** z-score over last 20 closes is ≤ −2 or ≥ +2 in a weak SMA20/SMA50 trend (<1.2 ATR separation); position opposite extreme.
- **LS-v3:** bar wicks through previous 20-bar range but closes back inside with wick fraction ≥45%; position opposite sweep.
- **FB-v3:** penultimate bar closes outside its preceding 20-bar range but latest confirmed candle closes back **inside that older range**, against the breakout.
- **TREND-v1, VOL-v1, RANGE-v1:** confirmed trend impulse, volatility expansion and range-wick rejection with predeclared thresholds.
- **CROSS-v1, RSI-v1, VWAP-v1:** confirmed SMA20/50 crossing, RSI14 extremes and rolling 20-bar typical-price VWAP reclaim/rejection.

**Baselines, used when an advanced signal is absent or unavailable:**

- `BR-proxy-v1`: follows signed 24h market move.
- `MR-proxy-v1`: fades signed 24h market move.
- `CTRL-v1`: deterministic hash of asset and 15-minute slot chooses side, regardless of recent move. This is a negative control, not a reliable alpha benchmark.

Kraken `o` references the day's opening price, **not always a rolling 24-hour window**; `price_change_reference` records this distinction. Indicator evidence is captured in each OPEN event. Labels signify research hypotheses, not market profits.

## Exit policy: fixed-horizon only, NO SL/TP

User-selected research has **no stop-loss, take-profit, trailing stop or early exit**. Each OPEN has one precommitted `evaluate_at`. The engine records a CLOSE using a valid, fresh same-venue/same-instrument observation after that due time; if missing, leave the experiment OPEN until a later observed snapshot. Report the genuine delay, keep late closes for audit and exclude delayed closes from timely learning. Never reprice an overdue experiment using a retrospective market quote as if it had been observed at the exact target second. Only CLOSED positions contribute to realized hypothetical P&L and win/loss.

Descriptive `fixed_horizon_outcomes` report includes side/horizon/strategy/symbol/market groupings, late rate and due counts; it intentionally does not mark OPEN trades to market. Hypothetical notionals can overlap massively, so their sum is not investable portfolio exposure.

## Fixed-horizon arithmetic

No TP/SL orders are submitted. At evaluation time the best **first observed eligible snapshot available on an actual later run** is used (not the missed target-time historical price). Horizon set: **1, 2, 4, 8, 12 and 24 hours**. Sample size is driven by independent run timing, not by retrospective market replay.

- Notional = **$10,000** per paper experiment.
- Hypothetical leverage = **3×**, implying approximate initial margin $3,333 before maintenance/fees (but margin/liquidation are **not modeled**).
- Signed return (%) = `(exit_price / entry_price - 1) * 100 * (1 for LONG, -1 for SHORT)`.
- Fee = 0.05% notional per side, so **$10 round trip** for a $10k experiment.
- Net research P&L = `10000 * signed_return_pct / 100 - 10`.
- `normalized_R = (signed_return_pct - 0.10%) / 1.5%`. The **1.5% is a research normalization constant**, not a tested stop or true account risk.
- Funding remains **0**; no variable funding, real fill probability, stop-outs or liquidation is modeled.
- **Additional non-execution stress scenario for new trades:** observed entry bid–ask spread when available, otherwise clearly assumed spread, plus an impact buffer that depends on registered asset category, recorded volatility and reported turnover. The result is stored at OPEN and verified at CLOSE, reported as separate stress P&L/R. It does NOT prove the real available execution price, exit spread, funding, or slippage; historical base P&L stays unchanged.

PnL calculations show **notional change, not 3× notional change again**. This prevents double-counting leverage. Real realized PnL can be substantially different.

## Evidence standards

Record cohort count by strategy × horizon and market regime; avoid mixing spot proxies with perpetual. Only **timely perpetual snapshots** contribute to `eligible_perpetual_timely`. Late trades and spot proxies remain separately reported, never erased.

- **n < 10:** collect observations, no edge inference.
- **10 ≤ n < 30:** hypotheses only.
- **30 ≤ n < 50:** preliminary, highly correlated.
- **n ≥ 50:** requires additional distinct volatility/directional regimes and clustered confidence analysis before stronger claims.

Assets share crypto-beta exposure: 50 concurrent BTC/ETH/SOL correlated trades are **not 50 independent tests**. Current engine reports raw expectation, profit factor, closed-trade drawdown, sample volume, fee burden, delayed and proxy exclusions. It does **not** establish causal alpha or guaranteed profitability.

Historical **LAB-074..115** belongs to an older compromised scheduler prompt and remains out of sample until complete original individual records are independently restored and reconciled. **Do not invent missing entries or merge aggregate snapshots.**

## Expanded prospective sampler (version 2026-10-08-v2)

Universe is defined in `universe.py` (38 assets). A deterministic 15-minute-slot hash stratifies by sector, movement direction and absolute-change band. It interleaves market groups instead of selecting only the highest 24h movers, which reduces extreme-momentum sampling bias but cannot make trades independent. Unsupported instruments and under-liquid quotes are skipped. The engine targets 14 new OPEN records per scheduled execution (configurable hard cap 24) with 850 maximum simultaneous OPEN, 50 per symbol, 1,400 new per UTC day and 65 per asset per UTC day. Existing OPEN→CLOSE events and the SHA-256 chain are never rewritten to accommodate the sampling upgrades.

More samples in a single day do not resolve small effective sample size: `learner.py` uses daily clustered scores and keeps a control arm and held-out monitoring partition, and reports no proven tradable edge without further independent validation. Maintenance can add new *versioned, explicit* strategies without revising older frozen rules or outcomes.

New writes use `data/events/YYYY-MM_daily_DD.jsonl` per UTC day. Prior `YYYY-MM.jsonl` is preserved verbatim, and the hash chain is continuous across both formats; the loader verifies files in deterministic chronological order. Daily sharding mitigates growth of each individual Git blob but is not unlimited storage.


## Derived entry-regime and daypart diagnostics (v3, 2026-10-10)

The v8 append-only OPEN/CLOSE source is preserved. The derived
`fixed_horizon_outcomes` v3 additionally reports **frozen-at-entry**
`entry_regime` and **UTC entry daypart** (00–05/06–11/12–17/18–23).
Every grouping shows the number of **eligible timely perpetual CLOSES**,
their hypothetical aggregate net R, their **distinct UTC entry days**,
and their late-closure share. Legacy events without an entry regime
or timestamp receive an explicit `unknown` label instead of a guessed
regime; they are not relabeled using later price performance.

The `eligible_day_breadth_ready` flag indicates only that at least
seven calendar entry dates occur in a group; it does NOT constitute
statistical independence, significance, out-of-sample validation or
evidence of a tradable edge. These are descriptive breakdowns, not new
strategy rules. Previous fixed-horizon v2 reports are still audited
against v2 while the next successful observation upgrades the derived
report to v3; the event hashes are unchanged.
