"""Pre-registered entry-frozen directional hypotheses, PAPER ONLY.

Only reuse authentic confirmed 15m OKX swap signals and the authentic OKX
same-instrument screening ticker. These hypotheses add NEW arms, not labels
for historical trades. No prices, orders, or exits are generated here.
"""
import math

VERSION = "entry-regime-confirmation-v1"
MIN_DIRECTIONAL_24H_PCT = 1.0
# Base signal labels are themselves produced solely from CONFIRMED candles.
SOURCE_ARMS = {"BR-v3": "BRREG-v1", "TP-v3": "TPREG-v1"}


def candidates(detections, snapshot, symbol):
    """Add directional regime-confirmed variants, or fail closed.

    ENTRY features: same-venue OKX USDT perpetual ticker pct24h,
    past confirmed OHLCV signal, trailing SMA20/50; never CLOSE data.
    """
    if not isinstance(snapshot, dict):
        return []
    if (snapshot.get("provider") != "okx-swap" or
            snapshot.get("market_type") != "perpetual" or
            snapshot.get("symbol") != symbol or
            snapshot.get("instrument") != symbol + "-USDT-SWAP" or
            not isinstance(snapshot.get("observed_at"), str)):
        return []
    move = snapshot.get("pct24h")
    if isinstance(move, bool) or not isinstance(move, (int, float)):
        return []
    if not math.isfinite(move) or abs(move) < MIN_DIRECTIONAL_24H_PCT:
        return []
    output = []
    for row in detections:
        if row.get("strategy") not in SOURCE_ARMS:
            continue
        side = row.get("side")
        if side not in ("LONG", "SHORT"):
            continue
        if (side == "LONG" and move <= 0) or (side == "SHORT" and move >= 0):
            continue
        evidence = row.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("bar_span") != "15m confirmed OKX USDT-SWAP":
            continue
        try:
            fast, slow = float(evidence["sma20"]), float(evidence["sma50"])
            atr = float(evidence["atr14"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(n) for n in (fast, slow, atr)) or atr <= 0:
            continue
        if not ((side == "LONG" and fast > slow) or
                (side == "SHORT" and fast < slow)):
            continue
        enriched = dict(evidence)
        enriched.update({
            "source_strategy": row["strategy"],
            "source_version": VERSION,
            "hypothesis_version": VERSION,
            "entry_direction_24h_pct": round(move, 6),
            "entry_regime_source": "same-instrument-okx-swap-public-screening-ticker",
            "entry_regime_observed_at": snapshot["observed_at"],
            "signal_rule": (
                row.get("evidence", {}).get("signal_rule", "confirmed-candle") +
                "; aligned SMA20/SMA50 and same-instrument 24h move >=1pct magnitude"
            ),
            "research_only": True,
        })
        output.append({"strategy": SOURCE_ARMS[row["strategy"]],
                       "side": side, "evidence": enriched})
    return output
