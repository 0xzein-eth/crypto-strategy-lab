# Forward shadow learning protocol — 2026-10-20, v2

## Objective and status

The older v8 ledger already contains >13,000 overlapping paper trades, most
negative after taker fees. More generated trades would compound sampling
bias. The research issue is not the number of rows; it is lack of
**prospectively paired, executable-side, independent-calendar-day evidence**.

This upgrade does **NOT** retroactively reinterpret those old observations.
It takes every newly observed **confirmed-candle** hypothesis from a
**frozen 26-arm catalog**, and records its 4h shadow markout on genuine later
same-venue order books. The physically separate one-wallet simulator still
opens only precommitted FB-v3 / VWAP-v1 proposals subject to its own balance
and risk limits. No additional wallet position or actual exchange order is
created for shadow arms.

## Frozen study specification

- Universe: **BTC, ETH, SOL USDT-SWAP on OKX**, unless a separately
  preregistered new cohort version expands it. An instrument's actual
  `ctVal` is verified before deriving top-of-book capacity.
- Source: OKX public `market/books?sz=1`, confirmed OHLCV via existing
  `signals.from_okx`, validated same-instrument ticker and complete
  15m candle; never use forming or future bars. Reject stale quotes.
- Hypotheses: `v2.shadow_research.ARMS` is **explicitly frozen**
  to the same 26 advanced research arms currently registered in
  `learner.ADVANCED`. If any strategy is added to code in the future,
  it **must** be reviewed and released as a new catalog/cohort version,
  rather than silently extending an existing historical hypothesis.
- A unique exposure opportunity is the exact
  `(symbol, arm, side, confirmed_bar_time)`; repeats do **not** increase
  sample size. A genuine market signal could result in zero approved
  funded-wallet positions.
- Proposed entry at the **first genuinely observed** bid/ask book after
  the signal; not the earlier candle close/next candle open. Hypothetical
  long pays ASK then exits BID; short receives BID then exits ASK.
  Both sides assume a *hypothetical* 0.05% taker fee and $200 reference
  notional. Same-side visible depth must cover requested base size.
- Fixed evaluation time: **4h after real observed entry**.
  A CLOSE is labelled in-time only when the **first subsequent genuine
  quote** at or after the due time is at most **30min late**. Missing
  data never gets a synthetic quote, candle endpoint backfill or fill.
- Control: for each frozen individual signal, SHA256 preselects a LONG
  or SHORT neutral control **at the same asset, exact entry observation,
  actual future exit observation and horizon**. Compare signal and
  contemporaneous control under the same bid/ask/taker assumptions;
  retain matched-control sample count, days, and ISO weeks.
  This is NOT randomized live experimentation or a separate funded
  `CTRL-v1` paper trade; controls across arms are correlated, and
  neutral direction can match the signal.
- Additional cost stress: **30bp adverse** per round trip is an
  explicit sensitivity assumption, NOT measured funding/impact.
  Keep quoted spread, fee-adjusted book markout and stressed markout
  separate. Funding settlement history is incomplete and must never
  be silently treated as zero economic funding.
- Report both opportunity counts and fee/spread/depth-eligible closures.
  Independent UTC **entry days** and ISO weeks, not number of coin
  events, are meaningful evidence units. Day-cluster bounds are
  descriptive, clipped, and NOT multiple-testing corrected.
- **No new winning strategy promoted.** The older FB/VWAP selection was
  repeatedly inspected, so new v2 evidence is an exploratory prospective
  cohort, not a freshly untouched final holdout. Nothing routes
  candidates to a real trading API.

## Output and audit

`v2_state/observations.jsonl` remains the sole append-only SHA256
public tick source. It records all real quotes and all 26-catalog
signal opportunities; no rewrites to `data/events`. The full
deterministic reconstruction generates:

- `v2_state/report.json`: **one hypothetical funded wallet**, equity
  and drawdown, only two preselected wallet arms.
- `v2_state/equity_curve.json`: mark-to-observed-book cash/equity over time
  (never interpolation; no unrealized estimate for unobserved periods).
- `v2_state/shadow_report.json`: **all** confirmed strategy shadow
  hypotheses, per-arm opportunity-to-executable-to-timely-close funnel,
  before unknown funding (explicit adverse stress scenario), matched
  neutral control delta, independent days/weeks and reasons **NOT** to
  promote a strategy.
- `v2-observer-run-health` Actions artifact: workflow trigger,
  step result and presence of files. This artifact is **not** a
  market observation; it remains available even after a failed public
  data request, for operational diagnosis.

The new v2 workflow runs on best-effort 30min native GitHub schedules,
manual dispatch, and **after successful completion of the canonical main
v8 lab workflow**. A dedicated single-writer concurrency group, no-force
push, source hash verification, and `--verify-only` make duplicates or
tampering visible. An unavailable 3-market book or source exception fails
closed; failing to observe is not a green fake trade.

## Next steps to improve true research quality

1. Obtain a verified multi-year survivorship-aware dataset, funding
   settlement histories, mark/index and proper bid/ask depth/impact
   context. Current 90-day, 12-instrument historical factory is NOT a
   regime-complete final study.
2. Freeze a **small set of economically distinct 4–6 hypotheses** per
   research epoch with causal hypotheses and independent train/validation
   schedule. Thousands of RSI threshold siblings are not independent
   discoveries. Counterfactual all-arm shadow observation can suggest
   what to investigate, but **selection from this stream requires a
   completely new untouched future cohort**.
3. In the next prospective version, predefine a falsifiable economic
   forecast using *training only*, not ATR volatility as a stand-in
   for predicted returns. Verify favorable movement exceeds quote
   spread + fee + adverse funding + impact/latency buffer.
4. Complete real settled funding and more realistic book depth/contract
   tick/lot, maintenance margin and liquidation tests before anything
   can be considered deployable. No real orders without user approval.
5. Accumulate >=20 independent UTC days, >=4 ISO weeks, >=100 matched
   controls per arm as **minimum diagnostic maturity**, plus untouched
   multi-month forward validation, multiple-testing correction, a
   financed equity/drawdown stress budget and persistent reliability.
   None of these counts by itself proves profitability.

## Research progress criteria

The appropriate improvement to monitor is *not* a rising total
backtested-trades count. It is: (a) reproducible authentic quote
coverage; (b) the fraction of confirmed signal opportunities with
tradable estimated book size; (c) eligible same-time shadow matched
controls after costs and unknown-funding caveat; (d) independent
calendar days across regimes, horizons, and sides; and (e) eventually
positive lower-bound net expectancy on an untouched final holdout.

Status as shipped: **INSTRUMENTATION IMPROVED / EDGE UNPROVEN /
EXPLORATORY ONLY / PAPER ONLY**.
