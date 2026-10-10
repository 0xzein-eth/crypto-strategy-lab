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
    timely=sum(r.get("late_excluded") is False for r in closed)
    eligible=[r for r in closed if r.get("late_excluded") is False
              and r["market_type"]=="perpetual"]
    eligible_dates={_utc(r["created_at"]).date().isoformat()
                    for r in eligible if r.get("created_at")}
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
        "late_share_of_closed":round((len(closed)-timely)/len(closed),4) if closed else None,
        "eligible_timely_perpetual_closed":len(eligible),
        "eligible_distinct_entry_utc_days":len(eligible_dates),
        "eligible_day_breadth_ready":len(eligible_dates)>=7,
        "eligible_timely_perpetual_share":round(len(eligible)/len(closed),4) if closed else None,
        "eligible_timely_perpetual_win_rate":round(
            sum(r["net_pnl_usd"]>0 for r in eligible)/len(eligible),4) if eligible else None,
        "eligible_timely_perpetual_net_R":round(sum(r["normalized_R"] for r in eligible),5),
        "eligible_timely_perpetual_expectancy_R":round(
            sum(r["normalized_R"] for r in eligible)/len(eligible),5) if eligible else None,
    }


def summarize(records, moment):
    """Group OPEN and CLOSED full individual records without double counting."""
    rows=list(records.values()) if isinstance(records,dict) else list(records)
    groups={"side":defaultdict(list),"horizon_hours":defaultdict(list),
            "strategy":defaultdict(list),"symbol":defaultdict(list),
            "market_type":defaultdict(list),
            "entry_regime":defaultdict(list),
            "entry_utc_daypart":defaultdict(list)}
    for r in rows:
        for dimension in ("side","horizon_hours","strategy","symbol","market_type"):
            groups[dimension][str(r[dimension])].append(r)
        # Pre-recorded regime at OPEN: NEVER label from future outcomes.
        groups["entry_regime"][str(r.get("regime") or "unknown")].append(r)
        # Coarse UTC hour bins expose missing scheduled observations.
        if r.get("created_at"):
            hour = _utc(r["created_at"]).hour
            daypart = ("00-05 UTC" if hour<6 else "06-11 UTC" if hour<12
                       else "12-17 UTC" if hour<18 else "18-23 UTC")
        else:
            daypart="unknown"
        groups["entry_utc_daypart"][daypart].append(r)
    due=[r for r in rows if r["status"]=="OPEN" and _utc(r["evaluate_at"])<=moment]
    next_60=[r for r in rows if r["status"]=="OPEN" and
             moment<_utc(r["evaluate_at"])<=moment+dt.timedelta(hours=1)]
    next_24=[r for r in rows if r["status"]=="OPEN" and
             moment<_utc(r["evaluate_at"])<=moment+dt.timedelta(hours=24)]
    completed=[r for r in rows if r["status"]=="CLOSED"]
    return {
        "method":"fixed_horizon_v3",
        "exit_policy":"first fresh same-venue observed ticker at/after due time; NO stop-loss or take-profit",
        "side":{k:_cohort(v) for k,v in sorted(groups["side"].items())},
        "horizon_hours":{k:_cohort(v) for k,v in sorted(groups["horizon_hours"].items(),key=lambda x:int(x[0]))},
        "strategy":{k:_cohort(v) for k,v in sorted(groups["strategy"].items())},
        "symbol":{k:_cohort(v) for k,v in sorted(groups["symbol"].items())},
        "market_type":{k:_cohort(v) for k,v in sorted(groups["market_type"].items())},
        "entry_regime":{k:_cohort(v) for k,v in sorted(groups["entry_regime"].items())},
        "entry_utc_daypart":{k:_cohort(v) for k,v in sorted(groups["entry_utc_daypart"].items())},
        "selection_note":"Regime/daypart labels frozen at entry, descriptive and correlated. " +
                         "Group-level seven-day breadth is only a MINIMUM collection check, not proof of edge.",
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
