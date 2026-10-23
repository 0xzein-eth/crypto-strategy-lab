# Legacy v8 negative expectancy: entry safety and economic audit
**Audit date:** 2026-10-23. **Mode:** PAPER RESEARCH ONLY, no real exchange/broker orders.

## Evidence and diagnosis (persisted main snapshot at 2026-10-23 10:38:05 UTC)
- 19,157 CLOSED, 8,887 WIN, 10,270 LOSS; win rate 46.39%, PF 0.8729.
- Net **-$207,404.44**, roundtrip fee **$191,570.00**, implied gross *before trading fees* **-$15,834.44**. Reconciliation: gross - fee = net.
- At $10,000 notional per position and 0.05% fee **per side**, the minimum price move needed to pay *fees alone* is 0.10% per roundtrip, even before spread, impact, and settled funding.
- The v8 ledger samples up to 44 hypothetical OPENs per observer and up to 1,750 per UTC day; it is not a capital-constrained $10k portfolio, so the cumulative negative PnL **must not** be described as wallet equity, and a lower cumulative loss from sampling less **cannot** be claimed as evidence of higher strategy quality.
- Canonical notional-based v8 CLOSEs do not model real fills, full funding or market impact. The separate friction stress is hypothetical, not an observed fill.
- Even the price-only component is negative in this snapshot. Removing fee alone would *not* make this observed v8 aggregate profitable.

## Implemented safety policy
1. Production CLI default and GitHub v8 observation workflow: `--entry-mode observe-only`. In this mode, NEW legacy v8 OPENs have an effective budget **zero** irrespective of the research counter requested on the command line. The policy does **not** cancel, backdate, or modify any existing event or fixed-horizon exit.
2. All outstanding positions retain genuine quote-dependent due-exit handling; the existing hash chain, audit, heartbeat/health, and report persist normally. A missing public quote remains an explicit source failure.
3. The continuous recovery observer also passes `--entry-mode observe-only`. The prior forecast-free scheduler quality throttle remains available for explicit legacy research but is *not* a profitable alpha gate.
4. The persisted v8 report gains `entry_mode`, `entry_safety_policy`, and `economic_reconciliation`. The latter reports price-only gross, fee totals and net fee-only, and marks all three as **unfunded hypothesis scorecard**.
5. `--entry-mode legacy-explore` remains available for explicit offline/manual PAPER experimentation, never for a broker/exchange. It is **not** enabled by any scheduled workflow. No backtest-derived leader is silently promoted.
6. Production default and manual legacy research modes are regression-tested. A test opens a historical fixture, then confirms the default mode closes it but does not create any further events; hash-ledger replay and gross-fee-net identity remain valid.

## Scope and next research milestone
The existing crypto v2 account is an independently maintained, pre-registered forward trial; do not modify its frozen strategy settings or confuse its 1,000 USDT simulated equity with the v8 scorecard. Adaptive 144-arm shadow research in PR #78 is *not yet merged*, and its historical results do not constitute real prospective out-of-sample proof. Nasdaq and LQ45 currently have too few CLOSED paper trades to demonstrate after-cost alpha and remain isolated.

Future entry proposals for any prospective *funded-style simulation* need to be designed and registered **in a separate epoch** with:
- Entry-time predictor / expected favorable move or explicitly NO FORECAST => NO TRADE, never a return-derived hindsight veto.
- Independently confirmed 15m source (crypto) or completed prior EOD (stocks), plus realistic bid/ask, depth, execution delays, fee tiers, full settled funding, liquidations/portfolio constraints or corporate actions/settlement.
- Side-by-side predeclared no-trade, deterministic neutral and matched-horizon controls, conservative adverse-cost stress, date/asset clustering and correction for many hypothesis tests.
- Sufficient independent untouched forward days/regimes and positive *lower-bound* incremental expectancy after all costs, before proposing even a PAPER-only allocator.
- Explicit release review; never turn on real orders from a profit chart alone.

**Expected behavior after deployment:** canonical v8 cumulative PnL can still fall as previously opened positions reach their fixed horizons. This is not a new entry. Only after the pending cohort resolves should `created` and fee count stay flat in observe-only mode. Strategy profitability remains **unproven**. If the objective is discovery, use new matched-control SHADOW/forward research, not thousands of additional legacy notional positions.
