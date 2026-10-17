"""Read-only prospective evidence map by frozen entry regime and horizon.

Diagnostic, not an allocation policy or a claim of profitable trading.
Only learner-eligible actual CLOSED paper positions enter calculations.
"""
from collections import defaultdict
from statistics import mean, stdev
import math
import learner

MIN_TRAIN_DAYS = 7
MIN_TRAIN_CLOSES = 30

def _interval(rows):
    by_day = defaultdict(list)
    for r in rows:
        value = learner.research_R(r)
        if not math.isfinite(value):
            raise ValueError("INTEGRITY_FAILURE: nonfinite stress-adjusted R")
        by_day[learner.day_of(r)].append(max(-learner.CLIP_R, min(learner.CLIP_R, value)))
    values = [mean(by_day[k]) for k in sorted(by_day)]
    if len(values) < 4:
        return None, None
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return round(mean(values)-margin, 6), round(mean(values)+margin, 6)

def evaluate(records):
    source = records.values() if isinstance(records, dict) else records
    cells = defaultdict(list)
    for row in source:
        if not learner.eligible(row):
            continue
        # Regime is frozen at OPEN; no retrospective CLOSE-derived regimes.
        key = (row["strategy"], str(row.get("regime", "unknown")),
               row["horizon_hours"], row.get("side", "unknown"))
        cells[key].append(row)
    results = []
    for key, rows in sorted(cells.items()):
        train = [r for r in rows if learner.stable_bucket("holdout:"+learner.day_of(r), 5) != 0]
        monitoring = [r for r in rows if learner.stable_bucket("holdout:"+learner.day_of(r), 5) == 0]
        days = len({learner.day_of(r) for r in train})
        low, high = _interval(train)
        ready = len(train) >= MIN_TRAIN_CLOSES and days >= MIN_TRAIN_DAYS
        results.append({
            "strategy": key[0], "entry_regime": key[1],
            "fixed_horizon_hours": key[2], "entry_side": key[3],
            "eligible_closes": len(rows), "training_closes": len(train),
            "monitoring_closes_not_used": len(monitoring),
            "training_entry_days": days,
            "training_mean_stress_R": round(mean(learner.research_R(r) for r in train), 6) if train else None,
            "day_cluster_descriptive_lcb_R": low,
            "day_cluster_descriptive_ucb_R": high,
            "sample_ready_for_diagnostics": ready,
            "persistent_negative_warning": bool(ready and high is not None and high < 0),
            "positive_training_observation_only": bool(ready and low is not None and low > 0),
            "edge_proven": False,
        })
    return {
        "method": "frozen-regime-evidence-v1",
        "paper_only": True, "read_only": True,
        "entry_regime_source": "OPEN record; no future features",
        "friction": "learner.research_R; stress scenario separate from published paper P&L",
        "monitoring_used_for_selection": False,
        "multiple_testing_adjusted": False,
        "warning": "Many correlated regime/horizon/side cells; descriptive intervals do not prove edge. No strategy promotion or execution changes.",
        "cells": results,
    }
