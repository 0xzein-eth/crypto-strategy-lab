"""Bounded expansion into a separate 16-market historical store and screen.

Historical repetitions never change prospective tier states. Existing
v8/v2/v9 raw data and reports are read-only seeds, never rewritten.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import time

from adaptive_lab import registry, source
from adaptive_lab.engine import canonical, sha, ROOT, funding_contract, funding_complete
from research_v9 import history as prices, funding
from research_v9.factory import Features
from v2 import history_warehouse

STORE=ROOT/"adaptive_history"


def path_for(store,symbol):
    if symbol not in registry.SYMBOLS:raise ValueError("unregistered historical symbol")
    return Path(store)/(symbol+".json.gz")


def validate(item,symbol):
    body={k:v for k,v in item.items() if k!="hash"}
    if (item.get("hash")!=sha(body) or item.get("instrument")!=symbol+"-USDT-SWAP" or
            item.get("schema")!="adaptive-historical-source-v1"):
        raise ValueError("INTEGRITY_FAILURE: adaptive history hash/source")
    prices.validate_series(item["candles"],min_bars=128)
    funding.validate_rates(item["funding"])
    return item


def load(store,symbol):
    path=path_for(store,symbol)
    return validate(json.loads(gzip.decompress(path.read_bytes())),symbol) if path.exists() else None


def refresh_one(store,symbol,*,pages=5,getter=source.get,sleeper=time.sleep):
    if isinstance(pages,bool) or not 0<=pages<=60:raise ValueError("unsafe history page budget")
    old=load(store,symbol)
    seed=(old["candles"] if old else history_warehouse.load(symbol,"candles")
          if symbol in history_warehouse.SYMBOLS else prices.load_cache(symbol))
    old_rates=(old["funding"] if old else history_warehouse.load(symbol,"settled_funding")
               if symbol in history_warehouse.SYMBOLS else funding.load_cache(symbol))
    asset=source.fetch_asset(symbol,getter=getter)
    fresh=asset["candles"]
    # Bridge a genuinely observed gap through bounded backwards API pages.
    for _ in range(pages):
        if not seed or fresh[0][0]<=seed[-1][0]:break
        batch=prices.parse_confirmed(getter("/market/history-candles",symbol,
            {"bar":"15m","limit":"100","after":str(fresh[0][0])}))
        fresh=prices.extend_older(fresh,batch,max_bars=730*96)
        sleeper(.12)
    candles=prices.merge_series(seed,fresh,max_bars=730*96) if seed else fresh
    added=0
    for _ in range(pages):
        if len(candles)>=730*96:break
        batch=prices.parse_confirmed(getter("/market/history-candles",symbol,
            {"bar":"15m","limit":"100","after":str(candles[0][0])}))
        updated=prices.extend_older(candles,batch,max_bars=730*96)
        if len(updated)==len(candles):break
        added+=len(updated)-len(candles)
        candles=updated
        sleeper(.12)
    rates={r[0]:r for r in old_rates}
    for row in asset["funding"]:
        if row[0] in rates and rates[row[0]]!=row:raise ValueError("settled funding changed")
        rates[row[0]]=row
    body={"schema":"adaptive-historical-source-v1","instrument":symbol+"-USDT-SWAP",
          "observed_at":source.iso(dt.datetime.now(source.UTC)),
          "candles":candles,"funding":[rates[k] for k in sorted(rates)],
          "new_older_bars":added,"real_orders":0}
    item={**body,"hash":sha(body)}
    validate(item,symbol)
    path=path_for(store,symbol)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp")
    temp.write_bytes(gzip.compress(canonical(item).encode(),mtime=0))
    os.replace(temp,path)
    return {"bars":len(candles),"genuine_days":len(candles)/96,
            "new_older_bars":added,"source_hash":item["hash"]}


def refresh(store=STORE,*,pages=5,symbols=registry.SYMBOLS,workers=3):
    good={}
    failures={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks={pool.submit(refresh_one,store,s,pages=pages):s for s in symbols}
        for future in as_completed(tasks):
            symbol=tasks[future]
            try:good[symbol]=future.result()
            except (ValueError,OSError,KeyError,IndexError,TypeError) as exc:
                failures[symbol]=type(exc).__name__+": "+str(exc)[:160]
    if not good:raise ValueError("SOURCE_UNAVAILABLE: zero historical markets; "+canonical(failures))
    return {"symbols":good,"source_failures":failures,"real_orders":0}


def screen(store=STORE):
    """144 arms on 3 distinct historical 14-day blocks, NEVER forward tiers."""
    hypotheses=[h for h in registry.catalog() if not h.parents]
    per_arm={h.id:{"family":h.family,"blocks":[{"trades":0,"known_funding_trades":0,
        "net_stress_sum_pct":0.0} for _ in range(3)]} for h in hypotheses}
    datasets={}
    failures={}
    for symbol in registry.SYMBOLS:
        try:
            item=load(store,symbol)
            if item is not None:datasets[symbol]=item
        except (ValueError,OSError) as exc:failures[symbol]=str(exc)[:160]
    if len(datasets)<2:raise ValueError("need two verified historical datasets")
    end=min(item["candles"][-1][0] for item in datasets.values())
    start=end-42*86400000
    provenance={}
    for symbol,item in datasets.items():
        bars=[r for r in item["candles"] if start-128*900000<=r[0]<=end]
        if len(bars)<42*96+128:
            failures[symbol]="INSUFFICIENT_REAL_HISTORY_FOR_THREE_BLOCKS"
            continue
        features=Features(bars)
        last_exit={}
        provenance[symbol]=item["hash"]
        for j in range(127,len(bars)-1):
            entry=j+1
            block=(bars[entry][0]-start)//(14*86400000)
            if not 0<=block<3:continue
            votes=registry.votes_at(features,j)
            for hypothesis in hypotheses:
                side=votes[hypothesis.family]
                final=entry+hypothesis.horizon
                if not side or entry<last_exit.get(hypothesis.id,0) or final>=len(bars):continue
                if bars[final][0]>=start+(block+1)*14*86400000:continue
                last_exit[hypothesis.id]=final
                row=per_arm[hypothesis.id]["blocks"][block]
                row["trades"]+=1
                rates=[r for r in item["funding"] if bars[entry][0]-4*28800000<=r[0]<=bars[final][0]]
                contract=funding_contract(rates,bars[entry][0])
                if funding_complete(rates,contract,bars[entry][0],bars[final][0]):
                    net=100*side*(bars[final][1]/bars[entry][1]-1)-.10-.30-funding.payment_pct(
                        rates,side,bars[entry][0],bars[final][0])
                    row["known_funding_trades"]+=1
                    row["net_stress_sum_pct"]+=net
    for data in per_arm.values():
        for block in data["blocks"]:
            n=block["known_funding_trades"]
            block["mean_net_stress_pct"]=block.pop("net_stress_sum_pct")/n if n else None
    return {"schema":"adaptive-historical-screen-v1","historical_only":True,
            "future_tier_assignments_created":0,"prospective_outcomes_created":0,
            "hypotheses_evaluated":len(hypotheses),"source_hashes":provenance,
            "source_failures":failures,"blocks":3,"block_days":14,
            "raw_trades_are_correlated_not_independent_samples":True,
            "fills":"hypothetical next 15m OPEN; fee .10% plus .30% stress and settled funding",
            "per_arm":per_arm,"real_orders":0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store",type=Path,default=STORE)
    parser.add_argument("--refresh",action="store_true")
    parser.add_argument("--pages",type=int,default=5)
    parser.add_argument("--screen",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"adaptive_history"/"screen.json")
    args=parser.parse_args()
    if not args.refresh and not args.screen:parser.error("choose --refresh and/or --screen")
    protected=[ROOT/p for p in ("data","v2_state","equity_state","stock_lab_state",
                                "research_cache","research_results","v2_history","adaptive_state")]
    if any(args.store.resolve().is_relative_to(p) or args.output.resolve().is_relative_to(p)
           for p in protected) or args.store.resolve()==ROOT:
        parser.error("historical outputs must be isolated from existing evidence")
    if args.refresh:print(canonical(refresh(args.store,pages=args.pages)))
    if args.screen:
        report=screen(args.store)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
        print(canonical({"hypotheses_evaluated":report["hypotheses_evaluated"],
            "symbols":len(report["source_hashes"]),"future_tier_assignments_created":0}))


if __name__=="__main__":main()
