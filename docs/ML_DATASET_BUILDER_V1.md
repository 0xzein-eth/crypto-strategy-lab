# ML Dataset Builder v1 — phase 1

## Purpose

Create a reproducible supervised-learning dataset from the canonical PAPER
event ledger without changing event history or experiment generation. This
phase prepares learning data; it does not train a model.

## Source and eligibility

- engine.replay() verifies the complete SHA-256 event chain and CLOSE arithmetic.
- Only CLOSED, timely (late_excluded == false) perpetual observations qualify.
  OPEN records, spot proxies, late closures, mismatched venue/instrument, and
  exits observed before evaluate_at are excluded.
- Labels come only from the existing same-venue/same-instrument public
  observation at or after evaluate_at; no historical lookup or synthetic price.
- Predictors are a strict whitelist of fields stored in the OPEN-time evidence
  snapshot plus OPEN-time strategy/context metadata. Missing features remain
  null and are never reconstructed from future data.
- Post-evaluation prices, timestamps, fees, P&L and normalized R are labels or
  audit metadata, never model features.

## Output

python ml_dataset.py writes deterministic JSONL rows and a JSON exclusion
report under artifacts/. These generated outputs should be retained as
workflow artifacts, not committed into the canonical ledger.

## Safety and scope

- Read-only: does not append, rewrite, or delete ledger events.
- PAPER-only research: no exchange order endpoints or credentials.
- Fixed 1/2/4/8/12/24-hour exit policy remains unchanged.
- No stop-loss, take-profit, or trailing-stop logic.
- No model training, prediction-driven allocation, or automatic promotion in
  phase 1. Phase 2 adds a baseline learner only after data coverage review.
