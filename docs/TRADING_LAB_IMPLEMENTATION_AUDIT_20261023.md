# Implementation and evaluation audit — 23 October 2026

## Snapshot provenance
Checked from versioned JSON files on the default branch; values are NOT predictions, real account balances, or guarantees.

| Epoch | Report snapshot | Verified / observations | Wallet / economic status |
|---|---|---|---|
| Crypto v8 unfunded hypothesis ledger | 2026-10-23T00:00:41Z | 18,412 CLOSED; 18,842 CREATED; 48 instruments | -$195,618.66 aggregate net hypothetical P&L; $184,120 trading fees; -$11,498.66 pre-fee price movement; PF 0.8762 |
| Crypto v2 single-wallet paper | 2026-10-22T23:15:52Z | 34 observations; 2 CLOSED / 2 losing | 997.76 USDT from 1,000 USDT; full funding and live slippage not modeled |
| Nasdaq USD cash PAPER | last EOD 2026-10-21 | 1 completed session, 0 CLOSED | 10,000 USD simulated equity; WR and PF unknown |
| LQ45 IDR cash PAPER | last EOD 2026-10-21 | 2 completed sessions, 3 open, 0 CLOSED | 9,966,590.18 IDR marked simulated equity; 0.3341% unrealized/mark-to-market decrease |

Cross-epoch performance cannot be summed. LQ45 expiry protection is October 30, 2026; a new verified membership snapshot is necessary for entries after this effective period.

## What this implementation changes
1. `research_quality/legacy_quality.py` and `research_quality/__init__.py` restore the original `research_quality.evaluate` API that the v8/v2 analysis imported. This resolves a namespace collision introduced by creating a same-named package.
2. `research_quality/crypto_forensics.py` audits the authenticated v8 event replay and reconciles total trade count, fee and PnL with the canonical report. Segments strategies by arm and holding horizon and counts independent entry days. Its P&L is never account equity.
3. `research_quality/calendar_evidence.py` gives day-cluster, multiplicity-adjusted **descriptive** bounds; correlated same-day trades cannot masquerade as independent samples.
4. `research_quality/crypto_composite_audit.py` and `research_quality/equity_ensemble.py` include those bounds in SHADOW-only composite reports. The equity vote now requires at least two BUY components and no contradictory EXIT among members.
5. `research_quality/audit.py` now rejects supposedly paper-only wallet reports with positive or unknown order status. This is a reporting safety invariant, not a live order-blocker.
6. `.github/workflows/research-diagnostics.yml` schedules hash/ledger checks, Python regressions, full v8 economics, independently clustered shadow evidence, compositional diagnostics, and archived report artifacts. `.github/workflows/ensemble-research.yml` tests Nasdaq/LQ45 composites separately.
7. Tests added/updated for package compatibility, forensics reconciliation, clustered uncertainty, conflict veto and paper-account flags.

## What does NOT change
- No trade is sent to an exchange or broker.
- No frozen 90-day crypto research selection, historical event or cash-wallet position is rewritten.
- No model is auto-promoted; no current strategy meets credible independent real-after-all-costs evidence.
- Existing v8 hypothesis ledger remains an experimental signal farm. Repeated 10k USD notional is NOT a funded 10k account; 18,412 trades do NOT mean 18,412 independent market regimes.

## Reproduce
From the repository root on Python 3.11+:

```bash
python -m unittest discover -s tests -p 'test_research_quality_*.py' -v
python -m unittest discover -s tests -p 'test_equity_ensemble_regression.py' -v
python engine.py --verify-only
python -m v2.forward_paper --verify-only
python -m equity_lab.forward --market NASDAQ --verify-only
python -m equity_lab.forward --market LQ45 --verify-only
python -m research_quality.crypto_forensics --output /tmp/crypto-v8-forensics.json
python -m v2.evidence_gate --source v2_state/shadow_report.json --output /tmp/v2-evidence.json
python -m research_quality.crypto_composite_audit --output /tmp/crypto-ensemble.json
python -m research_quality.audit --output /tmp/cross-market.json
```

Historical equity research additionally fetches genuine public EOD data and can fail when external sources are unavailable:
```bash
python -m research_quality.equity_ensemble --market NASDAQ --output /tmp/nasdaq-ensemble.json
python -m research_quality.equity_ensemble --market LQ45 --output /tmp/lq45-ensemble.json
```

## Explicit verification limitation
GitHub connector accepted these source commits, but its workflow-run listing/dispatch is unavailable. Combined commit-status endpoint did not return checks. **Do not mark CI green or the scripts production-ready until logs/artifacts have been inspected.** The code has not been proven to increase WR/ROI. Never interpret an absence of a failed check as a successful run.

## Next acceptance gates
- Confirm the diagnostic workflow passes every regression and ledger replay, inspect exported artifacts and correct any CI failure.
- Replace hypothetical execution friction with verified fee tiers, bid/ask depth, funding settlement coverage, and stock broker/investor-specific brokerage + corporate action accounting.
- Increase genuine independent forward days across multiple regimes, measure outcome completeness and within-horizon delayed exits.
- Demonstrate positive *net* expectancy and lower-bound across day clusters **and** benchmark/control after multiplicity and cost stress. Compare no-trade as a legitimate baseline.
- Keep independent prospective trials registered in advance. New experiments may be prepared now but cannot be called successful until they actually encounter subsequent markets.
