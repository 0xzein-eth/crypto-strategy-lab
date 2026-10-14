#!/usr/bin/env python3
"""Read-only, retrospective, exact-stratum control comparisons for PAPER research.

This module does NOT change strategy selection, trade entries, fixed-horizon
exits, canonical event history, or the published paper P&L. Comparisons are
observational, highly correlated and not evidence of a tradable edge.
"""
import argparse
from collections import defaultdict
import datetime as dt
import json
import math
import os
from pathlib import Path
from statistics import mean, stdev

import learner

VERSION = "matched-control-v1"
CONTROL = "CTRL-v1"
MAX_ENTRY_GAP_MINUTES = 120
UTC = dt.timezone.utc


def entry_time(record):
    value = dt.datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("INTEGRITY_FAILURE: naive entry timestamp")
    return value.astimezone(UTC)


def stratum(record):
    """Freeze all matching variables at OPEN, never infer a regime from CLOSE."""
    when = entry_time(record)
    return (when.date().isoformat(), record["symbol"], record["horizon_hours"],
            record["side"], record.get("regime", "unknown"))


def eligible_rows(records):
    """Use exactly the pre-existing prospective learner's eligibility gate."""
    source = records.values() if isinstance(records, dict) else records
    return [row for row in source if learner.eligible(row)]


def _round(value):
    return round(value, 6) if value is not None else None


def _daily_interval(pairs):
    grouped = defaultdict(list)
    for pair in pairs:
        # Clip each *paired difference*, not each trade, before day clustering.
        delta = pair["delta_after_friction_R"]
        clipped = max(-learner.CLIP_R, min(learner.CLIP_R, delta))
        grouped[pair["entry_day"]].append(clipped)
    daily = [mean(grouped[d]) for d in sorted(grouped)]
    if len(daily) < 4:
        return None, None
    error = 1.96 * stdev(daily) / math.sqrt(len(daily))
    return _round(mean(daily) - error), _round(mean(daily) + error)


def compare(records):
    """One-to-one nearest-entry matches per arm, within strict frozen strata.

    Controls are never reused *within* an arm; they can appear in different
    arm comparisons, so cross-arm estimates must not be treated as independent.
    No forward-selection, promotion, or training input consumes these results.
    """
    rows = eligible_rows(records)
    controls = [r for r in rows if r["strategy"] == CONTROL]
    by_arm = defaultdict(list)
    by_key = defaultdict(list)
    for r in rows:
        if r["strategy"] != CONTROL:
            by_arm[r["strategy"]].append(r)
    for r in controls:
        by_key[stratum(r)].append(r)
    for group in by_key.values():
        group.sort(key=lambda r: (entry_time(r), r["id"]))
    results = {}
    for arm in sorted(by_arm):
        used_controls = set()
        pairs = []
        for trade in sorted(by_arm[arm], key=lambda r: (entry_time(r), r["id"])):
            opened = entry_time(trade)
            options = []
            for control in by_key.get(stratum(trade), []):
                if control["id"] in used_controls:
                    continue
                gap = abs((opened - entry_time(control)).total_seconds()) / 60
                if gap <= MAX_ENTRY_GAP_MINUTES:
                    options.append((gap, entry_time(control), control["id"], control))
            if not options:
                continue
            gap, _, _, control = min(options, key=lambda x: x[:3])
            used_controls.add(control["id"])
            base = float(trade["normalized_R"]) - float(control["normalized_R"])
            after = learner.research_R(trade) - learner.research_R(control)
            if not math.isfinite(base) or not math.isfinite(after):
                raise ValueError("INTEGRITY_FAILURE: nonfinite paired outcome")
            pairs.append({
                "entry_day": opened.date().isoformat(),
                "entry_gap_minutes": gap,
                "strategy_R": float(trade["normalized_R"]),
                "control_R": float(control["normalized_R"]),
                "delta_fee_adjusted_R": base,
                "delta_after_friction_R": after,
            })
        n = len(pairs)
        days = len({p["entry_day"] for p in pairs})
        lcb, ucb = _daily_interval(pairs)
        results[arm] = {
            "eligible_arm_closes": len(by_arm[arm]),
            "matched_pairs": n,
            "unmatched_arm_closes": len(by_arm[arm]) - n,
            "matched_fraction": _round(n / len(by_arm[arm])) if by_arm[arm] else None,
            "matched_entry_utc_days": days,
            "mean_entry_gap_minutes": _round(mean(p["entry_gap_minutes"] for p in pairs)) if n else None,
            "mean_arm_fee_adjusted_R": _round(mean(p["strategy_R"] for p in pairs)) if n else None,
            "mean_control_fee_adjusted_R": _round(mean(p["control_R"] for p in pairs)) if n else None,
            "mean_paired_delta_fee_adjusted_R": _round(mean(p["delta_fee_adjusted_R"] for p in pairs)) if n else None,
            "mean_paired_delta_after_friction_scenario_R": _round(mean(p["delta_after_friction_R"] for p in pairs)) if n else None,
            "day_cluster_95pct_descriptive_lcb_after_friction_R": lcb,
            "day_cluster_95pct_descriptive_ucb_after_friction_R": ucb,
            "coverage": ("NO_MATCHED_PAIRS" if n == 0 else
                         "LIMITED_PAIRS_OR_DAYS" if n < 50 or days < 7 else
                         "DESCRIPTIVE_ONLY_NOT_VALIDATED"),
            "edge_proven": False,
        }
    return {
        "method": VERSION,
        "paper_only": True,
        "exit_policy_unchanged": "fixed horizon 1/2/4/8/12/24h, no SL/TP/trailing",
        "eligible_closed": len(rows),
        "eligible_controls": len(controls),
        "match_keys": ["entry_utc_day", "symbol", "fixed_horizon_hours",
                       "entry_side", "frozen_entry_regime"],
        "max_entry_gap_minutes": MAX_ENTRY_GAP_MINUTES,
        "matching": "retrospective nearest entry, without replacement within each arm",
        "friction": "fee-adjusted recorded R; additional frozen stress/fallback compared separately",
        "clustering": "UTC entry-day means of clipped paired differences (+/-3R); descriptive 1.96 SE",
        "limitations": [
            "No synthetic or historical entry/exit prices; only eligible real observed paper CLOSE records.",
            "Unmatched signals are excluded, so paired estimates can have selection bias.",
            "Controls can be reused across DIFFERENT strategy comparisons, not within one arm.",
            "Matching is retrospective; time-varying confounders and correlated markets remain.",
            "Seven days and 50 pairs are only a reporting coverage gate, not a statistical edge test.",
            "Multiple strategy comparisons, non-independent days, and previously inspected outcomes prevent any edge claim.",
            "This diagnostic is NEVER fed into the strategy allocator or a promotion decision.",
        ],
        "arms": results,
    }


def main():
    import audit
    import engine
    parser = argparse.ArgumentParser(description="Read-only paper control matching")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    integrity = audit.verify()
    records, seq, tip, _ = engine.replay()
    result = compare(records)
    result["ledger"] = {
        "verified_events": seq,
        "tip_sha256": tip,
        "verified_trades": integrity["trades"],
        "verified_closed": integrity["closed"],
    }
    report = json.loads(engine.REPORT.read_text(encoding="utf-8"))
    result["source_report_timestamp_utc"] = report["timestamp"]
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("### Retrospective matched controls — PAPER ONLY\n\n")
            out.write("Exact UTC day, symbol, horizon, side and frozen regime; <=120m entry gap.\n\n")
            out.write("| Arm | Pairs | Days | Fee delta R | Stress delta R | Coverage |\n")
            out.write("|---|---:|---:|---:|---:|---|\n")
            for arm, info in sorted(result["arms"].items()):
                out.write("| {} | {} | {} | {} | {} | {} |\n".format(
                    arm, info["matched_pairs"], info["matched_entry_utc_days"],
                    info["mean_paired_delta_fee_adjusted_R"],
                    info["mean_paired_delta_after_friction_scenario_R"],
                    info["coverage"]))
            out.write("\nObservational, correlated, multi-tested; no strategy promotion or proven edge.\n")


if __name__ == "__main__":
    main()
