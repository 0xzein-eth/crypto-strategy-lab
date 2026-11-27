# PAPER ML prospective freeze — v1

Status: **PRE-REGISTERED CANDIDATE SET; NO CHAMPION SELECTED**

This freeze records the model families, feature schema, training parameters, target, and prospective evaluation rules before any new prospective labels are inspected. It does not promote a model, change the strategy sampler, alter allocations, or enable orders.

## Why there is no historical winner

The historical chronological validation partition has already been inspected and is also used for early stopping by Logistic Regression and MLP. Its scores are therefore diagnostic only and cannot select a champion for an untouched forward test. A model that wins those historical metrics is not declared the best model.

## Frozen target and sample eligibility

- Target: binary label = 1 iff post-fee, frozen stress-adjusted research R is greater than zero.
- Eligible records: CLOSED, timely, same-venue OKX USDT-SWAP perpetual records with confirmed 15-minute OPEN-time evidence and fixed horizons 1, 2, 4, 8, 12, or 24 hours.
- Exclude spot, late outcomes, missing/unconfirmed candle evidence, and records without valid outcome timestamps.
- Features must be reconstructed only from evidence available at OPEN. Never use close/exit/future-derived fields as predictors.
- Chronological ordering is by entry timestamp; label availability must precede the training cutoff. Apply a 24-hour purge/embargo.

## Frozen feature schema

Use the exact ordered `dataset_builder.FEATURE_NAMES` from the frozen source revision. It consists of:
- 22 continuous/regime features: close-vs-SMA20/50, SMA20-vs-SMA50, SMA slopes, RSI14 and change, z20, ATR14 percentage, close-vs-prior high/low, volume ratio, candle body, upper/lower wick ratios, prior/older 20-bar ranges, range compression, prior mean range, close-vs-VWAP20, VWAP-missing flag, and entry-regime-up flag.
- One-hot categories: LONG/SHORT; 1/2/4/8/12/24h; the frozen `universe.SYMBOLS`; and `learner.BASELINES + learner.ADVANCED`.
- No feature additions, removals, reordering, or category remapping during the prospective cohort. A schema change requires a new freeze version and a fresh cohort.

## Frozen candidate implementations and parameters

All candidates use the same eligible records, feature order, chronological cutoff, and prospective evaluation rows.

| Candidate | Frozen configuration |
|---|---|
| Logistic Regression reference | max_epochs=30, batch_size=256, learning_rate=0.05, l2=0.001, patience=5, seed=17 |
| Gradient Boosting shadow | rounds=24, learning_rate=0.05, max_thresholds=12, min_leaf=12 |
| MLP backprop shadow | hidden_units=16, max_epochs=30, batch_size=128, learning_rate=0.01, l2=0.0005, patience=6, seed=29 |

No hyperparameter tuning, feature selection, threshold tuning, or model replacement is allowed after the prospective cohort begins.

## Prospective evaluation protocol

1. Verify the canonical PAPER ledger and record its tip hash, event count, dataset schema hash, training cutoff, and candidate model IDs in the run manifest.
2. Fit and freeze the candidate artifacts using only eligible records whose labels were available before the prospective start timestamp. Freeze the model artifacts and prediction code before collecting any cohort outcomes.
3. At each eligible OPEN event, persist all three candidate probabilities with timestamp, record ID, feature-schema hash, model ID, and code revision. Predictions are immutable.
4. Do not retrain or alter features/parameters during the cohort. If a model cannot score an event, record a missing prediction; do not backfill it after outcome.
5. Only score predictions after the fixed horizon has elapsed and the timely CLOSED outcome is available. Do not count overlapping trades as independent observations; report UTC-day clusters and strategy × side × horizon × symbol strata.
6. Compare Brier score and log loss against the constant training-prevalence reference and Logistic Regression; report ROC-AUC, accuracy, calibration, sample count, day count, and confidence intervals by day cluster.
7. Do not select a champion from one metric alone. Require improvement over both constant and Logistic Regression on Brier and log loss, non-degraded ROC-AUC, stable calibration, sufficient multi-day coverage, and positive net post-cost research R under the frozen cost assumptions. Report uncertainty; a point estimate alone is insufficient.
8. If no candidate meets every gate, declare **NO WINNER** and continue data collection without changing the frozen cohort.

## Safety boundaries

- PAPER research only. No broker/exchange credentials, real orders, wallet writes, sampler changes, allocation changes, or automatic promotion.
- The model comparison is a research diagnostic, not evidence of a profitable strategy or permission to trade live.
- Historical validation scores are not prospective evidence.
- Any change to features, labels, eligibility, costs, training parameters, or scoring rules invalidates this freeze and requires a new version before a new cohort.

