"""Fail-closed research diagnostics for negative expectancy (PAPER ONLY).

This is an advisory, read-only module. It never selects a strategy, rewrites
the ledger, or changes the pre-registered fixed-horizon exit policy.
"""
from collections import defaultdict
from statistics import mean, stdev
import math
import learner

MIN_DAYS = 7
MIN_CLOSES = 50

def _interval(rows):
    days = defaultdict(list)
    for record in rows:
        value = learner.research_R(record)
        if not math.isfinite(value):
            raise ValueError("INTEGRITY_FAILURE: nonfinite research outcome")
        days[learner.day_of(record)].append(max(-learner.CLIP_R, min(learner.CLIP_R, value)))
    daily = [mean(v) for _, v in sorted(days.items())]
    if len(daily) < 4:
        return None, None
    error = 1.96 * stdev(daily) / math.sqrt(len(daily))
    return round(mean(daily)-error, 6), round(mean(daily)+error, 6)

def evaluate(records, matched_comparison=None):
    source = records.values() if isinstance(records, dict) else records
    groups = defaultdict(list)
    for row in source:
        if learner.eligible(row):
            groups[row["strategy"]].append(row)
    # Matched controls are observational read-only comparators, NEVER an
    # instruction to change the future paper allocator or delete an arm.
    matched_arms = ((matched_comparison or {}).get("arms") or {})
    arms = {}
    for name in sorted(set(learner.BASELINES + learner.ADVANCED)):
        rows = groups[name]
        training = [r for r in rows if learner.stable_bucket("holdout:"+learner.day_of(r), 5) != 0]
        monitoring = [r for r in rows if learner.stable_bucket("holdout:"+learner.day_of(r), 5) == 0]
        train_days = len({learner.day_of(r) for r in training})
        low, high = _interval(training)
        enough = len(training) >= MIN_CLOSES and train_days >= MIN_DAYS
        matched = matched_arms.get(name, {})
        pairs = matched.get("paired_train_pairs", 0)
        paired_days = matched.get("paired_train_utc_days", 0)
        paired_ucb = matched.get("paired_train_descriptive_ucb_R")
        relative_ready = (isinstance(pairs, int) and not isinstance(pairs, bool)
                          and isinstance(paired_days, int) and not isinstance(paired_days, bool)
                          and pairs >= 30 and paired_days >= MIN_DAYS
                          and isinstance(paired_ucb, (int, float))
                          and not isinstance(paired_ucb, bool)
                          and math.isfinite(paired_ucb))
        arms[name] = {
            "eligible_closed": len(rows),
            "training_closed": len(training),
            "monitoring_closed_not_used_for_diagnosis": len(monitoring),
            "training_utc_days": train_days,
            "training_day_cluster_descriptive_lcb_R": low,
            "training_day_cluster_descriptive_ucb_R": high,
            "negative_expectancy_warning": bool(enough and high is not None and high < 0),
            "matched_control_training_pairs": pairs,
            "matched_control_training_utc_days": paired_days,
            "matched_control_training_descriptive_ucb_delta_R": paired_ucb,
            "matched_control_fraction": matched.get("matched_fraction"),
            "relative_control_evidence_sufficient_for_warning": relative_ready,
            "worse_than_matched_control_training_warning": bool(
                relative_ready and paired_ucb < 0),
            "both_absolute_and_relative_negative_warning": bool(
                enough and high is not None and high < 0 and
                relative_ready and paired_ucb < 0),
            "insufficient_evidence": not enough,
            "edge_proven": False,
        }
    return {
        "method": "negative-edge-diagnostic-v2-matched-training-only",
        "paper_only": True,
        "read_only": True,
        "minimum_training_closes": MIN_CLOSES,
        "minimum_training_days": MIN_DAYS,
        "holdout_used_for_selection": False,
        "warning": "Both absolute and exact-stratum matched-control TRAINING warnings are descriptive, correlated and not multiple-test-adjusted. Missing matches cannot establish relative underperformance; monitoring is excluded. No automatic strategy suppression or promotion.",
        "arms": arms,
    }
