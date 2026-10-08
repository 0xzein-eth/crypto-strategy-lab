#!/usr/bin/env python3
"""LEGACY v7 (disabled CLI). Use engine.py for the canonical append-only v8 lab."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "data" / "ledger.json"
REPORT = ROOT / "data" / "report.json"
UTC = dt.timezone.utc
SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","LINK","AVAX","SUI","LTC","TRX"]
HORIZONS = (1,2,4,8,12,24)
MAX_RECORDS = 80
NOTIONAL = 10000.0
FEE_SIDE_PCT = .05
TIMEOUT = 9

def utcnow():
    return dt.datetime.now(UTC).replace(microsecond=0)

def stamp(t):
    return t.isoformat().replace("+00:00","Z")

def parse(s):
    t = dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("naive timestamp")
    return t.astimezone(UTC)

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"crypto-strategy-lab/2.0 (paper-only research)","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.load(response)

def finite_positive(value):
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise ValueError("invalid non-positive or non-finite price")
    return n

def market(symbol, clock=None):
    """Current observations from PUBLIC perpetual tickers, no historic substitution."""
    clock = clock or utcnow
    errors = []
    # Provider priority: Bybit linear USDT, OKX USDT swap, Binance USDT perpetual.
    for provider in ("bybit-linear","okx-swap","binance-futures","kraken-spot-proxy"):
        try:
            if provider == "bybit-linear":
                d = get_json("https://api.bybit.com/v5/market/tickers?category=linear&symbol="+symbol+"USDT")
                if str(d.get("retCode")) != "0":
                    raise ValueError("Bybit error")
                item = d["result"]["list"][0]
                price = finite_positive(item["lastPrice"])
                pct = float(item.get("price24hPcnt",0))*100
                volume = float(item.get("turnover24h",0))
                observed = clock()
            elif provider == "okx-swap":
                d = get_json("https://www.okx.com/api/v5/market/ticker?instId="+symbol+"-USDT-SWAP")
                if d.get("code") != "0" or not d.get("data"):
                    raise ValueError("OKX error")
                item = d["data"][0]
                price = finite_positive(item["last"])
                open24 = finite_positive(item["open24h"])
                pct = (price/open24-1)*100
                volume = float(item.get("volCcy24h") or 0)
                observed = dt.datetime.fromtimestamp(int(item["ts"])/1000,UTC)
            elif provider == "binance-futures":
                d = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr?symbol="+symbol+"USDT")
                price = finite_positive(d["lastPrice"])
                pct = float(d["priceChangePercent"])
                volume = float(d.get("quoteVolume",0))
                observed = clock()
            else:
                # Explicit spot proxy fallback for regions blocking futures APIs.
                # This is research-only, never mislabel as actual perpetual execution.
                pairs = {"BTC":"XBTUSD","ETH":"ETHUSD","SOL":"SOLUSD","BNB":"BNBUSD",
                         "XRP":"XRPUSD","ADA":"ADAUSD","DOGE":"DOGEUSD","LINK":"LINKUSD",
                         "AVAX":"AVAXUSD","SUI":"SUIUSD","LTC":"LTCUSD","TRX":"TRXUSD"}
                d = get_json("https://api.kraken.com/0/public/Ticker?pair="+pairs[symbol])
                if d.get("error") or not d.get("result"):
                    raise ValueError("Kraken unavailable")
                item = next(iter(d["result"].values()))
                price = finite_positive(item["c"][0])
                open24 = finite_positive(item["o"])
                pct = (price/open24-1)*100
                volume = float(item["v"][1])*price
                observed = clock()
            if not math.isfinite(pct) or abs(pct)>95:
                raise ValueError("invalid 24h change")
            if observed > clock()+dt.timedelta(minutes=2) or clock()-observed > dt.timedelta(minutes=10):
                raise ValueError("stale/future market snapshot")
            return {"price":price,"change24h_pct":pct,"quote_volume_24h":volume,
                    "provider":provider,"observed_at":stamp(observed),
                    "instrument":symbol+("USD spot proxy" if provider=="kraken-spot-proxy" else "USDT perpetual")}
        except (ValueError,KeyError,IndexError,TypeError,urllib.error.URLError,TimeoutError) as exc:
            errors.append(provider+":"+str(exc)[:90])
    raise RuntimeError("; ".join(errors))

def load():
    if not LEDGER.exists():
        raise RuntimeError("INTEGRITY_FAILURE: missing ledger; refusing implicit reset")
    d = json.loads(LEDGER.read_text(encoding="utf-8"))
    if d.get("schema_version") != 7 or not isinstance(d.get("records"),list):
        raise RuntimeError("INTEGRITY_FAILURE: malformed ledger")
    records = d["records"]
    if len(records)>MAX_RECORDS or len({r["id"] for r in records}) != len(records):
        raise RuntimeError("INTEGRITY_FAILURE: duplicate ID or capacity exceeded")
    if not isinstance(d.get("next_id"),int) or d["next_id"]<116:
        raise RuntimeError("INTEGRITY_FAILURE: invalid next_id")
    for r in records:
        if r["status"] not in ("OPEN","DATA_MISSING_PENDING","CLOSED"):
            raise RuntimeError("INTEGRITY_FAILURE: invalid status")
        if r["id"].startswith("LAB-") and int(r["id"][4:])>=d["next_id"]:
            raise RuntimeError("INTEGRITY_FAILURE: id counter regression")
        if r["status"]=="CLOSED":
            for k in ("exit_price","resolved_at","net_pnl_usd","normalized_R","exit_observed_at"):
                if k not in r:
                    raise RuntimeError("INTEGRITY_FAILURE: incomplete closed record "+r["id"])
    return d

def atomic_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".atomic-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def close_due(d,prices,t):
    closed=0
    pending=0
    for r in d["records"]:
        if r["status"]=="CLOSED" or parse(r["evaluate_at"])>t:
            continue
        q=prices.get(r["symbol"])
        if not q or parse(q["observed_at"])<parse(r["evaluate_at"]):
            r["status"]="DATA_MISSING_PENDING"
            r["missing_checks"]=r.get("missing_checks",0)+1
            pending+=1
            continue
        ret=(q["price"]/r["entry_price"]-1)*100*(1 if r["side"]=="LONG" else -1)
        fees=NOTIONAL*(2*FEE_SIDE_PCT)/100
        pnl=NOTIONAL*ret/100-fees
        r.update(status="CLOSED",exit_price=q["price"],exit_source=q["provider"],
                 exit_observed_at=q["observed_at"],resolved_at=stamp(t),
                 delay_seconds=max(0,int((parse(q["observed_at"])-parse(r["evaluate_at"])).total_seconds())),
                 signed_return_pct=round(ret,8),fee_round_trip_usd=fees,
                 funding_assumption_usd=0,net_pnl_usd=round(pnl,6),
                 normalized_R=round((ret-2*FEE_SIDE_PCT)/r["research_risk_pct"],8),
                 outcome="WIN" if pnl>0 else "LOSS" if pnl<0 else "BREAKEVEN")
        closed+=1
    return closed,pending

def signal_candidates(prices,t):
    """Explicitly modest exploratory signals; no false market-structure labels."""
    out=[]
    ranked=sorted(prices.items(),key=lambda item:abs(item[1]["change24h_pct"]),reverse=True)
    for rank,(sym,q) in enumerate(ranked):
        pct=q["change24h_pct"]
        if abs(pct)<.6:
            continue
        # Two distinct, falsifiable baseline rules; no look-ahead.
        for strategy in ("BR-v3-proxy","MR-v3-proxy","CTRL-v1"):
            if strategy=="BR-v3-proxy":
                side="LONG" if pct>0 else "SHORT"
            elif strategy=="MR-v3-proxy":
                side="SHORT" if pct>0 else "LONG"
            else:
                side="LONG" if rank%2==0 else "SHORT"
            h=HORIZONS[(rank+{"BR-v3-proxy":0,"MR-v3-proxy":2,"CTRL-v1":4}[strategy])%len(HORIZONS)]
            out.append((sym,q,strategy,side,h,rank))
    return out

def create_new(d,prices,t,requested):
    remaining=MAX_RECORDS-len(d["records"])
    if remaining<=0:
        return 0
    added=0
    used_symbols=set()
    for sym,q,strategy,side,h,rank in signal_candidates(prices,t):
        if added>=min(max(0,requested),remaining):
            break
        if sym in used_symbols:
            continue
        if any(r["symbol"]==sym and r["status"]!="CLOSED" and r["horizon_hours"]==h for r in d["records"]):
            continue
        observed=parse(q["observed_at"])
        if observed>t or (t-observed).total_seconds()>600:
            continue
        ident="LAB-"+str(d["next_id"])
        d["next_id"]+=1
        d["records"].append({
            "id":ident,"created_at":stamp(t),"symbol":sym,"instrument":q["instrument"],
            "strategy":strategy,"horizon_hours":h,
            "regime":"24h_risk_off" if q["change24h_pct"]<0 else "24h_risk_on",
            "side":side,"entry_price":q["price"],"entry_source":q["provider"],
            "entry_observed_at":q["observed_at"],"evaluate_at":stamp(t+dt.timedelta(hours=h)),
            "research_risk_pct":1.5,"notional_usd":NOTIONAL,"hypothetical_leverage":3,
            "fee_per_side_pct":FEE_SIDE_PCT,"funding_assumption_usd":0,
            "quality":"C-exploratory","cluster":"CRYPTO_BETA",
            "evidence":{"change24h_pct":q["change24h_pct"],"rank":rank,
                        "rule":"deterministic 24h direction/countertrend/control proxy"},
            "status":"OPEN"})
        used_symbols.add(sym)
        added+=1
    return added

def stats(d):
    records=d["records"]
    closed=[r for r in records if r["status"]=="CLOSED"]
    pnl=[r["net_pnl_usd"] for r in closed]
    pos=sum(x for x in pnl if x>0)
    neg=-sum(x for x in pnl if x<0)
    groups=defaultdict(list)
    for r in closed:
        groups[r["strategy"]+" / "+str(r["horizon_hours"])+"h"].append(r)
    chronological=sorted(closed,key=lambda r:(r["resolved_at"],r["id"]))
    equity=peak=drawdown=0.
    for r in chronological:
        equity+=r["net_pnl_usd"]
        peak=max(peak,equity)
        drawdown=max(drawdown,peak-equity)
    n=len(closed)
    return {"schema_version":7,"created":len(records),"remaining_capacity":MAX_RECORDS-len(records),
            "storage_capacity_milestone":len(records)==MAX_RECORDS,
            "closed":n,"open":sum(r["status"]=="OPEN" for r in records),
            "pending":sum(r["status"]=="DATA_MISSING_PENDING" for r in records),
            "wins":sum(x>0 for x in pnl),"losses":sum(x<0 for x in pnl),
            "win_rate":round(sum(x>0 for x in pnl)/n,4) if n else None,
            "net_pnl_usd":round(sum(pnl),2),
            "net_R":round(sum(r["normalized_R"] for r in closed),5),
            "net_expectancy_usd":round(sum(pnl)/n,4) if n else None,
            "net_expectancy_R":round(sum(r["normalized_R"] for r in closed)/n,5) if n else None,
            "profit_factor":round(pos/neg,4) if neg else None,
            "max_closed_equity_drawdown_usd":round(drawdown,2),
            "total_round_trip_fees_usd":round(sum(r["fee_round_trip_usd"] for r in closed),2),
            "strategy_horizon":{k:{"n":len(v),"net_R":round(sum(x["normalized_R"] for x in v),5),
               "evidence":"collect" if len(v)<10 else "hypothesis" if len(v)<30 else "early evidence" if len(v)<50 else "needs multi-regime validation"} for k,v in sorted(groups.items())},
            "limitations":["Highly correlated crypto beta; trades not independent",
                           "Perpetual ticker proxy, no order fills or liquidation modeling",
                           "Zero assumed funding, no slippage or spread",
                           "Historical LAB-074..115 excluded pending verified full records",
                           "No established strategy edge"]}

def run(args):
    d=load()
    t=utcnow()
    prices={}
    errors={}
    for sym in SYMBOLS:
        try:
            prices[sym]=market(sym)
        except Exception as exc:
            errors[sym]=str(exc)[:250]
    closed,pending=close_due(d,prices,t)
    # Abort experiment generation when no market snapshots are available.
    if not prices:
        atomic_json(LEDGER,d)
        result=stats(d)
        result.update(timestamp=stamp(t),added=0,closed_this_run=closed,
                      market_errors=errors,status="DATA_UNAVAILABLE")
        atomic_json(REPORT,result)
        print(json.dumps(result,indent=2))
        raise RuntimeError("DATA_UNAVAILABLE: no market provider succeeded; refusing silent success")
    # Every due resolution and every new record is persisted in the same committed transaction.
    added=create_new(d,prices,t,args.count)
    atomic_json(LEDGER,d)
    result=stats(d)
    result.update(timestamp=stamp(t),added=added,closed_this_run=closed,
                  pending_this_run=pending,market_snapshots=len(prices),
                  market_errors=errors,status="STORAGE_CAPACITY_MILESTONE" if len(d["records"])==MAX_RECORDS else "OK")
    atomic_json(REPORT,result)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    raise SystemExit(
        "LEGACY_V7_DISABLED: do not write data/ledger.json or report.json with lab.py; "
        "use 'python engine.py' for canonical v8 experiments.")
