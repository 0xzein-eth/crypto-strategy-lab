"""Independent cash-equity ensemble backtest, no wallet or order changes.

Uses completed daily signals at t; entry at next observed OPEN, exit at fifth
later OPEN. Chronological 60/20/20 segments with five-session boundary purge.
Historic LQ45 universe is survivor-biased, never a pristine final holdout.
"""
import argparse
import json
from pathlib import Path
from statistics import mean
from collections import defaultdict
from equity_lab import source, universe
from stock_lab import strategies, experimental

FAMILIES={
 "trend_confirmation":("TREND20_60","TREND_RECLAIM30","MOMENTUM60"),
 "breakout_confirmation":("BREAKOUT20","DONCHIAN40","DONCHIAN60"),
 "reversal_confirmation":("RSI_REVERT","RSI_RECOVERY35","BOLLINGER_REENTRY20"),
 "volume_confirmation":("VOLUME_SQUEEZE20","ATR_EXPANSION14","VOLUME_CLIMAX_FADE"),
 "momentum_pullback":("LOWVOL_MOM","LOWVOL_PULLBACK60","MOMENTUM60"),
}
HORIZON=5
def ensemble_votes(signals):
    return {key:sum(signals.get(name)=="BUY" for name in members)>=2
            for key,members in FAMILIES.items()}

def evaluate(market, stocks):
    cfg=universe.market(market,now=__import__("datetime").datetime(2026,10,21,tzinfo=source.UTC))
    if not stocks or set(stocks)-set(cfg["symbols"]):
        raise ValueError("invalid venue or cohort")
    fee=cfg["buy_fee_pct"]+cfg["sell_fee_pct"]+2*cfg["adverse_impact_each_side_pct"]
    total_cost=fee+.25
    buckets=defaultdict(list)
    n_symbols=0
    for symbol, packet in sorted(stocks.items()):
        if (packet["market"]!=market or packet["currency"]!=cfg["currency"]
            or source.sha(packet["history"])!=packet["history_sha256"]):
            raise ValueError("unverified OHLCV")
        bars=packet["history"]
        if len(bars)<200:
            continue
        n_symbols+=1
        ca=set(packet.get("corporate_action_dates",{}))
        borders=[0,int(.6*len(bars)),int(.8*len(bars)),len(bars)]
        last_seen={}
        for i in range(experimental.MIN_BARS-1,len(bars)-HORIZON-1):
            segment=next((k for k in range(3) if borders[k]<=i<borders[k+1]),None)
            if segment is None or i+1+HORIZON>=borders[segment+1]:
                continue
            if bars[i+1]["volume"]<10000 or any(
                x["date"] in ca for x in bars[i+1:i+HORIZON+2]):
                continue
            prefix=bars[:i+1]
            signals={**strategies.signals(prefix),**experimental.signals(prefix)}
            votes=ensemble_votes(signals)
            for name,enabled in votes.items():
                if not enabled or i<=last_seen.get((name,segment),-1):
                    continue
                entry,exit_=bars[i+1],bars[i+1+HORIZON]
                if entry["open"]<=0:
                    raise ValueError("invalid entry")
                result=100*(exit_["open"]/entry["open"]-1)-total_cost
                buckets[(name,segment)].append((bars[i]["date"],result))
                last_seen[(name,segment)]=i+1+HORIZON
    phases=("training","validation","inspected_historical_holdout")
    output={}
    for name in FAMILIES:
        output[name]={}
        for segment,phase in enumerate(phases):
            rows=buckets[(name,segment)]
            values=[v for _,v in rows]
            dates=len({d for d,_ in rows})
            positive=sum(max(v,0) for v in values)
            negative=-sum(min(v,0) for v in values)
            output[name][phase]={
                "trades":len(values),"independent_signal_days":dates,
                "net_stress_mean_pct":round(mean(values),6) if values else None,
                "win_rate_pct":round(100*sum(v>0 for v in values)/len(values),4) if values else None,
                "profit_factor":round(positive/negative,5) if negative else None,
                "sufficient_for_exploratory_review":len(values)>=100 and dates>=20}
    return {"schema":"equity-ensemble-shadow-research-v1","market":market,
            "paper_only":True,"real_orders":0,"no_forward_wallet_mutation":True,
            "holdout_already_inspected":True,"frozen_membership_survivor_bias":True,
            "base_roundtrip_cost_pct":fee,"stress_extra_cost_pct":.25,
            "usable_symbols":n_symbols,"ensemble_count":len(FAMILIES),
            "not_a_portfolio_roi":True,"champions_automatically_promoted":[],
            "results":output}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--market",required=True,choices=["NASDAQ","LQ45"])
    p.add_argument("--output",required=True)
    args=p.parse_args()
    feed=source.collect(args.market)
    result=evaluate(args.market,feed["stocks"])
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
