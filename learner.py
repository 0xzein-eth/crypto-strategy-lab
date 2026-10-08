"""Pre-registered, deterministic PAPER-ONLY online research allocator.

Learning observes only CLOSED, timely same-venue perpetual outcomes recorded by
the canonical ledger. It never edits prior decisions or invents new executable
trading code. No new signal means no trade. Correlation is treated by UTC-day
clusters; this is research triage rather than proof of edge.
"""
import datetime as dt
import hashlib
import math
from collections import defaultdict
from statistics import mean, stdev

BASELINES=("BR-proxy-v1","MR-proxy-v1","CTRL-v1")
ADVANCED=("TP-v3","BR-v3","MR-v3","LS-v3","FB-v3",
          "TREND-v1","VOL-v1","RANGE-v1","RSI-v1","CROSS-v1","VWAP-v1")
MIN_TRAIN=10
PREFER_TRAIN=30
MIN_TRAIN_DAYS=7
MIN_HOLDOUT=10
MIN_HOLDOUT_DAYS=3
CLIP_R=3.0
# Historical v8 closes without a frozen friction scenario remain eligible
# with a transparent, conservative extra 0.12%-of-notional roundtrip haircut.
LEGACY_EXTRA_COST_PCT=0.12

def research_R(record):
    if "stress_normalized_R" in record:
        return float(record["stress_normalized_R"])
    risk = float(record.get("research_risk_pct", 1.5))
    return float(record["normalized_R"]) - LEGACY_EXTRA_COST_PCT/risk



def stable_bucket(value, modulo):
    return int.from_bytes(hashlib.sha256(str(value).encode("utf-8")).digest()[:8],"big")%modulo


def day_of(record):
    return dt.datetime.fromisoformat(record["created_at"].replace("Z","+00:00")).date().isoformat()


def eligible(record):
    try:
        return (record["status"]=="CLOSED"
                and record["market_type"]=="perpetual"
                and not record.get("late_excluded",True)
                and record.get("strategy") in BASELINES+ADVANCED
                and math.isfinite(float(record["normalized_R"]))
                and record["horizon_hours"] in (1,2,4,8,12,24))
    except (ValueError,KeyError,TypeError):
        return False


def daily_lcb(rows):
    """Day-level *means*, rather than falsely independent correlated trades."""
    by_day=defaultdict(list)
    for r in rows:
        by_day[day_of(r)].append(max(-CLIP_R,min(CLIP_R,research_R(r))))
    arr=[mean(v) for v in by_day.values()]
    if len(arr)<4:
        return None
    # Conservative descriptive lower confidence bound; not a formal alpha test.
    return round(mean(arr)-1.96*stdev(arr)/math.sqrt(len(arr)),6)


def analysis(records):
    """Summarize ONLY past eligible CLOSE records; frozen 20% day holdout."""
    if isinstance(records,dict):
        records=records.values()
    groups=defaultdict(list)
    all_eligible=[]
    for r in records:
        if eligible(r):
            all_eligible.append(r)
            groups[r["strategy"]].append(r)
    summary={}
    for arm in BASELINES+ADVANCED:
        rows=groups[arm]
        train=[r for r in rows if stable_bucket("holdout:"+day_of(r),5)!=0]
        test=[r for r in rows if stable_bucket("holdout:"+day_of(r),5)==0]
        train_days=len({day_of(r) for r in train})
        test_days=len({day_of(r) for r in test})
        t_lcb=daily_lcb(train)
        h_lcb=daily_lcb(test)
        train_net=round(sum(research_R(r) for r in train),5)
        test_net=round(sum(research_R(r) for r in test),5)
        # Never promote based on cherry-picked training results alone.
        controls=groups["CTRL-v1"]
        control_train=[r for r in controls if stable_bucket("holdout:"+day_of(r),5)!=0]
        baseline_ready=len(control_train)>=MIN_TRAIN
        ctrl_avg=(mean([research_R(r) for r in control_train])
                  if baseline_ready else None)
        arm_train_avg=(mean([research_R(r) for r in train]) if train else None)
        beats_control=(baseline_ready and arm_train_avg is not None
                       and arm_train_avg>ctrl_avg)
        nominated=(arm!="CTRL-v1" and
                   len(train)>=PREFER_TRAIN and train_days>=MIN_TRAIN_DAYS and
                   len(test)>=MIN_HOLDOUT and test_days>=MIN_HOLDOUT_DAYS and
                   t_lcb is not None and t_lcb>0 and
                   h_lcb is not None and h_lcb>0 and
                   test_net>0 and beats_control)
        preliminary=(len(train)>=MIN_TRAIN and train_days>=4 and
                     t_lcb is not None and t_lcb>0)
        summary[arm]={
            "n":len(rows),"train_n":len(train),"holdout_n":len(test),
            "train_days":train_days,"holdout_days":test_days,
            "train_net_R":train_net,"holdout_net_R":test_net,
            "train_cluster_lcb_R":t_lcb,
            "holdout_cluster_lcb_R":h_lcb,
            "beats_control_train":bool(beats_control),
            "stage":("candidate_for_validation" if nominated else
                     "preliminary_explore" if preliminary else "collect"),
            "preferential":bool(nominated),
        }
    candidates=[k for k,v in summary.items() if v["preferential"]]
    candidates.sort(key=lambda name:(-(summary[name]["holdout_cluster_lcb_R"] or 0),
                                     -(summary[name]["train_cluster_lcb_R"] or 0),name))
    return {
        "method":"v2; entry-spread/impact stress R with conservative legacy haircut; 20% calendar-day monitoring and clustered daily lower bound",
        "eligible_closed":len(all_eligible),
        "eligible_days":len({day_of(r) for r in all_eligible}),
        "arms":summary,
        "provisional_leaders":candidates,
        "champion":candidates[0] if candidates else None,
        "warning":("No strategy has demonstrated a reliable tradable edge. "
                   "Selection is observational, multi-tested and correlated.")
    }


def choose(options,records,symbol,horizon,slot,rank):
    """Pick a pre-registered eligible arm, preserving controls and exploration.

    Cannot choose an advanced signal unless it is explicitly in options
    following confirmed OHLCV validation by signals.py.
    """
    if not options:
        return None
    available={o["strategy"]:o for o in options}
    if len(available)!=len(options):
        raise ValueError("duplicate strategy candidates")
    bucket=stable_bucket("allocation:%s:%s:%s:%s"%(symbol,horizon,slot,rank),100)
    # Minimum 20% control where CTRL is offered; independent of performance.
    if bucket<20 and "CTRL-v1" in available:
        return available["CTRL-v1"],"control_exploration"
    advanced=[s for s in ADVANCED if s in available]
    baselines=[s for s in BASELINES[:2] if s in available]
    # Commit to exploring advanced rules only if OHLCV actually confirms them.
    if bucket<60 and advanced:
        pick=advanced[stable_bucket("advanced:%s:%s"%(symbol,slot),len(advanced))]
        return available[pick],"confirmed_signal_exploration"
    if bucket<75 and baselines:
        pick=baselines[stable_bucket("baseline:%s:%s"%(symbol,slot),len(baselines))]
        return available[pick],"baseline_exploration"
    # Learning/preservation: only reproducible, held-out and control-aware
    # candidates receive extra allocation. All other arms keep their slots.
    profile=analysis(records)
    leaders=[s for s in profile["provisional_leaders"] if s in available]
    if leaders and bucket>=75:
        best=leaders[0]
        return available[best],"provisional_leader_allocation"
    # Deterministic balanced exploration, including baselines and signals.
    ordered=sorted(available)
    pick=ordered[stable_bucket("explore:%s:%s:%s"%(symbol,horizon,slot),len(ordered))]
    return available[pick],"balanced_exploration"
