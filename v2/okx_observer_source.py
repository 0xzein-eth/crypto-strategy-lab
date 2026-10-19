"""Read-only OKX perpetual book + confirmed 15m source for v2 PAPER.

No credentials, no trade, no order endpoints. Order-book quantities for OKX
USDT-SWAP are CONTRACTS, not base coins; contract value metadata is required.
Missing/wrong instrument/old quotes fail closed; no synthetic market data.
"""
import datetime as dt
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

import signals
from v2.paper_portfolio import D, OrderRejected, ts, iso, verify_quote

UTC = dt.timezone.utc
API = "https://www.okx.com/api/v5"
ALLOWED = ("BTC", "ETH", "SOL")
SOURCE_POLICY = "okx-public-swap-book-ctval-confirmed15m-v1"
USER_AGENT = "CryptoStrategyLab-v2-PaperObserver/1.0-public-no-orders"


def public_json(url, opener=urllib.request.urlopen, sleeper=time.sleep):
    """GET PUBLIC data only. Bounded retry on transient endpoint failures."""
    if not url.startswith(API + "/"):
        raise ValueError("SOURCE_INVALID: only public OKX API origin allowed")
    if any(x in url for x in ("trade/order", "account/", "private/", "apikey")):
        raise ValueError("SOURCE_INVALID: order or account endpoints forbidden")
    for attempt in range(3):
        try:
            request = urllib.request.Request(url,headers={
                "User-Agent":USER_AGENT, "Accept":"application/json"})
            with opener(request, timeout=9) as response:
                data = json.load(response)
            if not isinstance(data, dict) or data.get("code")!="0":
                raise ValueError("SOURCE_INVALID: exchange returned failure")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt == 2:
                raise
        except (urllib.error.URLError,TimeoutError):
            if attempt == 2:
                raise
        sleeper(1+attempt)
    raise AssertionError("unreachable")


def endpoint(path, symbol, params=None):
    if symbol not in ALLOWED:
        raise ValueError("SOURCE_INVALID: market outside research universe")
    args = {"instId":symbol+"-USDT-SWAP"}
    if params:
        args.update(params)
    return API + path + "?" + urllib.parse.urlencode(args)


def instrument_contract_base(symbol, getter=public_json):
    raw = getter(endpoint("/public/instruments",symbol,{"instType":"SWAP"}))
    rows = raw.get("data",[])
    if len(rows) != 1:
        raise ValueError("SOURCE_INVALID: missing or ambiguous OKX instrument")
    row = rows[0]
    if (row.get("instId") != symbol+"-USDT-SWAP" or
            row.get("instType") != "SWAP" or
            row.get("ctType") != "linear" or
            row.get("ctValCcy") != symbol or
            row.get("state") != "live" or
            row.get("settleCcy") != "USDT"):
        raise ValueError("SOURCE_INVALID: wrong contract valuation currency/type")
    contract_base = D(row.get("ctVal"))
    if not 0 < contract_base < 100000:
        raise ValueError("SOURCE_INVALID: invalid contract size")
    return contract_base


def one_book(symbol, now, *, getter=public_json):
    """Authenticated request address + exchange timestamp + contract geometry."""
    # Fetch metadata BEFORE top book so the latter has the newest clock.
    ct_base = instrument_contract_base(symbol,getter)
    raw = getter(endpoint("/market/books",symbol,{"sz":"1"}))
    rows = raw.get("data",[])
    if len(rows) != 1 or not rows[0].get("bids") or not rows[0].get("asks"):
        raise ValueError("SOURCE_UNAVAILABLE: empty OKX order book")
    row = rows[0]
    stamp_ms = int(row["ts"])
    observed = dt.datetime.fromtimestamp(stamp_ms/1000,UTC)
    if observed > ts(now) or (ts(now)-observed).total_seconds()>160:
        raise ValueError("SOURCE_STALE: public book older than 160s")
    bid_price, bid_contracts = D(row["bids"][0][0]),D(row["bids"][0][1])
    ask_price, ask_contracts = D(row["asks"][0][0]),D(row["asks"][0][1])
    quote = {
        "provider":"okx-swap", "market_type":"perpetual",
        "symbol":symbol, "instrument":symbol+"-USDT-SWAP",
        "bid":str(bid_price), "ask":str(ask_price),
        # OKX SWAP sizes are CONTRACTS. Convert with confirmed ctVal in BASE.
        "bid_size_base":str(bid_contracts*ct_base),
        "ask_size_base":str(ask_contracts*ct_base),
        "observed_at":iso(observed),
        "public_depth_source":"OKX market/books sz=1; base=contracts*ctVal",
        "contracts_value_in_base":str(ct_base),
        "instrument_metadata_verified":True,
    }
    verify_quote(quote,symbol=symbol,now=now)
    return quote


def one_signals(symbol, quote, *, getter=public_json):
    """Current deployed v8 confirmed-candle rules; no v9 fill assumption."""
    book_time = ts(quote["observed_at"])
    raw = getter(endpoint("/market/ticker",symbol))
    data = raw.get("data",[])
    if len(data)!=1:
        raise ValueError("SOURCE_UNAVAILABLE: OKX 24h ticker")
    item = data[0]
    if item.get("instId") != symbol+"-USDT-SWAP":
        raise ValueError("SOURCE_INVALID: ticker instrument mismatch")
    ticker_at = dt.datetime.fromtimestamp(int(item["ts"])/1000,UTC)
    if abs((ticker_at-book_time).total_seconds())>160:
        raise ValueError("SOURCE_STALE: book/ticker time skew")
    last, opening = float(item["last"]),float(item["open24h"])
    if not all(math.isfinite(x) and x>0 for x in (last,opening)):
        raise ValueError("SOURCE_INVALID: ticker last/open")
    snapshot = {
        "provider":"okx-swap", "market_type":"perpetual",
        "symbol":symbol, "instrument":symbol+"-USDT-SWAP",
        "observed_at":iso(ticker_at),
        "pct24h":100*(last/opening-1),
    }
    # Freeze candle cutoff at REAL book time, not a later system clock.
    confirmed = signals.from_okx(
        symbol,snapshot,
        lambda url: getter(url),
        lambda:book_time)
    accepted=[]
    for item in confirmed:
        if item.get("strategy") in ("FB-v3","VWAP-v1"):
            evidence=item["evidence"]
            accepted.append({
                "strategy":item["strategy"],"side":item["side"],
                "evidence":{
                    "bar_span":evidence["bar_span"],
                    "bar_time":evidence["bar_time"],
                    "atr14":evidence["atr14"],
                    "last_close":evidence["last_close"],
                    "source_version":evidence["source_version"],
                    "signal_rule":evidence["signal_rule"],
                },
            })
    return accepted


def current_tick(*, clock=lambda:dt.datetime.now(UTC),getter=public_json):
    """Fetch all markets first; one missing input refuses a new equity mark."""
    from v2.forward_paper import VERSION, SYMBOLS
    books, candidates = {}, {}
    for symbol in SYMBOLS:
        # Re-read clock after public request(s). Future/old timestamps fail.
        book = one_book(symbol,clock(),getter=getter)
        books[symbol] = book
        candidates[symbol] = one_signals(symbol,book,getter=getter)
    now = clock()
    from v2.forward_paper import validate_tick
    tick = {
        "version":VERSION,"observed_at":iso(now),
        "source_policy":SOURCE_POLICY,
        "books":books,"signals":candidates,
        "funding_settlement_history_verified":False,
        "market_orders_ever_submitted":False,
    }
    validate_tick(tick)
    return tick
