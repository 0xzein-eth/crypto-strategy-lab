# Long-term Crypto Strategy Lab research programme

Status: PAPER-TRADING ONLY. No live orders, backdated or invented fills, retroactive strategy relabels, or historical ledger rewrites. The exit remains FIXED HORIZON 1/2/4/8/12/24 hours; NEVER add SL, TP or trailing stops.

## North-star objective

Identify a *reproducible* positive post-fee and post-stress-cost incremental expectancy versus a contemporaneous, same-instrument matched control across independent real UTC weeks and market regimes. Win rate alone is an inadequate optimisation target. Trading performance and an edge are NOT currently proven.

The canonical published paper P&L uses observed public-market snapshots and base simulated fees, NOT actual exchange fills. Supplemental spread/slippage impact is a separate hypothetical scenario and must NEVER silently replace the published P&L. Correlated crypto symbols and overlapping horizons are not independent trials.

## Baseline audit — 2026-10-17

About 10 genuine eligible entry UTC days and only 2 distinct ISO weeks existed despite thousands of CLOSED experiments. Aggregated profit factor and expectancy were negative. There is no eligible champion. GitHub cron remains best-effort; some observations are delayed or absent. Existing integrity and readiness components: audit.py, matched_controls.py, learner.py, negative_edge_diagnostic.py, research_quality.py, temporal_evidence.py, regime_evidence.py.

## M0/M1: data integrity and observability — completed, ongoing surveillance

Every research run audits all actual immutable events and records the verified ledger hash, report timestamp and sample eligibility. Reject mismatched venue/instrument, old/non-finite public quotes, unconfirmed/stale OHLCV, and premature CLOSE before evaluate_at. Report closure delay and exclude late observations from timely evidence; never delete or backfill historical rows. Inspect scheduler interval gaps and horizon-specific timely fraction. Preserve permanent CTRL and exploratory allocation. Cron coverage above 90% is a readiness prerequisite, NOT a reliability guarantee.

## M2: register forward-only candidate strategies — code change under CI review

Two NEW v1 research labels without changing original signals:
- BRREG-v1: previously confirmed BR-v3 breakout in a genuine completed 15m OKX USDT swap candle; SMA20 > SMA50 for LONG (inverse for SHORT); the same-instrument OKX public ticker shows a +1.0% or greater 24h move for LONG (negative -1.0% or lower for SHORT).
- TPREG-v1: previously confirmed TP-v3 SMA pullback and exactly the same 24h directional/SMA filters.

All thresholds are frozen. Invalid/missing quote, wrong instrument/venue, stale/unconfirmed candle, wrong 24h direction or SMA trend means NO NEW variant. Freeze rule version, source strategy, signal timestamp and actual ticker observation in each NEW OPEN. No future observations enter the signal. Existing arms' semantics and fixed-horizon CLOSE policy remain unchanged. All arm assignment is outcome-neutral, while CTRL exploration is preserved.

Two hypotheses across six horizons constitute at least TWELVE comparisons before extra regimes, side or symbols. No favourable one-off trade or selected winner proves alpha.

## M3: gather genuine future evidence — estimated 4–12+ weeks of observation

Wait for fresh post-registration OPEN/CLOSE paper samples. These new strategy IDs inherit no historical BR-v3 or TP-v3 results. At least 20 distinct eligible entry UTC days, 4 separate ISO weeks, 5 weekdays, 10 days covering both up/down entry-frozen regimes, and 6 days representing all four UTC 6-hour periods are a readiness target, not enough alone for statistical power. Strive for at least 100 one-to-one matched controls per tested arm, match fraction above 50%, and 25 or more eligible holdout matched pairs. Exact-stratum matching: same UTC entry day, symbol, horizon, side, entry-frozen regime, no reused controls and <=120 min entry separation. Report unmatched samples and leakage.

Holdout monitoring has been looked at in earlier research and is NOT a pristine final test set. Establish a later timestamped untouched final prospective validation cohort, with frozen candidate list, thresholds and rules before that window. Do not tune parameters or reduce an arm by reading the final validation results.

## M4: evaluate causal plausibility and generalisation

Primary comparison: within-pair differences in net simulated R under published base fees; separately report additional spread/slippage stress assumptions. Include day-cluster and crypto-beta dependence, adverse regimes, asset/time concentration, 1/2/4/8/12/24h horizon interactions, explicit unmatched fraction, losing-day severity and scheduler delays. Correct multiplicity across at least 12 preregistered arm-by-horizon tests (e.g. Holm family-wise procedure where assumptions hold). Day-cluster descriptive confidence bands from repeated looks do NOT by themselves prove edge. Demand stable results across independent forward calendar weeks AND untouched post-selection calendar holdout. Publish uncertainty as well as win rate, P&L, expectancy and PF.

## M5: governed *future* allocation policy — NOT yet authorised

Only after M4 and independent review may a new allocator-vN PR preferentially allocate a qualified candidate to future experiments. It must retain CTRL exposure, remaining arm exploration, one OPEN per symbol/15m signal slot, all capacity and freshness budgets, true public quotes and fixed-horizon exits. No live orders or automatic promotion. Revert or revise only with versioned policy and green full-ledger audit, never retroactively edit positions.

## Continuous work and publication cadence

Daily: full hash-chain replay, unit tests, evidence artifacts; quote errors, late exclusions, missed scheduled slots, verified ledger tip.
Weekly: per-arm/per-horizon/per-regime outcomes, matched-control coverage, time breadth, fee versus impact stress and decision-record review.
Monthly: prospective cohort age, sample balance, volatility regime drift, read-only negative expectancy alerts, duplicate hypotheses, workflow cost, source API maintenance.
Quarterly: hypotheses/preregistration and broad market-regime review; add new variants only if inputs actually exist when entries are observed.

## Operational acceptance criteria

Every new PR must pass all tests, ledger audit, backward compatibility and no-lookahead fixtures. Never promise that more trades, more variants or a high historical WR automatically improves returns. Data-quality and statistical gates must fail CLOSED. Pending milestones cannot be marked done before independent future weeks have actually elapsed.

Milestone state: M0 complete; M1 complete (PR #36); M2 implemented in experimental branch pending CI; M3–M5 pending real future observations and adequate evidence.
