"""Entry-frozen statistical-band funnel and a NEW independent paper hypothesis.

BANDREV-v1 is unchanged. BANDSWEEP-v1 is pre-registered separately: an
intrabar sweep through the PREVIOUS completed 20-close envelope, followed
by a confirmed closing rejection. It is NOT a backfit or a real market fill.
All bars must already be validated as 15m confirmed same-instrument OKX swap.
"""
import math

VERSION="confirmed-band-sweep-2026-10-19-v1"
LOOKBACK=20


def evaluate(bars, f):
    """Return (new-paper-options, opportunity funnel); zero fabricated data."""
    if len(bars)<60 or f.get("bar_span")!="15m confirmed OKX USDT-SWAP":
        raise ValueError("INTEGRITY_FAILURE: band audit requires confirmed 15m bars")
    prior=[float(row["close"]) for row in bars[-LOOKBACK-1:-1]]
    latest=[float(row["close"]) for row in bars[-LOOKBACK:]]
    if len(prior)!=LOOKBACK or len(latest)!=LOOKBACK:
        raise ValueError("INTEGRITY_FAILURE: insufficient previous closes")
    mu=sum(prior)/LOOKBACK
    sd=math.sqrt(sum((p-mu)**2 for p in prior)/LOOKBACK)
    now_mu=sum(latest)/LOOKBACK
    now_sd=math.sqrt(sum((p-now_mu)**2 for p in latest)/LOOKBACK)
    atr=float(f["atr14"])
    price=float(f["last_close"])
    previous=float(f["c_prev"])
    vol=float(f["vol_ratio"])
    high=float(f["last_high"]); low=float(f["last_low"])
    op=float(f["last_open"])
    if not all(math.isfinite(x) for x in (mu,sd,now_mu,now_sd,atr,price,previous,
                                          vol,high,low,op)):
        raise ValueError("INTEGRITY_FAILURE: nonfinite confirmed band features")
    if atr<=0 or high<low or low>min(price,op) or high<max(price,op):
        raise ValueError("INTEGRITY_FAILURE: invalid confirmed band OHLC")
    trend=(float(f["sma20"])-float(f["sma50"]))/atr
    previous_z=(previous-mu)/sd if sd>0 else 0
    current_z=(price-now_mu)/now_sd if now_sd>0 else 0
    length=high-low
    lower_wick=(min(price,op)-low)/length if length>0 else 0
    upper_wick=(high-max(price,op))/length if length>0 else 0

    # Reproduce v1 observation stages in diagnostics ONLY. Never change or
    # relabel BANDREV-v1's existing rule, trading choice or current P&L.
    prev_long=sd>0 and previous_z<=-1.8
    prev_short=sd>0 and previous_z>=1.8
    reentry_long=prev_long and now_sd>0 and current_z>-1
    reentry_short=prev_short and now_sd>0 and current_z<1
    recovered_long=reentry_long and price>previous
    recovered_short=reentry_short and price<previous
    final_long=recovered_long and abs(trend)<1.5 and vol>=0.75
    final_short=recovered_short and abs(trend)<1.5 and vol>=0.75
    # New variant uses the CURRENT bar's confirmed LOW/HIGH excursion
    # relative to the PREVIOUS (frozen) 20-bar price band, then a recovery
    # back inside the less extreme portion of that prior band.
    sweep_long=(sd>0 and low < mu-1.8*sd and price > mu-1.2*sd
                and price>op and lower_wick>=0.25
                and abs(trend)<1.8 and vol>=0.85)
    sweep_short=(sd>0 and high > mu+1.8*sd and price < mu+1.2*sd
                 and price<op and upper_wick>=0.25
                 and abs(trend)<1.8 and vol>=0.85)

    funnel={
        "band_previous_std_positive":int(sd>0),
        "bandrev_previous_outside_long":int(prev_long),
        "bandrev_previous_outside_short":int(prev_short),
        "bandrev_current_reentry_long":int(reentry_long),
        "bandrev_current_reentry_short":int(reentry_short),
        "bandrev_directional_recovery_long":int(recovered_long),
        "bandrev_directional_recovery_short":int(recovered_short),
        "bandrev_complete_long":int(final_long),
        "bandrev_complete_short":int(final_short),
        "bandsweep_confirmed_long":int(sweep_long),
        "bandsweep_confirmed_short":int(sweep_short),
    }
    signals=[]
    for condition,side in ((sweep_long,"LONG"),(sweep_short,"SHORT")):
        if not condition:
            continue
        # Existing features are frozen by signals.features() at confirmed
        # entry candle. No future bar and no CLOSE outcome enters this label.
        evidence={k:round(v,8) if isinstance(v,float) else v for k,v in f.items()}
        evidence.update({
            "hypothesis_version":VERSION,"source_version":VERSION,
            "research_only":True,
            "signal_rule":("confirmed 15m intrabar envelope sweep outside prior 20 close band "
                           "1.8sd; close recovers inside 1.2sd; rejection wick>=0.25, "
                           "trend <1.8ATR, vol>=0.85"),
            "frozen_band_observation":{
                "prior20_mean":round(mu,8),"prior20_sd":round(sd,8),
                "prior_band_high":round(mu+1.8*sd,8),
                "prior_band_low":round(mu-1.8*sd,8),
                "last_low":round(low,8),"last_high":round(high,8),
                "last_close":round(price,8),"last_open":round(op,8),
                "wick_ratio":round(lower_wick if side=="LONG" else upper_wick,8),
                "trend_atr":round(trend,8),
            },
        })
        signals.append({"strategy":"BANDSWEEP-v1","side":side,"evidence":evidence})
    return signals,funnel
