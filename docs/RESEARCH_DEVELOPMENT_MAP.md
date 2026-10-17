# Crypto Strategy Lab — prospective evidence development map

Status: PAPER ONLY. No live orders, no synthetic fills, no historical OPEN/CLOSE edits.
Exit remains FIXED HORIZON 1/2/4/8/12/24 hours; NO stop-loss, take-profit, or trailing stop.

## Current bottleneck

High trade count does not imply independent evidence. Correlated crypto symbols,
regimes, UTC days and repeated strategy tests can manufacture apparent winners.
The published fee-adjusted P&L and separate spread/slippage stress scenarios
must remain distinct. Never retroactively relabel an entry or use future data.

## Workstream 1 — Integrity and observability

- Audit full canonical hash-chain before research, verify report against replay.
- Reject stale/non-same-instrument or wrong-venue public observations.
- CLOSE only from observed fresh public quotes at/after evaluate_at; record delay,
  and exclude late CLOSE from timely research without deleting it.
- Track GitHub Actions cron gaps, unique confirmed 15m symbol slots and genuine
  independent UTC days/weeks; do not backfill missed entries.
- Attach source ledger tip and report timestamp to every research artifact.

## Workstream 2 — Evidence, not hindsight optimization

- Use entry-frozen 24h regime, side, horizon and strategy for descriptive
  stratification (regime_evidence.py). Keep separate day-frozen monitoring rows.
- Continue exact-stratum matched controls with no within-arm control reuse;
  report matched fraction and unmatched selection bias.
- Require adequate real calendar coverage, positive after-friction paired
  holdout estimates, robust multi-week forward evaluation and explicit
  multiplicity controls before ANY champion claim.
- Check concentration by symbol/day/regime; negative and positive regimes must
  both remain represented. Record version and hypothesis registration date.
- Compare fee-adjusted recorded R with separate spread/slippage stress R.
  Never silently replace official paper P&L with stressed scenario.

## Workstream 3 — New prospective hypotheses

Candidate ideas, NOT approved or activated:
1. BR-regime-v1: only a confirmed 15m Donchian breakout with positive
   frozen 24h regime for LONG (negative for SHORT), on OKX USDT swaps.
2. TP-regime-v1: confirmed SMA20 pullback in matching frozen 24h direction.
3. RANGE-reject-v1: confirmed wick rejection under weak SMA20/SMA50
   separation, test separately for 1/2/4/8/12/24h horizons.

Before implementation: ensure all required features exist at OPEN; freeze
thresholds and rule version; verify confirmed-bar timing and sample provenance;
add deterministic synthetic fixture tests, missing-data rejection tests,
no-lookahead tests, and explicit control/neutral allocation. Deploy only to
NEW paper entries. Never alter historical trades or fixed-horizon exits.
These hypotheses are NOT claimed profitable.

## Workstream 4 — Decision protocol

- Keep a permanent CTRL arm and nonzero exploration of all eligible arms.
- No allocation changes from reused holdout, retrospective matched-control
  estimates, or cherry-picked short-term win rate.
- Introduce changes through versioned PR + green CI + full ledger audit.
- Evaluate across distinct future weeks and stress scenarios; retire or
  revise hypotheses only under a pre-registered policy, without erasing data.
- Publish wins, losses, late-excluded counts, coverage, sample size and
  uncertainty together. No promises of positive returns.

## Immediate deliverable

A read-only, reproducible frozen-regime/horizon/side evidence map and tests.
It is diagnostic only and intentionally does not increase or suppress trade
frequency or claim edge. The next candidate rule needs independent prospective
qualification before allocation.
