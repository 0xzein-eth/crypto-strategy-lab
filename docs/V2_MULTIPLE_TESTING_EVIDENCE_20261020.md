# Crypto Lab v2 — 26-arm shared-day familywise evidence rule

**Frozen 2026-10-20, research only, no orders, not an alpha promotion.**

## Why thousands of trades are insufficient

Cryptocurrency markets have shared shocks: trades on BTC/ETH/SOL on the
same calendar day and adjacent 4h horizons have correlated outcomes.
A collection of 13,000 labels across 13 days is NOT equivalent to 13,000
independent samples. Scanning 26 advanced hypotheses and 2,000 historical
parameters, repeatedly, creates enormous selection risk.

The v2 original ledger is a hash-verified real public exchange snapshot
stream, *not* actual executed venue fills. The v2 shadow study evaluates
26 frozen OHLCV hypotheses and a precommitted same-time same-symbol
SHA256 neutral LONG/SHORT direction for each signal, with modeled
0.05% per-side fees, observed bid/ask and hypothetical additional
30bps stress. Funding and impact can remain missing, which bars
any deployment inference.

## New read-only evidence procedure

`v2.evidence_gate` consumes **only** `v2_state/shadow_report.json`:

1. Refuses unknown/catalog-relabelled, duplicate, malformed,
   non-UTC, unobserved-future and incorrectly paired outcomes.
2. Includes only authentic **timely** 4h exits and adequate depth for
   BOTH signal and neutral control. The control side is frozen BEFORE
   the future outcome; the same control may match the strategy's
   direction, legitimately producing zero difference.
3. Aggregates signal-minus-control stress-adjusted %-return into
   equal-weight **UTC entry-day** blocks, clipping each difference to
   ±3pp. Report the absolute net stress return *separately*.
4. Requires at least **100 genuine matched closures, 20 independent
   UTC days, 4 ISO weeks** before performing any exploratory
   inferential statistic. Many simultaneous trades do not bypass this.
5. Uses 2,048 deterministic shared-UTC-day sign permutations,
   computing the maximum positive t statistic across the registered
   hypothesis family per perturbation (shared-day maxT adjustment).
   Permutation signs for a given day are **the same across all arms**,
   reflecting broad cryptocurrency market dependence. Randomness
   source is frozen SHA256, not repeated sampling to cherry-pick
   favorable p-values.
6. Reports adjusted exploratory p-values and raw day-level effect for
   diagnostics but **never promotes** an arm, changes the wallet
   allocator, or enables a real order.
7. `--asof` excludes results whose ACTUAL exit observation occurred
   in the future relative to a frozen cutoff; a candlestick's
   earlier signal alone is not a sufficient complete label.

**Limitations**: Even familywise correction does NOT compensate for
repeated inspection of a continuing dataset, non-exchange fills,
unknown funding, poorly balanced market regimes, serial correlation
within days/weeks, dynamic universe survivorship, or validation
reuse. The sign-flip null is an exploratory sensitivity analysis
requiring symmetry/exchangeability; do not describe its output as
a proof of trading profitability, a regulator-grade hypothesis test
or a clean final holdout.

## Final acceptance remains future-only

A *separately registered new* strategy version must pass a
truly untouched 60–90+ calendar-day **future** trial, after all
fees, funding, spread, latency and stress. Disallow tuning of
that version during the trial. Evaluate actual after-cost
incremental profit versus matched controls, conservative
risk-adjusted portfolio equity/drawdown and confidence/multiplicity
correction. If conditions fail, do not silently rerun or relabel
the same validation window as untouched.

The automated `v2-evidence-gate.yml` publishes an **artifact**,
never commits altered source or positions. When genuine observations
are missing, it publishes an explicit no-data status, never
manufacturing matched controls.
