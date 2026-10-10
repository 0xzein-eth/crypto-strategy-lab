"""Read-only liveness and integrity watchdog for unattended PAPER research."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
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


def check_guarded(root=ROOT, moment=None, max_hours=MAX_STALENESS_HOURS,
                  guardian_decision=None):
    """Do not mark stale data healthy merely because a recovery was dispatched.

    A *fresh* authenticated recovery receipt can temporarily turn an expected
    stale failure into a visible DEGRADED alert while a legitimate paper
    workflow is being started/running. No receipt, cooldown or stuck worker
    still fails closed. This is NOT a successful market observation.
    """
    now = moment or dt.datetime.now(dt.timezone.utc)
    try:
        return check(root, moment=now, max_hours=max_hours)
    except RuntimeError as exc:
        if not str(exc).startswith("STALE_RUN:"):
            raise
        decision = guardian_decision
        if not isinstance(decision, dict) or decision.get("status") not in (
                "RECOVERY_DISPATCHED", "IN_FLIGHT"):
            raise
        receipt = engine.parse(decision["inspected_at_utc"])
        receipt_age = (now - receipt).total_seconds()
        if not -30 <= receipt_age <= 300:
            raise RuntimeError("STALE_RUN: guardian receipt missing/old/future") from exc
        latest = json.loads((root / "data" / "report.json").read_text(encoding="utf-8"))
        if (engine.parse(decision["last_report_utc"]) >
                engine.parse(latest["timestamp"])):
            raise RuntimeError("CLOCK_INTEGRITY: guardian report after canonical report") from exc
        if (not isinstance(decision.get("ledger_events"), int)
                or decision["ledger_events"] > latest["verified_events"]):
            raise RuntimeError("INTEGRITY_FAILURE: guardian receipt cannot match ledger") from exc
        if decision["status"] == "IN_FLIGHT" and (
                decision.get("pending_age_minutes") is None or
                not 0 <= decision["pending_age_minutes"] <= 230):
            raise RuntimeError("STALE_RUN: invalid in-flight worker age") from exc
        # check() has already audited the complete chain before detecting stale.
        return {
            "health": "DEGRADED_RECOVERING",
            "recovery_status": decision["status"],
            "last_observation_utc": latest["timestamp"],
            "last_observation_age_hours": round(
                (now-engine.parse(latest["timestamp"])).total_seconds()/3600, 3),
            "canonical_events": latest["verified_events"],
            "market_data_fresh": False,
            "note": "Recovery attempt acknowledged, NOT verified; stale observations remain excluded",
        }


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-hours",type=float,default=MAX_STALENESS_HOURS)
    parser.add_argument("--guardian-state-file",type=Path,default=None)
    args=parser.parse_args()
    decision = (json.loads(args.guardian_state_file.read_text(encoding="utf-8"))
                if args.guardian_state_file is not None else None)
    result = check_guarded(max_hours=args.max_hours, guardian_decision=decision)
    print(json.dumps(result,indent=2))
    if result["health"] == "DEGRADED_RECOVERING":
        print("::warning::STALE_RUN: recovery pending; NO verified fresh observation yet",
              file=sys.stderr)
