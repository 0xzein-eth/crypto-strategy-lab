# ML feature engineering and availability audit v1

## Why this phase exists

The v1 dataset showed that many technical-indicator fields are missing in roughly
half of all rows. The missingness is not random: it is concentrated in strategy
families such as CTRL-v1, BR-proxy-v1 and MR-proxy-v1, whose entry records do not
carry the same candle-derived evidence. Filling these values with outcomes or
later market observations would create leakage, so this phase keeps them null.

## Derived OPEN-time features

This module adds normalized features using only evidence already frozen in the
dataset at OPEN:
- price distance from SMA20, SMA50 and VWAP20;
- centered RSI and RSI change from prior RSI;
- ATR as a percentage of entry-time close;
- existing z-score, volume ratio and prior range width;
- lower-minus-upper wick imbalance.

Every derived row records the same `features_asof` timestamp. Missing or invalid
inputs remain null. No future candles, exit prices, labels or P&L enter feature
calculation.

## Availability diagnostics

The audit reports missingness by strategy and horizon. This is important because
a global missingness percentage hides structural differences between strategy
families. The artifact is intended to guide the next data-collection repair:
capture consistent entry-time market context at OPEN for strategies that
currently omit candle evidence. It does not synthesize or backfill old samples.

## Safety and evaluation

This is feature preparation and audit only. It does not alter trade generation,
allocation, the canonical ledger, or fixed 1/2/4/8/12/24-hour exits. All outputs
remain shadow research. No live orders, stop-loss, take-profit or trailing stop.
