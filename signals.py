"""Auditable 15-minute OHLCV research signals (only CONFIRMED candles).

These are falsifiable hypotheses, not proven market advantages.
Never use a forming candle or a future candle. Venue: OKX USDT swap only.
"""
import datetime as dt
import math

BAR_MINUTES = 15
MIN_BARS = 60
MAX_LATEST_AGE_MINUTES = 50


def parse_okx_candles(payload, observed):
    """Parse and validate confirmed OKX candlesticks, oldest->newest."""
    if payload.get("code") != "0" or not payload.get("data"):
        raise ValueError("OKX candle endpoint returned no data")
    bars = []
    for line in payload["data"]:
        if len(line) < 9 or str(line[8]) != "1":
            continue
        start = dt.datetime.fromtimestamp(int(line[0])/1000, dt.timezone.utc)
        end = start + dt.timedelta(minutes=BAR_MINUTES)
        if end > observed + dt.timedelta(seconds=10):
            continue
        op,hi,lo,close,volume = [float(line[i]) for i in (1,2,3,4,5)]
        if not all(math.isfinite(x) and x > 0 for x in (op,hi,lo,close)):
            continue
        if not math.isfinite(volume) or volume < 0 or lo > min(op,close) or hi < max(op,close):
            continue
        bars.append({"time":start.isoformat().replace("+00:00","Z"),
                     "open":op,"high":hi,"low":lo,"close":close,"volume":volume})
    bars.sort(key=lambda x:x["time"])
    if len(bars)<MIN_BARS:
        raise ValueError("too few confirmed 15m bars")
    if len({x["time"] for x in bars}) != len(bars):
        raise ValueError("duplicate timestamps")
    for a,b in zip(bars,bars[1:]):
        if dt.datetime.fromisoformat(b["time"].replace("Z","+00:00")) - dt.datetime.fromisoformat(a["time"].replace("Z","+00:00")) != dt.timedelta(minutes=BAR_MINUTES):
            raise ValueError("gap in 15m bars")
    last = dt.datetime.fromisoformat(bars[-1]["time"].replace("Z","+00:00"))
    if (observed - (last + dt.timedelta(minutes=BAR_MINUTES))).total_seconds() > MAX_LATEST_AGE_MINUTES*60:
        raise ValueError("stale confirmed candle sequence")
    return bars


def features(bars):
    """Compute only trailing historical features at most recent confirmed close."""
    if len(bars)<MIN_BARS:raise ValueError("insufficient candles")
    c=[b["close"] for b in bars]
    h=[b["high"] for b in bars]
    l=[b["low"] for b in bars]
    v=[b["volume"] for b in bars]
    sma20=sum(c[-20:])/20
    sma50=sum(c[-50:])/50
    sma20prev=sum(c[-21:-1])/20
    window=c[-20:]
    var=sum((x-sma20)**2 for x in window)/20
    sd=math.sqrt(var)
    ranges=[]
    for i in range(len(bars)-14,len(bars)):
        ranges.append(max(h[i]-l[i], abs(h[i]-c[i-1]),abs(l[i]-c[i-1])))
    atr=sum(ranges)/14
    prev_high=max(h[-21:-1])
    prev_low=min(l[-21:-1])
    vol20=sum(v[-21:-1])/20
    cur=bars[-1]
    return {"last_close":cur["close"],"last_open":cur["open"],
            "last_high":cur["high"],"last_low":cur["low"],
            "last_volume":cur["volume"],"c_prev":c[-2],
            "sma20":sma20,"sma50":sma50,"sma20prev":sma20prev,
            "z20":(c[-1]-sma20)/sd if sd>0 else 0,
            "atr14":atr,"prev_high20":prev_high,"prev_low20":prev_low,
            "vol_ratio":cur["volume"]/vol20 if vol20>0 else 0,
            "prior_breakout_up":c[-2]>max(h[-22:-2]),
            "prior_breakout_down":c[-2]<min(l[-22:-2]),
            "regime_high_before_breakout":max(h[-22:-2]),
            "regime_low_before_breakout":min(l[-22:-2]),
            "bar_time":cur["time"],
            "bar_span":"15m confirmed OKX USDT-SWAP"}


def classify(bars):
    """Return zero or more independently specifiable hypothesis signals."""
    f=features(bars)
    p=f["last_close"];atr=f["atr14"]
    if not atr:return []
    range_=max(1e-12,f["last_high"]-f["last_low"])
    upper_wick=(f["last_high"]-max(p,f["last_open"]))/range_
    lower_wick=(min(p,f["last_open"])-f["last_low"])/range_
    trend=(f["sma20"]-f["sma50"])/atr
    events=[]
    def add(strategy,side,rule):
        evidence={k:round(v,8) if isinstance(v,float) else v for k,v in f.items()}
        evidence.update(signal_rule=rule, upper_wick_ratio=round(upper_wick,5),
                        lower_wick_ratio=round(lower_wick,5), source_version="confirmed-15m-v1")
        events.append({"strategy":strategy,"side":side,"evidence":evidence})
    # Continuation: confirmed 20-bar closing breakout plus above-baseline volume.
    if p>f["prev_high20"]+0.1*atr and f["vol_ratio"]>=1.2:
        add("BR-v3","LONG","close > previous-20 high + 0.1ATR, volume >=1.2x")
    if p<f["prev_low20"]-0.1*atr and f["vol_ratio"]>=1.2:
        add("BR-v3","SHORT","close < previous-20 low - 0.1ATR, volume >=1.2x")
    # Trend pullback confirmation to 20 SMA inside higher-timeframe SMA trend.
    if trend>0.8 and f["c_prev"]<f["sma20prev"] and p>f["sma20"] and abs(p-f["sma20"])<=0.65*atr:
        add("TP-v3","LONG","uptrend SMA20>SMA50; return above SMA20 after pullback")
    if trend<-.8 and f["c_prev"]>f["sma20prev"] and p<f["sma20"] and abs(p-f["sma20"])<=0.65*atr:
        add("TP-v3","SHORT","downtrend SMA20<SMA50; return below SMA20 after pullback")
    # Mean-reversion extremes only in a weak SMA20/SMA50 trend.
    if abs(trend)<1.2 and f["z20"]<=-2.0:
        add("MR-v3","LONG","zscore20 <= -2; weak SMA20/SMA50 separation")
    if abs(trend)<1.2 and f["z20"]>=2.0:
        add("MR-v3","SHORT","zscore20 >= 2; weak SMA20/SMA50 separation")
    # Wick sweep outside prior 20-bar range but close re-enters old range.
    if f["last_low"]<f["prev_low20"] and p>f["prev_low20"] and lower_wick>=.45:
        add("LS-v3","LONG","low sweeps prior-20 minimum; >=45% lower wick; close inside")
    if f["last_high"]>f["prev_high20"] and p<f["prev_high20"] and upper_wick>=.45:
        add("LS-v3","SHORT","high sweeps prior-20 maximum; >=45% upper wick; close inside")
    # Breakout attempt on penultimate bar fails on newest confirmed bar.
    if f["prior_breakout_up"] and p<f["regime_high_before_breakout"] and p<f["last_open"]:
        add("FB-v3","SHORT","previous bar broke 20-bar high, latest close back inside and bearish")
    if f["prior_breakout_down"] and p>f["regime_low_before_breakout"] and p>f["last_open"]:
        add("FB-v3","LONG","previous bar broke 20-bar low, latest close back inside and bullish")
    return events


def from_okx(symbol, market_snapshot, requester, clock):
    """Compute signals only for matching OKX-USDT-SWAP market snapshots."""
    if market_snapshot.get("provider") != "okx-swap":
        return []
    now=clock()
    data=requester("https://www.okx.com/api/v5/market/candles?instId="+
                   symbol+"-USDT-SWAP&bar=15m&limit=120")
    bars=parse_okx_candles(data,now)
    return classify(bars)
