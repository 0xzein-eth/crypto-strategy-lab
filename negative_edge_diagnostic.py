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

def evaluate(records):
    source = records.values() if isinstance(records, dict) else records
    groups = defaultdict(list)
    for row in source:
        if learner.eligible(row):
            groups[row["strategy"]].append(row)
    arms = {}
    for name in sorted(set(learner.BASELINES + learner.ADVANCED)):
        rows = groups[name]
        training = [r for r in rows if learner.stable_bucket("holdout:"+learner.day_of(r), 5) != 0]
        monitoring = [r for r in rows if learner.stable_bucket("holdout:"+learner.day_of(r), 5) == 0]
        train_days = len({learner.day_of(r) for r in training})
        low, high = _interval(training)
        enough = len(training) >= MIN_CLOSES and train_days >= MIN_DAYS
        arms[name] = {
            "eligible_closed": len(rows),
            "training_closed": len(training),
            "monitoring_closed_not_used_for_diagnosis": len(monitoring),
            "training_utc_days": train_days,
            "training_day_cluster_descriptive_lcb_R": low,
            "training_day_cluster_descriptive_ucb_R": high,
            "negative_expectancy_warning": bool(enough and high is not None and high < 0),
            "insufficient_evidence": not enough,
            "edge_proven": False,
        }
    return {
        "method": "negative-edge-diagnostic-v1",
        "paper_only": True,
        "read_only": True,
        "minimum_training_closes": MIN_CLOSES,
        "minimum_training_days": MIN_DAYS,
        "holdout_used_for_selection": False,
        "warning": "Day-cluster intervals are descriptive, not multiple-test-adjusted proof; no automatic strategy suppression or promotion.",
        "arms": arms,
    }
