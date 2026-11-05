#!/usr/bin/env python3
"""Quality audit for the versioned ML dataset; no fitting or ledger writes."""
import argparse
import json
from collections import Counter
from pathlib import Path
import ml_train

def audit(rows):
    result = {"dataset_version": "ml-dataset-v1", "rows": len(rows),
              "by_horizon": {}, "feature_missingness": {},
              "label_distribution": {}, "entry_date_range": None}
    for horizon in (1, 2, 4, 8, 12, 24):
        cohort = [r for r in rows if r["features"].get("horizon_hours") == horizon]
        labels = Counter(r["labels"]["net_profit"] for r in cohort)
        result["by_horizon"][str(horizon)] = {
            "n": len(cohort), "positive": labels.get(1, 0),
            "negative_or_breakeven": labels.get(0, 0),
            "positive_share": labels.get(1, 0)/len(cohort) if cohort else None}
    feature_names = sorted({key for row in rows for key in row["features"]})
    for key in feature_names:
        missing = sum(row["features"].get(key) is None for row in rows)
        result["feature_missingness"][key] = {
            "missing": missing, "share": missing/len(rows) if rows else None}
    labels = Counter(row["labels"]["net_profit"] for row in rows)
    result["label_distribution"] = dict(labels)
    if rows:
        times = sorted(ml_train.parse_time(row["entry_at"]) for row in rows)
        result["entry_date_range"] = {"first": times[0].isoformat(),
                                      "last": times[-1].isoformat()}
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="artifacts/ml_dataset_v1.jsonl")
    parser.add_argument("--output", default="artifacts/ml_dataset_audit_v1.json")
    args = parser.parse_args()
    report = audit(ml_train.load_rows(args.dataset))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
