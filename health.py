"""Read-only liveness and integrity watchdog for unattended PAPER research."""
import argparse
import datetime as dt
import json
from pathlib import Path
import audit
import engine

ROOT=Path(__file__).resolve().parent
MAX_STALENESS_HOURS=3


def check(root=ROOT, moment=None, max_hours=MAX_STALENESS_HOURS):
    now=moment or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone required")
    if not 0 < max_hours <= 72:
        raise ValueError("max_hours must be between 0 and 72")
    info=audit.verify(root)
    r=json.loads((root/"data"/"report.json").read_text(encoding="utf-8"))
    last=engine.parse(r["timestamp"])
    age=(now-last).total_seconds()/3600
    if age < -5/60:
        raise RuntimeError("CLOCK_INTEGRITY: last report is unexpectedly in the future")
    if age > max_hours:
        raise RuntimeError("STALE_RUN: latest committed market report age %.2f hours; threshold %.2f" %
                           (age,max_hours))
    if r.get("provider_observations",0)<1:
        raise RuntimeError("DATA_UNAVAILABLE: no live market observations reported")
    closed = int(r.get("closed", 0))
    late = int(r.get("late_closures", 0))
    if closed < 0 or late < 0 or late > closed:
        raise RuntimeError("INTEGRITY_FAILURE: invalid close/late diagnostics")
    eligible = r.get("eligible_perpetual_timely", {})
    scheduling = r.get("scheduling_diagnostics", {})
    return dict(info, report_age_hours=round(age,3), health="OK",
                paper_closed=closed, paper_late=late,
                paper_timely_share=round((closed-late)/closed,4) if closed else None,
                eligible_perpetual_timely_n=eligible.get("n"),
                last_gap_minutes=scheduling.get("prior_observation_gap_minutes"),
                last_run_throttled=bool(scheduling.get("recovery_throttled",False)),
                recent_observed_intervals=scheduling.get("recent_observed_intervals"),
                estimated_missed_10m_slots=scheduling.get("estimated_missed_10m_slots"),
                estimated_10m_slot_coverage=scheduling.get("estimated_10m_slot_coverage"),
                schedule_quality=("INSUFFICIENT_SAMPLE"
                                  if (scheduling.get("recent_observed_intervals") or 0) < 12
                                  else ("BELOW_TARGET"
                                        if (scheduling.get("estimated_10m_slot_coverage") or 0) < 0.8
                                        else "ON_TARGET")))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-hours",type=float,default=MAX_STALENESS_HOURS)
    args=parser.parse_args()
    print(json.dumps(check(max_hours=args.max_hours),indent=2))
