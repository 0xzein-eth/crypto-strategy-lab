# FROZEN research epoch 2026-10-21 to 2027-01-19

Pre-registered before start. Forward PAPER ONLY. Not a real exchange order.

## Frozen protocol

- Candidate strategies: FB-v3 and VWAP-v1, repeatedly inspected previously, not proven. All 26 arm shadow research may continue separately.
- Exchange scope: BTC/ETH/SOL OKX USDT-SWAP, validated 15-minute confirmed candles, genuine future top bid/ask snapshots. Fixed 4-hour evaluation.
- Future entry interval: 2026-10-21T00:00:00Z inclusive until 2027-01-19T00:00:00Z exclusive. Entries too close to end for complete fixed exit are not valid.
- Evaluation: positive absolute stressed post-cost mean AND incremental expectancy over the same-time neutral reference, shared-day 26-arm familywise adjustment, >=40 UTC entry-day clusters, >=8 ISO weeks and >=100 true liquidity matched reference closes per candidate.
- Account: 1000 simulated USDT initially; at most 2 x 200 notional positions; leverage <=2x, observed portfolio drawdown <=100 USDT and modeled fee-only profit factor >=1.20 are necessary but insufficient.
- Actual funding settlements, order execution, market impact, queue/latency, and liquidation fills are not validated fully. Missing conditions strictly block deployment.
- Exact Git blob fingerprints of signals.py, v2/forward_paper.py, v2/shadow_research.py are pinned in v2/frozen_trial.py. Any silent edit invalidates the research epoch; enhancements need a separately preregistered future version, not retroactive relabelling.
- For the next 90 days, the separate trial tracker publishes ONLY observation counts and integrity progress, not candidate returns, rankings, profit factor or Sharpe. No interim strategy selection may be driven by the results.
- The repository and generic v2_state data remain PUBLIC and inspectable. This makes the trial prospectively pre-committed but NOT cryptographically sealed from human peeking. Seeing/using results during the epoch invalidates any claim of a clean human-blind holdout. Even after 90 days, the tracker never automatically claims a proven alpha or enables trading.

The workflow validates source hashes and exit timestamps using actually observed exchange time rather than the GitHub job clock. No unobserved market tick is fabricated. Outputs are WAITING, COLLECTING, or FINAL_WINDOW_ENDED with explicit blockers and zero real orders.

At registration, the future 90-day period has not yet elapsed. Code completion, CI success, and a high sample count cannot meet the calendar prerequisite.
