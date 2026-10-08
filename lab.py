#!/usr/bin/env python3
"""Strict prospective, fixed-horizon PAPER research. No order endpoints."""
import argparse, datetime as dt, json, os, pathlib, tempfile, urllib.request
from collections import defaultdict

ROOT=pathlib.Path(__file__).parent
LEDGER=ROOT/"data"/"ledger.json"
UTC=dt.timezone.utc
SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT"]
HOURS=[1,2,4,8,12,24]
MAX_RECORDS=80

def now():
    return dt.datetime.now(UTC).replace(microsecond=0)
def iso(t):
    return t.isoformat().replace("+00:00","Z")
def parse(s):
    return dt.datetime.fromisoformat(s.replace("Z","+00:00"))
def market(symbol):
    url="https://api.binance.com/api/v3/ticker/24hr?symbol="+symbol
    req=urllib.request.Request(url,headers={"User-Agent":"crypto-strategy-lab-paper/1.0"})
    with urllib.request.urlopen(req,timeout=15) as r:
        j=json.load(r)
    px=float(j["lastPrice"]); change=float(j["priceChangePercent"])
    if px<=0 or abs(change)>90:
        raise ValueError("invalid market data")
    return {"price":px,"change24h":change,"provider":"Binance spot proxy (not perpetual mark/index)","observed_at":iso(now())}

def load():
    if not LEDGER.exists():
        return {"schema_version":7,"next_id":116,"records":[],"legacy_note":"LAB-074..115 archived externally, NOT imported; do not include in statistics"}
    data=json.loads(LEDGER.read_text())
    assert data["schema_version"]==7
    records=data["records"]
    ids=[r["id"] for r in records]
    assert len(ids)==len(set(ids)) and len(records)<=MAX_RECORDS
    for r in records:
        assert r["status"] in ("OPEN","CLOSED","DATA_MISSING_PENDING")
    return data

def write(data):
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=LEDGER.parent,prefix=".ledger-",suffix=".tmp")
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(data,f,indent=2,sort_keys=True,allow_nan=False)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(name,LEDGER)
    finally:
        if os.path.exists(name):os.unlink(name)

def resolve(data, t, prices):
    for r in data["records"]:
        if r["status"]=="CLOSED" or parse(r["evaluate_at"])>t:continue
        snap=prices.get(r["symbol"])
        if not snap or parse(snap["observed_at"])<parse(r["evaluate_at"]):
            r["status"]="DATA_MISSING_PENDING";continue
        direction=1 if r["side"]=="LONG" else -1
        ret=direction*(snap["price"]/r["entry_price"]-1)*100
        cost=0.10
        pnl=10000*(ret-cost)/100
        r.update(status="CLOSED",exit_price=snap["price"],exit_source=snap["provider"],
                 exit_observed_at=snap["observed_at"],resolved_at=iso(t),
                 delay_seconds=int((parse(snap["observed_at"])-parse(r["evaluate_at"])).total_seconds()),
                 signed_return_pct=round(ret,8),fee_round_trip_usd=10,
                 net_pnl_usd=round(pnl,6),normalized_R=round((ret-cost)/r["research_risk_pct"],8))
        # Never overwrite an already CLOSED record.
    return data

def discover(data,t,prices,count=5):
    available=MAX_RECORDS-len(data["records"])
    if available<=0:return 0
    candidates=sorted(
        ((s,v) for s,v in prices.items() if abs(v["change24h"])>=0.75),
        key=lambda a:abs(a[1]["change24h"]),reverse=True)
    existing={(r["symbol"],r["strategy"],r["horizon_hours"],r["status"]) for r in data["records"]}
    added=0
    for ix,(sym,snap) in enumerate(candidates):
        if added>=min(count,available):break
        change=snap["change24h"]
        strategy="BR-v3" if ix%3!=2 else ("MR-v3" if ix%3==2 else "TP-v3")
        side=("SHORT" if change<0 else "LONG") if strategy=="BR-v3" else ("LONG" if change<0 else "SHORT")
        horizon=HOURS[ix%len(HOURS)]
        if any(r["symbol"]==sym and r["status"]!="CLOSED" and r["horizon_hours"]==horizon for r in data["records"]):continue
        rid="LAB-"+str(data["next_id"])
        r={"id":rid,"created_at":iso(t),"symbol":sym,"strategy":strategy,
           "horizon_hours":horizon,"regime":"24h_down" if change<0 else "24h_up",
           "side":side,"entry_price":snap["price"],"entry_source":snap["provider"],
           "entry_observed_at":snap["observed_at"],"evaluate_at":iso(t+dt.timedelta(hours=horizon)),
           "research_risk_pct":1.5,"notional_usd":10000,"hypothetical_leverage":3,
           "fee_per_side_pct":0.05,"funding_assumption_usd":0,
           "quality":"C - exploratory, spot proxy","cluster":"CRYPTO_BETA",
           "evidence":{"change24h_pct":change,"rule":"24h direction, deterministic exploratory candidate"},
           "status":"OPEN"}
        data["records"].append(r);data["next_id"]+=1;added+=1
    return added

def report(data):
    closed=[x for x in data["records"] if x["status"]=="CLOSED"]
    wins=[x for x in closed if x["net_pnl_usd"]>0]
    losses=[x for x in closed if x["net_pnl_usd"]<0]
    g=sum(x["net_pnl_usd"] for x in wins)
    l=-sum(x["net_pnl_usd"] for x in losses)
    by=defaultdict(list)
    for x in closed:by[x["strategy"]+" / "+str(x["horizon_hours"])+"h"].append(x)
    return {"created":len(data["records"]),"closed":len(closed),
            "open":sum(x["status"]!="CLOSED" for x in data["records"]),
            "wins":len(wins),"losses":len(losses),
            "net_pnl_usd":round(sum(x["net_pnl_usd"] for x in closed),2),
            "net_R":round(sum(x["normalized_R"] for x in closed),5),
            "profit_factor":round(g/l,4) if l else None,
            "strategy_horizon":{k:{"n":len(v),"net_R":round(sum(z["normalized_R"] for z in v),4),
              "evidence":"collect only" if len(v)<10 else "hypothesis only" if len(v)<30 else "early evidence"} for k,v in by.items()},
            "warning":"Correlated crypto beta; spot proxy != perpetual execution; no verified edge."}

def run(args):
    data=load();t=now(); prices={}
    for sym in SYMBOLS:
        try:prices[sym]=market(sym)
        except Exception as e: print("DATA_MISSING",sym,str(e))
    resolve(data,t,prices)
    # Persist due resolutions before generating experiments.
    write(data)
    added=discover(data,t,prices,args.count)
    write(data)
    result=report(data);result["added"]=added;result["timestamp"]=iso(t)
    (ROOT/"data"/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--count",type=int,default=5)
    run(parser.parse_args())
