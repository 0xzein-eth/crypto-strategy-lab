"""IDX DAILY OHLCV research. Unofficial Yahoo chart data; never orders.

No intraday quote, broker authority, actual fills or official IDX settlement
calendar is exposed by this provider. As-of observations are ONLY after
18:00 Asia/Jakarta. Raw prices are not total returns; corporate actions
must remain visible and halt unsafe account assumptions.
"""
import datetime as dt
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

WIB=ZoneInfo("Asia/Jakarta")
UTC=dt.timezone.utc
MARKET="IDX"
PROVIDER="yahoo-chart-public-unauthenticated"
SYMBOLS=("BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","ICBP.JK")
MIN_HISTORY=75
PUBLISH_AFTER_HOUR_WIB=18
BASE="https://query1.finance.yahoo.com/v8/finance/chart/"
USER_AGENT="Mozilla/5.0 (compatible; StockStrategyLab-PAPER-Research/0.1)"


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def iso(now):
    if not isinstance(now,dt.datetime) or now.tzinfo is None:
        raise ValueError("CLOCK_INVALID: timezone aware datetime required")
    return now.astimezone(UTC).isoformat().replace("+00:00","Z")


def allowed_symbol(symbol):
    if symbol not in SYMBOLS:
        raise ValueError("SOURCE_INVALID: ticker outside frozen IDX research universe")
    return symbol


def endpoint(symbol):
    name=allowed_symbol(symbol)
    return BASE+urllib.parse.quote(name,safe=".")+"?interval=1d&range=2y&events=div%2Csplits&includeAdjustedClose=true"


def get_json(url,*,opener=urllib.request.urlopen,sleeper=time.sleep):
    if not url.startswith(BASE) or not url.split("?")[0].endswith(".JK"):
        raise ValueError("SOURCE_INVALID: no untrusted or private endpoint")
    last=None
    for i in range(3):
        try:
            request=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
            with opener(request,timeout=12) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            last=exc
            if exc.code not in (429,500,502,503,504) or i==2:
                raise
        except (TimeoutError,urllib.error.URLError) as exc:
            last=exc
            if i==2:raise
        sleeper(2*(i+1))
    raise RuntimeError("SOURCE_UNAVAILABLE: bounded attempts exhausted") from last


def _positive(value,*,zero_ok=False):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
        return False
    return value>=0 if zero_ok else value>0


def parse_chart(payload,symbol,*,now):
    """Fail closed on wrong symbol/currency, partial day, duplicate and split.

    The API supplies daily OHLC and event dates, NOT a tradeable bid/ask.
    We never turn its current unfinished candle into a signal.
    """
    allowed_symbol(symbol)
    if not isinstance(payload,dict):
        raise ValueError("SOURCE_INVALID: no JSON object")
    chart=payload.get("chart")
    if not isinstance(chart,dict) or chart.get("error"):
        raise ValueError("SOURCE_UNAVAILABLE: chart provider error")
    data=chart.get("result")
    if not isinstance(data,list) or len(data)!=1:
        raise ValueError("SOURCE_UNAVAILABLE: missing/ambiguous IDX chart result")
    d=data[0]
    meta=d.get("meta") or {}
    if (meta.get("symbol")!=symbol or meta.get("currency")!="IDR" or
            meta.get("exchangeTimezoneName")!="Asia/Jakarta"):
        raise ValueError("SOURCE_INVALID: wrong IDX venue/clock/currency")
    if meta.get("instrumentType") not in (None,"EQUITY"):
        raise ValueError("SOURCE_INVALID: not common equity")
    stamps=d.get("timestamp") or []
    quote=(d.get("indicators") or {}).get("quote") or []
    if len(quote)!=1 or not stamps:
        raise ValueError("SOURCE_UNAVAILABLE: no IDX daily OHLCV")
    q=quote[0]
    if any(not isinstance(q.get(k),list) or len(q[k])!=len(stamps)
           for k in ("open","high","low","close","volume")):
        raise ValueError("SOURCE_INVALID: OHLCV arrays misaligned")
    observed=now.astimezone(WIB)
    if not now.tzinfo:
        raise ValueError("CLOCK_INVALID: aware now required")
    active_date=observed.date().isoformat()
    history=[]
    for idx,t in enumerate(stamps):
        at=dt.datetime.fromtimestamp(int(t),WIB)
        day=at.date().isoformat()
        if day>=active_date and observed.hour<PUBLISH_AFTER_HOUR_WIB:
            # The current daily candle is incomplete even when it appears
            # fully shaped in a public chart response.
            continue
        if day>active_date:
            raise ValueError("CLOCK_INTEGRITY: chart includes future daily bar")
        values=[q[k][idx] for k in ("open","high","low","close","volume")]
        if any(v is None for v in values):
            # Providers often include one partial/placeholder record. Never
            # fabricate a day's volume/close or interpolate the missing bar.
            if idx<len(stamps)-1:
                raise ValueError("DATA_INVALID: missing historical daily OHLCV")
            continue
        op,hi,lo,cl,vol=values
        if (not all(_positive(x) for x in (op,hi,lo,cl)) or
                not _positive(vol,zero_ok=True) or
                lo>min(op,cl) or hi<max(op,cl) or hi<lo):
            raise ValueError("DATA_INVALID: impossible IDX OHLCV")
        history.append({"date":day,"open":round(float(op),6),
                        "high":round(float(hi),6),
                        "low":round(float(lo),6),
                        "close":round(float(cl),6),
                        "volume":int(vol)})
    if len(history)<MIN_HISTORY:
        raise ValueError("DATA_INSUFFICIENT: fewer than 75 real daily bars")
    if len({r["date"] for r in history})!=len(history) or any(
            a["date"]>=b["date"] for a,b in zip(history,history[1:])):
        raise ValueError("DATA_INVALID: nonmonotonic/duplicate trading dates")
    if history[-1]["date"]!=active_date and (observed.date()-dt.date.fromisoformat(history[-1]["date"])).days>6:
        raise ValueError("DATA_STALE: no fresh recently closed IDX session")
    # Dividends are not payable when merely announced; cash payment is not
    # invented. For splits, reject cross-split stock position accounting.
    actions={}
    for category in ("splits","dividends"):
        for item in (d.get("events") or {}).get(category,{}).values():
            date=dt.datetime.fromtimestamp(int(item["date"]),WIB).date().isoformat()
            if category=="splits":
                numerator=item.get("numerator")
                denominator=item.get("denominator")
                if not _positive(numerator) or not _positive(denominator):
                    raise ValueError("SOURCE_INVALID: unverifiable split ratio")
                value={"numerator":float(numerator),"denominator":float(denominator)}
            else:
                value={"amount_idr_per_share":item.get("amount"),
                       "ex_date_not_payment_date":True}
            actions.setdefault(date,{})[category[:-1]]=value
    return {"provider":PROVIDER,"venue":MARKET,"currency":"IDR",
            "instrument":symbol,"observed_at":iso(now),
            "last_complete_session_date":history[-1]["date"],
            "history":history,"history_sha256":sha(history),
            "actions":actions,"dividend_cash_credited":False,
            "provider_is_not_official_idx":True,
            "book_bid_ask_verified":False}


def capture(*,now=None,getter=get_json,symbols=SYMBOLS):
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None:raise ValueError("CLOCK_INVALID: UTC-aware capture")
    local=now.astimezone(WIB)
    if local.hour<PUBLISH_AFTER_HOUR_WIB:
        raise ValueError("CLOCK_INTEGRITY: wait until >=18:00 WIB before EOD capture")
    if tuple(symbols)!=SYMBOLS:
        raise ValueError("SOURCE_INVALID: fixed cash-equity research universe cannot change silently")
    markets={}
    for symbol in symbols:
        markets[symbol]=parse_chart(getter(endpoint(symbol)),symbol,now=now)
    latest={data["last_complete_session_date"] for data in markets.values()}
    if len(latest)!=1:
        raise ValueError("SOURCE_STALE: incomplete cross-symbol EOD session; no fake mark")
    day=next(iter(latest))
    if (local.date()-dt.date.fromisoformat(day)).days>4:
        raise ValueError("DATA_STALE: latest complete market session is old")
    return {"source_policy":"idx-yahoo-eod-unofficial-2026-10-20-v1",
            "date":day,"captured_at_utc":iso(now),
            "markets":markets,"market_session_calendar_verified":False,
            "no_intraday_book_or_actual_broker_fills":True,
            "never_ordered_stocks":True}
