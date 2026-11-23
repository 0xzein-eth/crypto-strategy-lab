"""Build and train a leakage-aware logistic baseline from the verified PAPER ledger."""
import argparse
import datetime as dt
import json
from pathlib import Path

import dataset_builder
import ml_baseline


def run(output=None, max_epochs=30):
    import engine

    records, event_count, ledger_tip, next_id = engine.replay()
    dataset = dataset_builder.build_dataset(records)
    result = {
        "schema": "paper-ml-baseline-research-report-v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_ledger_events": event_count,
        "source_ledger_tip_sha256": ledger_tip,
        "dataset": {key:value for key,value in dataset.items() if key != "examples"},
        "model_family": "logistic_regression",
        "model_purpose": "predict positive post-cost fixed-horizon research R",
        "paper_only": True,
        "automatic_allocation_change": False,
        "real_orders": False,
        "live_deployment_allowed": False,
    }
    try:
        split = dataset_builder.chronological_split(dataset)
        result["split"] = {key:value for key,value in split.items()
                           if key not in ("train","validation")}
        trained = ml_baseline.fit(
            split["train"], split["validation"], dataset["feature_names"],
            max_epochs=max_epochs)
        result["training_rows"] = len(split["train"])
        result["validation_rows"] = len(split["validation"])
        result["training_positive_rate"] = trained["model"]["training_positive_rate"]
        result["model"] = trained["model"]
        result["model_id"] = trained["model_id"]
        result["validation"] = trained["validation"]
        result["validation_status"] = trained["validation_status"]
        result["validation_predictions"] = trained["validation_predictions"]
        result["historical_validation_previously_inspected"] = True
        result["independent_future_holdout_completed"] = False
        result["candidate_promotion"] = False
        result["status"] = "DIAGNOSTIC_MODEL_TRAINED_NOT_VALIDATED_ALPHA"
    except ValueError as exc:
        result["status"] = "INSUFFICIENT_OR_INVALID_DATA"
        result["reason"] = str(exc)
        result["independent_future_holdout_completed"] = False
        result["candidate_promotion"] = False

    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True,
                                   allow_nan=False) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="research_results/ml_baseline_report.json")
    parser.add_argument("--max-epochs", type=int, default=30)
    args = parser.parse_args()
    result = run(args.output, args.max_epochs)
    print(json.dumps({key:value for key,value in result.items()
                      if key != "validation_predictions"}, indent=2, sort_keys=True))
    if result["status"] == "INSUFFICIENT_OR_INVALID_DATA":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
