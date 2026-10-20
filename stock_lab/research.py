"""Research v1: same-stock signal code, chronological purged IDX EOD evaluation.

UNOFFICIAL Yahoo history is distinct from real forward paper observations.
Training/validation/holdout are chronological; no signal from a future bar
may enter a historical entry, and the 5-session outcome must finish inside
its split. Historical holdout is repeatedly examined and NOT untouched.
No real fills, fully reconciled dividends, brokerage integration or
survivorship-adjusted market universe; never promote a strategy from this.
"""
import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from statistics import mean
from pathlib import Path

from stock_lab import source,strategies
from stock_lab import engine

SCHEMA="idx-daily-purged-three-period-study-v1"
HORIZON=5
MIN_COMMON_DAYS=200
TRAIN_FRAC=.60
VALIDATION_FRAC=.20
RESEARCH_TRAIN_MIN_TRADES=10
BENCHMARK="equal_weight_frozen_six_symbol_5day_open_to_open_after_same_assumed_costs"


def cross_window_return(rows, entry_index, exit_index):
    """Next future session OPEN, model fees+slippage, not actual fills."""
    entry=float(engine._price_open(rows[entry_index],"BUY"))*(1+float(engine.BUY_FEE))
    exit_=float(engine._price_open(rows[exit_index],"SELL"))*(1-float(engine.SELL_FEE))
    if entry<=0 or exit_<=0:
        raise ValueError("DATA_INVALID: after-cost value impossible")
    return (exit_/entry-1)*100


def evaluate(market, *, withholding_future_outcomes=False):
    """Only current historical source, all 6 tickers and frozen 4 arms.

    Daily data before the first actual stock EOD observation are
    BACKTEST input, never credited as genuine prospective fills.
    """
    if set(market)!=set(source.SYMBOLS):
        raise ValueError("SOURCE_INVALID: entire predeclared IDX sector cohort required")
    indexed={}
    discarded={}
    actions={}
    for symbol in source.SYMBOLS:
        item=market[symbol]
        if item.get("provider")!=source.PROVIDER or item.get("venue")!="IDX" or item.get("currency")!="IDR":
            raise ValueError("SOURCE_INVALID: wrong ticker/venue/currency source")
        rows=item.get("history")
        if not isinstance(rows,list) or len(rows)<MIN_COMMON_DAYS:
            raise ValueError("DATA_INSUFFICIENT: 200 real daily bars per asset required")
        if item.get("history_sha256")!=source.sha(rows):
            raise ValueError("INTEGRITY_FAILURE: historical source bytes differ from hashed evidence")
        if len({r["date"] for r in rows})!=len(rows) or any(
                a["date"]>=b["date"] for a,b in zip(rows,rows[1:])):
            raise ValueError("DATA_INVALID: duplicate/reordered daily market dates")
        indexed[symbol]={r["date"]:r for r in rows}
        actions[symbol]=item.get("actions",{})
    common=set(indexed[source.SYMBOLS[0]])
    for symbol in source.SYMBOLS[1:]:
        common &=set(indexed[symbol])
    days=sorted(common)
    if len(days)<MIN_COMMON_DAYS:
        raise ValueError("DATA_INSUFFICIENT: fewer than 200 common authentic IDX sessions")
    for symbol in source.SYMBOLS:
        discarded[symbol]=len(indexed[symbol])-len(days)
    # The six-stock universe and providers' unadjusted raw OHLCVs create
    # survivor/total-return bias; this is a screening diagnostic only.
    aligned={symbol:[indexed[symbol][day] for day in days] for symbol in source.SYMBOLS}
    total=len(days)
    bounds={"training":(0,int(total*TRAIN_FRAC)),
            "validation":(int(total*TRAIN_FRAC),int(total*(TRAIN_FRAC+VALIDATION_FRAC))),
            "historical_holdout_repeatedly_inspected":(
                int(total*(TRAIN_FRAC+VALIDATION_FRAC)),total)}
    accum=defaultdict(list)
    excluded_actions=defaultdict(int)
    excluded_depth=defaultdict(int)
    excluded_boundary=defaultdict(int)
    for symbol in source.SYMBOLS:
        rows=aligned[symbol]
        for i in range(strategies.MIN_BARS-1,total-HORIZON-1):
            plan=strategies.signals(rows[:i+1])
            eligible=[arm for arm in strategies.ARMS if plan[arm]=="BUY"]
            if not eligible:continue
            entry=i+1
            exit_=entry+HORIZON
            period=next((name for name,(a,b) in bounds.items()
                         if a<=i<b),None)
            if period is None:continue
            first,last=bounds[period]
            if exit_>=last:
                for arm in eligible:excluded_boundary[arm]+=1
                continue
            if (rows[entry]["volume"]<10000 or
                    rows[entry]["open"]<=0 or rows[exit_]["open"]<=0):
                for arm in eligible:excluded_depth[arm]+=1
                continue
            interval=set(days[entry:exit_+1])
            if interval & set(actions[symbol]):
                for arm in eligible:excluded_actions[arm]+=1
                continue
            actual=cross_window_return(rows,entry,exit_)
            # Frozen same-calendar six-security buy-and-hold reference.
            # This is a *sector-unadjusted market proxy*, not official IHSG.
            basket=mean(cross_window_return(aligned[other],entry,exit_)
                        for other in source.SYMBOLS)
            for arm in eligible:
                accum[(period,arm)].append({
                    "arm":arm,"symbol":symbol,
                    "signal_session":days[i],
                    "hypothetical_entry_session":days[entry],
                    "hypothetical_exit_session":days[exit_],
                    "modeled_cost_net_return_pct":round(actual,7),
                    "equal_weight_six_stocks_same_window_net_return_pct":round(basket,7),
                    "incremental_sector_proxy_net_pct":round(actual-basket,7),
                    "prices_assumed_next_open_after_session_is_complete":True,
                    "actual_order_fill":False,
                })
    def score(rows):
        deltas=[r["incremental_sector_proxy_net_pct"] for r in rows]
        values=[r["modeled_cost_net_return_pct"] for r in rows]
        return {
            "closed_historical_hypothetical_trades":len(rows),
            "distinct_signal_session_days":len({r["signal_session"] for r in rows}),
            "mean_net_after_model_fees_pct":round(mean(values),6) if values else None,
            "mean_excess_vs_six_stock_proxy_pct":round(mean(deltas),6) if deltas else None,
            "win_rate_model_pct":round(100*sum(r>0 for r in values)/len(values),3) if values else None,
            "historical_backtest_not_prospective_validation":True,
            "real_broker_fills":0,
        }
    per_arm={}
    for arm in strategies.ARMS:
        per_arm[arm]={period:score(accum[(period,arm)])
                      for period in bounds}
        per_arm[arm]["excluded_actions_or_dividend_windows"]=excluded_actions[arm]
        per_arm[arm]["excluded_without_volume_or_price"]=excluded_depth[arm]
        per_arm[arm]["excluded_crossing_chronological_embargo"]=excluded_boundary[arm]
    training_eligible=[
        (arm,per_arm[arm]["training"]["mean_excess_vs_six_stock_proxy_pct"])
        for arm in strategies.ARMS
        if (per_arm[arm]["training"]["closed_historical_hypothetical_trades"]
            >=RESEARCH_TRAIN_MIN_TRADES and
            per_arm[arm]["training"]["mean_excess_vs_six_stock_proxy_pct"] is not None)
    ]
    training_rank=sorted(training_eligible,key=lambda a:(-a[1],a[0]))
    # Candidate selection is TRAINING-ONLY; validation and holdout are
    # observed later, NEVER used to silently rewrite selected family.
    training_selected=training_rank[0][0] if training_rank else None
    return {
        "schema":SCHEMA,"market":"IDX","currency":"IDR",
        "provider":source.PROVIDER,
        "universe":list(source.SYMBOLS),
        "common_authentic_market_days":total,
        "source_window_first_session":days[0],
        "source_window_last_session":days[-1],
        "dropped_noncommon_source_sessions_by_symbol":discarded,
        "fixed_arms":list(strategies.ARMS),
        "chronological_splits":{
            name:{"first_session":days[a],"last_session":days[b-1],
                  "observed_trading_days":b-a}
            for name,(a,b) in bounds.items()
        },
        "embargo_trading_sessions":HORIZON,
        "no_signal_enters_before_its_prior_confirmed_close":True,
        "modeled_roundtrip_costs_included":True,
        "unadjusted_prices_missing_dividend_total_returns":True,
        "all_symbols_are_current_survivors_no_delisted_members":True,
        "same_day_sector_proxy_not_official_IDX_benchmark":True,
        "experimental_training_only_selected_arm":training_selected,
        "selected_according_to_training_only":True,
        "training_ranked_by_after_cost_excess_return_only":training_rank,
        "outcome_blind_untouched_future_holdout_not_completed":True,
        "selected_arm_historical_validation_if_any":(
            per_arm[training_selected]["validation"] if training_selected else None),
        "candidate_auto_promoted_to_wallet":False,
        "further_unmeasured_dividend_tax_slippage_funding":True,
        "live_order_permission":False,
        "per_arm":per_arm,
    }


def main():
    p=argparse.ArgumentParser(description="IDX CASH PAPER historical research, NEVER live trades")
    p.add_argument("--output",default=None)
    args=p.parse_args()
    feed=source.capture()
    report=evaluate(feed["markets"])
    text=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n"
    if args.output:
        out=Path(args.output)
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(text,encoding="utf-8")
    else:print(text)


if __name__=="__main__":
    main()
