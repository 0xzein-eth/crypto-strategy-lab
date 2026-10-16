"""Read-only temporal maturity of genuine prospective paper evidence.

Measures distinct UTC entry days and weeks, daily concentration and frozen
market breadth. Does not claim correlated assets/trades become iid samples.
No backfilling, promotion decisions or paper OPEN/CLOSE writes.
"""
from collections import defaultdict
import datetime as dt
from math import isfinite

import learner


MIN_MATURE_DAYS = 20
MIN_MATURE_WEEKS = 4
MIN_WEEKDAY_BREADTH = 5
MIN_BIDIRECTIONAL_DAYS = 10
MIN_FULL_DAYPART_DAYS = 6


def _time(value):
    stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("INTEGRITY_FAILURE: naive entry time")
    return stamp.astimezone(dt.timezone.utc)


def _metrics(rows, today):
    by_day = defaultdict(list)
    for record in rows:
        when = _time(record["created_at"])
        if when.date() > today:
            raise ValueError("INTEGRITY_FAILURE: future eligible entry")
        by_day[when.date()].append(record)
    days = sorted(by_day)
    totals = [len(by_day[d]) for d in days]
    total = sum(totals)
    weeks = {"%04d-W%02d" % d.isocalendar()[:2] for d in days}
    weekdays = {d.weekday() for d in days}
    six_hour_bins = {0: set(), 1: set(), 2: set(), 3: set()}
    regimes = defaultdict(set)
    per_day = []
    for day in days:
        trades = by_day[day]
        bins = {(_time(r["created_at"]).hour // 6) for r in trades}
        for bucket in bins:
            six_hour_bins[bucket].add(day)
        frozen_regimes = {r.get("regime", "unknown") for r in trades}
        regimes[day].update(frozen_regimes)
        per_day.append({
            "utc_day": day.isoformat(),
            "eligible_closes": len(trades),
            "observed_utc_six_hour_bins": sorted(bins),
            "frozen_entry_regimes": sorted(frozen_regimes),
        })
    concentration = (sum(n*n for n in totals) / (total*total)
                     if total else None)
    # Effective number of equally weighted day-sized clusters: NOT an
    # inference of independent trading outcomes or an alpha sample size.
    effective = (round(1 / concentration, 2) if concentration else 0.0)
    last = days[-1] if days else None
    # Reporting boundaries must treat today's PARTIAL UTC day differently
    # from the seven most recent fully completed UTC calendar days.
    completed_days = [today - dt.timedelta(days=offset)
                      for offset in range(7,0,-1)]
    completed_missing = [day.isoformat() for day in completed_days
                         if day not in by_day]
    bidirectional_days = sum(
        {"24h_up", "24h_down"}.issubset(regimes[d]) for d in days)
    full_daypart_days = sum(
        all(day in six_hour_bins[k] for k in six_hour_bins) for day in days)
    def window(n):
        cutoff = today - dt.timedelta(days=n-1)
        selection = [r for day in days if cutoff <= day <= today
                     for r in by_day[day]]
        return {
            "calendar_window_days": n,
            "observed_entry_utc_days": len({
                _time(r["created_at"]).date() for r in selection}),
            "eligible_closes": len(selection),
        }
    return {
        "eligible_closes": total,
        "distinct_entry_utc_days": len(days),
        "distinct_iso_weeks": len(weeks),
        "distinct_weekdays": len(weekdays),
        "days_with_both_up_and_down": bidirectional_days,
        "days_covering_all_four_six_hour_bins": full_daypart_days,
        "bidirectional_regime_breadth_target_days": MIN_BIDIRECTIONAL_DAYS,
        "four_daypart_breadth_target_days": MIN_FULL_DAYPART_DAYS,
        "bidirectional_regime_breadth_ready": (
            bidirectional_days >= MIN_BIDIRECTIONAL_DAYS),
        "four_daypart_breadth_ready": (
            full_daypart_days >= MIN_FULL_DAYPART_DAYS),
        "additional_bidirectional_regime_days_needed": max(
            0,MIN_BIDIRECTIONAL_DAYS-bidirectional_days),
        "additional_four_daypart_days_needed": max(
            0,MIN_FULL_DAYPART_DAYS-full_daypart_days),
        "completed_utc_day_yesterday":completed_days[-1].isoformat(),
        "completed_utc_day_yesterday_has_eligible_close": (
            completed_days[-1] in by_day),
        "missing_eligible_entry_days_last_7_completed_utc_days":completed_missing,
        "observed_entry_days_last_7_completed_utc_days":(
            7-len(completed_missing)),
        "longest_unobserved_calendar_gap_between_entry_days":max(
            [(later-earlier).days-1 for earlier,later in zip(days,days[1:])] or [0]),
        "six_hour_bin_day_coverage": {
            "%02d-%02d_UTC" % (k*6, k*6+5): len(v)
            for k, v in six_hour_bins.items()},
        "effective_equally_weighted_day_clusters_upper_bound": effective,
        "largest_single_day_trade_share": round(max(totals)/total, 4) if total else None,
        "first_entry_utc_day": days[0].isoformat() if days else None,
        "latest_entry_utc_day": last.isoformat() if last else None,
        "calendar_span_days": (last-days[0]).days+1 if days else 0,
        "recent_7_calendar_days": window(7),
        "recent_14_calendar_days": window(14),
        "recent_30_calendar_days": window(30),
        "recent_30_observed_entry_days": per_day[-30:],
        "data_maturity_ready": (len(days) >= MIN_MATURE_DAYS
                                and len(weeks) >= MIN_MATURE_WEEKS
                                and len(weekdays) >= MIN_WEEKDAY_BREADTH),
        "additional_distinct_days_needed": max(0, MIN_MATURE_DAYS-len(days)),
        "additional_distinct_weeks_needed": max(0, MIN_MATURE_WEEKS-len(weeks)),
    }


def summarize(records, moment):
    """Read eligible CLOSED paper events; no inference from existing OPENs."""
    now = moment if moment.tzinfo is not None else None
    if now is None:
        raise ValueError("INTEGRITY_FAILURE: UTC observation clock required")
    now = now.astimezone(dt.timezone.utc)
    source = records.values() if isinstance(records, dict) else records
    eligible = [r for r in source if learner.eligible(r)]
    by_strategy = defaultdict(list)
    for r in eligible:
        by_strategy[r["strategy"]].append(r)
    return {
        "version": "prospective-entry-day-maturity-v1",
        "as_of_utc": now.isoformat(),
        "min_distinct_entry_days": MIN_MATURE_DAYS,
        "min_distinct_iso_weeks": MIN_MATURE_WEEKS,
        "min_distinct_weekdays": MIN_WEEKDAY_BREADTH,
        "minimum_bidirectional_regime_days": MIN_BIDIRECTIONAL_DAYS,
        "minimum_full_daypart_days": MIN_FULL_DAYPART_DAYS,
        "overall": _metrics(eligible, now.date()),
        "by_strategy": {arm: _metrics(rows, now.date())
                        for arm, rows in sorted(by_strategy.items())},
        "gate_kind": "observation-window-readiness-only",
        "edge_proven": False,
        "note": (
            "Only authentic eligible closed prospective paper observations. "
            "Distinct days and weeks improve temporal coverage, but correlated "
            "crypto exposures are not statistically independent. Today's "
            "partial UTC day is excluded from completed-day diagnostics. "
            "Bidirectional/daypart targets measure coverage only, not alpha. "
            "1/sum(day "
            "weight squared) describes concentration only, not an alpha "
            "effective sample size. A readiness pass never promotes an arm."),
    }
