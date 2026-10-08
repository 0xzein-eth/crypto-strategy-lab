"""Derived fixed-horizon paper outcome diagnostics.

Only CLOSED snapshots count as wins, losses or realized hypothetical P&L.
Never synthesize stop-loss, take-profit, liquidation or a target-time fill.
All figures are descriptive; correlated experiment notionals are NOT capital.
"""
from collections import defaultdict
import datetime as dt


def _utc(iso):
    t=dt.datetime.fromisoformat(iso.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("naive date")
    return t.astimezone(dt.timezone.utc)


def _cohort(records):
    closed=[r for r in records if r["status"]=="CLOSED"]
    wins=sum(r["net_pnl_usd"]>0 for r in closed)
    losses=sum(r["net_pnl_usd"]<0 for r in closed)
    breakeven=len(closed)-wins-losses
    timely=sum(not r.get("late_excluded",False) for r in closed)
    return {
        "opened":len(records),
        "active":sum(r["status"]=="OPEN" for r in records),
        "closed":len(closed),
        "wins":wins,"losses":losses,"breakeven":breakeven,
        "win_rate":round(wins/len(closed),4) if closed else None,
        "closed_net_usd":round(sum(r["net_pnl_usd"] for r in closed),2),
        "closed_net_R":round(sum(r["normalized_R"] for r in closed),5),
        "closed_expectancy_R":round(sum(r["normalized_R"] for r in closed)/len(closed),5) if closed else None,
        "timely_closes":timely,
        "late_closes":len(closed)-timely,
    }


def summarize(records, moment):
    """Group OPEN and CLOSED full individual records without double counting."""
    rows=list(records.values()) if isinstance(records,dict) else list(records)
    groups={"side":defaultdict(list),"horizon_hours":defaultdict(list),
            "strategy":defaultdict(list),"symbol":defaultdict(list),
            "market_type":defaultdict(list)}
    for r in rows:
        for dimension in groups:
            groups[dimension][str(r[dimension])].append(r)
    due=[r for r in rows if r["status"]=="OPEN" and _utc(r["evaluate_at"])<=moment]
    next_60=[r for r in rows if r["status"]=="OPEN" and
             moment<_utc(r["evaluate_at"])<=moment+dt.timedelta(hours=1)]
    next_24=[r for r in rows if r["status"]=="OPEN" and
             moment<_utc(r["evaluate_at"])<=moment+dt.timedelta(hours=24)]
    completed=[r for r in rows if r["status"]=="CLOSED"]
    return {
        "method":"fixed_horizon_v1",
        "exit_policy":"first fresh same-venue observed ticker at/after due time; NO stop-loss or take-profit",
        "side":{k:_cohort(v) for k,v in sorted(groups["side"].items())},
        "horizon_hours":{k:_cohort(v) for k,v in sorted(groups["horizon_hours"].items(),key=lambda x:int(x[0]))},
        "strategy":{k:_cohort(v) for k,v in sorted(groups["strategy"].items())},
        "symbol":{k:_cohort(v) for k,v in sorted(groups["symbol"].items())},
        "market_type":{k:_cohort(v) for k,v in sorted(groups["market_type"].items())},
        "due_unresolved":len(due),
        "evaluation_next_hour":len(next_60),
        "evaluation_next_24_hours":len(next_24),
        "eligible_timely_perpetual_closures":sum(
            r["market_type"]=="perpetual" and not r.get("late_excluded",False)
            for r in completed),
        "total_research_notional_usd":round(sum(r["notional_usd"] for r in rows),2),
        "simultaneous_open_research_notional_usd":round(sum(
            r["notional_usd"] for r in rows if r["status"]=="OPEN"),2),
        "exposure_note":"Sum of overlapping virtual research notionals; NOT deployable capital or portfolio equity.",
        "pnl_note":"Only fixed-horizon CLOSED outcomes, fee-adjusted; OPEN unrealized P&L deliberately excluded.",
    }
