"""Read-only v2 hypothesis triage; no winner promotion and no trade routing.

Compares actual eligible CLOSED evidence and exact-stratum controls using
existing audited modules. DESCRIPTIVE metrics are not a final fresh holdout.
Selection notes depend only on TRAINING UTC days; monitoring is summarized
but is NEVER consulted to select future positions.
"""
import argparse
from collections import defaultdict
import datetime as dt
import json
from statistics import mean

import learner
import matched_controls
import research_quality

VERSION = "v2-hypothesis-readiness-1"


def evaluate(records, *, schedule_coverage=None):
    if isinstance(records,dict):
        rows=list(records.values())
    else:
        rows=list(records)
    comparison=matched_controls.compare(rows)
    readiness=research_quality.evaluate(rows,comparison,schedule_coverage)
    learner_summary=learner.analysis(rows)
    groups=defaultdict(list)
    for row in rows:
        if learner.eligible(row):
            groups[row["strategy"]].append(row)
    output=[]
    for arm in learner.BASELINES+learner.ADVANCED:
        eligible=groups[arm]
        is_control = arm == "CTRL-v1"
        train=[r for r in eligible if learner.stable_bucket(
            "holdout:"+learner.day_of(r),5)!=0]
        monitoring_n=len(eligible)-len(train)
        days={learner.day_of(r) for r in train}
        weeks={dt.date.fromisoformat(x).isocalendar()[:2] for x in days}
        stress_values=[learner.research_R(r) for r in train]
        frozen=learner_summary["arms"][arm]
        pair=comparison["arms"].get(arm,{})
        gate=readiness["arms"].get(arm,{})
        neg=frozen["underperformer_train_only"]
        avg=mean(stress_values) if stress_values else None
        # Conservative research triage only, never automatic allocation.
        # No shadow holdout outcome changes this qualitative status.
        if is_control:
            status="REFERENCE_NEVER_PROMOTE"
        elif len(train)<50 or len(days)<7 or len(weeks)<3:
            status="INSUFFICIENT_INDEPENDENT_TRAINING_DAYS"
        elif neg:
            status="PERSISTENT_TRAINING_NEGATIVE_REVIEW"
        elif avg is not None and avg>0 and frozen["train_cluster_lcb_R"] is not None and frozen["train_cluster_lcb_R"]>0:
            status="POSITIVE_TRAIN_SCREEN_ONLY_NO_DEPLOYMENT"
        else:
            status="NO_POSITIVE_TRAINING_EDGE_DEMONSTRATED"
        output.append({
            "strategy":arm, "triage":status,
            "training_eligible_n":len(train),
            "training_distinct_utc_days":len(days),
            "training_distinct_iso_weeks":len(weeks),
            "training_stress_scenario_mean_R":round(avg,6) if avg is not None else None,
            "training_daily_descriptive_lcb_R":frozen["train_cluster_lcb_R"],
            "persistent_training_negative":bool(neg),
            "previously_inspected_monitoring_n_NOT_for_selection":monitoring_n,
            "actual_matched_control_pairs":pair.get("matched_pairs",0),
            "matched_control_fraction":pair.get("matched_fraction"),
            "quality_gate_readiness":gate.get("quality_gate_pass",False),
            "quality_blockers":gate.get("blocking_reasons",
                  ["NO_ELIGIBLE_CONTROL_STRATUM_EVIDENCE"]),
            "independent_future_holdout_complete":False,
            "after_fee_and_real_fill_edge_proven":False,
        })
    # No profit ranking based on periodically inspected winner labels.
    return {
        "version":VERSION,"paper_only":True,"real_orders":False,
        "existing_allocation_untouched":True,
        "edge_proven":False, "champion":None,
        "repeated_monitoring_is_not_untouched_final_holdout":True,
        "scheduler_coverage_diagnostic":schedule_coverage,
        "risk_warning":"Study hypothesis/independent calendar days, exact matched controls, funding and REAL executable bid/ask; high WR alone is not a sufficient promotion signal.",
        "training_status_uses_only_train_return":True,
        "arms":output,
    }


def main():
    parser=argparse.ArgumentParser(description="read-only training vs matched control scorecard")
    parser.add_argument("--output",default=None,
                        help="Optional derived JSON output; NOT canonical v8 ledger")
    args=parser.parse_args()
    import engine
    records,_,_,_=engine.replay()
    report=json.loads(engine.REPORT.read_text())
    coverage=(report.get("scheduling_diagnostics") or {}).get("estimated_10m_slot_coverage")
    result=evaluate(records,schedule_coverage=coverage)
    document=json.dumps(result,sort_keys=True,indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(document+"\n",encoding="utf-8")
    else:
        print(document)


if __name__=="__main__":
    main()
