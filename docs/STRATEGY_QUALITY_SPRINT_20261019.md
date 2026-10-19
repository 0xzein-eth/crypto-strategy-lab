# Prospective quality-first PAPER experiment policy — 2026-10-19

**Pre-registered next OPEN only.** No historical event mutation, retroactive
backfill, real orders, margin changes, SL/TP/trailing, or changes to fixed
1/2/4/8/12/24-hour evaluation. This document describes sampling policies,
NOT profitable strategies.

## Why change sampling?

The canonical 2026-10-19 report contained more than 12,000 experiments,
but the historical research results had negative overall post-cost expected
value. Direction-only BR-proxy and MR-proxy (24h change without a verified
15m setup) represented thousands of research CLOSED outcomes, dwarfing
new confirmed-signal arms. More of those unfiltered probes adds correlated
observations without necessarily helping distinguish falsifiable hypotheses.
Shrinking gross negative paper P&L by shrinking exposure would **NOT**
demonstrate an improvement in actual trading performance.

## v8 policy — two independent quality guards

### 1. Sparse NO-confirmed-signal baseline probes (12% of real symbol-slots)

- For each genuinely available, same-venue OKX USDT perpetual ticker,
  the system still evaluates confirmed 15-minute OHLCV signals and logs
  the candidate opportunities.
- If no registered confirmed strategy is currently offered, the system
  samples a *pre-declared deterministic 12%* of unique symbol × frozen
  15-minute slots as a direction-only baseline probe, using a stable SHA256
  bucket. Other no-signal slots are **not paper trades**, not missed fills.
  No strategy is invented to maintain throughput.
- If one or more verified 15m hypotheses exist, the normal candidate
  allocation applies unchanged, with **at least a 20% CTRL hash band**
  when CTRL is offered. All six horizons remain possible subject to
  independently recorded scheduler-health gates.
- No-signal proxy probes preserve an observable negative / inactive
  market reference; they are NOT an independently randomized matched
  control for every arm. The exact-stratum matched-control diagnostics
  still report unmatched fraction and refuse false advantage claims.
- This quality gate only applies to the actual automated engine with
  verified OKX ticker+OHLCV evaluation; pure offline proxy fixtures
  and old spot proxy experiments remain unchanged for reproducibility.
- Some arm P&L totals may become less negative simply because **fewer
  paper entries** are opened. The correct test is prospective **eligible
  expectancy per arm** versus appropriately matched control after fees,
  stress-cost sensitivity and UTC-day/ISO-week validity.

### 2. Bounded downside-based RESEARCH exploration guard (not a champion)

- The learner already publishes `training_only_underperformers`. It
  requires **at least 50 qualifying TRAINING CLOSEDs, 7 independent
  TRAINING UTC entry days**, a negative day-cluster descriptive UCB
  below **−0.05 R**, and a training mean at least **0.05 R worse than
  the eligible CTRL mean**. Holding-out 20% of UTC days remains frozen.
- Only the **ordinary advanced-candidate sampling band** uses a 4:1
  *relative* weight reduction for flagged losers (still sampled, never
  banned). The 20% CTRL band, the coverage-first band for undersampled
  confirmed arms, and the low-rate baseline exploration branch remain
  unchanged. If only one arm is available, it can still be selected.
- Do not rank/promote an apparent winner from recent lucky outcomes.
  This is exploratory negative evidence triage, NOT statistically
  calibrated proof that other strategies beat CTRL. It is conservative
  and reversible as new prospective evidence accumulates.
- Never consult monitoring/holdout CLOSE outcomes, historical v9
  backtests, future candle closes or retrospective winners to select
  a current OPEN. Tests flip monitoring P&L and require decisions to be
  exactly identical.
- A new OPEN freezes the `learner-v8` allocation policy, signal catalog
  version and `training_loss_research_guard` selection mode. Old v7
  events retain their previous sampling meaning.

## Run-level auditable quality indicators

`data/report.json → entry_opportunity_audit` distinguishes:

- `eligible_quote_symbols` and `advanced_source_checks`:
  authentic quote eligibility and real confirmed-candle checks.
- `slots_with_any_confirmed_signal` and
  `confirmed_arm_opportunities`: genuine inspected candidates.
- `no_confirmed_signal_proxy_slots_skipped`:
  opportunities **not opened** because no confirmed setup existed.
- `no_confirmed_signal_baseline_probes_allowed`:
  the strictly hashed fallback reference cohort.
- `new_paper_opens_by_arm`: actual immutable, prospective new OPENs.
- `training_only_negative_arms_v1`: descriptive training watchlist
  used for cautious downsizing of only one exploration band.
- `no_new_entry_reason`: distinguishes quote starvation, capacity
  limits, and no-confirmed-signal throttling.

**Metrics to revisit only after honest future observations:** new-OPEN
composition by policy version; post-fee and stress R per eligible
strategy; >=20 actual UTC days, >=4 ISO weeks, enough matched CTRL pairs,
week/daypart breadth and scheduler coverage. No user-facing statement of
"improved win rate" or "working strategy" follows from passing these
tests or reducing the total number of baseline probes alone.

## Operational and measurement trade-offs

A training-only adaptive reduction can introduce sequential selection
bias. The final validation must be conducted on a *future untouched*
holdout with versioned, frozen policy and multiple-testing correction.
The existing retrospective matched-control analyses remain descriptive
and can suffer unmatched-selection bias. Never mix v7 and v8 cohorts
without a policy-version covariate, and never silently compare raw
cumulative paper notional USD P&L across different opening rates.
