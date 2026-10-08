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
    return dict(info, report_age_hours=round(age,3),health="OK")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--max-hours",type=float,default=MAX_STALENESS_HOURS)
    args=parser.parse_args()
    print(json.dumps(check(max_hours=args.max_hours),indent=2))
