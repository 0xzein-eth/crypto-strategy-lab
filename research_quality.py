"""Read-only quality gates for prospective PAPER research evidence.

Never promotes a strategy; protects against correlated observations,
multiple comparisons, low control coverage, and short observation windows.
"""
from collections import defaultdict
from statistics import mean
import datetime as dt
import math

MIN_DAYS = 20
MIN_PAIRS = 100
MIN_MATCH_FRACTION = 0.50
MIN_HOLDOUT_DAYS = 5
MIN_HOLDOUT_PAIRS = 25
MIN_COVERAGE = 0.90


def _day(value):
    date = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("INTEGRITY_FAILURE: timezone missing")
    return date.date().isoformat()


def _holdout(day):
    import learner
    return learner.stable_bucket("holdout:" + day, 5) == 0


def evaluate(records, comparison, schedule_coverage=None):
    """Conservative audit: quality gates, not statistical proof of edge."""
    import learner
    source = records.values() if isinstance(records, dict) else records
    rows = [r for r in source if learner.eligible(r)]
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["strategy"]].append(r)
    coverage_ok = (isinstance(schedule_coverage, (int, float))
                   and not isinstance(schedule_coverage, bool)
                   and math.isfinite(schedule_coverage)
                   and MIN_COVERAGE <= schedule_coverage <= 1)
    results = {}
    for arm, stats in sorted(comparison["arms"].items()):
        arm_rows = by_arm[arm]
        days = {_day(r["created_at"]) for r in arm_rows}
        holdout = [r for r in arm_rows if _holdout(_day(r["created_at"]))]
        train = [r for r in arm_rows if not _holdout(_day(r["created_at"]))]
        holdout_days = {_day(r["created_at"]) for r in holdout}
        reasons = []
        if stats["matched_pairs"] < MIN_PAIRS:
            reasons.append("INSUFFICIENT_MATCHED_PAIRS")
        if stats["matched_entry_utc_days"] < MIN_DAYS:
            reasons.append("INSUFFICIENT_MATCHED_DAYS")
        if (stats["matched_fraction"] or 0) < MIN_MATCH_FRACTION:
            reasons.append("LOW_MATCH_FRACTION")
        if len(holdout) < MIN_HOLDOUT_PAIRS or len(holdout_days) < MIN_HOLDOUT_DAYS:
            reasons.append("INSUFFICIENT_FROZEN_HOLDOUT")
        if not train:
            reasons.append("NO_TRAIN_SAMPLE")
        if not coverage_ok:
            reasons.append("LOW_OR_UNKNOWN_SCHEDULER_COVERAGE")
        if (stats["day_cluster_95pct_descriptive_lcb_after_friction_R"] is None or
            stats["day_cluster_95pct_descriptive_lcb_after_friction_R"] <= 0):
            reasons.append("NONPOSITIVE_OR_UNAVAILABLE_DESCRIPTIVE_LCB")
        results[arm] = {
            "eligible_closed": len(arm_rows),
            "distinct_entry_days": len(days),
            "train_closes": len(train),
            "frozen_holdout_closes": len(holdout),
            "frozen_holdout_days": len(holdout_days),
            "matched_pairs": stats["matched_pairs"],
            "matched_fraction": stats["matched_fraction"],
            "quality_gate_pass": not reasons,
            "blocking_reasons": reasons,
            "edge_proven": False,
        }
    return {
        "method": "quality-gates-v1",
        "paper_only": True,
        "schedule_coverage": schedule_coverage,
        "schedule_coverage_gate": coverage_ok,
        "min_distinct_matched_days": MIN_DAYS,
        "min_matched_pairs": MIN_PAIRS,
        "min_frozen_holdout_days": MIN_HOLDOUT_DAYS,
        "multiple_testing": "No multiplicity-adjusted inference; no strategy can be declared proven",
        "caveat": "Holdout counts are not paired holdout estimates. A pass is only data readiness, not edge validation.",
        "arms": results,
    }
