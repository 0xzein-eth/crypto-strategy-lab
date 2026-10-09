"""Bounded GitHub-hosted recovery observations after a missed schedule.

A long scheduler gap makes a SINGLE successful GitHub cron tick insufficient
for timely-horizon research. After a real recovered paper tick is persisted,
retain the SAME serialized lab job for at most two later observations spaced
10 minutes apart. Every follow-up uses a *new current public market quote*,
is audited, and is independently committed; NO historical fill is fabricated.

Only starts on a *degraded* recent main report. No unconditional/recursive
workflow_dispatch, no external scheduler, and no real exchange orders.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time

import engine

ROOT = Path(__file__).resolve().parent
MAX_PULSES = 2
DEFAULT_INTERVAL_MINUTES = 10
MAX_INITIAL_AGE_MINUTES = 10
UTC = dt.timezone.utc


def report_at(root=ROOT):
    report = json.loads((root / "data" / "report.json").read_text(encoding="utf-8"))
    if (report.get("schema_version") != 8 or
            not isinstance(report.get("timestamp"), str)):
        raise ValueError("INTEGRITY_FAILURE: missing canonical v8 report")
    return report


def recovery_eligible(report, now=None):
    now = now or dt.datetime.now(UTC)
    diagnostics = report.get("scheduling_diagnostics") or {}
    timestamp = engine.parse(report["timestamp"])
    age = (now - timestamp).total_seconds() / 60
    if age < -5:
        raise ValueError("CLOCK_INTEGRITY: report is in future")
    return (diagnostics.get("recovery_throttled") is True and
            diagnostics.get("prior_observation_gap_minutes", 0) > 45 and
            0 <= age <= MAX_INITIAL_AGE_MINUTES)


def remaining_seconds(last_timestamp, now, interval_minutes):
    if now.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: clock lacks UTC offset")
    if not 5 <= interval_minutes <= 15:
        raise ValueError("invalid recovery cadence")
    last = engine.parse(last_timestamp)
    if (now - last).total_seconds() < -300:
        raise ValueError("CLOCK_INTEGRITY: future prior observation")
    return max(0, (last + dt.timedelta(minutes=interval_minutes) - now).total_seconds())


def run_checked(command, cwd=ROOT):
    return subprocess.run(command, cwd=cwd, check=True, text=True,
                          capture_output=True).stdout.strip()


def publish(root, runner):
    """Publish a verified new observation without force pushing canonical data."""
    runner(["python", "engine.py", "--verify-only"], root)
    runner(["python", "audit.py"], root)
    runner(["python", "health.py", "--max-hours", "1"], root)
    runner(["python", "-m", "json.tool", "data/report.json"], root)
    runner(["git", "diff", "--check"], root)
    runner(["git", "add", "-A", "data/"], root)
    if not runner(["git", "diff", "--cached", "--name-only"], root):
        raise RuntimeError("PERSISTENCE_FAILURE: no observation data to commit")
    runner(["git", "commit", "-m",
            "paper(v8): bounded recovery observation [skip ci]"], root)
    for attempt in range(3):
        try:
            runner(["git", "push", "origin", "HEAD:main"], root)
            return
        except subprocess.CalledProcessError:
            if attempt == 2:
                break
            runner(["git", "fetch", "--quiet", "origin", "main"], root)
            try:
                runner(["git", "rebase", "origin/main"], root)
            except subprocess.CalledProcessError:
                runner(["git", "rebase", "--abort"], root)
                raise RuntimeError(
                    "INTEGRITY_FAILURE: paper ledger rebase conflict; no overwrite"
                ) from None
    raise RuntimeError("PERSISTENCE_FAILURE: could not safely push observation")


def run_window(root=ROOT, pulses=MAX_PULSES, interval_minutes=DEFAULT_INTERVAL_MINUTES,
               now=None, sleeper=time.sleep, runner=run_checked):
    """Keep at most one GitHub-hosted recovery job alive for a bounded time.

    This holds the *existing* canonical paper lab concurrency lock. New
    schedule jobs may queue, but cannot concurrently write to main ledger.
    """
    if not 0 <= pulses <= MAX_PULSES:
        raise ValueError("max recovery pulses must be 0..2")
    if not 5 <= interval_minutes <= 15:
        raise ValueError("recovery cadence must be 5..15 minutes")
    current = now or (lambda: dt.datetime.now(UTC))
    initial = report_at(root)
    if not pulses or not recovery_eligible(initial, current()):
        return {"status": "SKIPPED_NO_RECOVERY", "requested_pulses": pulses,
                "completed_pulses": 0}
    if runner(["git", "status", "--porcelain"], root):
        raise RuntimeError("INTEGRITY_FAILURE: dirty checkout before recovery window")
    total = 0
    last_stamp = initial["timestamp"]
    observations = []
    for index in range(pulses):
        delay = remaining_seconds(last_stamp, current(), interval_minutes)
        if delay:
            sleeper(delay)
        if runner(["git", "status", "--porcelain"], root):
            raise RuntimeError("INTEGRITY_FAILURE: dirty checkout before next observation")
        runner(["git", "fetch", "--quiet", "origin", "main"], root)
        # Never overwrite or force a divergent main; fast-forward only.
        runner(["git", "merge", "--ff-only", "origin/main"], root)
        recent = report_at(root)
        if engine.parse(recent["timestamp"]) > engine.parse(last_stamp):
            # Another successfully committed real observation advanced main.
            # Do not submit redundant market requests or synthetic events.
            last_stamp = recent["timestamp"]
            observations.append({"pulse": index + 1, "status": "SKIPPED_NEWER_MAIN"})
            continue
        if recent["timestamp"] != last_stamp:
            raise RuntimeError("CLOCK_INTEGRITY: canonical report went backwards")
        # A fresh observed quote, not historical interpolation/backfill.
        runner(["python", "engine.py", "--count", "14"], root)
        updated = report_at(root)
        if engine.parse(updated["timestamp"]) <= engine.parse(last_stamp):
            raise RuntimeError("CLOCK_INTEGRITY: recovery report did not advance")
        publish(root, runner)
        last_stamp = updated["timestamp"]
        total += 1
        observations.append({"pulse": index + 1, "status": "PUBLISHED",
                             "observation_utc": last_stamp,
                             "new_paper_experiments": updated.get("added", 0),
                             "closed_this_run": updated.get("closed_this_run", 0)})
    outcome = {"status": "RECOVERY_WINDOW_COMPLETE",
               "requested_pulses": pulses, "completed_pulses": total,
               "observations": observations,
               "note": "Each recovery observation is actual-time paper data; no backfill"}
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("### Bounded paper recovery window\n\n")
            out.write("Additional fresh observations committed: **" +
                      str(total) + "/" + str(pulses) + "**.\n\n")
            out.write("Late historical closures remain excluded from eligible evidence.\n")
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pulses", type=int, default=MAX_PULSES)
    parser.add_argument("--interval-minutes", type=int,
                        default=DEFAULT_INTERVAL_MINUTES)
    args = parser.parse_args()
    run_window(pulses=args.pulses, interval_minutes=args.interval_minutes)


if __name__ == "__main__":
    main()
