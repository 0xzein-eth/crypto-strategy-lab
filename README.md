# Crypto Strategy Lab — PAPER ONLY

Automated, prospective research simulator. **No orders, API keys, real capital, or live trading.**

## Current prototype
GitHub Actions triggers every hour at minute 17, best effort (it can be delayed or skipped). Python 3.12 retrieves Binance **spot** ticker snapshots, not perpetual mark prices. It attempts to close overdue and pending paper experiments using the first *observed* eligible snapshot from an execution; records delay; then creates up to 5 new diversified, exploratory candidates. Missing prices leave experiments pending.

Complete individual records are stored in `data/ledger.json`; Git history provides an audit trail, though repo administrators can rewrite history. `data/report.json` has the summary.

The **historical** LAB-074..115 ledger is NOT migrated because original full individual records have not been independently verified in GitHub. Historical aggregates must NOT be blended with new results. Fresh IDs start at LAB-116; new ledger is capped at 80 records.

Each simulated trade: $10,000 notional, hypothetical 3x leverage, 0.05% fee per side. Normalized R = (signed return percent - 0.10%)/research risk percent. Funding assumed zero for this prototype; spread, slippage, liquidation and actual perp funding not modeled.

**Research warning:** current BR-v3/MR-v3 signal labels are simple 24-hour momentum/countertrend exploratory proxies, NOT complete strategy implementations. TP-v3, LS-v3, FB-v3, CTRL-v1, multi-regime analysis, effective sample size and funding/slippage modeling are future work. Do not claim a proven edge. Strategy/horizon groups below 10 closed only collect data.

## Usage
1. In GitHub Settings > Actions > General, ensure Actions can run and workflow has read/write contents permission.
2. In Actions > Paper research lab, select Run workflow, or await scheduled execution.
3. Inspect workflow logs, `data/ledger.json`, and `data/report.json`. Failed runs must not be mistaken for successful experiments.

Locally: `python lab.py` (Python standard library only).

Every run resolves positions before creating new experiments. Workflow uses serialized concurrency and commits the ledger. If Git push conflicts, the job fails rather than overwrite other writes.

**This is not financial advice and is strictly a paper research system.**
