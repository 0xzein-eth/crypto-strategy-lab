"""Frozen checkpoint triage and bounded research allocation, never orders."""
from collections import defaultdict
import datetime as dt
import hashlib
import math
from statistics import mean, stdev

from adaptive_lab.registry import catalog

DAY_MS=86400000
BLOCK_MS=14*DAY_MS
EMBARGO_MS=DAY_MS
MIN_TOTAL=100
MIN_DAYS=20
MIN_WEEKS=4
MIN_BLOCK_PAIRS=30
MIN_BLOCK_DAYS=10
LOW_REVIEW_MS=28*DAY_MS
ALPHA=.05
BUDGET=32
EXPLORATION=8
CADENCE={"HIGH":1,"MEDIUM":4,"LOW":16,"WARMUP":2}
WEIGHT={"HIGH":12,"MEDIUM":4,"LOW":1,"WARMUP":2}


def utc_day(ms):
    return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).date()


def interval(values):
    if len(values)<2:return None
    error=1.96*stdev(values)/math.sqrt(len(values))
    return [mean(values)-error,mean(values)+error]


def sign_p(values):
    """One-sided exact day-sign tail; assumptions are explicit in the plan."""
    signs=[v for v in values if v!=0]
    n=len(signs)
    if not n:return 1.0
    wins=sum(v>0 for v in signs)
    return sum(math.comb(n,k) for k in range(wins,n+1))/2**n


def holm(pvalues):
    adjusted={}
    maximum=0.0
    ordered=sorted(pvalues,key=lambda key:(pvalues[key],key))
    for i,key in enumerate(ordered):
        maximum=max(maximum,min(1.0,pvalues[key]*(len(ordered)-i)))
        adjusted[key]=maximum
    return adjusted


def block_stats(rows):
    daily=defaultdict(list)
    delta=defaultdict(list)
    for row in rows:
        day=utc_day(row["entry_ms"])
        daily[day].append(row["stress_pct"])
        delta[day].append(row["delta_pct"])
    net_days=[mean(daily[day]) for day in sorted(daily)]
    delta_days=[mean(delta[day]) for day in sorted(delta)]
    return {"pairs":len(rows),"entry_days":len(daily),
            "symbols":len({r["symbol"] for r in rows}),
            "mean_day_net_stress_pct":mean(net_days) if net_days else None,
            "mean_day_delta_pct":mean(delta_days) if delta_days else None,
            "day_net_interval":interval(net_days),
            "day_delta_interval":interval(delta_days),
            "day_sign_p":sign_p(delta_days),
            "valid":len(rows)>=MIN_BLOCK_PAIRS and len(daily)>=MIN_BLOCK_DAYS and
                    len({r["symbol"] for r in rows})>=2}


def classify(outcomes,*,epoch_ms,checkpoint,previous=None):
    if isinstance(checkpoint,bool) or not isinstance(checkpoint,int) or checkpoint<1:
        raise ValueError("invalid completed checkpoint")
    previous=previous or {}
    cutoff=epoch_ms+checkpoint*BLOCK_MS
    groups=defaultdict(list)
    ids=set()
    for row in outcomes:
        if row["id"] in ids:raise ValueError("duplicate outcome")
        ids.add(row["id"])
        if row["lane"]!="EXPLORATION" or not row["eligible"] or row["exit_ms"]>cutoff:
            continue
        if not all(isinstance(row[k],(float,int)) and not isinstance(row[k],bool) and
                   math.isfinite(row[k]) for k in ("stress_pct","delta_pct")):
            raise ValueError("nonfinite research outcome")
        block=(row["entry_ms"]-epoch_ms)//BLOCK_MS
        if not 0<=block<checkpoint:continue
        end=epoch_ms+(block+1)*BLOCK_MS
        if row["entry_ms"]>=end-EMBARGO_MS or row["exit_ms"]>end:continue
        groups[row["strategy"]].append(row)
    hypotheses=catalog()
    details={}
    pvalues={}
    for hypothesis in hypotheses:
        ident=hypothesis.id
        rows=groups[ident]
        recent=[r for r in rows if r["entry_ms"]>=cutoff-3*BLOCK_MS]
        blocks=[]
        for block in range(max(0,checkpoint-5),checkpoint):
            start=epoch_ms+block*BLOCK_MS
            blocks.append({"block":block+1,**block_stats(
                [r for r in rows if start<=r["entry_ms"]<start+BLOCK_MS])})
        days={utc_day(r["entry_ms"]) for r in recent}
        enough=(len(recent)>=MIN_TOTAL and len(days)>=MIN_DAYS and
                len({d.isocalendar()[:2] for d in days})>=MIN_WEEKS and
                len(blocks)>=3 and all(b["valid"] for b in blocks[-3:]))
        stats=block_stats(recent)
        pvalues[ident]=stats["day_sign_p"] if enough else 1.0
        details[ident]={"blocks":blocks,"enough":enough,"stats":stats}
    adjusted=holm(pvalues)
    threshold=ALPHA/(checkpoint*(checkpoint+1))
    result={}
    for hypothesis in hypotheses:
        ident=hypothesis.id
        d=details[ident]
        blocks=d["blocks"]
        recent=blocks[-3:]
        stats=d["stats"]
        positive=lambda b:b["valid"] and b["mean_day_net_stress_pct"]>0 and b["mean_day_delta_pct"]>0
        positive_streak=0
        for block in reversed(blocks):
            if not positive(block):break
            positive_streak+=1
        high=(d["enough"] and all(positive(b) for b in recent) and
              stats["day_net_interval"] is not None and stats["day_net_interval"][0]>0 and
              stats["day_delta_interval"] is not None and stats["day_delta_interval"][0]>0 and
              adjusted[ident]<=threshold)
        low=d["enough"] and all(b["mean_day_net_stress_pct"]<0 for b in recent)
        tier="WARMUP" if not d["enough"] else "HIGH" if high else "LOW" if low else "MEDIUM"
        old=previous.get(ident,{})
        low_since=(old.get("low_since_ms") if old.get("tier")=="LOW" else cutoff) if tier=="LOW" else None
        result[ident]={"tier":tier,"checkpoint":checkpoint,
            "eligible_exploration_pairs_last_three_blocks":stats["pairs"],
            "blocks":blocks,"stats":stats,"holm_day_sign_p":adjusted[ident],
            "checkpoint_alpha":threshold,"positive_block_streak":positive_streak,
            "low_since_ms":low_since,
            "needs_redevelopment":low_since is not None and cutoff-low_since>=LOW_REVIEW_MS,
            "candidate_for_human_review":tier=="HIGH" and positive_streak>=5,
            "live_orders_authorized":False}
    return result


def priority(candidate,slot,weight=1):
    raw=f"adaptive-v1:{slot}:{candidate['strategy']}:{candidate['symbol']}"
    unit=(int.from_bytes(hashlib.sha256(raw.encode()).digest()[:8],"big")+1)/(2**64+1)
    return -math.log(unit)/weight


def select(candidates,tiers,*,slot):
    """Uniform lane is independent of tier. Priority lane increases effort."""
    unique={(c["strategy"],c["symbol"]):c for c in candidates}
    if len(unique)!=len(candidates):raise ValueError("duplicate candidate")
    selected=[]
    families=defaultdict(int)
    symbols=defaultdict(int)
    def admit(rows,limit,lane):
        count=0
        for row in rows:
            if any((x["strategy"],x["symbol"])==(row["strategy"],row["symbol"]) for x in selected):continue
            if families[row["family"]]>=8 or symbols[row["symbol"]]>=8:continue
            selected.append({**row,"lane":lane})
            families[row["family"]]+=1
            symbols[row["symbol"]]+=1
            count+=1
            if count>=limit:break
    admit(sorted((c for c in candidates if c.get("exploration_available",True)),
                 key=lambda c:priority(c,slot)),EXPLORATION,"EXPLORATION")
    available=[]
    for row in candidates:
        tier=tiers.get(row["strategy"],{}).get("tier","WARMUP")
        if row.get("priority_available",True) and slot%CADENCE[tier]==0:available.append(row)
    admit(sorted(available,key=lambda c:priority(c,slot,
        WEIGHT[tiers.get(c["strategy"],{}).get("tier","WARMUP")])),BUDGET-EXPLORATION,"PRIORITY")
    return selected
