# Matched ML feature ablation v1

This phase compares the existing numeric baseline with trend, momentum,
volatility, candle and combined OPEN-time feature groups.

## Experimental controls

- Same eligible sample cohort for every feature set and horizon.
- Same chronological 60/20/20 split and 24-hour boundary purge.
- Imputation, scaling and category vocabulary are fit on training rows only.
- Fixed logistic-regression hyperparameters; no test-set tuning.
- Test Brier deltas are reported against the baseline; negative is better.
- All outputs remain shadow-only. No allocation, signal or exit policy changes.

The ablation runner consumes the feature-engineered dataset and writes
`ml_feature_ablation_v1.json`. A result is not accepted as an improvement
merely because one horizon or one feature group happens to win. Validation
and test behavior must be stable, and classification improvement does not
establish positive after-fee expectancy.

## Data capture diagnosis

Confirmed 15-minute OHLCV features are produced by `signals.features` and
attached to confirmed signal evidence. The legacy BR-proxy, MR-proxy and
CTRL arms do not independently carry this context on every OPEN. This is a
capture-coverage gap, not a reason to impute historical samples. Historical
nulls remain null. The next capture change must attach the same validated,
entry-time candle context to every sampled arm when the OKX confirmed-candle
source is available, while preserving the absence of context when unavailable.

## Learning and economic validation

The existing logistic model is a retrospective shadow baseline, not an
online learner. A genuine walk-forward learner must train only on labels whose
`exit_observed_at` is earlier than each prediction timestamp, freeze each
prediction with model/version/features, and score it only after the relevant
`evaluate_at`. Until that immutable prediction-to-outcome path exists, do not
describe the system as learning online.

Economic review must separately report after-fee expectancy, net R, profit
factor, drawdown, and performance by horizon/strategy/regime. Classification
metrics alone are insufficient. No live orders or strategy promotion.
