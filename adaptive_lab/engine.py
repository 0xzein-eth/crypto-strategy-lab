"""Replayable adaptive SHADOW research; public observations, zero orders."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path

from adaptive_lab import policy, registry, source
from research_v9 import funding
from v2.paper_portfolio import D, ts, iso, verify_quote

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"adaptive_state"
SCHEMA="adaptive-crypto-prospective-shadow-v1"
ZERO="0"*64
NOTIONAL=D(200)
FEE=D(".0005")
STRESS_PCT=D(".30")


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def code_contract():
    paths=list((ROOT/"adaptive_lab").glob("*.py"))
    paths += [ROOT/p for p in ("research_v9/factory.py","research_v9/history.py",
                               "research_v9/funding.py","v2/paper_portfolio.py")]
    return {"registry":registry.digest(),"source_sha256":{
        str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)}}


def seal(tick,events):
    body={"schema":SCHEMA,"seq":len(events)+1,
          "prev_hash":events[-1]["hash"] if events else ZERO,
          "code_contract":code_contract(),"tick":tick}
    return {**body,"hash":sha(body)}


def read_events(state=STATE):
    folder=Path(state)/"observations"
    if not folder.exists():return []
    paths=sorted(folder.iterdir())
    if any(p.name!=f"{i:08d}.json.gz" for i,p in enumerate(paths,1)):
        raise ValueError("INTEGRITY_FAILURE: missing/unexpected adaptive observation file")
    events=[json.loads(gzip.decompress(path.read_bytes())) for path in paths]
    verify_events(events)
    return events


def verify_events(events):
    expected_contract=code_contract()
    previous=ZERO
    last_slot=-1
    for i,event in enumerate(events,1):
        body={k:v for k,v in event.items() if k!="hash"}
        if (set(body)!={"schema","seq","prev_hash","code_contract","tick"} or
                event["schema"]!=SCHEMA or event["seq"]!=i or
                event["prev_hash"]!=previous or event.get("hash")!=sha(body)):
            raise ValueError("INTEGRITY_FAILURE: broken adaptive source hash chain")
        if event["code_contract"]!=expected_contract:
            raise ValueError("EPOCH_FROZEN: code changed; register a new state directory/epoch")
        tick=event["tick"]
        now=ts(tick["observed_at"])
        slot=int(now.timestamp())//900
        if slot<=last_slot:raise ValueError("CLOCK_INTEGRITY: duplicate/reversed adaptive slot")
        if tick.get("real_orders")!=0 or tick.get("public_sources_only") is not True:
            raise ValueError("SOURCE_INVALID: public/no-order contract")
        if not 2<=len(tick["assets"])<=16 or set(tick["assets"])-set(registry.SYMBOLS):
            raise ValueError("SOURCE_INVALID: invalid observed universe")
        for symbol,asset in tick["assets"].items():source.validate_asset(symbol,asset,now=now)
        previous=event["hash"]
        last_slot=slot


def side_price(book,side,*,entry):
    return D(book["ask"] if (side==1)==entry else book["bid"])


def deep_enough(book,side,quantity,*,entry):
    return D(book["ask_size_base"] if (side==1)==entry else book["bid_size_base"])>=quantity


def funding_contract(rates,entry_ms):
    """Freeze the observed regular settlement schedule BEFORE entry."""
    prior=[r[0] for r in rates if r[0]<=entry_ms]
    if len(prior)<4:return None
    gaps={b-a for a,b in zip(prior[-4:],prior[-3:])}
    if len(gaps)!=1:return None
    interval=next(iter(gaps))
    if interval not in (3600000,7200000,14400000,28800000) or entry_ms-prior[-1]>=interval:
        return None
    return {"anchor_ms":prior[-1],"interval_ms":interval}


def funding_complete(rates,contract,entry_ms,exit_ms):
    if contract is None:return False
    expected=set(range(contract["anchor_ms"]+contract["interval_ms"],exit_ms+1,
                       contract["interval_ms"]))
    expected={moment for moment in expected if moment>entry_ms}
    actual={r[0] for r in rates if entry_ms<r[0]<=exit_ms}
    # A changed/irregular venue schedule is UNKNOWN until registered; a
    # missing expected payment cannot become zero in a short hold window.
    return actual==expected


def outcome(position,asset,now_ms,rates):
    book=asset["book"]
    entry_ms=position["entry_ms"]
    window=[row for row in rates if entry_ms-12*3600000<=row[0]<=now_ms]
    complete=funding_complete(window,position.get("funding_contract"),entry_ms,now_ms)
    metrics=[]
    sufficient=True
    for side in (position["side"],position["control_side"]):
        entry=side_price(position["entry_book"],side,entry=True)
        exit_=side_price(book,side,entry=False)
        quantity=NOTIONAL/entry
        sufficient &= deep_enough(book,side,quantity,entry=False)
        gross=100*side*(exit_/entry-1)
        fee=100*FEE*(1+exit_/entry)
        paid=(D(funding.payment_pct(window,side,entry_ms,now_ms)) if complete else None)
        stress=(gross-fee-paid-STRESS_PCT if paid is not None else None)
        metrics.append({"gross_book_pct":float(gross),"fee_pct":float(fee),
                        "funding_paid_pct":float(paid) if paid is not None else None,
                        "stress_pct":float(stress) if stress is not None else None})
    own,control=metrics
    timely=now_ms-position["due_ms"]<=1800000
    return {"id":position["id"],"strategy":position["strategy"],
            "symbol":position["symbol"],"lane":position["lane"],
            "entry_ms":entry_ms,"exit_ms":now_ms,
            "eligible":bool(complete and sufficient and timely),
            "timely":timely,"exit_depth_sufficient":bool(sufficient),
            "settled_funding_coverage":complete,"costs":own,
            "stress_pct":own["stress_pct"],
            "delta_pct":(own["stress_pct"]-control["stress_pct"] if complete else None)}


def activate_children(tiers,existing,observed_at):
    result=dict(existing)
    for hypothesis in registry.catalog():
        if hypothesis.parents and hypothesis.id not in result and all(
                tiers[parent].get("needs_redevelopment",False) for parent in hypothesis.parents):
            result[hypothesis.id]={"activated_at":observed_at,
                "parents":list(hypothesis.parents),"parent_outcomes_inherited":0}
    return result


def replay(events):
    verify_events(events)
    hypotheses={x.id:x for x in registry.catalog()}
    tiers={key:{"tier":"WARMUP","candidate_for_human_review":False,
                "needs_redevelopment":False} for key in hypotheses}
    pending={}
    known=set()
    rates=defaultdict(dict)
    closed=[]
    activations={}
    transitions=[]
    admissions=Counter()
    opportunities=Counter()
    rejections=Counter()
    checkpoint=0
    epoch_ms=int(ts(events[0]["tick"]["observed_at"]).timestamp()*1000) if events else None
    for event in events:
        tick=event["tick"]
        now_ms=int(ts(tick["observed_at"]).timestamp()*1000)
        slot=now_ms//900000
        for symbol,asset in tick["assets"].items():
            for row in asset["funding"]:
                if row[0] in rates[symbol] and rates[symbol][row[0]]!=row:
                    raise ValueError("INTEGRITY_FAILURE: revised settled funding")
                rates[symbol][row[0]]=row
        for key,pos in list(pending.items()):
            if now_ms<pos["due_ms"] or pos["symbol"] not in tick["assets"]:continue
            symbol=pos["symbol"]
            closed.append(outcome(pos,tick["assets"][symbol],now_ms,
                                  [rates[symbol][k] for k in sorted(rates[symbol])]))
            del pending[key]
        completed=(now_ms-epoch_ms)//policy.BLOCK_MS
        while checkpoint<completed:
            checkpoint+=1
            updated=policy.classify(closed,epoch_ms=epoch_ms,checkpoint=checkpoint,previous=tiers)
            for key,verdict in updated.items():
                if verdict["tier"]!=tiers[key]["tier"]:
                    transitions.append({"strategy":key,"from":tiers[key]["tier"],
                        "to":verdict["tier"],"checkpoint":checkpoint,"observed_at":tick["observed_at"]})
            tiers=updated
            activations=activate_children(tiers,activations,tick["observed_at"])
        candidates=[]
        active_pairs={(p["strategy"],p["symbol"],p["lane"]) for p in pending.values()}
        for symbol,asset in tick["assets"].items():
            signals=registry.proposals(asset["candles"],activations)
            book=asset["book"]
            checked=verify_quote(book,symbol=symbol,now=tick["observed_at"])
            spread=(checked["ask"]-checked["bid"])/((checked["ask"]+checked["bid"])/2)*10000
            bar=asset["candles"][-1][0]
            for ident,side in signals.items():
                key=f"{ident}:{symbol}:{bar}"
                if key in known:continue
                known.add(key)
                opportunities[ident]+=1
                exploration_available=(ident,symbol,"EXPLORATION") not in active_pairs
                priority_available=(ident,symbol,"PRIORITY") not in active_pairs
                if not exploration_available and not priority_available:
                    rejections["nonoverlap"]+=1
                    continue
                control=1 if int(sha(["neutral-v1",key])[:8],16)%2==0 else -1
                enough=all(deep_enough(book,s,NOTIONAL/side_price(book,s,entry=True),entry=True)
                           for s in (side,control))
                if spread>15 or not enough:
                    rejections["spread_or_entry_depth"]+=1
                    continue
                hypothesis=hypotheses[ident]
                candidates.append({"id":key,"strategy":ident,"family":hypothesis.family,
                    "symbol":symbol,"side":side,"control_side":control,
                    "exploration_available":exploration_available,
                    "priority_available":priority_available,
                    "funding_contract":funding_contract(asset["funding"],now_ms),
                    "entry_ms":now_ms,"due_ms":now_ms+hypothesis.horizon*900000,
                    "entry_book":book})
        selected=policy.select(candidates,tiers,slot=slot)
        rejections["budget_or_cadence"]+=len(candidates)-len(selected)
        for pos in selected:
            pending[pos["id"]]=pos
            admissions[pos["lane"]]+=1
    diagnostics={}
    for ident in hypotheses:
        rows=[r for r in closed if r["strategy"]==ident]
        valued=[r for r in rows if r["stress_pct"] is not None]
        diagnostics[ident]={"signal_opportunities":opportunities[ident],
            "closed_shadow_pairs":len(rows),"eligible_exploration_pairs":sum(
                r["eligible"] and r["lane"]=="EXPLORATION" for r in rows),
            "late_pairs":sum(not r["timely"] for r in rows),
            "unknown_funding_pairs":sum(not r["settled_funding_coverage"] for r in rows),
            "insufficient_exit_depth_pairs":sum(not r["exit_depth_sufficient"] for r in rows),
            "mean_gross_book_pct":sum(r["costs"]["gross_book_pct"] for r in rows)/len(rows) if rows else None,
            "mean_fee_pct":sum(r["costs"]["fee_pct"] for r in rows)/len(rows) if rows else None,
            "mean_stress_pct":sum(r["stress_pct"] for r in valued)/len(valued) if valued else None,
            "stress_extra_pct":float(STRESS_PCT),
            "review_required":tiers[ident]["needs_redevelopment"]}
    return {"schema":SCHEMA,"registry_digest":registry.digest(),"observations":len(events),
        "last_source_hash":events[-1]["hash"] if events else ZERO,
        "epoch_start_ms":epoch_ms,"last_observed_at":events[-1]["tick"]["observed_at"] if events else None,
        "completed_fourteen_day_blocks":checkpoint,
        "last_observed_symbols":sorted(events[-1]["tick"]["assets"]) if events else [],
        "last_source_failures":events[-1]["tick"]["source_failures"] if events else {},
        "registered_single_hypotheses":144,"registered_reserve_children":30,
        "active_hypotheses":144+len(activations),"inactive_reserved_children":30-len(activations),
        "active_children":activations,"tier_counts":dict(Counter(v["tier"] for v in tiers.values())),
        "active_tier_counts":dict(Counter(v["tier"] for k,v in tiers.items()
            if not hypotheses[k].parents or k in activations)),
        "tiers":tiers,"tier_transitions":transitions,"diagnostics":diagnostics,
        "admissions_by_lane":dict(admissions),"pending_shadow_pairs":len(pending),
        "closed_shadow_pairs":len(closed),"rejections":dict(rejections),
        "candidates_for_human_review":[k for k,v in tiers.items() if v["candidate_for_human_review"]],
        "mode":"PROSPECTIVE_SHADOW_NOT_A_FUNDED_PORTFOLIO",
        "actual_exchange_fills":0,"real_orders":0,"live_trading_authorized":False,
        "research_tiers_are_not_profit_probabilities":True,
        "priority_outcomes_used_to_set_tiers":False}


def report_path(state):return Path(state)/"report.json"


def write_report(state,report):
    target=report_path(state)
    temp=target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    os.replace(temp,target)


def verify_saved(state=STATE):
    events=read_events(state)
    report=replay(events)
    path=report_path(state)
    if events and (not path.is_file() or json.loads(path.read_text())!=report):
        raise ValueError("INTEGRITY_FAILURE: missing/divergent adaptive report; explicit --rebuild-report required")
    return events,report


def observe(state=STATE,*,getter=source.get,symbols=registry.SYMBOLS):
    events,_=verify_saved(state)
    slot=int(dt.datetime.now(source.UTC).timestamp())//900
    if events and int(ts(events[-1]["tick"]["observed_at"]).timestamp())//900>=slot:
        return {"status":"SLOT_ALREADY_OBSERVED","observations":len(events)}
    tick=source.capture(symbols=symbols,getter=getter)
    event=seal(tick,events)
    report=replay([*events,event])
    folder=Path(state)/"observations"
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f"{len(events)+1:08d}.json.gz"
    # Exclusive creation protects a concurrent/local writer from overwrites.
    with target.open("xb") as stream:
        stream.write(gzip.compress(canonical(event).encode(),mtime=0))
        stream.flush()
        os.fsync(stream.fileno())
    write_report(state,report)
    return {"status":"AUTHENTIC_SHADOW_CAPTURED","observations":len(events)+1,
        "symbols":report["last_observed_symbols"],"source_failures":report["last_source_failures"],
        "admissions_by_lane":report["admissions_by_lane"],"tier_counts":report["active_tier_counts"],
        "inactive_reserved_children":report["inactive_reserved_children"],
        "pending_shadow_pairs":report["pending_shadow_pairs"],"real_orders":0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state",type=Path,default=STATE)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--observe",action="store_true")
    actions.add_argument("--verify-only",action="store_true")
    actions.add_argument("--rebuild-report",action="store_true")
    args=parser.parse_args()
    protected=[ROOT/x for x in ("data","v2_state","equity_state","stock_lab_state",
                                "research_cache","research_results","v2_history","adaptive_history")]
    if args.state.resolve()==ROOT or any(args.state.resolve().is_relative_to(p) for p in protected):
        parser.error("adaptive state must be isolated from existing evidence")
    if args.observe:
        output=observe(args.state)
    elif args.rebuild_report:
        events=read_events(args.state)
        report=replay(events)
        args.state.mkdir(parents=True,exist_ok=True)
        write_report(args.state,report)
        output={"status":"DERIVED_REPORT_REBUILT","observations":len(events),"real_orders":0}
    else:
        _,report=verify_saved(args.state)
        output={k:report[k] for k in ("observations","last_source_hash","tier_counts",
                                     "closed_shadow_pairs","pending_shadow_pairs","real_orders")}
    print(canonical(output))


if __name__=="__main__":main()
