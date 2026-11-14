# Phase 2 — dataset audit and logistic baseline

The audit is generated from the v1 JSONL dataset. It reports sample counts by
horizon, missingness of every declared OPEN-time feature, positive-label share,
and entry-date coverage. It does not modify the canonical ledger.

The baseline uses a standard-library logistic regression trained by full-batch
gradient descent. A separate model is fit per fixed horizon. Numeric scaling,
missing-value handling, and categorical vocabularies are fit on training rows
only. The chronological split is 60/20/20 with a 24-hour purge at each boundary.
Fixed hyperparameters are declared in code; validation does not tune thresholds.

Metrics are Brier score, log loss, and 0.5-threshold accuracy, compared with a
constant training-prevalence no-skill baseline. Insufficient cohorts are
reported, not force-fit. The model is shadow-only and cannot allocate, suppress,
or open trades. Positive prediction metrics do not establish positive net
expectancy or deployable edge.
