# Confirmed diverse paper hypotheses — registered 2026-10-19

**Scope:** future-only OPEN on authentic confirmed 15-minute OKX USDT perpetual OHLCV. Fixed exits **1/2/4/8/12/24h**, never SL/TP/trailing, historical edits or real-money orders. No hypothesis has proved positive alpha. Original family identifiers, results, learner profile and hash-chain history are not altered.

## Four structurally different new strategies

| New research arm | Hypothesis (calculated only from LAST CONFIRMED 15m candles) | Counter-hypothesis |
| --- | --- | --- |
| `IBREAK-v1` | A 15m *inside-bar* (child high/low contained by prior mother, width <=75% mother), followed by a **confirmed close beyond mother high/low +0.05 ATR**, >=1.15x prior-20 volume, SMA20/SMA50 trend same direction | Most range releases are noisy after fees; breakouts fail on correlated volatile assets |
| `BANDREV-v1` | Previous confirmed close beyond its own trailing 20-close **±1.8 sigma**, followed by a new CONFIRMED close back inside ±1.0 sigma, directional rebound, SMA20-SMA50 separation <1.5 ATR, volume >=0.75x | Snapback is an overfit artefact, real fees or momentum crashes dominate |
| `VWAPTR-v1` | New confirmed volume-weighted typical price VWAP20 reclaim (previous close opposite previous VWAP), now close aligns SMA20>SMA50 and RSI14>=52 LONG; symmetric SHORT RSI<=48. Directional candle body and volume >=1.05x | Trend filtering lowers sampling and does not add significant incremental edge vs original VWAP-v1 |
| `EFFTREND-v1` | Six confirmed 15m close-to-close steps with *net displacement / gross absolute travel* >=0.82, net movement >=0.7 ATR; SMA20/SMA50 direction and SMA20 slope align; volume between 0.9 and 2.5x, last range <=2.5 ATR to reject single spikes | Efficiency ratio can be predictive only during a particular market episode; continuation fails after costs |

All features use only observed, confirmed same-market 15-minute bars and no CLOSE outcome. The per-OPEN feature evidence includes `source_version`, `hypothesis_version`, `signal_rule`, `bar_time`, `bar_span`, and the decisive observation values (e.g. last efficiency / prior z-score). Signal labels are independent of older `BR-v3`, `FB-v3`, `RSI-v1` and `VWAP-v1` even if multiple hypotheses coincide on the same candle.

**What did not change:** existing basic baselines, 20% deterministic control branch if offered, positive baseline exploration, 15m one-OPEN-per-symbol-slot, strict source freshness/venue/instrument, six fixed horizons, delayed observations classification, UTC-day volume / OPEN caps, no automatic champion. The new families add 4 arms to the previous 21 confirmed arms: **25 confirmed** plus 3 baselines = 28 registered arms. Counts are not independent tests.

## Prospectively frozen protocol

1. Do NOT fill in historical earlier OPENs as these new arms. First eligible observations can only start after deployment commit; initial histories are empty.
2. The new 4 arms × 6 horizons create at least **24 separately evaluable hypothesis-by-horizon cells**. Further symbol / direction / regime splits increase multiplicity; don't claim a winner after many peeks.
3. Report actual `entry_opportunity_audit.confirmed_arm_opportunities` for each new arm (when a symbol can actually be evaluated), actual `new_paper_opens_by_arm`, eligible CLOSEs and a source-ledger hash. Opportunity counts are per tick and NOT a day-long counter.
4. For any candidate, compare fee-adjusted net R and separate hypothetical friction-stress cost to matched contemporaneous CTRL-v1 on the same original entry day, symbol, side, 1/2/4/8/12/24h horizon and frozen regime, within <=120min and no duplicate control WITHIN one arm.
5. Initial 20 genuine distinct UTC days, four calendar weeks and 100 matched controls are **readiness thresholds**, NOT inferential proof. Day-cluster descriptive intervals and win rate are NOT independent final validation or familywise-adjusted hypothesis tests.
6. A final calendar holdout must be registered **BEFORE** it begins, AFTER rule choice, with no tuning from the same validation outcomes; include multi-test correction, funding/spread stress, concentration and availability sensitivity. A failure is a useful result, not a reason to rewrite earlier observations.
7. A future allocator that reduces negative arms or promotes a positive strategy must be a separate reviewed prospective policy with controls and positive exploration retained. It is NOT included in this change.

## No-new-entry diagnosis

The versioned learner-v7 prospectively favors the availability of REAL confirmed signals: 35/100 hash buckets for original-OPEN-count source-balanced arm sampling, 35/100 for uniform confirmed exploration, 20/100 for CTRL when offered, 5/100 for simple directional proxy experiments, 5/100 for neutral mixture. This **changes the allocation distribution** but not any historical OPEN, baseline controls or winning-trade-based selection. It cannot force advanced entries when no confirmed candle exists.

The existing paper status `NO_NEW_SIGNALS` is retained for compatibility, but it previously conflated depleted daily intake quota, full concurrency, occupied 15-minute asset slots, no qualifying real public quotes, and rejected candidate selections.

The extended `data/report.json → entry_opportunity_audit` now records: `daily_new_entry_quota`, `utc_day_opens_before_tick`, `utc_day_quota_remaining_before_tick`, `concurrent_open_before_tick`, `concurrent_open_remaining_before_tick`, `effective_new_slots_before_signal_checks`, and `no_new_entry_reason`. This diagnosis is computed from the actual ledger at the observed time, never from fabricated prices. Zero eligible quotes from an already depleted quota means **not screened**, rather than a claim that no signals existed in market data.

## Acceptance

- Offline fixtures prove all four arms and both long/short directions from confirmed bars; weak/false patterns suppressed.
- Unconfirmed 15m future bars and non-OKX ticker return zero new ARM outcomes.
- End-to-end paper OPEN retains exact fixed horizon and previous records byte-for-byte.
- All GitHub Actions code, audit and matched-control workflows pass before merge; no marker `edge_proven` becomes true.
