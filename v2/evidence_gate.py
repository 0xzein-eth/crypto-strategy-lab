"""Read-only, explicitly exploratory shared-day multiple-hypothesis evidence gate.

26 registered arms, 4h true-forward book snapshots, one data-peeking
surface: BOTH multiple comparisons and common UTC-day clusters matter.
Use deterministic *shared-day* null sign flips and max-statistic FWER
to guard naive best-arm searching; this is a descriptive sensitivity
test, NOT a calibrated strategy promotion or an untouched OOS trial.

NO trading, no automatic capital reallocations, no false funding fills.
"""
import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, stdev

from v2.shadow_research import ARMS, VERSION as SHADOW_VERSION

VERSION="v2-shared-day-maxT-exploratory-v1"
MIN_ENTRY_DAYS=20
MIN_ISO_WEEKS=4
MIN_VALID_MATCHES=100
EXTRA_COST_STRESS_BPS=30
PERMUTATIONS=2048
CLIP_PCT=3.0
UTC=dt.timezone.utc


def iso(value):
    if isinstance(value,str):
        value=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    if not isinstance(value,dt.datetime) or value.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: aware timestamp required")
    return value.astimezone(UTC)


def _stat(means):
    if len(means)<MIN_ENTRY_DAYS:
        return 0.0
    avg=mean(means)
    if avg<=0:
        return 0.0
    scatter=stdev(means)
    return min(1000.0,avg*math.sqrt(len(means))/scatter) if scatter>0 else 1000.0


def deterministic_sign(day,permutation):
    """Same UTC day gets SAME sign across all assets and strategies."""
    b=hashlib.sha256(
        ("v2-frozen-maxT-null-v1|"+str(permutation)+"|"+day).encode()).digest()
    return 1 if b[0]%2 else -1


def evaluate(source, *, asof=None, permutations=PERMUTATIONS):
    if source.get("version")!=SHADOW_VERSION or source.get("catalog_arms")!=list(ARMS):
        raise ValueError("INTEGRITY_FAILURE: unexpected/future shadow research catalog")
    if not isinstance(permutations,int) or not 200<=permutations<=4096:
        raise ValueError("invalid bounded test budget")
    cutoff=iso(asof) if asof is not None else None
    outcomes=source.get("closed_outcomes")
    if not isinstance(outcomes,list):
        raise ValueError("INTEGRITY_FAILURE: missing raw shadow outcomes")
    seen=set()
    cohorts=defaultdict(list)
    candidate_count=defaultdict(int)
    ignored_asof=0
    for row in outcomes:
        if not isinstance(row,dict) or row.get("arm") not in ARMS:
            raise ValueError("INTEGRITY_FAILURE: unregistered arm")
        key=row.get("entry_id")
        if not isinstance(key,str) or not key or key in seen:
            raise ValueError("INTEGRITY_FAILURE: duplicate/missing entry identity")
        seen.add(key)
        entry=iso(row["entry_at"])
        exit_time=iso(row["genuine_exit_book_at"])
        if exit_time<=entry:
            raise ValueError("CLOCK_INTEGRITY: exit before true entry")
        if cutoff and exit_time>cutoff:
            ignored_asof+=1
            continue
        if not row.get("timely") or not row.get("executable_topbook_quantity_both_sides"):
            continue
        if row.get("funding_observed_complete") is not False or row.get("real_exchange_fill") is not False:
            raise ValueError("INTEGRITY_FAILURE: unknown funding or real fill mislabelled")
        if entry.date().isoformat()!=row.get("entry_day"):
            raise ValueError("INTEGRITY_FAILURE: inconsistent entry UTC day")
        signal=float(row["assumed_stressed_net_pct"])
        neutral=float(row["same_time_neutral_stressed_net_pct"])
        delta=float(row["delta_stress_pct"])
        if any(not math.isfinite(x) for x in (signal,neutral,delta)):
            raise ValueError("DATA_INVALID: NaN or infinite return")
        if abs((signal-neutral)-delta)>0.000001:
            raise ValueError("INTEGRITY_FAILURE: counterpart mismatch")
        candidate_count[row["arm"]]+=1
        cohorts[row["arm"]].append(row)
    by_days={}
    raw_scores={}
    study={}
    for arm in ARMS:
        rows=cohorts[arm]
        day_delta=defaultdict(list)
        day_net=defaultdict(list)
        symbols=defaultdict(int)
        for row in rows:
            day=row["entry_day"]
            day_delta[day].append(max(-CLIP_PCT,min(CLIP_PCT,row["delta_stress_pct"])))
            day_net[day].append(max(-CLIP_PCT,min(CLIP_PCT,row["assumed_stressed_net_pct"])))
            symbols[row["symbol"]]+=1
        per_day={d:mean(z) for d,z in sorted(day_delta.items())}
        independent_days=len(per_day)
        weeks=len({dt.date.fromisoformat(d).isocalendar()[:2] for d in per_day})
        net_days=[mean(day_net[d]) for d in sorted(day_net)]
        delta_days=list(per_day.values())
        by_days[arm]=per_day
        candidate_ready=(len(rows)>=MIN_VALID_MATCHES and
                         independent_days>=MIN_ENTRY_DAYS and weeks>=MIN_ISO_WEEKS)
        raw_scores[arm]=_stat(delta_days) if candidate_ready else 0
        study[arm]={
            "timely_depth_matched_closed":len(rows),
            "distinct_utc_entry_days":independent_days,
            "distinct_iso_weeks":weeks,
            "hypotheses_counted_at_first_real_entry":candidate_count[arm],
            "net_stress_mean_pct_trades":round(mean(
                r["assumed_stressed_net_pct"] for r in rows),7) if rows else None,
            "neutral_stress_mean_pct_trades":round(mean(
                r["same_time_neutral_stressed_net_pct"] for r in rows),7) if rows else None,
            "paired_day_equal_weight_mean_pct":round(mean(delta_days),7) if delta_days else None,
            "absolute_stress_day_equal_weight_mean_pct":round(mean(net_days),7) if net_days else None,
            "largest_symbol_share":round(max(symbols.values())/len(rows),5) if rows else None,
            "sufficient_exploratory_calendar_sample":candidate_ready,
            "positive_day_level_statistic":round(raw_scores[arm],6),
            "shared_day_maxT_adjusted_p_exploratory":None,
            "positive_absolute_stressed_mean_required":mean(net_days)>0 if net_days else False,
            "funding_and_market_impact_fully_modeled":False,
            "untouched_final_validation":False,
            "eligible_for_live_or_auto_promotion":False,
        }
    # Shared UTC-day null flips preserve cross-arm dependence on global
    # BTC/liquidity regimes. A max statistic adjusts the 26-arm family.
    # Fixed deterministic hash avoids randomised leaderboard re-runs.
    hypotheses=[arm for arm in ARMS if study[arm]["sufficient_exploratory_calendar_sample"]]
    maxima=[]
    if hypotheses:
        for ix in range(permutations):
            scores=[
                _stat([m*deterministic_sign(day,ix)
                       for day,m in by_days[arm].items()])
                for arm in hypotheses]
            maxima.append(max(scores))
        for arm in hypotheses:
            val=raw_scores[arm]
            study[arm]["shared_day_maxT_adjusted_p_exploratory"]=round(
                (1+sum(t>=val-1e-12 for t in maxima))/(permutations+1),6)
    counted=sum(candidate_count.values())
    return {
        "version":VERSION,"source_study_version":SHADOW_VERSION,
        "source_hash_sha256":source.get("last_source_hash"),
        "source_observation_events":source.get("source_observation_events"),
        "asof_utc":cutoff.isoformat() if cutoff else None,
        "excluded_closed_outcomes_after_asof":ignored_asof,
        "frozen_familywise_hypotheses":len(ARMS),
        "bonferroni_not_used_shared_day_maxT_used":True,
        "fixed_permutation_budget":permutations,
        "common_utc_day_null_flips":True,
        "absolute_positive_after_fee_spread_30bps_stress_required":True,
        "funding_unknown_blocks_deployment":True,
        "all_arm_frozen_same_venue_reference":True,
        "continually_inspected_descriptive_significance_not_valid_deployment_proof":True,
        "trial_count_is_not_independent_days":True,
        "no_untouched_future_validation_period_has_completed":True,
        "real_orders_enabled":False,
        "promoted_strategies":[],
        "arms":study,
        "next_prerequisite":"LOCK future chronological protocol before independent final trial, including executable funding/impact and cash-constrained alpha confidence after familywise correction",
    }


def main():
    p=argparse.ArgumentParser(description="Pre-registered descriptive familywise control study")
    p.add_argument("--source",default="v2_state/shadow_report.json")
    p.add_argument("--output",default=None)
    p.add_argument("--asof",default=None)
    args=p.parse_args()
    path=Path(args.source)
    if not path.is_file():
        status={
            "version":VERSION,"status":"NO_VERIFIED_SHADOW_SOURCE",
            "source":str(path),
            "real_orders_enabled":False,"promoted_strategies":[],
            "future_data_maturity_required":True,
        }
    else:
        status=evaluate(json.loads(path.read_text(encoding="utf-8")),asof=args.asof)
    payload=json.dumps(status,indent=2,sort_keys=True,allow_nan=False)+"\n"
    if args.output:
        out=Path(args.output)
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(payload,encoding="utf-8")
    else:
        print(payload)


if __name__=="__main__":
    main()
