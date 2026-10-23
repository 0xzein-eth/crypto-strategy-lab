"""Crypto ensemble descriptive outcome audit on existing frozen shadow observations.

Vote based ONLY on simultaneous registered strategy signals. Evaluate the
observed matched 4h outcomes afterwards. No signal rewriting, order placement,
or untouched holdout claims. Missing or divergent fills are excluded.
"""
import argparse
import json
import math
import datetime as dt
from collections import defaultdict
from pathlib import Path
from statistics import mean
from research_quality.composites import COMPOSITES
from research_quality.calendar_evidence import interval_by_entry_day
from v2.shadow_research import VERSION as SOURCE_VERSION

def analyze(source):
    if source.get("version")!=SOURCE_VERSION:
        raise ValueError("shadow schema mismatch")
    groups=defaultdict(dict)
    for row in source.get("closed_outcomes",[]):
        if not isinstance(row,dict):
            raise ValueError("invalid shadow outcome")
        key=(row["symbol"],row["entry_at"])
        arm=row["arm"]
        if arm in groups[key]:
            raise ValueError("duplicate arm on matched entry instant")
        groups[key][arm]=row
    result={}
    for name,arms in COMPOSITES.items():
        candidates=[]
        for (symbol,at),rows in sorted(groups.items()):
            matched=[rows[a] for a in arms if a in rows]
            if len(matched)<2:
                continue
            sides={r["signal_side"] for r in matched}
            if len(sides)!=1:
                continue
            eligible=[r for r in matched if r.get("timely") is True and
                      r.get("executable_topbook_quantity_both_sides") is True]
            if len(eligible)!=len(matched):
                continue
            # The same observed asset/time/direction must have the same result;
            # NEVER select a profitable outcome among contradictory snapshots.
            values=[float(r["assumed_stressed_net_pct"]) for r in matched]
            if any(isinstance(r["assumed_stressed_net_pct"],bool) for r in matched) or not all(math.isfinite(v) for v in values):
                raise ValueError("nonfinite/nonnumeric matched outcome")
            if max(values)-min(values)>0.000001:
                raise ValueError("different payoffs for identical quote path")
            moment=dt.datetime.fromisoformat(at.replace("Z","+00:00"))
            if moment.tzinfo is None:raise ValueError("entry UTC timezone required")
            candidates.append({"symbol":symbol,"at":at,"side":next(iter(sides)),
                               "entry_day":moment.astimezone(dt.timezone.utc).date().isoformat(),"stressed_net_pct":values[0],
                               "constituent_votes":len(matched)})
        days=len({c["entry_day"] for c in candidates})
        vals=[c["stressed_net_pct"] for c in candidates]
        pos=sum(max(0,v) for v in vals)
        neg=-sum(min(0,v) for v in vals)
        result[name]={"matched_closed":len(vals),"entry_days":days,
                      "mean_stressed_net_pct":round(mean(vals),7) if vals else None,
                      "win_rate":sum(v>0 for v in vals)/len(vals) if vals else None,
                      "profit_factor":round(pos/neg,5) if neg else None,
                      "ready_for_descriptive_review":len(vals)>=100 and days>=20,
                      "day_cluster_multiple_testing":interval_by_entry_day(
                          [(r["entry_day"],r["stressed_net_pct"]) for r in candidates],families=len(COMPOSITES)),
                      "not_independent_trade_fills":True}
    return {"schema":"v2-composite-shadow-observed-outcomes-v1",
            "source_version":SOURCE_VERSION,"source_observation_hash":source.get("last_source_hash"),"shadow_only":True,
            "funding_incomplete":True,"already_inspected_data":True,
            "real_orders":0,"auto_promoted":[],"results":result}

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--source",default="v2_state/shadow_report.json")
    cli.add_argument("--output",required=True)
    args=cli.parse_args()
    raw=json.loads(Path(args.source).read_text(encoding="utf-8"))
    Path(args.output).write_text(json.dumps(analyze(raw),indent=2,sort_keys=True)+"\n")
if __name__=="__main__":
    main()
