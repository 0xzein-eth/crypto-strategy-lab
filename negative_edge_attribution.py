"""Prospective PAPER loss attribution by pre-existing, observed dimensions.

Pure report: never changes strategy weights, market universe, closed trades,
or the evaluation horizon. Results are descriptive, not multiplicity-adjusted
alpha or evidence for real-money execution.
"""
from collections import defaultdict
from statistics import mean, stdev
import math

import learner
import universe

MIN_INDEPENDENT_DAYS=7
MIN_ELIGIBLE_CLOSES=50


def _group_report(rows):
    if not rows:
        return {"eligible_closes":0, "distinct_entry_utc_days":0,
                "after_cost_mean_R":None,"day_cluster_ucb_R":None,
                "descriptive_negative_warning":False,
                "insufficient_independent_evidence":True}
    by_day=defaultdict(list)
    values=[]
    for row in rows:
        value=learner.research_R(row)
        if not math.isfinite(value):
            raise ValueError("INTEGRITY_FAILURE: nonfinite cost-adjusted R")
        by_day[learner.day_of(row)].append(
            max(-learner.CLIP_R,min(learner.CLIP_R,value)))
        values.append(value)
    daily=[mean(v) for _,v in sorted(by_day.items())]
    enough=(len(rows)>=MIN_ELIGIBLE_CLOSES and
            len(daily)>=MIN_INDEPENDENT_DAYS)
    upper=(mean(daily)+1.96*stdev(daily)/math.sqrt(len(daily))
           if len(daily)>=4 else None)
    return {
        "eligible_closes":len(rows),
        "distinct_entry_utc_days":len(daily),
        "after_cost_mean_R":round(mean(values),6),
        "day_cluster_ucb_R":round(upper,6) if upper is not None else None,
        "descriptive_negative_warning":bool(
            enough and upper is not None and upper<0),
        "insufficient_independent_evidence":not enough,
    }


def evaluate(records):
    source=records.values() if isinstance(records,dict) else records
    groups={name:defaultdict(list) for name in
            ("strategy","symbol","horizon_hours","side","entry_regime","sector")}
    eligible=0
    missing={"strategy":0,"symbol":0,"side":0,"entry_regime":0,"sector":0}
    for row in source:
        if not learner.eligible(row):
            continue
        eligible+=1
        ev=row.get("evidence") or {}
        stratum=ev.get("sampling_stratum") or []
        sector=(stratum[0] if stratum else universe.ASSET_SECTORS.get(row.get("symbol")))
        dimensions={
            "strategy":row.get("strategy") or "UNKNOWN",
            "symbol":row.get("symbol") or "UNKNOWN",
            "horizon_hours":str(row["horizon_hours"]),
            "side":row.get("side") or "UNKNOWN",
            "entry_regime":row.get("regime") or ev.get("entry_regime") or "UNKNOWN",
            "sector":sector or "UNKNOWN",
        }
        for name,value in dimensions.items():
            if value=="UNKNOWN" and name in missing:
                missing[name]+=1
            groups[name][str(value)].append(row)
    return {
        "method":"cost-adjusted-entry-day-cluster-loss-attribution-v1",
        "paper_only":True,
        "read_only":True,
        "no_strategy_selection_or_auto_reweight":True,
        "not_a_live_trading_signal":True,
        "multiple_testing_adjusted":False,
        "minimum_independent_days_for_descriptive_warning":MIN_INDEPENDENT_DAYS,
        "minimum_closes_for_descriptive_warning":MIN_ELIGIBLE_CLOSES,
        "eligible_closes":eligible,
        "missing_frozen_metadata":missing,
        "dimensions":{name:{k:_group_report(rows)
                            for k,rows in sorted(values.items())}
                      for name,values in groups.items()},
        "caveat":"Clipped entry-day aggregates are correlated and multiply inspected; no filter, winner selection, strategy promotion, or execution authorization.",
    }
