"""Ten versioned IDX daily-bar hypotheses for HISTORICAL SHADOW research.

The original 4-arm cash PAPER wallet is deliberately unchanged: adding
experimental arms there would rewrite past signal semantics. These BUY signals
consume exclusively completed trailing OHLCV, never actual broker orders.
"""
import math
from stock_lab import strategies

VERSION="idx-expanded-shadow-ten-v1"
ARMS=(
    "TREND_RECLAIM30",
    "DONCHIAN40",
    "DONCHIAN60",
    "RSI_RECOVERY35",
    "BOLLINGER_REENTRY20",
    "VOLUME_SQUEEZE20",
    "VOLUME_CLIMAX_FADE",
    "ATR_EXPANSION14",
    "MOMENTUM60",
    "LOWVOL_PULLBACK60",
)
MIN_BARS=120


def _std(values):
    avg=sum(values)/len(values)
    return math.sqrt(sum((v-avg)**2 for v in values)/len(values))


def signals(rows):
    """Frozen BUY/FLAT proposals for NEXT observed session; no EXIT tuning."""
    if len(rows)<MIN_BARS:
        raise ValueError("DATA_INSUFFICIENT: 120 completed sessions required")
    f=strategies.features(rows)
    close=rows[-1]["close"]
    prev=rows[-2]["close"]
    sma20=f["sma20"]
    sma60=f["sma60"]
    positive=close>sma60 and sma60>=f["sma60_prev"]
    volume=f["volume_ratio"]
    high40=max(x["high"] for x in rows[-41:-1])
    high60=max(x["high"] for x in rows[-61:-1])
    upper10=max(x["high"] for x in rows[-11:-1])
    rsi_now=f["rsi14"]
    rsi_prev=strategies.rsi(rows[:-1])
    trailing20=[x["close"] for x in rows[-20:]]
    sd20=_std(trailing20)
    lower=sma20-2*sd20
    prior20=[x["close"] for x in rows[-21:-1]]
    prior_lower=sum(prior20)/20-2*_std(prior20)
    returns=[math.log(b["close"]/a["close"])
             for a,b in zip(rows[-21:-1],rows[-20:])]
    previous_vol=_std(returns)
    recent_returns=[math.log(b["close"]/a["close"])
                    for a,b in zip(rows[-11:-1],rows[-10:])]
    squeeze=previous_vol>0 and _std(recent_returns)<0.75*previous_vol
    yesterday=rows[-2]
    yesterday_mid=(yesterday["high"]+yesterday["low"])/2
    today=rows[-1]
    wick_denominator=today["high"]-today["low"]
    lower_wick=((min(close,today["open"])-today["low"])/wick_denominator
                if wick_denominator>0 else 0)
    true_ranges=[max(r["high"]-r["low"],
                     abs(r["high"]-p["close"]),abs(r["low"]-p["close"]))
                 for p,r in zip(rows[-16:-1],rows[-15:])]
    atr14=sum(true_ranges[-14:])/14
    true_range=max(today["high"]-today["low"],
                   abs(today["high"]-prev),abs(today["low"]-prev))
    momentum60=(close/rows[-61]["close"]-1)*100
    prior_low10=min(x["low"] for x in rows[-11:-1])
    checks={
        "TREND_RECLAIM30":positive and prev<=f["sma20_prev"] and
            close>sma20 and volume>=1.0 and close>yesterday_mid,
        "DONCHIAN40":positive and close>high40 and volume>=1.10,
        "DONCHIAN60":positive and close>high60 and volume>=1.15,
        "RSI_RECOVERY35":rsi_prev<35<=rsi_now and close>sma60*.95,
        "BOLLINGER_REENTRY20":prev<prior_lower and close>lower and
            rsi_now<48 and close>sma60*.85,
        "VOLUME_SQUEEZE20":positive and squeeze and
            close>upper10 and volume>=1.10,
        "VOLUME_CLIMAX_FADE":volume>=2.0 and lower_wick>=.50 and
            close>today["open"] and close>sma60*.80,
        "ATR_EXPANSION14":positive and atr14>0 and
            true_range>=1.6*atr14 and close>upper10 and volume>=1.25,
        "MOMENTUM60":positive and 8<=momentum60<=40 and
            close>sma20 and f["return5_pct"]>0 and volume>=.75,
        "LOWVOL_PULLBACK60":positive and
            f["daily_realized_vol20"]<=.025 and
            f["return20_pct"]>=2 and prev<=f["sma20_prev"]*1.015 and
            close>sma20 and close>prior_low10,
    }
    if set(checks)!=set(ARMS):
        raise ValueError("INTEGRITY_FAILURE: experimental catalog changed")
    return {name:"BUY" if value else "FLAT" for name,value in checks.items()}
