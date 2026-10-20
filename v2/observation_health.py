"""Read-only 30m market-observation availability audit (not a trading signal).

Counts truly recorded hash-verified observer timestamps. Never interpolates,
backfills, or claims an exchange fill for a missing GitHub Actions interval.
The 90% service target is diagnostic, not a scheduler guarantee.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

from v2.forward_paper import SLOT_SECONDS, read_events
from v2.paper_portfolio import ts, iso

SCHEMA = "v2-cadence-availability-audit-v1"
UTC = dt.timezone.utc


def summarize(events, *, now):
    now = ts(now)
    slots = []
    observed = []
    for record in events:
        moment = ts(record["tick"]["observed_at"])
        if moment > now:
            raise ValueError("CLOCK_INTEGRITY: future journal observation")
        slot = int(moment.timestamp()) // SLOT_SECONDS
        if slots and slot <= slots[-1]:
            raise ValueError("CLOCK_INTEGRITY: duplicate or reversed v2 observation slot")
        slots.append(slot)
        observed.append(moment)
    if not slots:
        return {
            "schema": SCHEMA, "status": "NO_VERIFIED_OBSERVATIONS",
            "verified_observations": 0, "completed_slots_since_first": 0,
            "observed_slots_since_first": 0, "overall_coverage_pct": None,
            "recent_6h_coverage_pct": None, "max_recorded_gap_minutes": None,
            "minutes_since_last_observation": None, "latest_observed_utc": None,
            "market_observations_were_not_synthesized": True,
            "real_order_submissions": 0,
        }
    current_slot = int(now.timestamp()) // SLOT_SECONDS
    first_slot = slots[0]
    expected = current_slot - first_slot + 1
    if expected <= 0:
        raise ValueError("CLOCK_INTEGRITY: invalid slot denominator")
    recent_start = max(first_slot, current_slot - 11)
    recent_expected = current_slot - recent_start + 1
    recent_count = sum(s >= recent_start for s in slots)
    gaps = [
        (b - a).total_seconds() / 60
        for a, b in zip(observed, observed[1:])
    ]
    stale_minutes = max(0.0, (now - observed[-1]).total_seconds() / 60)
    overall_pct = round(100 * len(slots) / expected, 2)
    recent_pct = round(100 * recent_count / recent_expected, 2)
    # Sub-hour jitter is expected. Separate availability from alpha.
    status = ("STALE" if stale_minutes > 90 else
              "BELOW_90_PERCENT_TARGET" if recent_pct < 90 else
              "COVERAGE_TARGET_MET")
    return {
        "schema": SCHEMA, "status": status,
        "verified_observations": len(slots),
        "completed_slots_since_first": expected,
        "observed_slots_since_first": len(slots),
        "overall_coverage_pct": overall_pct,
        "recent_6h_coverage_pct": recent_pct,
        "max_recorded_gap_minutes": round(max(gaps), 2) if gaps else None,
        "minutes_since_last_observation": round(stale_minutes, 2),
        "latest_observed_utc": iso(observed[-1]),
        "market_observations_were_not_synthesized": True,
        "real_order_submissions": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional diagnostic artifact path; never v2_state/")
    args = parser.parse_args()
    output = summarize(read_events(), now=dt.datetime.now(UTC))
    rendered = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = Path(args.output)
        if target.resolve().is_relative_to(Path(__file__).resolve().parent.parent / "v2_state"):
            raise ValueError("INTEGRITY_FAILURE: health diagnostics cannot modify v2 observations")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
