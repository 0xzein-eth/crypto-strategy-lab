# High-throughput PAPER strategy research and evidence quality — 2026-10-24

## Objective and correction

The owner correctly distinguishes **research throughput** from **real capital risk**. Running 44 hypothesis entries per observer in the canonical v8 event ledger DOES NOT place $440,000 actual trades; v8 has no real order system and repeats a $10,000 hypothetical notional *per sampled hypothesis*. Large negative cumulative notional PnL measures the combined score of weak/unproven hypotheses, **not the loss of a funded $10k portfolio**. Pausing all research OPENs in #79 did not increase model quality or expected alpha, and is reversed by this change.

**Production mode now:** `python engine.py --count 44 --entry-mode legacy-explore`, also in the continuous recovery runner. This is never exchange execution. The strict per-run 44, UTC daily 1,750, total 1,050 open, per-symbol 50 open, and 1 real symbol/15m signal slot limits remain in place. A 10-minute tick with no genuine opportunity may produce zero entries; 44 is a ceiling, not a target to fill with fake samples. Scheduler coverage quality throttles remain for true missing/late observation windows. `--entry-mode observe-only` remains available for manual source debugging, with due exits preserved.

## Enforce quality at the source, NOT by stopping research

Prior code returned `[]` when acquiring or parsing 15-minute OHLCV failed. Downstream mistakenly treated it as **valid checked candle, but no signal**, so a deterministic 12% control/proxy cohort could still enter for a candle that was *never verified*. Now:
- `advanced(...)` returns `None` for missing/invalid candle observations and **no PAPER OPEN** is created from that unavailable OKX slot;
- actual, validated candle observations that yield `[]` correctly remain real *no-confirmed-signal* opportunities with the predeclared sparse 20% baseline probe;
- confirmed 15m strategy signals may enter only when the original signal check returned actual evidence; fresh same-venue quote, true instrument identity, age and hash-ledger constraints remain;
- missing candle slots get their **own diagnostic counter**, not falsely included among no-signal or sampled cases;
- the former unconditional **abs(24h price change) >=0.5%** screen is removed for genuine fresh liquid quotes, allowing quiet/range regimes to enter 15m hypothesis discovery; the number of admitted quiet market quotes is measured. This is an expansion of sampling support, **not** proof those regimes have positive alpha.
- spot-proxy study events remain structurally possible when genuine source data exist, but are EXCLUDED from perpetual strategy evidence as before.

## Use research data instead of judging raw aggregate PnL

The immutable canonical ledger now drives read-only `cohort_diagnostics` in every v8 report. Every CLOSED outcome is partitioned in this order:
1. non-perpetual excluded from perpetual alpha evidence;
2. perpetual late closures excluded from *timely* alpha evidence;
3. genuinely timely perpetual outcomes grouped by **pre-entry signal provenance**, strategy and fixed holding horizon.

For every group, the report gives true observed **distinct entry UTC days**, number of (correlated) sampled hypotheses, gross price-only PnL, roundtrip fees, net fee-only PnL, mean per hypothesis, and optional modeled stress coverage/net. Provenance:
- `confirmed_15m_candle`: recorded confirmed OKX 15m indicator evidence with bar timestamp;
- `direction_proxy_or_neutral_control`: hypothesis based on 24h direction or deterministic CTRL, never claimed as confirmed 15m strategy alpha;
- `unverified_advanced_signal_metadata`: advanced label but lacking the required provenance, **never silently classified as confirmed**.

This reporting is **strictly descriptive** and NEVER fed into the online chooser; doing so would contaminate prospective unbiased exploration and result in data snooping. It has no champion, independent positive return, wallet fill or real trade declaration.

## Next validation enhancements, ordered by scientific value
- Export immutable per-signal opportunity history (including NO_TRADE/no-signal/rejected/missing source) so opportunity denominators are measured over 100% of genuinely inspected moments; current opportunity audit is only for the latest observer tick.
- Attribute date-clustered **after-stress** expectancy for each matched symbol/horizon/regime cohort against a simultaneous deterministic neutral comparator, with *minimum sample-by-date* and familywise multiple-hypothesis penalties (no comparing a 1h signal directly to a 24h control).
- Distinguish training-selection from sealed untouched independent multi-month holdout. Historical 2400-arm searches and repeated monitored partitions are discovery material, NOT final proof.
- Expand original measured OHLCV, spread orderbook, settled funding and feasible fills at matching decision times; do not replace missing execution cost with assumed zero. Add complete attribution of adverse slippage and market impact.
- Maintain a separate fee-aware and margin/cash constrained v2 shadow paper wallet; NEVER optimize v8 raw cumulative notional PnL as if it were investable equity.
- Only use independently positive *after-all-costs* net edge for a proposed and reviewed simulated allocation. Never authorize real orders from backtests or v8 historical drawdowns.

## Acceptance and audit
- High-volume research workflow/recovery runner both explicitly opt into `legacy-explore`.
- Existing hash-immutable history left unchanged. Source exceptions and missing OHLCV do not yield fake fallback experiments.
- Synthetic offline tests cover no-candle-versus-valid-no-signal separation; per-group fee/provenance/cost reconciliation; preservation of optional observe-only and exit lifecycle.
- All existing CI and ledger audit jobs must succeed before merge. Future observer report must independently show `entry_mode=legacy-explore`, while `added` may be zero in genuinely sparse conditions.
- This change restores **data generation**, not positive expectancy. Strategy selection remains unsupported until independent prospective after-cost validation.


## Implemented follow-up — 2026-10-28

- The valid-candle/no-confirmed-signal baseline probe rate is now 20% (up from 12%). This applies only after a fresh eligible quote and successful confirmed-candle evaluation; missing/failed OHLCV still cannot create a fallback entry. This is a declared research-coverage change, not an alpha claim.
- A separate `data/opportunity_history.jsonl` records one aggregate row per observer tick, including screened slots, confirmed/no-signal counts, unavailable-candle counts, rejections, opens and the no-entry reason. Rows are hash-chained and verified before each append; the immutable canonical trade event ledger remains untouched.
- The history is run-level aggregate telemetry, NOT a reconstructed per-symbol opportunity tape. The next enhancement should add per-symbol decision records and matched, same-symbol/same-horizon controls before using these data for causal comparisons.
