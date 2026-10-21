# V2 REAL settled funding — separate ex-post cash-flow scorecard

Funding is an actual perpetual-contract cash flow. The earlier
v2 paper wallet uses observed BID/ASK and an assumed 0.05% taker
fee per side, but it **does not** incorporate live/account-level
settled funding or order execution into its official equity curve.
Assuming funding is always zero for thousands of strategy candidates
is economically unjustified.

This new module v2/funding_evidence.py only reads:
- verified v2_history BTC/ETH/SOL SETTLED funding with source hashes,
- original v2_state/report.json closed wallet positions,
- original v2_state/shadow_report.json per-arm matched real-book
  research outcomes.

Each eligible 4h interval checks continuity/settlement coverage of
the exact instrument. For a LONG, the historical settled rate is paid
positive; SHORT pays the inverse. Only events with actual settlement
times in (entry, exit] are counted, using a constant reference notional.
If ANY required interval cannot be qualified, its performance is
explicitly UNKNOWN and excluded; never substitute 0. Some genuinely
fully verified intervals have zero payments when no settlement
occurred during the 4h position — this is not gap filling.

Publish:
- per-arm number of matched timely genuine book marks with fully
  qualified funding coverage; number excluded because missing;
- average top-of-book/fee return after genuine historical funding;
- same entry/exit, same-market neutral funded control and increment;
- a separate *unmeasured* 20bps extra impact/latency scenario;
- per-closed-wallet historical net USDT after measured funding;
- no unmeasured open-position funding adjustments or revised account
  wallet/equity ledger.

This is retrospective attribution of actual settled public funding,
not evidence that an exchange position existed or was executed.
Funding itself is not an alpha feature available before settlement.
This calculation does not model varying position notional,
maintenance margin, liquidation fills, full multi-level depth,
queue/latency or true traded fees. It never enables real orders,
selects champions, revises frozen source algorithms or interprets
a missing settlement history as real zero trading expense.

Independent read-only workflow v2-funding-evidence.yml publishes
source-complete and source-missing results as downloadable artifacts.

**Critical deployment blocker remains:** wallet/final holdout
cannot be considered net-real-execution ready until funding is
reconciled within the complete funded account state and
actual execution slippage/impact has been validated. No
backtested or prospectively marked candidate is automatically tradable.
