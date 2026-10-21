"""Authentic public DAILY prices, two exchanges, no orders or gap filling.

Yahoo chart is unofficial: not a licensed bid/ask, dividend-total-return,
exchange holiday calendar or broker execution feed. All future-only
observations are dated AFTER venue-local EOD, never at today's partial close.
"""
import datetime as dt
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

from equity_lab import universe

VERSION="dual-equity-public-eod-source-2026-10-21-v1"
ROOT1="https://query1.finance.yahoo.com/v8/finance/chart/"
ROOT2="https://query2.finance.yahoo.com/v8/finance/chart/"
MIN_BARS=125
MAX_MARKET_STALE_DAYS=5
UTC=dt.timezone.utc


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def iso(t):
    if t.tzinfo is None:raise ValueError("CLOCK_INVALID: timezone-naive observation")
    return t.astimezone(UTC).isoformat().replace("+00:00","Z")


def request(symbol, *, getter=urllib.request.urlopen, sleeper=time.sleep):
    if not (symbol.isascii() and (symbol in universe.NASDAQ or
                                  symbol in universe.LQ45 or symbol in ("^NDX","^JKSE"))):
        raise ValueError("SOURCE_INVALID: forbidden market ticker")
    path=urllib.parse.quote(symbol,safe=".")
    query="?interval=1d&range=2y&events=div%2Csplits&includeAdjustedClose=true"
    last=None
    for host in (ROOT1,ROOT2):
        for retry in range(2):
            url=host+path+query
            try:
                req=urllib.request.Request(url,headers={
                    "User-Agent":"Mozilla/5.0 (compatible; DualEquityResearch/1.0)",
                    "Accept":"application/json"})
                with getter(req,timeout=12) as reply:
                    return json.load(reply)
            except urllib.error.HTTPError as exc:
                last=exc
                if exc.code not in (403,429,500,502,503,504):
                    raise
            except (urllib.error.URLError,TimeoutError) as exc:
                last=exc
            if retry==0:sleeper(.7)
    raise RuntimeError("SOURCE_UNAVAILABLE: Yahoo public endpoints failed") from last


def parse(payload,symbol,market_name,*,now,is_benchmark=False):
    config=universe.market(market_name,now=now)
    expected=config["benchmark"] if is_benchmark else config["symbols"]
    if (symbol!=expected if is_benchmark else symbol not in expected):
        raise ValueError("SOURCE_INVALID: symbol not in market frozen universe")
    result=(payload.get("chart") or {}).get("result") if isinstance(payload,dict) else None
    if not isinstance(result,list) or len(result)!=1 or (payload["chart"].get("error")):
        raise ValueError("SOURCE_UNAVAILABLE: malformed public chart")
    raw=result[0]
    meta=raw.get("meta") or {}
    if (meta.get("symbol")!=symbol or meta.get("currency")!=config["currency"] or
            meta.get("exchangeTimezoneName")!=config["timezone"]):
        raise ValueError("SOURCE_INVALID: venue, currency, timezone or ticker mismatch")
    if not is_benchmark and meta.get("instrumentType") not in (None,"EQUITY"):
        raise ValueError("SOURCE_INVALID: no ETFs, futures, forex or indices as stock fills")
    if is_benchmark and meta.get("instrumentType") not in (None,"INDEX"):
        raise ValueError("SOURCE_INVALID: benchmark must be a non-tradable index")
    local=now.astimezone(ZoneInfo(config["timezone"]))
    stamps=raw.get("timestamp") or []
    quote=(raw.get("indicators") or {}).get("quote") or []
    if not stamps or len(quote)!=1 or any(len(quote[0].get(k,[]))!=len(stamps)
        for k in ("open","high","low","close","volume")):
        raise ValueError("DATA_INVALID: OHLCV vectors absent or misaligned")
    history=[]
    for i,stamp in enumerate(stamps):
        day=dt.datetime.fromtimestamp(int(stamp), ZoneInfo(config["timezone"])).date().isoformat()
        if day>local.date().isoformat():raise ValueError("CLOCK_INTEGRITY: future daily candle")
        if day==local.date().isoformat() and local.hour<config["min_complete_local_hour"]:
            continue
        fields=[quote[0][k][i] for k in ("open","high","low","close","volume")]
        if any(x is None for x in fields):
            if i!=len(stamps)-1:raise ValueError("DATA_INVALID: missing historical bar")
            continue
        op,hi,lo,cl,volume=fields
        if (not all(isinstance(x,(float,int)) and not isinstance(x,bool)
                    and math.isfinite(x) for x in fields) or
            min(op,hi,lo,cl)<=0 or volume<0 or
            lo>min(op,cl) or hi<max(op,cl)):
            raise ValueError("DATA_INVALID: invalid OHLCV")
        history.append({"date":day,"open":round(float(op),6),
                        "high":round(float(hi),6),"low":round(float(lo),6),
                        "close":round(float(cl),6),"volume":int(volume)})
    if len(history)<MIN_BARS:
        raise ValueError("DATA_INSUFFICIENT: at least 125 completed bars")
    days=[r["date"] for r in history]
    if days!=sorted(set(days)):
        raise ValueError("INTEGRITY_FAILURE: duplicate/out of order daily bar")
    if (local.date()-dt.date.fromisoformat(days[-1])).days>MAX_MARKET_STALE_DAYS:
        raise ValueError("DATA_STALE: latest completed venue session too old")
    actions={}
    for key in ("splits","dividends"):
        for ev in ((raw.get("events") or {}).get(key) or {}).values():
            when=dt.datetime.fromtimestamp(int(ev["date"]),ZoneInfo(config["timezone"])).date().isoformat()
            actions.setdefault(when,[]).append(key)
    return {
        "symbol":symbol,"market":market_name,"currency":config["currency"],
        "provider":"unofficial-yahoo-chart","is_nontradable_benchmark":bool(is_benchmark),
        "observed_at_utc":iso(now),"last_complete_session":days[-1],
        "history":history,"history_sha256":sha(history),
        "corporate_action_dates":actions,"actual_exchange_fills":0,
    }


def collect(market_name, *, now=None, symbols=None, getter=request,workers=3):
    """Fetch only frozen members. Misses are explicit; at least a usable
    partial authentic panel is required. Never synthesize missing tickers.
    """
    now=now or dt.datetime.now(UTC)
    conf=universe.market(market_name,now=now)
    selected=tuple(symbols) if symbols is not None else conf["symbols"]
    if len(set(selected))!=len(selected) or any(x not in conf["symbols"] for x in selected):
        raise ValueError("SOURCE_INVALID: invalid cohort")
    if not selected:raise ValueError("DATA_INSUFFICIENT: empty source cohort")
    def obtain(sym):
        return parse(getter(sym),sym,market_name,now=now)
    good={}
    errors={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        mapping={pool.submit(obtain,sym):sym for sym in selected}
        for future in as_completed(mapping):
            sym=mapping[future]
            try:good[sym]=future.result()
            except (ValueError,RuntimeError,urllib.error.HTTPError,
                    urllib.error.URLError,TimeoutError) as exc:
                errors[sym]=type(exc).__name__+": "+str(exc)[:130]
    latest={r["last_complete_session"] for r in good.values()}
    if not latest:raise RuntimeError("SOURCE_UNAVAILABLE: zero authentic equity bars; "+canonical(errors))
    # A multi-date partial panel is not a valid session snapshot.
    dates=sorted(latest)
    session=dates[-1]
    synchronized={sym:r for sym,r in good.items() if r["last_complete_session"]==session}
    for sym in sorted(set(good)-set(synchronized)):
        errors[sym]="DATA_STALE: prior EOD session (not this observation)"
    minimum=min(len(selected),8)
    if len(synchronized)<minimum:
        raise RuntimeError("SOURCE_INSUFFICIENT: fewer than 8 synchronized authentic stock histories")
    benchmark=None
    try:
        benchmark=parse(getter(conf["benchmark"]),conf["benchmark"],market_name,
                        now=now,is_benchmark=True)
        if benchmark["last_complete_session"]!=session:
            raise ValueError("BENCHMARK_STALE: benchmark not same completed session")
    except (ValueError,RuntimeError,urllib.error.HTTPError,
            urllib.error.URLError,TimeoutError) as exc:
        errors[conf["benchmark"]]="BENCHMARK_UNAVAILABLE: "+str(exc)[:130]
        benchmark=None
    return {
        "schema":VERSION,"market":market_name,"currency":conf["currency"],
        "session":session,"observed_at_utc":iso(now),
        "membership_effective":conf["membership_effective"],
        "membership_expiry":conf["membership_expiry"],
        "requested_symbols":list(selected),
        "observed_symbols":sorted(synchronized),
        "missing_symbols":errors,
        "stocks":dict(sorted(synchronized.items())),
        "benchmark":benchmark,
        "no_real_orders":True,"historical_window_is_not_forward_execution":True,
    }
