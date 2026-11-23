# PAPER ML prospective forward validation v1

## Activation boundary

The prospective cohort starts only after the first successful main-branch run has trained all three preregistered candidates from the verified historical PAPER ledger and persisted `ml_forward_state/frozen_bundle.json`. The bundle records the ledger tip, training/early-stopping row hashes, latest historical label timestamp, ordered feature-schema hash, source-code fingerprint, manifest hash, and each model ID.

If any candidate cannot be trained, the initialization fails and no cohort begins. An existing bundle is never overwritten. Changes to the manifest, model implementation, feature builder, training code, or forward-validation code invalidate the bundle and require a separately versioned freeze.

## Prediction capture

The workflow is serialized and triggered by successful canonical PAPER observer runs, with a ten-minute scheduled retry. It reads the canonical ledger but never writes to `data/`.

A prediction is recorded only when:
- the canonical record is still `OPEN`;
- it is a timely eligible OKX USDT-SWAP perpetual record with confirmed 15-minute OPEN evidence;
- its OPEN timestamp is at or after the frozen cohort start; and
- the observer captures it within the preregistered 900-second window.

The three model probabilities and the constant training-prevalence reference are stored with record ID, strategy, symbol, side, horizon, bundle ID, model IDs, and feature-schema hash. Each prediction is immutable. A stale OPEN record or a record already CLOSED before capture is recorded as skipped. Predictions are never backfilled after an outcome is known.

## Outcome scoring

A prediction is scored only after its fixed horizon has elapsed and the canonical ledger records a timely eligible CLOSED outcome. Late, spot, missing-evidence, or otherwise ineligible closes are excluded. Outcome labels are appended as separate events, not written into the original prediction.

## Integrity and evaluation

Predictions, scores, skips, and exclusions are recorded in a sequential SHA-256 hash-chained journal. The journal is physically append-only. The derived report compares Logistic Regression, Gradient Boosting, and MLP against the frozen training-prevalence constant and Logistic Regression reference, using Brier score, log loss, ROC-AUC, accuracy, UTC-day cluster deltas, and strategy/side/horizon/symbol strata.

The report is diagnostic while the cohort accumulates. No champion is selected, no mid-cohort retraining or tuning is allowed, and no strategy sampler, wallet, allocation, or order interface is connected. A prospective score is not proof of alpha or permission to trade live.

## Commands

- `python -m ml_forward_validation --run`: initialize the frozen bundle once, or capture eligible OPEN predictions and score matured outcomes.
- `python -m ml_forward_validation --verify-only`: verify the bundle, journal chain, and derived status without mutation.
