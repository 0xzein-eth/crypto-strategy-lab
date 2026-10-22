# MASTER BLUEPRINT — Crypto, Nasdaq & LQ45 Research Lab
**Version:** 2026-10-22 | **Status:** architecture and staged acceptance plan | **Mode:** PAPER/RESEARCH ONLY

> Objective: maximize *credible, risk-adjusted, net-of-cost* performance through reproducible testing—not maximize trade count, backtested peak ROI, or advertised win rate. No guaranteed positive returns. No broker/exchange order submission is authorized.

## 0. Current baseline, evidence hierarchy
- Main crypto v8 at 2026-10-22T02:04:29Z: 16,733 CLOSED, 7,735 wins, 8,998 losses; total fees USD 167,330; net P&L USD -169,730.94; win rate 46.23%; profit factor 0.8788. Implied gross pre-fee USD **-2,400.94**. These are repeated USD 10,000 hypothetical notional positions, **NOT funded-account equity**. v8 remains append-only archival experimental epoch.
- Crypto v2 paper: one 1,000 USDT wallet, separate verified ledger, 200 USDT hypothetical entries; latest observed report 998.65 USDT equity / one CLOSED, funding incomplete. Historic forward trial began 2026-10-21; preserve frozen 90-day candidate rules through 2027-01-19 UTC. Never claim a pristine holdout for inspected candidates.
- Equity active successor: `equity_lab/`; Nasdaq 25 listed securities, benchmark ^NDX; IDX LQ45 45-company dated membership snapshot, benchmark ^JKSE, which EXPIRES 2026-10-30. Isolated USD 10,000 and IDR 10m cash wallets. Current LQ45 report zero CLOSED, so no WR or PF inference. Previous `stock_lab/` and `stock_lab_state/` are archives.
- Authority hierarchy: verified raw observations/events -> replay-generated P&L -> research reports -> prose. Never retroactively overwrite underlying events, fake fills, or backfill forward ticks.

## 1. Non-negotiable invariants
1. Keep crypto v8, crypto v2, Nasdaq, LQ45 ledgers completely separate; record USD/IDR/USDT denominations, starting equity and units.
2. No lookahead: a decision at t uses only candles fully completed and available by t. Execute at an observed future bid/ask or explicitly labeled retrospective next open; no same-close execution from same-close features.
3. Preserve costs: maker/taker fee *as actually applicable*, both sides spread, impact/slippage, funding (crypto), borrow if shorting, dividends/splits/taxes/settlement for equities. Unknown costs = unknown, not zero.
4. Record every experiment, including failed ones, variants and combinations. Stale calendars/data stop execution, never fill from fabricated prices. Accurate exchange calendar and LQ45 membership as-of date mandatory.
5. No automatic promotion of a top-ranked hypothesis based on continuously monitored results. Existing locked trial may not change rules mid-trial.
6. Independent sampled trades != observations != asset-date clusters. Use cluster-aware statistical uncertainty and include rejected candidates.
7. No private keys, trading endpoints, or orders; separately authorize any eventual live component only after independent validation, account safeguards and human review.

## 2. Target architecture
```
public OHLCV+quotes+venue metadata+funding+corporate actions
       -> immutable raw warehouse & hashes + schema validators
       -> timestamp-availability / survivorship / holidays / membership checks
       -> versioned features (past-only) + regime labels (past-only)
       -> immutable hypothesis registry (single + composite + control)
       -> walk-forward / purged chronological validation
       -> realistic cost/fill/capital-limited simulator
       -> reproducible performance & uncertainty reports
       -> untouched future prospective SHADOW
       -> separate capped PAPER accounts (only after gate) 
       -> dashboard + research registry + audit artifacts
```
Each experiment identity: source hashes, signal-code commit SHA, asset universe snapshot, parameter hash, train/validation/holdout boundaries, seed, cost version, optimizer budget, full failed/selected arm accounting, observation coverage, strategy family, data timestamp and expiry.

## 3. Data specifications
### Crypto
- Start BTC/ETH/SOL, expand only after completeness passes; 15m OHLCV confirmed; longer horizons 1h/4h/1d derived with strict as-of.
- Official perpetual venue instrument contract value, tick/lot, active listing history; funding settled timestamps and cash flows.
- Observed bid/ask size and depth, timestamp skew, stale tolerance, book and signal clock; no OHLCV proxy for fill.
- Independent acquisition periods; target at least 365d and ideally 730d *genuine* 15m history per liquid instrument, with monthly regime coverage and gaps reported. Source API limitations explicitly recorded.

### Nasdaq
- Liquid Nasdaq-listed cohort is **not** interchangeable with Nasdaq-100 index constituents. Document snapshot/membership survivorship, splits/dividends, delistings, USD, sessions, holidays, auction mechanics, full-day/extended-hours.
- Need corporate-action-corrected total returns before performance claims; fills are hypothetical next-open with friction bounds, not broker executions.

### LQ45
- 100-share lot rules, Indonesia exchange trading sessions/holidays, 45 member snapshots with effective dates, price limits, corporate actions, market liquidity, capital available after settlement, taxes and brokerage fee scenarios.
- LQ45 membership frozen August–October 2026 and must halt/revalidate after October 30 until verified new list. Do not present membership snapshots as point-in-time historic LQ45 constituents.
- IHSG (^JKSE) is a price-index-only reference, NOT a tradable account.

## 4. Strategy inventory and hypothesis program
Keep ALL registered arms evaluated with neutral controls, not just an apparent winner.
- Trend: multi-timeframe alignment, moving average slope, Donchian breakout, ADX-like regime trend evidence.
- Momentum: cross-sectional momentum (Nasdaq/LQ45), residual/sector-adjusted momentum, volume confirmation.
- Mean reversion: RSI/extreme z-score/Bollinger/reclaim, regime conditioned, volatility-normalized.
- Breakout/false breakout: range failure, volatility squeeze and high-volume follow-through.
- Microstructure: spread/liquidity gating and order book imbalance for **shadow** crypto only; unobserved quote history cannot be backfilled.
- Factor/market-neutral exploratory controls for Nasdaq/IDX require tradability, transaction costs and short constraints; **never** short in current cash wallet.
- Portfolio: long-only risk parity/volatility targeting, capital-constrained allocation, cash abstention and market-relative controls.
- Ensemble: frozen constituents with 2-of-3 agreements and conflict veto, compare against each component AND random, no data-learned reweighting on holdout.
- Regime-dependent routing (trend vs range vs high volatility): regime classification fitted only on prior training data, with guardrail for threshold instability. Avoid proliferating arms unless economic rationale is explicit.
- Every new composite increases multiple-testing burden. Add to NEW registry, not frozen 26-arm v2 study.

## 5. Evaluation — actual acceptance gates
**P0 integrity:** reproducible hashes/replay; order-free; no mixed currency/membership; no duplicate/reversed timestamps; observation coverage and missing data denominators; code tests in CI.
**P1 economic feasibility:** expectancy in bps before costs and after itemized costs, under base AND adverse assumptions; fee-to-gross-edge ratio, turnover, break-even price move, max notional, participation and concentration. Reject if no credible forecast rather than use ATR as predicted favorable direction.
**P2 statistical reliability:** chronological train/validation/never-before-seen holdout; walk-forward with purge/embargo at least longest holding horizon; count all variants; cluster dates and related assets; adjusted false discovery / family-wise sensitivity and deflated Sharpe when applicable. No winner promotion merely from train rank.
**P3 independent SHADOW:** versioned registration in advance, new forward period and no tuning from its future outcome, minimum 100 eligible closed hypotheses **and** 20 distinct entry dates/4 ISO weeks for exploratory evaluation only. Higher production criteria must be pre-registered; no numerical thresholds guarantee profitability.
**P4 account risk:** prospectively observed one-wallet realized and marked equity, net after FULL costs, drawdown, maximum gross exposure, concentration, risk of ruin, scenario shocks, latency, outage kill switches; positive net trade expectancy lower-bound where statistically meaningful.
**P5 paper-eligible:** independent forward performance AFTER costs, at least two different market regimes, reproducibility on out-of-sample, review of worst days and multiple-testing correction, documented sign-off; paper wallet remains capped. The locked 90-day crypto trial is *evaluation only*, not permission to promote mid-trial.
**P6 live:** out of scope. Requires fresh explicit authorization, regulated provider/venue review and new system design.

Report metrics: n signals/feasible/filled/closed/rejected, observation coverage, number of independent entry days, win rate and its uncertainty, average win/loss and expectancy, PF, Sharpe/Sortino (with suitable sample), max drawdown, exposure, actual capital ROI, turnover, fee drag, net price-edge, tail/CVaR, benchmark-relative return, stability by quarter/regime, bootstrap clustered intervals and stress scenarios. `null` where unidentifiable.

## 6. Executable work breakdown / stage ownership
| Phase | Priority | Deliverables | Acceptance |
|---|---|---|---|
| A. Freeze and forensic | P0 NOW | event-version manifest, actual pre-fee vs fee reconciliation, health snapshot for all four ledgers | no altered events; signed-off accounting identity |
| B. Source contracts | P0 | candle/funding/CA schema, timetable, quality reports and missing-data reason codes | fail closed and reversible import |
| C. Cost and execution | P0 | read-only cost sensitivity comparison + simulated bid/ask/impact/funding/fee model, separate by venue | no unknown cost silently zero; wallet parity tests |
| D. Baseline and controls | P1 | zero-trade, buy-hold/index price comparator, same-time neutral directions and passive variants; full experiment registry | baseline reproducible by SHA |
| E. Search research | P1 | 26 frozen crypto shadow arms + separately registered new crypto/equity families & 5 composites | no leakage; train-only selection; no auto-promotion |
| F. Validation | P1 | purged chronological folds + nested selection, day-cluster CIs, multiple comparisons, across regime reports | held-out period not reused for tuning |
| G. Portfolio | P2 | independent realistic funded cash paper replay per market, settled trade and equity curves | journal replay reconciles exactly |
| H. Scheduling | P2 | Actions integrity alarms, provider failure and rate-limit backoff, health dashboard, fixed release cadence | objective observed coverage >=90% measured, not guessed |
| I. Prospective trial | P2 | crypto frozen trial through 2027-01-19 and new pre-registered cohorts for Nasdaq/LQ45 | proof based only on future independent observations |
| J. Champion review | P3 | side-by-side net-of-cost results and human review packet | NO auto-live; underperformers retained in history |

## 7. Program cadence
- Daily: raw data hash, integrity, observation health, no-order controls; standalone CI regression.
- Weekly: ALL family scoreboard with sample-size and fee decomposition, but no changes to frozen trial; stable new hypothesis proposals in a separate branch.
- Monthly: regime and turnover audit, retry/outage postmortem, compare model vs execution feasibility, dated membership universe update.
- Quarterly: independent holdout review only after predefined lock, archive experiment family versions and full failing cases.

## 8. Release checklist and stop conditions
Before merging any change: unit and property-based tests, deterministic fixtures, shadow-vs-historical signal parity, replay hash, negative tests for missing data/fees/market calendar, currency precision and account constraints, and Actions verified. Do not claim CI passed until actual logs pass.
Stop new paper entries on invalid funding cost assumptions where material, stale quote, instrument delisting, invalid LQ45 membership, missing corporate actions during positions, unexplained ledger discrepancies or drawdown breach. Continually monitor whether no-trade dominates after costs; inactivity is valid.

## 9. Optimization objective and anti-goals
Primary: maximize **lower confidence bound of independent future net risk-adjusted portfolio performance** subject to capital, drawdown and cost constraints—not gross ROI from cherry-picked trades. Secondary: capacity, recovery time, data quality and statistical efficiency. More strategies and trades are *research coverage*, not evidence of better alpha. Never optimize hyperparameters on a final holdout then call it untouched.

## 10. Research references
- Bailey & López de Prado, *Deflated Sharpe Ratio* (2014): https://doi.org/10.3905/jpm.2014.40.5.094
- Bailey et al., *Probability of Backtest Overfitting* (2017): https://escholarship.org/uc/item/4w1110bb
- CFA Institute, Backtesting & Simulation (2026): https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation
- QuantConnect, Reality Modelling: https://www.quantconnect.com/docs/v1/algorithm-reference/reality-modelling
- U.S. SEC Investor Bulletin, Performance Claims: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-47

## 11. Definition of done
The **blueprint** may be published now; the **research system** is complete only when every phase's acceptance criteria are evidenced by committed code, hashes, tests, CI logs, and subsequent real prospective observations. No current candidate has proven sustainable live positive returns. This document is a living design; proposed refinements create versioned, dated changes without rewriting frozen experiments.
