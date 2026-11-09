# Strategy health review — 9 November 2026

## Scope and observation age

Snapshot from the canonical v8 paper ledger and report at **2026-11-09 11:36:51 UTC**. The first verified OPEN in the ledger is **2026-10-08 03:18:04.667 UTC**, so the prospective paper experiment had been running for approximately **32 days 8 hours (4.6 weeks)**.

This is an unfunded PAPER-only research ledger. The USD figures below are hypothetical notional P&L, not exchange-account losses, wallet equity or investable portfolio drawdown.

## Canonical v8 paper results

| Metric | Snapshot |
|---|---:|
| Verified events | 94,069 |
| Closed experiments | 46,764 |
| Still open | 541 |
| Wins / losses | 21,395 / 25,368 |
| Win rate | 45.75% |
| Gross price P&L before fees | -$142,377.05 |
| Assumed round-trip fees | $467,640.00 |
| Net fee-only paper P&L | **-$610,017.05** |
| Net expectancy | -0.08696 R per close |
| Profit factor | 0.8354 |
| Cumulative closed-equity drawdown diagnostic | $611,158.23 (not investable-account drawdown) |

The assumed fee is $10 per $10,000 notional experiment (0.05% each side). Fees represent approximately 76.7% of the net paper loss; gross price movement was already negative before fees. Average gross price result was about -$3.04 per close, before the $10 assumed round-trip fee.

## Directional and horizon diagnosis

Only timely same-venue perpetual closures are used for the eligible comparison.

| Cohort | n | Net expectancy | Net R |
|---|---:|---:|---:|
| LONG | 21,533 | -0.21270 R | -4,580.16 |
| SHORT | 22,037 | +0.04227 R | +931.58 |
| 1h | 10,350 | -0.06361 R | -658.32 |
| 2h | 7,882 | -0.05953 R | -469.19 |
| 4h | 7,086 | -0.07705 R | -545.97 |
| 8h | 6,551 | -0.10425 R | -682.97 |
| 12h | 6,208 | -0.09964 R | -618.57 |
| 24h | 5,493 | -0.12262 R | -673.56 |

The apparent SHORT advantage is not robust enough to promote: after the report's separate spread/impact or legacy extra-cost treatment, SHORT expectancy is -0.02427 R. The combined eligible after-friction expectancy is -0.15036 R. Every fixed horizon remains negative after that treatment.

The report's broader hypothetical friction-stress scenario is -$1,074,722.88, including $466,335.45 of additional assumed costs. These are stress assumptions, not observed fills.

## Strategy-level triage

Largest negative eligible net-R contributors in the canonical v8 report:

| Strategy | n | Net R | Expectancy |
|---|---:|---:|---:|
| BR-proxy-v1 | 6,349 | -918.41 | -0.14465 R |
| RSITREND-v1 | 3,248 | -894.66 | -0.27545 R |
| CTRL-v1 | 8,297 | -398.42 | -0.04802 R |
| ATRCHAN-v1 | 1,224 | -323.72 | -0.26448 R |
| BRREG-v1 | 495 | -292.54 | -0.59099 R |
| BR-v3 | 711 | -201.67 | -0.28364 R |

Some strategy-level totals are positive before the full friction treatment (for example MR-v3, FB-v3 and RSIREC-v1), but their evidence is observational, correlated and drawn from a short market window. They are not champions and are not promoted.

## Independent historical v9 cross-check

The separate v9 historical research lane evaluated 2,400 predeclared variants across 16 OKX USDT perpetual instruments over a 90-day common window. It reported:

- `champion = null` and `proven_edge = false`.
- 2,384 candidates rejected by the non-positive/unavailable training day-cluster lower-bound gate.
- In fold 1, variants with training expectancy around +0.16 to +0.20 R deteriorated to roughly -0.19 to -0.31 R in the next validation window; after an additional 25 bp assumed cost, validation expectancy was roughly -0.36 to -0.48 R.
- Folds 2 and 3 selected no candidate for validation.

This is a strong warning against promoting a strategy based on its training leaderboard.

## Identified learning-system weakness and change in this PR

The existing v8 learner grouped evidence mainly by strategy name. That aggregation can conceal a weak LONG cell behind a better SHORT cell, or a weak 24h cohort behind better short-horizon results.

This PR adds a prospective **strategy × side × horizon** diagnostic:
- only timely CLOSED same-venue perpetual records are eligible; the advanced candle arms are matched against OKX CTRL, not pooled cross-venue controls;
- each advanced cell is compared with the OKX CTRL cohort for the same direction and horizon;
- both the candidate and matched control require at least 50 training closes over at least 7 UTC days;
- a cell is downweighted to 1:4 only when its training day-cluster upper bound is below -0.05 R and its mean is at least 0.05 R worse than matched CTRL;
- the 20% CTRL control band, confirmed-signal source-coverage exploration, total entry budget, and all six fixed horizons remain intact;
- no cell is disabled; monitoring/holdout outcomes do not affect the prospective selection.

This improves the granularity of learning without reducing the total requested paper sample count. It does **not** make the strategy profitable or establish an edge.

## Safety and interpretation

- PAPER-only; no live exchange orders.
- No immutable OPEN/CLOSE event is rewritten.
- No stop-loss, take-profit, trailing stop, early exit or horizon change.
- No prediction-driven promotion; no champion is declared.
- Continue to treat every positive subgroup as a hypothesis requiring independent future validation.
