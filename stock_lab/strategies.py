"""Four fixed, economically distinct *unproven* IDX cash-equity hypotheses.

Inputs are only completed daily OHLCV at/before a frozen session date.
BUY/EXIT decisions are not executable fills: modeled next-session
OPEN can only be *confirmed retrospectively* after that day is complete.
No futures, margin, SHORT, leveraged strategies or technical lookahead.
"""
import math

SCHEMA="idx-4-hypotheses-daily-v1"
ARMS=("TREND20_60","BREAKOUT20","RSI_REVERT","LOWVOL_MOM")
MIN_BARS=75


def sma(rows,n):
    return sum(r["close"] for r in rows[-n:])/n


def rsi(rows,n=14):
    closes=[r["close"] for r in rows[-(n+1):]]
    changes=[b-a for a,b in zip(closes,closes[1:])]
    gain=sum(max(0,v) for v in changes)/n
    loss=sum(max(0,-v) for v in changes)/n
    if loss==0:
        return 100.0 if gain else 50.0
    return 100-100/(1+gain/loss)


def features(rows):
    if len(rows)<MIN_BARS:
        raise ValueError("DATA_INSUFFICIENT: fewer than 75 completed equity sessions")
    if len({b["date"] for b in rows})!=len(rows) or any(
            a["date"]>=b["date"] for a,b in zip(rows,rows[1:])):
        raise ValueError("DATA_INVALID: historical price dates not increasing")
    last=rows[-1]
    prior=rows[:-1]
    last_sma20=sma(rows,20)
    last_sma60=sma(rows,60)
    prev_sma20=sma(prior,20)
    prev_sma60=sma(prior,60)
    vbase=sum(x["volume"] for x in prior[-20:])/20
    if vbase<=0:raise ValueError("DATA_INSUFFICIENT: no reference trading volume")
    closes=[r["close"] for r in rows[-21:]]
    ret=[math.log(b/a) for a,b in zip(closes,closes[1:])]
    mu=sum(ret)/len(ret)
    vol=math.sqrt(sum((v-mu)**2 for v in ret)/len(ret))
    return {
        "close":last["close"],
        "sma20":last_sma20,"sma60":last_sma60,
        "sma20_prev":prev_sma20,"sma60_prev":prev_sma60,
        "prev_close":prior[-1]["close"],
        "prev_20_high":max(x["high"] for x in prior[-20:]),
        "prev_10_low":min(x["low"] for x in prior[-10:]),
        "volume_ratio":last["volume"]/vbase,
        "rsi14":rsi(rows),
        "return20_pct":(last["close"]/rows[-21]["close"]-1)*100,
        "return5_pct":(last["close"]/rows[-6]["close"]-1)*100,
        "daily_realized_vol20":vol,
    }


def signals(rows):
    """Return fixed BUY/EXIT/FLAT per-arm decisions for NEXT session."""
    f=features(rows)
    p=f["close"]
    uptrend=p>f["sma20"]>f["sma60"]
    positive_trend=f["sma60"]>=f["sma60_prev"]*.998
    result={
        "TREND20_60":"BUY" if uptrend and positive_trend and
            f["prev_close"]<=f["sma20_prev"] else
            "EXIT" if p<f["sma20"] else "FLAT",
        "BREAKOUT20":"BUY" if p>f["prev_20_high"] and
            f["volume_ratio"]>=1.15 and p>f["sma60"] else
            "EXIT" if p<f["prev_10_low"] or p<f["sma20"] else "FLAT",
        "RSI_REVERT":"BUY" if f["rsi14"]<=34 and p<f["sma20"]*.98
            and positive_trend else
            "EXIT" if f["rsi14"]>=56 or p>=f["sma20"] else "FLAT",
        "LOWVOL_MOM":"BUY" if uptrend and positive_trend and
            f["return20_pct"]>=3 and f["return20_pct"]<=18 and
            0<f["daily_realized_vol20"]<=.025 and f["volume_ratio"]>=.75 else
            "EXIT" if p<f["sma20"] or f["return5_pct"]< -2 else "FLAT",
    }
    if set(result)!=set(ARMS) or any(x not in ("BUY","EXIT","FLAT") for x in result.values()):
        raise ValueError("INTEGRITY_FAILURE: frozen stock experiment catalog mismatch")
    return result
