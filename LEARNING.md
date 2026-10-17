# Adaptive strategy research, v2

## What the software actually learns\n\nCurrent authoritative methodology and independent validation milestones: [Long-term research programme](docs/LONG_TERM_RESEARCH_PROGRAM.md). **No strategy has demonstrated a tradable edge.** BRREG-v1 and TPREG-v1 apply only to new PAPER entries and do not inherit older outcomes.\n
The paper lab does **not** write code, place real exchange orders, forecast certain returns, or promise to discover a profitable strategy. It continuously tests a **pre-registered catalog** of falsifiable hypotheses with **performance-neutral allocation** for future paper experiments. Completed outcomes are reported, but are not fed back into live paper arm probabilities without a separately approved new prospective policy. It **never** changes an OPEN/CLOSE historical event.

Current hypotheses:

| Arm | Signal |
|---|---|
| BR-proxy-v1 | 24-hour directional continuation baseline |
| MR-proxy-v1 | 24-hour contrarian baseline |
| CTRL-v1 | Deterministic, price-independent long/short control |
| TP-v3 | Confirmed 15m SMA trend pullback and reclaim |
| BR-v3 | Confirmed 15m ATR/volume breakout |
| MR-v3 | Confirmed 15m range-normalized z-score extreme |
| LS-v3 | Confirmed wick sweep and range re-entry |
| FB-v3 | Confirmed failure of previous bar's breakout |
| TREND-v1 | Confirmed 15m trend-separation continuation with volume |
| VOL-v1 | Confirmed 15m range/volume expansion |
| RANGE-v1 | Confirmed weak-trend rejection wick at statistical extreme |
| CROSS-v1 | Confirmed SMA20/SMA50 directional crossover |
| RSI-v1 | Confirmed RSI14 extreme with trend guard |
| VWAP-v1 | Confirmed 20-bar rolling typical-price VWAP reclaim or rejection |\n| BRREG-v1 | NEW: confirmed BR-v3 breakout, trailing SMA20/50 and same-instrument OKX 24h direction agree |\n| TPREG-v1 | NEW: confirmed TP-v3 pullback, trailing SMA20/50 and same-instrument OKX 24h direction agree |\n\nThe authoritative complete catalog including additional historical versions is the BASELINES + ADVANCED sequence in learner.py; this table is illustrative and not exhaustive.

New variants are **versioned, predeclared rules** added to `signals.py`; the learner cannot hallucinate an indicator when its market inputs are missing. A new rule affects *new* prospective experiments only.

## Continuous allocation, with safeguards
Each run begins by replaying and verifying the complete SHA-256 event chain. Due positions are resolved at the first available fresh same-venue observation **after their evaluation time**. Only then does the system consider bounded new paper experiments per observation, with a healthy hard cap of 44, one OPEN per symbol/15-minute signal slot, and schedule-dependent intake throttles. All decisions are frozen into each complete OPEN event as `allocation_policy`, `selection_mode`, and versioned signal evidence.

The `learner.py` policy uses a stress-adjusted R value for new closes when available. Older v8 records without a stored stress scenario receive a disclosed flat additional 0.12%-of-notional round-trip haircut for *learning only*, without editing their historical P&L. Catalog versions are fingerprinted to avoid false integrity alarms on additive strategy updates.

The `learner.py` policy:

- Considers **CLOSED perpetual-market experiments resolved no more than 30 minutes late**. Spot proxies, still-OPEN, missing and late records are excluded from *learning*, while all records remain in the public historical ledger.
- Splits calendar dates reproducibly by SHA-256 into about **80% development / 20% monitoring**. Entire UTC dates are together in one partition to reduce intraday leakage, though dates and assets are still correlated.
- Computes each arm's descriptive lower confidence bound after conservative scenario costs from **one clipped mean-R per distinct UTC day**, not from hundreds of statistically independent-looking simultaneous trades. Results are NOT formal hypothesis-test p-values or proof of alpha.
- With fewer than ten eligible training closes, continues collecting. A preliminary arm additionally needs four distinct training days and positive day-cluster lower bound.
- **Provisional leadership** is a descriptive diagnostic only; it does NOT trigger additional allocation. Past monitoring data have been inspected, so proof requires an untouched future calendar cohort and independent matched controls.
- **Preserves at least a planned 20% control allocation**, baseline and confirmed-signal exploration. Winner-take-all is deliberately disallowed; changing regimes can break apparent performance.
- If there is no qualified provisional leader, allocation stays diversified. No strategy is deleted for performing badly; old versions remain in the ledger, and new observations can alter the ranking.

This is a *repeatedly inspected monitoring split*, **NOT an untouched final holdout**. Repeated trials, adaptive assignment and correlated markets introduce selection bias. Even a provisional leader requires a separately frozen, forward out-of-sample assessment in multiple regimes before a tradable edge can be argued. Actual execution profitability is not tested.

## Capacity and schedule
The workflow targets nominal 10-minute GitHub Actions observation slots (best effort), with no timing SLA. Healthy capacity: up to 44 new entries per run, 1,050 concurrent OPEN, 50 OPEN per symbol, 1,750 new OPEN per UTC day and 70 per symbol/day. All are maximums, not guaranteed new positions. Observations still require authentic supported instruments, entry-time eligible markets, confirmed candles for advanced signals, and at least $2 million estimated 24-hour quote turnover. Missing or unsupported contracts are skipped, and new event files rotate daily while original month archives remain without deleting historic records.

**Higher trade count is not higher independent sample size.** Each UTC-day cluster and the volume of within-asset overlapping positions should be considered when interpreting edge. Selection uses observed confirmed candle signals, plus stratified sampling of asset sector, price direction and volatility.

Two independent GitHub-native recovery clock workflows target six checks per hour each, in addition to the paper workflow; each checks the canonical report and serialized cooldown gate before requesting a recovery after 14 minutes without successful persisted observations. Both **fail** health verification if the last report is more than 1.25 hours old, no source observations exist, or integrity checks fail. Failed Actions require troubleshooting; self-healing is NOT guaranteed for blocked APIs, GitHub outages, or changes to Actions privileges.

## Interpreting results
- `data/report.json → adaptive_research`: counts per strategy, training and monitoring splits, daily lower bounds, provisional leader and warnings.
- `data/events/YYYY-MM.jsonl or YYYY-MM_daily_DD.jsonl`: immutable-by-policy full OPEN/CLOSE records and original feature evidence in legacy monthly plus new daily-sharded files; hash chain plus Git commits. Git admins can rewrite history.
- `data/state.json`: active positions plus most recent 80 closed for public dashboard.
- All net P&L is hypothetical: canonical base retains 0.05% fee per side, and new records additionally report a hypothetical frozen spread/market-impact **stress** scenario. It is not a real bid/ask fill model; funding remains zero and liquidation is unmodeled. Do **not** treat R as actual stop-based account risk.

This lab is for continuous research, not unattended capital deployment.


## Historical research integrity revision — 2026-10-09 (policy history; current source is learner.py)

The v3 learner **never feeds monitoring-partition results into future
experiment selection**. The `allocation_leaders` field is calculated
only from training rows (minimum 30 trades across 7 UTC days, a positive
day-cluster lower bound, positive aggregate net R, and a 7-day/10-trade
minimum control comparator). Even these rankings are *exploratory* and
may receive at most the pre-existing non-control 25% bucket; the fixed
control fraction and broad randomized exploration remain.

`provisional_leaders` and `champion` are **descriptive monitoring
statistics**, NOT inputs to `choose()`, and never establish profitable
trading. Previous lab versions did repeatedly consult the monitoring
partition to allocate experiments, so earlier results **cannot be
rebranded as a genuinely untouched final test**. Any proof-of-edge claim
requires a separately frozen, independent future test not inspected
while selecting strategies. All historical OPEN/CLOSE events are unchanged.

Fixed-horizon diagnostics v2 additionally separate full hypothetical
closed trade returns (including late observations) from *timely,
same-market perpetual* outcome counts and net R by side, horizon,
strategy, symbol and market type. A cohort with zero valid closes has
a null eligible win rate/expectancy, never an invented profitable result.
