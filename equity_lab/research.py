"""Cross-market historical, purged, fixed-horizon PAPER diagnostics only.

Returns from mutually overlapping strategy tests are NOT a funded portfolio.
No historic symbol backfill of LQ45 membership: snapshot is valid only
during its frozen interval; past bars are reference, not contemporaneous
membership. No future candle feeds an earlier signal.
"""
import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from equity_lab import source,universe,forward
from stock_lab import strategies,experimental

HORIZON=5
MIN_ALIGNED=200
STRESS_ADDITIONAL_ROUNDTRIP_PCT=.25
SCHEMA="dual-nasdaq-lq45-historical-14-armed-after-cost-purged-v1"


def fees(market):
    cfg=universe.market(market,now=dt.datetime(2026,10,21,tzinfo=source.UTC))
    return (cfg["buy_fee_pct"]+cfg["sell_fee_pct"]+
            2*cfg["adverse_impact_each_side_pct"])


def returns(market,entry,exit_):
    cost=fees(market)
    return 100*(exit_["open"]/entry["open"]-1)-cost


def evaluate(market, stocks, benchmark=None):
    """Per-symbol historical split, fixed 5 sessions, no future selection."""
    config=universe.market(market,now=dt.datetime(2026,10,21,tzinfo=source.UTC))
    if not stocks or set(stocks)-set(config["symbols"]):
        raise ValueError("SOURCE_INVALID: wrong research market")
    benchmark_by_day={}
    if benchmark is not None:
        if (benchmark.get("symbol")!=config["benchmark"] or
            benchmark.get("market")!=market or
            benchmark.get("currency")!=config["currency"] or
            benchmark.get("is_nontradable_benchmark") is not True or
            source.sha(benchmark.get("history",[]))!=benchmark.get("history_sha256")):
            raise ValueError("BENCHMARK_INTEGRITY: wrong index, currency or missing source hash")
        benchmark_by_day={r["date"]:r for r in benchmark["history"]}
    accum=defaultdict(list)
    errors={}
    usable={}
    for symbol,packet in stocks.items():
        if (packet.get("market")!=market or
            packet.get("currency")!=config["currency"] or
            packet.get("is_nontradable_benchmark") is not False or
            source.sha(packet["history"])!=packet["history_sha256"]):
            raise ValueError("INTEGRITY_FAILURE: verified frozen OHLCV required")
        bars=packet["history"]
        if len(bars)<MIN_ALIGNED:
            errors[symbol]="DATA_INSUFFICIENT: fewer than 200 EOD sessions"
            continue
        usable[symbol]=bars
        split={"training":(0,int(len(bars)*.6)),
               "validation":(int(len(bars)*.6),int(len(bars)*.8)),
               "historical_holdout_repeatedly_inspected":
                    (int(len(bars)*.8),len(bars))}
        corporate=set(packet.get("corporate_action_dates",{}))
        last_accepted=defaultdict(lambda:-1)
        for i in range(experimental.MIN_BARS-1,len(bars)-HORIZON-1):
            # no future data in decision function.
            prefix=bars[:i+1]
            signal={**strategies.signals(prefix),**experimental.signals(prefix)}
            active=[arm for arm,flag in signal.items() if flag=="BUY"]
            if not active:continue
            period=next((p for p,(a,b) in split.items() if a<=i<b),None)
            if period is None:continue
            a,b=split[period]
            entry=i+1
            final=entry+HORIZON
            if final>=b:continue  # five-session purge before split boundary
            if any(r["date"] in corporate for r in bars[entry:final+1]):
                continue # Unadjusted dividends/splits -> not coherent total return
            if bars[entry]["volume"]<10000:continue
            net=returns(market,bars[entry],bars[final])
            stress=net-STRESS_ADDITIONAL_ROUNDTRIP_PCT
            # The benchmark is an index and cannot be physically filled.
            # Paired date-to-date price move is a descriptive control only,
            # not an executable fee-adjusted index portfolio.
            index_start=benchmark_by_day.get(bars[entry]["date"])
            index_end=benchmark_by_day.get(bars[final]["date"])
            benchmark_return=(100*(index_end["open"]/index_start["open"]-1)
                              if index_start and index_end else None)
            for arm in active:
                key=(period,arm)
                if i<=last_accepted[(symbol,arm,period)]:
                    continue
                last_accepted[(symbol,arm,period)]=final
                accum[key].append({
                    "signal":bars[i]["date"],"symbol":symbol,
                    "return_pct":net,"stress_return_pct":stress,
                    "index_open_to_open_pct":benchmark_return,
                    "stress_excess_vs_index_pct":(
                        stress-benchmark_return
                        if benchmark_return is not None else None)})
    def stats(rows):
        vals=[r["stress_return_pct"] for r in rows]
        gross_pos=sum(max(0,x) for x in vals)
        gross_neg=-sum(min(0,x) for x in vals)
        per_day=defaultdict(list)
        for r in rows:per_day[r["signal"]].append(r["stress_return_pct"])
        index_pairs=[r["stress_excess_vs_index_pct"] for r in rows
                     if r["stress_excess_vs_index_pct"] is not None]
        return {
            "historical_hypothetical_trades":len(rows),
            "distinct_signal_session_days":len(per_day),
            "stressed_win_rate_pct":round(100*sum(x>0 for x in vals)/len(vals),4)
                                   if vals else None,
            "stressed_mean_trade_pct":round(mean(vals),6) if vals else None,
            "stressed_profit_factor":round(gross_pos/gross_neg,5)
                                      if gross_neg else None,
            "index_paired_historical_trades":len(index_pairs),
            "stressed_mean_excess_vs_price_index_pct":(
                 round(mean(index_pairs),6) if index_pairs else None),
            "price_index_is_not_investable":True,
            "worst_day_cluster_avg_pct":round(min(mean(x) for x in per_day.values()),6)
                                         if per_day else None,
            "not_portfolio_roi":True}
    grouped={arm:{split:stats(accum[(split,arm)]) for split in
                    ("training","validation","historical_holdout_repeatedly_inspected")}
             for arm in forward.ALL_ARMS}
    eligible=[(arm,v["training"]["stressed_mean_trade_pct"]) for arm,v in grouped.items()
              if v["training"]["historical_hypothetical_trades"]>=20 and
                 v["training"]["distinct_signal_session_days"]>=12 and
                 v["training"]["stressed_mean_trade_pct"] is not None]
    eligible.sort(key=lambda x:(-x[1],x[0]))
    return {
        "schema":SCHEMA,"market":market,"currency":config["currency"],
        "price_data_unofficial":True,"paper_only":True,"real_orders":0,
        "observed_verified_history_symbols":sorted(usable),
        "symbols_with_too_little_history":errors,
        "frozen_membership_effective":config["membership_effective"],
        "frozen_membership_expiry":config["membership_expiry"],
        "historical_universe_survivor_bias_remains":True,
        "repeatedly_inspected_holdout_not_pristine":True,
        "same_symbol_arm_nonoverlap":True,
        "purge_sessions":HORIZON,
        "additional_roundtrip_cost_stress_pct":STRESS_ADDITIONAL_ROUNDTRIP_PCT,
        "benchmark":config["benchmark"],
        "benchmark_index_nontradable":True,
        "benchmark_available":bool(benchmark),
        "benchmark_evidence_hash":(benchmark["history_sha256"] if benchmark else None),
        "training_only_ranked_by_after_cost_stress":eligible,
        "new_experiments_not_auto_selected_for_forward_trading":True,
        "out_of_sample_alpha_proven":False,
        "hypothesis_family_count":len(forward.ALL_ARMS),
        "per_arm":grouped,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--market",required=True,choices=("NASDAQ","LQ45"))
    p.add_argument("--output",required=True)
    args=p.parse_args()
    feed=source.collect(args.market)
    report=evaluate(args.market,feed["stocks"],feed["benchmark"])
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",
                    encoding="utf-8")
    print(source.canonical({"market":args.market,
                          "genuine_symbols":len(report["observed_verified_history_symbols"]),
                          "strategy_families":len(forward.ALL_ARMS),
                          "eligible_train_ranked":len(report["training_only_ranked_by_after_cost_stress"]),
                          "real_orders":0}))


if __name__=="__main__":
    main()
