"""Research-only 18-ticker x 10-hypothesis IDX historical matrix.

STRICTLY not the existing cash PAPER wallet. Only public authentic complete
EOD bars; no derived historical trades are ever appended to forward journals.
Securities with rejected provenance are not replaced by fake prices.
"""
import argparse
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

from stock_lab import source, experimental, research

SCHEMA="idx-expanded-historical-18x10-threeway-coststress-v1"
HORIZON=5
MIN_COMMON=250
EMBARGO=HORIZON
MIN_TRAIN_TRADES=15
MIN_DISTINCT_TRAIN_DAYS=12
EXTRA_COST_STRESS_PCT=.25


def evaluate(markets, *, errors=None, requested=None):
    """Chronological 60/20/20 research, candidate ranking from TRAIN only."""
    if len(markets)<6:
        raise ValueError("DATA_INSUFFICIENT: 6 authentic IDX equities minimum")
    indexes={}
    for symbol, item in markets.items():
        if symbol not in source.HISTORICAL_RESEARCH_SYMBOLS:
            raise ValueError("SOURCE_INVALID: non-frozen research ticker")
        if (item.get("provider")!=source.PROVIDER or
                item.get("venue")!="IDX" or item.get("currency")!="IDR"):
            raise ValueError("SOURCE_INVALID: market venue or currency")
        rows=item.get("history")
        if not isinstance(rows,list) or len(rows)<MIN_COMMON:
            raise ValueError("DATA_INSUFFICIENT: at least 250 genuine sessions")
        if item.get("history_sha256")!=source.sha(rows):
            raise ValueError("INTEGRITY_FAILURE: OHLCV provenance mismatch")
        ordered=[bar["date"] for bar in rows]
        if ordered!=sorted(set(ordered)):
            raise ValueError("DATA_INVALID: missing chronology")
        indexes[symbol]={row["date"]:row for row in rows}
    common=set.intersection(*(set(x) for x in indexes.values()))
    dates=sorted(common)
    if len(dates)<MIN_COMMON:
        raise ValueError("DATA_INSUFFICIENT: common real sessions fewer than 250")
    aligned={symbol:[rows[d] for d in dates] for symbol,rows in indexes.items()}
    symbols=sorted(aligned)
    total=len(dates)
    boundaries={
        "training":(0,int(total*.6)),
        "validation":(int(total*.6),int(total*.8)),
        "historical_holdout_repeatedly_inspected":(int(total*.8),total),
    }
    shadow=defaultdict(list)
    skipped=defaultdict(int)
    for symbol in symbols:
        bars=aligned[symbol]
        corporate_days=set(markets[symbol].get("actions") or {})
        # Precompute frozen features from every prefix without future leakage.
        for i in range(experimental.MIN_BARS-1,total-HORIZON-1):
            signal=experimental.signals(bars[:i+1])
            active=[arm for arm,v in signal.items() if v=="BUY"]
            if not active:
                continue
            entry=i+1
            exit_at=entry+HORIZON
            period=next((name for name,(a,b) in boundaries.items()
                         if a<=i<b),None)
            if period is None:continue
            _,last=boundaries[period]
            if exit_at>=last:
                for arm in active:skipped["embargo"]+=1
                continue
            # No forward quote/volume inference from signal date.
            # Entry-day volume check is a historical feasibility label ONLY.
            if min(bars[entry]["volume"],bars[exit_at]["volume"])<10000:
                for arm in active:skipped["historical_liquidity"]+=1
                continue
            if any(date in corporate_days for date in dates[entry:exit_at+1]):
                for arm in active:skipped["unknown_total_return_corporate_action"]+=1
                continue
            actual=research.cross_window_return(bars,entry,exit_at)
            control=mean(research.cross_window_return(
                aligned[other],entry,exit_at) for other in symbols)
            for arm in active:
                # One fixed 5-session horizon per arm/symbol. The next
                # candidate while the previous position is open is excluded.
                previous=shadow[(period,arm,symbol)]
                if previous and previous[-1]["exit_idx"]>=entry:
                    skipped["overlapping_same_arm_symbol"]+=1
                    continue
                shadow[(period,arm,symbol)].append({
                    "signal_date":dates[i],"entry_date":dates[entry],
                    "exit_date":dates[exit_at],"exit_idx":exit_at,
                    "symbol":symbol,"net_pct":actual,
                    "stressed_net_pct":actual-EXTRA_COST_STRESS_PCT,
                    "excess_vs_basket_pct":actual-control,
                    "stressed_excess_pct":actual-control-EXTRA_COST_STRESS_PCT,
                })
    def summary(rows):
        if not rows:
            return {"trades":0,"independent_signal_days":0,
                    "win_rate_after_fees_pct":None,"win_rate_after_stress_pct":None,
                    "mean_net_return_pct":None,"mean_after_stress_pct":None,
                    "mean_stressed_excess_vs_basket_pct":None,
                    "profit_factor_after_stress":None,
                    "worst_trade_after_stress_pct":None,
                    "worst_entry_day_mean_after_stress_pct":None,
                    "symbol_breadth":0,"portfolio_roi_claimed":False}
        s=[r["stressed_net_pct"] for r in rows]
        gain=sum(max(0,v) for v in s)
        loss=-sum(min(0,v) for v in s)
        dates_by_day=defaultdict(list)
        for r in rows:
            dates_by_day[r["signal_date"]].append(r["stressed_net_pct"])
        return {
            "trades":len(rows),
            "independent_signal_days":len(dates_by_day),
            "symbol_breadth":len({r["symbol"] for r in rows}),
            "win_rate_after_fees_pct":round(100*sum(r["net_pct"]>0 for r in rows)/len(rows),3),
            "win_rate_after_stress_pct":round(100*sum(x>0 for x in s)/len(s),3),
            "mean_net_return_pct":round(mean(r["net_pct"] for r in rows),5),
            "mean_after_stress_pct":round(mean(s),5),
            "mean_stressed_excess_vs_basket_pct":round(
                mean(r["stressed_excess_pct"] for r in rows),5),
            "profit_factor_after_stress":round(gain/loss,5) if loss>0 else None,
            "worst_trade_after_stress_pct":round(min(s),5),
            "worst_entry_day_mean_after_stress_pct":round(
                min(mean(x) for x in dates_by_day.values()),5),
            "portfolio_roi_claimed":False,
        }
    per_arm={}
    for arm in experimental.ARMS:
        per_arm[arm]={}
        for period in boundaries:
            rows=[r for symbol in symbols for r in shadow[(period,arm,symbol)]]
            per_arm[arm][period]=summary(rows)
    train_only=[]
    for arm in experimental.ARMS:
        m=per_arm[arm]["training"]
        if (m["trades"]>=MIN_TRAIN_TRADES and
            m["independent_signal_days"]>=MIN_DISTINCT_TRAIN_DAYS and
            m["mean_stressed_excess_vs_basket_pct"] is not None):
            train_only.append((arm,m["mean_stressed_excess_vs_basket_pct"]))
    train_only.sort(key=lambda x:(-x[1],x[0]))
    # Do not promote a parameter merely because it beat cash, or because
    # validation was repeatedly read. New *future* sessions are required.
    return {
        "schema":SCHEMA,"paper_only":True,
        "historical_backtest_only":True,"live_orders":0,
        "preserved_frozen_six_stock_forward_wallet":True,
        "expanded_symbols_observed":symbols,
        "requested_symbols":list(requested or source.HISTORICAL_RESEARCH_SYMBOLS),
        "symbol_source_failures":dict(errors or {}),
        "all_existing_four_prospective_arm_ids_unchanged":True,
        "new_experimental_arm_count":len(experimental.ARMS),
        "new_experimental_arms":list(experimental.ARMS),
        "common_genuine_sessions":len(dates),
        "source_dates":[dates[0],dates[-1]],
        "split_sessions":{p:{"start":dates[a],"end":dates[b-1],
                              "days":b-a} for p,(a,b) in boundaries.items()},
        "five_session_purge":EMBARGO,
        "modeled_baseline_transaction_fees_and_impact_included":True,
        "extra_stress_roundtrip_pct":EXTRA_COST_STRESS_PCT,
        "basket_comparator":"same-date surviving observed IDX research stocks (not IHSG)",
        "survivorship_dividend_and_open_auction_bias_remain":True,
        "historical_holdout_not_pristine":True,
        "independent_out_of_sample_edge_proven":False,
        "candidate_auto_promoted":False,
        "multiple_comparison_adjusted":False,
        "training_rank_only_descriptive":train_only,
        "excluded_counters":dict(skipped),
        "per_arm":per_arm,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    args=p.parse_args()
    feed=source.capture_research_history()
    report=evaluate(feed["markets"],errors=feed["missing_or_rejected_symbols"],
                    requested=feed["requested_symbols"])
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",
                      encoding="utf-8")
    print(json.dumps({"observed_symbols":len(report["expanded_symbols_observed"]),
                      "genuine_common_sessions":report["common_genuine_sessions"],
                      "hypotheses":len(report["new_experimental_arms"]),
                      "not_an_investable_roi":True,"live_orders":0}))


if __name__=="__main__":
    main()
