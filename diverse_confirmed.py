"""Four distinct forward-only PAPER hypotheses from completed OKX 15-minute bars.

All observations are computed from bars ending at the candidate's confirmed
close. No future candle, historical outcome, actual order, stop or fill.
Hypotheses are falsifiable; they are NOT verified trading advantages.
"""
import math

VERSION = "diverse-confirmed-2026-10-19-v1"
ARMS = ("IBREAK-v1", "BANDREV-v1", "VWAPTR-v1", "EFFTREND-v1")
MIN_BARS = 60


def detect(bars, frozen_features):
    if len(bars) < MIN_BARS:
        raise ValueError("insufficient confirmed 15m bars for diverse hypotheses")
    f = frozen_features
    if f.get("bar_span") != "15m confirmed OKX USDT-SWAP":
        raise ValueError("INTEGRITY_FAILURE: missing confirmed source")
    atr = f["atr14"]
    if not isinstance(atr, (int, float)) or not math.isfinite(atr) or atr <= 0:
        return []
    close = f["last_close"]
    volume = f["vol_ratio"]
    outputs = []

    def emit(arm, side, rule, observed):
        if arm not in ARMS or side not in ("LONG", "SHORT"):
            raise ValueError("unregistered paper hypothesis")
        evidence = {key: round(value, 8) if isinstance(value, float) else value
                    for key, value in f.items()}
        evidence.update({
            "signal_rule": rule,
            "source_version": VERSION,
            "hypothesis_version": VERSION,
            "research_only": True,
            "frozen_signal_observation": {
                key: round(value, 8) if isinstance(value, float) else value
                for key, value in observed.items()
            },
        })
        outputs.append({"strategy": arm, "side": side, "evidence": evidence})

    # 1: Inside-bar compression releases in the direction of the trailing
    # SMA trend. Mother, daughter and breakout are three actual CLOSED bars.
    mother, child = bars[-3], bars[-2]
    mother_width = mother["high"] - mother["low"]
    child_width = child["high"] - child["low"]
    if (mother_width > 0 and 0 <= child_width <= 0.75*mother_width
            and child["high"] <= mother["high"]
            and child["low"] >= mother["low"] and volume >= 1.15):
        if close > mother["high"] + 0.05*atr and f["sma20"] > f["sma50"]:
            emit("IBREAK-v1", "LONG",
                 "confirmed inside child <=75pct mother range; break mother high +0.05ATR, volume >=1.15, SMA20>50",
                 {"mother_high": mother["high"], "mother_low": mother["low"],
                  "child_width_ratio": child_width/mother_width})
        elif close < mother["low"] - 0.05*atr and f["sma20"] < f["sma50"]:
            emit("IBREAK-v1", "SHORT",
                 "confirmed inside child <=75pct mother range; break mother low -0.05ATR, volume >=1.15, SMA20<50",
                 {"mother_high": mother["high"], "mother_low": mother["low"],
                  "child_width_ratio": child_width/mother_width})

    # 2: Two-bar statistical extreme REENTRY (not the static extreme
    # mean-reversion arm). The previous bar was outside its own trailing
    # 20-close band; current CONFIRMED bar moved back inside a narrower band.
    closes = [bar["close"] for bar in bars]
    prior = closes[-21:-1]
    current = closes[-20:]
    prior_mean = sum(prior)/20
    current_mean = sum(current)/20
    prior_sd = math.sqrt(sum((x-prior_mean)**2 for x in prior)/20)
    current_sd = math.sqrt(sum((x-current_mean)**2 for x in current)/20)
    trend = (f["sma20"]-f["sma50"])/atr
    if prior_sd > 0 and current_sd > 0 and abs(trend) < 1.5 and volume >= 0.75:
        old = closes[-2]
        prior_z = (old-prior_mean)/prior_sd
        current_z = (close-current_mean)/current_sd
        if prior_z <= -1.8 and current_z > -1.0 and close > old:
            emit("BANDREV-v1", "LONG",
                 "prior confirmed z20<=-1.8; current z20>-1; weak SMA trend, positive recovery",
                 {"previous_z20": prior_z, "current_z20": current_z})
        elif prior_z >= 1.8 and current_z < 1.0 and close < old:
            emit("BANDREV-v1", "SHORT",
                 "prior confirmed z20>=1.8; current z20<1; weak SMA trend, negative recovery",
                 {"previous_z20": prior_z, "current_z20": current_z})

    # 3: VWAP price reclaim must ALSO align with the SMA20/SMA50 direction,
    # confirmed RSI momentum, current candle body and confirmed volume.
    previous_vwap, current_vwap = f["vwap20prev"], f["vwap20"]
    if (previous_vwap is not None and current_vwap is not None
            and volume >= 1.05):
        if (f["c_prev"] <= previous_vwap and close > current_vwap
                and close > f["sma20"] > f["sma50"]
                and f["rsi14"] >= 52 and close > f["last_open"]):
            emit("VWAPTR-v1", "LONG",
                 "confirmed VWAP20 reclaim, SMA20>SMA50, RSI14>=52, bullish body, volume>=1.05",
                 {"vwap_before": previous_vwap, "vwap_now": current_vwap})
        elif (f["c_prev"] >= previous_vwap and close < current_vwap
              and close < f["sma20"] < f["sma50"]
              and f["rsi14"] <= 48 and close < f["last_open"]):
            emit("VWAPTR-v1", "SHORT",
                 "confirmed VWAP20 breakdown, SMA20<SMA50, RSI14<=48, bearish body, volume>=1.05",
                 {"vwap_before": previous_vwap, "vwap_now": current_vwap})

    # 4: Price-path EFFICIENCY over six confirmed changes, not just RSI
    # or a single impulse. Rejects oscillating bars and one huge outlier.
    last7 = closes[-7:]
    travel = sum(abs(b-a) for a, b in zip(last7, last7[1:]))
    displacement = last7[-1]-last7[0]
    current_range = f["last_high"]-f["last_low"]
    if (travel > 0 and 0.9 <= volume <= 2.5 and
            current_range <= 2.5*atr):
        efficiency = abs(displacement)/travel
        if efficiency >= 0.82 and displacement >= 0.7*atr and (
                close > f["sma20"] > f["sma50"] and
                f["sma20"] > f["sma20prev"]):
            emit("EFFTREND-v1", "LONG",
                 "6 confirmed close-to-close changes efficiency>=0.82 and drift>=0.7ATR; SMA20>50 rises, volume0.9..2.5",
                 {"efficiency6": efficiency, "net_change6": displacement})
        elif efficiency >= 0.82 and displacement <= -0.7*atr and (
                close < f["sma20"] < f["sma50"] and
                f["sma20"] < f["sma20prev"]):
            emit("EFFTREND-v1", "SHORT",
                 "6 confirmed close-to-close changes efficiency>=0.82 and drift<=-0.7ATR; SMA20<50 falls, volume0.9..2.5",
                 {"efficiency6": efficiency, "net_change6": displacement})
    return outputs
