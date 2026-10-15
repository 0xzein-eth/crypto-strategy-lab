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
          "TREND-v1","VOL-v1","RANGE-v1","RSI-v1","CROSS-v1","VWAP-v1",
          "DC-v1","RSITREND-v1","ATRCHAN-v1",
          "COMPBR-v1","IMPULSE-v1","TRECLAIM-v1")
MIN_TRAIN=10
PREFER_TRAIN=30
MIN_TRAIN_DAYS=7
MIN_HOLDOUT=10
MIN_HOLDOUT_DAYS=3
CLIP_R=3.0
# Only a sufficiently large multi-day TRAINING partition, with a negative
# day-cluster upper confidence bound and worse outcome than the matched
# control, can reduce exploratory sampling. Never stop control or shut off
# an unfavored arm: positive later regimes must remain observable.
REDUCE_TRAIN_N=50
REDUCE_TRAIN_DAYS=7
REDUCE_UCB_R=-0.05
REDUCE_WORSE_THAN_CONTROL_R=0.05
NORMAL_EXPLORATION_WEIGHT=4
REDUCED_EXPLORATION_WEIGHT=1
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


def _daily_interval(rows):
    """Clipped daily mean +/- 1.96 SE, descriptive not a formal alpha test."""
    by_day=defaultdict(list)
    for r in rows:
        by_day[day_of(r)].append(max(-CLIP_R,min(CLIP_R,research_R(r))))
    arr=[mean(v) for _,v in sorted(by_day.items())]
    if len(arr)<4:
        return None, None
    center=mean(arr)
    margin=1.96*stdev(arr)/math.sqrt(len(arr))
    return round(center-margin,6), round(center+margin,6)


def daily_lcb(rows):
    """Day-level lower bound; many correlated trades are not independent."""
    return _daily_interval(rows)[0]


def weighted_exploration(names, underperformers, key):
    """Never exclude an arm. Less-promising TRAIN-only arms retain 1/4 weight."""
    if not names:
        return None
    slots=[]
    for name in sorted(names):
        slots.extend([name] * (REDUCED_EXPLORATION_WEIGHT
                     if name in underperformers else NORMAL_EXPLORATION_WEIGHT))
    return slots[stable_bucket(key,len(slots))]


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
        t_lcb,t_ucb=_daily_interval(train)
        h_lcb=daily_lcb(test)
        train_net=round(sum(research_R(r) for r in train),5)
        test_net=round(sum(research_R(r) for r in test),5)
        # Never promote based on cherry-picked training results alone.
        controls=groups["CTRL-v1"]
        control_train=[r for r in controls if stable_bucket("holdout:"+day_of(r),5)!=0]
        baseline_ready=(len(control_train)>=MIN_TRAIN and
                        len({day_of(r) for r in control_train})>=MIN_TRAIN_DAYS)
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
        # Forward allocation MUST NOT consult the monitoring partition.
        # Monitoring-based nominations are reporting diagnostics only, never
        # inputs to choose(). This prevents holdout feedback leakage.
        train_only_ready=(arm!="CTRL-v1" and
                          len(train)>=PREFER_TRAIN and
                          train_days>=MIN_TRAIN_DAYS and
                          train_net>0 and t_lcb is not None and t_lcb>0 and
                          beats_control)
        preliminary=(len(train)>=MIN_TRAIN and train_days>=4 and
                     t_lcb is not None and t_lcb>0)
        persistently_underperforming=(
            arm!="CTRL-v1" and len(train)>=REDUCE_TRAIN_N and
            train_days>=REDUCE_TRAIN_DAYS and baseline_ready and
            t_ucb is not None and t_ucb<REDUCE_UCB_R and
            arm_train_avg is not None and
            arm_train_avg < ctrl_avg-REDUCE_WORSE_THAN_CONTROL_R)
        summary[arm]={
            "n":len(rows),"train_n":len(train),"holdout_n":len(test),
            "train_days":train_days,"holdout_days":test_days,
            "train_net_R":train_net,"holdout_net_R":test_net,
            "train_cluster_lcb_R":t_lcb,
            "train_cluster_ucb_R":t_ucb,
            "holdout_cluster_lcb_R":h_lcb,
            "underperformer_train_only":bool(persistently_underperforming),
            "beats_control_train":bool(beats_control),
            "stage":("candidate_for_validation" if nominated else
                     "preliminary_explore" if preliminary else "collect"),
            "preferential":bool(nominated),
            "allocation_train_only":bool(train_only_ready),
        }
    reduced=[name for name,stats in summary.items()
             if stats["underperformer_train_only"]]
    allocation_candidates=[name for name,stats in summary.items()
                           if stats["allocation_train_only"] and name not in reduced]
    allocation_candidates.sort(
        key=lambda name: (-(summary[name]["train_cluster_lcb_R"] or 0),name))
    candidates=[k for k,v in summary.items() if v["preferential"]]
    candidates.sort(key=lambda name:(-(summary[name]["holdout_cluster_lcb_R"] or 0),
                                     -(summary[name]["train_cluster_lcb_R"] or 0),name))
    return {
        "method":"v4-"+hashlib.sha256("|".join(BASELINES+ADVANCED).encode()).hexdigest()[:8]+
                   "; training-only allocation; 20% day monitoring withheld from selection; clustered daily lower bound",
        "eligible_closed":len(all_eligible),
        "eligible_days":len({day_of(r) for r in all_eligible}),
        "arms":summary,
        "provisional_leaders":candidates,
        "allocation_leaders":allocation_candidates,
        "training_only_underperformers":sorted(reduced),
        "underperformer_policy":(
            ">=50 eligible training closes and >=7 training UTC days, "
            "clipped daily upper bound < -0.05R, training mean >0.05R "
            "worse than CTRL; only 4:1 exploration reweight, never disable; "
            "monitoring outcomes excluded"),
        "champion":None,  # Descriptive candidates do not meet independent promotion criteria.
        "warning":("No strategy has demonstrated a reliable tradable edge. "
                   "Training-only allocations never access monitoring results. "
                   "Historical monitoring was previously used for allocations, "
                   "so it is not an untouched final holdout. "
                   "Selection remains observational, multi-tested and correlated.")
    }


def choose(options,records,symbol,horizon,slot,rank,profile=None):
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
    # Performance-neutral prospective experimentation: neither preliminary
    # training rankings nor repeated-look monitoring, provisional leaders, or
    # underperformer tags change arm weights before strict qualification.
    # The separately published analysis remains descriptive/read-only.
    if bucket<75 and advanced:
        pick=weighted_exploration(advanced,set(),
                                  "advanced:%s:%s:%s:%s"%(symbol,horizon,slot,rank))
        return available[pick],"confirmed_signal_neutral_exploration"
    if bucket<90 and baselines:
        pick=weighted_exploration(baselines,set(),
                                  "baseline:%s:%s:%s:%s"%(symbol,horizon,slot,rank))
        return available[pick],"baseline_neutral_exploration"
    pick=weighted_exploration(available,set(),
                              "neutral:%s:%s:%s:%s"%(symbol,horizon,slot,rank))
    return available[pick],"balanced_neutral_exploration"
