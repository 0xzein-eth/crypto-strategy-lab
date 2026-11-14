# Walk-forward shadow learning and economic review v1

`ml_walkforward.py` reconstructs a historical weekly prediction process. For each horizon, it trains only on observations whose `exit_observed_at` is strictly earlier than the prediction week's UTC Monday. It uses OPEN-time features, training-only preprocessing, a fixed 120-epoch logistic model and at most the most recent 1,500 matured training rows. This is a bounded rolling training window, not a full expanding sample.

Each output record includes the prediction timestamp, model version, training cutoff, training sample count, horizon, probability and subsequently observed outcome. The artifact is explicitly marked as a historical simulation. It is not a live prediction frozen in the canonical OPEN event; no claim of online learning is made until that integration exists.

`ml_economic_review.py` evaluates all walk-forward predictions and fixed probability buckets. It reports Brier score, observed win rate, net P&L after recorded simulated fees, expectancy in normalized R, profit factor and sample drawdown in R. Probability buckets are descriptive, not optimized trade filters. Overlapping observations are not account equity.

No output changes strategy selection, trade generation, allocation, fixed 1/2/4/8/12/24-hour exits or the PAPER-only constraint. Promotion remains prohibited.
