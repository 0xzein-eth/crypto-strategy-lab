"""Public GET-only, multi-symbol OKX observations for a NEW shadow epoch."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from adaptive_lab.registry import SYMBOLS
from research_v9.history import parse_confirmed, validate_series, BAR_MS
from research_v9.funding import parse_settled, validate_rates
from v2.paper_portfolio import D, ts, iso, verify_quote

UTC=dt.timezone.utc
ORIGIN="https://www.okx.com/api/v5"
PATHS=("/public/instruments","/market/candles","/market/books","/public/funding-rate-history",
       "/market/history-candles")


def get(path,symbol,params=None,*,opener=urllib.request.urlopen,sleeper=time.sleep):
    if path not in PATHS or symbol not in SYMBOLS:
        raise ValueError("PUBLIC_SOURCE_ONLY: unregistered endpoint/instrument")
    args={"instId":symbol+"-USDT-SWAP",**(params or {})}
    if args["instId"]!=symbol+"-USDT-SWAP":raise ValueError("instrument override")
    url=ORIGIN+path+"?"+urllib.parse.urlencode(args)
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"AdaptiveCryptoShadow/1.0-public-only"})
            with opener(req,timeout=12) as response:payload=json.load(response)
            if payload.get("code")!="0":raise ValueError("SOURCE_UNAVAILABLE: OKX response code")
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt==2:raise
        except (urllib.error.URLError,TimeoutError) as exc:
            if "403" in str(exc) or attempt==2:raise
        sleeper(2**attempt)
    raise AssertionError("unreachable")


def fetch_asset(symbol,*,getter=get,clock=lambda:dt.datetime.now(UTC)):
    metadata=getter("/public/instruments",symbol,{"instType":"SWAP"})["data"]
    if len(metadata)!=1:raise ValueError("SOURCE_INVALID: ambiguous instrument")
    contract=metadata[0]
    if (contract.get("instId")!=symbol+"-USDT-SWAP" or contract.get("instType")!="SWAP" or
            contract.get("ctType")!="linear" or contract.get("ctValCcy")!=symbol or
            contract.get("settleCcy")!="USDT" or contract.get("state")!="live"):
        raise ValueError("SOURCE_INVALID: contract metadata mismatch")
    ctval=D(contract["ctVal"])
    if not 0<ctval<100000:raise ValueError("SOURCE_INVALID: ctVal")
    raw_bars=getter("/market/candles",symbol,{"bar":"15m","limit":"130"})
    raw_funding=getter("/public/funding-rate-history",symbol,{"limit":"100"})
    raw_book=getter("/market/books",symbol,{"sz":"1"})["data"]
    now=ts(clock())
    if len(raw_book)!=1:raise ValueError("SOURCE_INVALID: ambiguous book")
    book=raw_book[0]
    quote={"provider":"okx-swap","market_type":"perpetual","symbol":symbol,
        "instrument":symbol+"-USDT-SWAP","bid":book["bids"][0][0],
        "ask":book["asks"][0][0],
        "bid_size_base":str(D(book["bids"][0][1])*ctval),
        "ask_size_base":str(D(book["asks"][0][1])*ctval),
        "observed_at":iso(dt.datetime.fromtimestamp(int(book["ts"])/1000,UTC))}
    verify_quote(quote,symbol=symbol,now=now)
    # Candles fetched before the book; book time is the as-of signal cutoff.
    bars=parse_confirmed(raw_bars,now=ts(quote["observed_at"]))[-128:]
    rates=parse_settled(raw_funding,symbol,now=now)
    result={"book":quote,"candles":bars,"funding":rates,
            "contract_base_value":str(ctval),"real_orders":0}
    validate_asset(symbol,result,now=now)
    return result


def validate_asset(symbol,asset,*,now):
    if symbol not in SYMBOLS or asset.get("real_orders")!=0:
        raise ValueError("SOURCE_INVALID: unregistered market/order flag")
    verify_quote(asset["book"],symbol=symbol,now=now)
    if not 0<D(asset["contract_base_value"])<100000:
        raise ValueError("SOURCE_INVALID: missing contract base units")
    bars=validate_series(asset["candles"],min_bars=128)
    if len(bars)!=128:raise ValueError("SOURCE_INVALID: unbounded source capture")
    if any(isinstance(value,bool) for row in bars for value in row):
        raise ValueError("SOURCE_INVALID: boolean OHLCV")
    book_ms=int(ts(asset["book"]["observed_at"]).timestamp()*1000)
    if not 0<=book_ms-(bars[-1][0]+BAR_MS)<=2*BAR_MS:
        raise ValueError("SOURCE_STALE: stale/future confirmed candle")
    validate_rates(asset["funding"])
    if any(row[0]>int(ts(now).timestamp()*1000) for row in asset["funding"]):
        raise ValueError("SOURCE_INVALID: future funding settlement")


def capture(*,symbols=SYMBOLS,getter=get,clock=lambda:dt.datetime.now(UTC),workers=4):
    if not 2<=len(symbols)<=len(SYMBOLS) or len(set(symbols))!=len(symbols) or set(symbols)-set(SYMBOLS):
        raise ValueError("SOURCE_INVALID: select 2..16 registered symbols")
    assets={}
    errors={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks={pool.submit(fetch_asset,s,getter=getter,clock=clock):s for s in symbols}
        for future in as_completed(tasks):
            symbol=tasks[future]
            try:assets[symbol]=future.result()
            except (ValueError,OSError,KeyError,IndexError,TypeError) as exc:
                errors[symbol]=type(exc).__name__+": "+str(exc)[:160]
    now=ts(clock())
    for symbol in list(assets):
        try:validate_asset(symbol,assets[symbol],now=now)
        except ValueError as exc:
            errors[symbol]=str(exc)
            del assets[symbol]
    if len(assets)<2:
        raise ValueError("SOURCE_UNAVAILABLE: fewer than two fresh markets; "+json.dumps(errors,sort_keys=True))
    return {"observed_at":iso(now),"assets":dict(sorted(assets.items())),
            "source_failures":errors,"symbols_requested":list(symbols),
            "public_sources_only":True,"real_orders":0}
