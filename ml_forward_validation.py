"""Blind prospective PAPER-only validation for frozen ML shadow candidates.

Predictions are captured only while a record is still OPEN and shortly after
its OPEN timestamp. Closed records without a captured prediction are never
backfilled. Predictions and outcome scores are separate hash-chained events.
This module has no sampler, wallet, allocation, or order-writing integration.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

import dataset_builder
import ml_baseline
import ml_shadow_models
import learner

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "ml_forward_state"
BUNDLE_PATH = STATE / "frozen_bundle.json"
EVENTS_PATH = STATE / "events.jsonl"
REPORT_PATH = STATE / "report.json"
MANIFEST_PATH = ROOT / "research" / "model_freeze_v1.json"
ZERO_HASH = "0" * 64
UTC = dt.timezone.utc
VERSION = "paper-ml-forward-v1"
MAX_CAPTURE_DELAY_SECONDS = 15 * 60
FINGERPRINT_PATHS = (
    "engine.py", "dataset_builder.py", "ml_baseline.py",
    "ml_shadow_models.py", "train_models.py", "learner.py",
    "universe.py", "friction.py", "signals.py", "diverse_confirmed.py",
    "band_hypotheses.py", "regime_hypotheses.py", "entry_sampling.py",
    "cohort_diagnostics.py", "opportunity_history.py",
    "temporal_evidence.py", "archive_event_data.py",
    "ml_forward_validation.py", "research/model_freeze_v1.json",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def stamp(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: timezone required")
    return result.astimezone(UTC)


def feature_schema_hash(names):
    return digest(list(names))


def code_fingerprint():
    hashes = {}
    for relative in FINGERPRINT_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError("FREEZE_INVALID: missing source file " + relative)
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest(hashes)


def model_digest(model):
    return digest(model)


def load_manifest():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema") != "paper-ml-prospective-freeze-v1":
        raise ValueError("FREEZE_INVALID: unknown manifest schema")
    if manifest.get("status") != "PREREGISTERED_CANDIDATES_NO_CHAMPION":
        raise ValueError("FREEZE_INVALID: candidate manifest status changed")
    return manifest


def verify_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("schema") != VERSION:
        raise ValueError("FREEZE_INVALID: bundle schema")
    payload = {key: value for key, value in bundle.items() if key != "bundle_id"}
    if bundle.get("bundle_id") != digest(payload):
        raise ValueError("INTEGRITY_FAILURE: frozen model bundle hash")
    manifest = load_manifest()
    if bundle.get("manifest_sha256") != hashlib.sha256(
            MANIFEST_PATH.read_bytes()).hexdigest():
        raise ValueError("FREEZE_INVALID: manifest changed after model freeze")
    if bundle.get("code_fingerprint") != code_fingerprint():
        raise ValueError("FREEZE_INVALID: model or feature source changed after freeze")
    if bundle.get("feature_schema_sha256") != feature_schema_hash(
            dataset_builder.FEATURE_NAMES):
        raise ValueError("FREEZE_INVALID: feature schema changed")
    if bundle.get("feature_names") != list(dataset_builder.FEATURE_NAMES):
        raise ValueError("FREEZE_INVALID: frozen feature order changed")
    if (bundle.get("prediction_capture_delay_seconds") != manifest[
            "prospective_rules"]["max_prediction_capture_delay_seconds"] or
            MAX_CAPTURE_DELAY_SECONDS != manifest["prospective_rules"][
                "max_prediction_capture_delay_seconds"]):
        raise ValueError("FREEZE_INVALID: prediction capture window changed")
    expected = {item["name"] for item in manifest["candidates"]}
    models = bundle.get("models", {})
    if set(models) != expected:
        raise ValueError("FREEZE_INVALID: candidate set mismatch")
    for name, record in models.items():
        model = record.get("model")
        if not isinstance(model, dict) or record.get("model_id") != model_digest(model):
            raise ValueError("INTEGRITY_FAILURE: model artifact hash " + name)
        if model.get("feature_names") != list(dataset_builder.FEATURE_NAMES):
            raise ValueError("FREEZE_INVALID: model feature order " + name)
    if bundle.get("paper_only") is not True or bundle.get("real_orders") is not False:
        raise ValueError("SAFETY_FAILURE: model bundle execution boundary")
    return True


def read_bundle(path=BUNDLE_PATH):
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    verify_bundle(bundle)
    return bundle


def initialize_bundle(records, event_count, ledger_tip, now=None, path=BUNDLE_PATH):
    """Train all preregistered candidates once, then freeze before cohort start."""
    path = Path(path)
    if path.exists():
        raise FileExistsError("FREEZE_EXISTS: refusing to overwrite frozen model bundle")
    requested_freeze_time = now
    if requested_freeze_time is not None and requested_freeze_time.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: freeze time must be timezone-aware")
    manifest = load_manifest()
    dataset = dataset_builder.build_dataset(records)
    split = dataset_builder.chronological_split(dataset, validation_fraction=0.20,
                                                 embargo_hours=24)
    train, validation = split["train"], split["validation"]
    prevalence = sum(int(row["label"]) for row in train) / len(train)
    if not 0 < prevalence < 1:
        raise ValueError("INSUFFICIENT_DATA: training prevalence must contain both classes")
    candidates = {
        "logistic_regression": lambda: ml_baseline.fit(
            train, validation, dataset["feature_names"], max_epochs=30,
            batch_size=256, learning_rate=0.05, l2=0.001,
            patience=5, seed=17),
        "gradient_boosting": lambda: ml_shadow_models.fit_gradient_boosting(
            train, validation, dataset["feature_names"], rounds=24,
            learning_rate=0.05, max_thresholds=12, min_leaf=12),
        "mlp_backprop": lambda: ml_shadow_models.fit_mlp(
            train, validation, dataset["feature_names"], hidden_units=16,
            max_epochs=30, batch_size=128, learning_rate=0.01,
            l2=0.0005, patience=6, seed=29),
    }
    models = {}
    for name, fit in candidates.items():
        fitted = fit()
        model = fitted["model"]
        models[name] = {
            "model": model,
            "model_id": model_digest(model),
            "role": "FROZEN_SHADOW_CANDIDATE",
        }
    latest_label = max(parse(row["label_available_at"]) for row in dataset["examples"])
    freeze_time = requested_freeze_time or dt.datetime.now(UTC)
    if latest_label > freeze_time:
        raise ValueError("CLOCK_INTEGRITY: training label timestamp after model freeze")
    payload = {
        "schema": VERSION,
        "version": 1,
        "created_at_utc": stamp(freeze_time),
        "cohort_start_utc": stamp(freeze_time),
        "training_labels_available_through_utc": stamp(latest_label),
        "source_ledger_events": int(event_count),
        "source_ledger_tip_sha256": ledger_tip,
        "eligible_historical_examples": dataset["eligible_examples"],
        "training_rows": len(train),
        "early_stopping_rows": len(validation),
        "training_record_ids_sha256": hashlib.sha256(
            "\\n".join(row["record_id"] for row in train).encode("utf-8")
        ).hexdigest(),
        "early_stopping_record_ids_sha256": hashlib.sha256(
            "\\n".join(row["record_id"] for row in validation).encode("utf-8")
        ).hexdigest(),
        "validation_start_utc": split["validation_start_utc"],
        "purged_training_rows": split["purged_training_rows"],
        "training_positive_prevalence": round(prevalence, 12),
        "feature_names": list(dataset["feature_names"]),
        "feature_schema_sha256": feature_schema_hash(dataset["feature_names"]),
        "prediction_capture_delay_seconds": manifest["prospective_rules"][
            "max_prediction_capture_delay_seconds"],
        "manifest_sha256": hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "code_fingerprint": code_fingerprint(),
        "models": models,
        "candidate_selection": "NONE_ALL_PREREGISTERED_CANDIDATES_FROZEN",
        "historical_validation_used_for_early_stopping": True,
        "historical_validation_is_not_prospective_evidence": True,
        "paper_only": True,
        "real_orders": False,
        "automatic_allocation_change": False,
    }
    bundle = {**payload, "bundle_id": digest(payload)}
    verify_bundle(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True,
                                allow_nan=False) + "\n", encoding="utf-8")
    return bundle


def read_events(path=EVENTS_PATH):
    path = Path(path)
    if not path.exists():
        return []
    events, previous = [], ZERO_HASH
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError("INTEGRITY_FAILURE: blank forward event")
            event = json.loads(line)
            body = {key: value for key, value in event.items() if key != "hash"}
            if (event.get("seq") != len(events) + 1 or
                    event.get("prev_hash") != previous or
                    event.get("hash") != digest(body) or
                    set(body) != {"seq", "prev_hash", "kind", "payload"}):
                raise ValueError("INTEGRITY_FAILURE: forward event hash chain")
            if event.get("kind") not in ("prediction", "score", "skip", "excluded"):
                raise ValueError("INTEGRITY_FAILURE: unknown forward event type")
            events.append(event)
            previous = event["hash"]
    return events


def append_event(events, kind, payload):
    if kind not in ("prediction", "score", "skip", "excluded"):
        raise ValueError("invalid event kind")
    previous = events[-1]["hash"] if events else ZERO_HASH
    body = {"seq": len(events) + 1, "prev_hash": previous,
            "kind": kind, "payload": payload}
    event = {**body, "hash": digest(body)}
    events.append(event)
    return event


def prediction_index(events):
    predictions, scored, seen = {}, set(), set()
    for event in events:
        payload = event["payload"]
        record_id = payload["record_id"]
        if event["kind"] == "prediction":
            if record_id in predictions or record_id in seen:
                raise ValueError("INTEGRITY_FAILURE: duplicate prediction " + record_id)
            predictions[record_id] = payload
            seen.add(record_id)
        elif event["kind"] == "skip":
            if record_id in seen:
                raise ValueError("INTEGRITY_FAILURE: duplicate skip " + record_id)
            seen.add(record_id)
        elif event["kind"] in ("score", "excluded"):
            if record_id not in predictions or record_id in scored:
                raise ValueError("INTEGRITY_FAILURE: orphan/duplicate outcome " + record_id)
            scored.add(record_id)
    return predictions, scored, seen


def _predict(model_name, model, features):
    if model_name == "logistic_regression":
        return ml_baseline.predict(model, features)
    if model_name == "gradient_boosting":
        return ml_shadow_models.predict_gradient_boosting(model, features)
    if model_name == "mlp_backprop":
        return ml_shadow_models.predict_mlp(model, features)
    raise ValueError("FREEZE_INVALID: unknown candidate " + model_name)


def process_records(records, bundle, events, now=None):
    """Capture OPEN-time predictions and score only already-predicted CLOSED rows."""
    verify_bundle(bundle)
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: run time must be timezone-aware")
    records_by_id = {record["id"]: record for record in
                     (records.values() if isinstance(records, dict) else records)}
    predictions, scored, seen = prediction_index(events)
    start = parse(bundle["cohort_start_utc"])
    prevalence = float(bundle["training_positive_prevalence"])
    added_predictions = added_scores = added_skips = 0

    # Capture only while the original record is still OPEN. Never infer or
    # reconstruct a prediction for a record whose outcome is already known.
    for record_id in sorted(records_by_id):
        record = records_by_id[record_id]
        if record_id in seen:
            continue
        try:
            created = parse(record["created_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if created < start:
            continue
        if record.get("status") == "OPEN":
            age = (now - created).total_seconds()
            reason = None
            if age < 0:
                reason = "open_timestamp_in_future"
            elif age > bundle["prediction_capture_delay_seconds"]:
                reason = "prediction_capture_window_missed"
            elif (record.get("provider") != "okx-swap" or
                  record.get("market_type") != "perpetual" or
                  record.get("horizon_hours") not in dataset_builder.HORIZONS):
                reason = "record_outside_frozen_eligibility"
            if reason is None:
                try:
                    features = dataset_builder.feature_values(record)
                    probabilities = {
                        name: round(_predict(name, item["model"], features), 12)
                        for name, item in bundle["models"].items()
                    }
                    if not all(math.isfinite(value) and 0 <= value <= 1
                               for value in probabilities.values()):
                        raise ValueError("MODEL_OUTPUT_INVALID")
                    payload = {
                        "record_id": record_id,
                        "created_at": record["created_at"],
                        "prediction_recorded_at_utc": stamp(now),
                        "strategy": record.get("strategy"),
                        "symbol": record.get("symbol"),
                        "side": record.get("side"),
                        "horizon_hours": record.get("horizon_hours"),
                        "feature_schema_sha256": bundle["feature_schema_sha256"],
                        "bundle_id": bundle["bundle_id"],
                        "model_ids": {name: item["model_id"]
                                      for name, item in bundle["models"].items()},
                        "probabilities_positive_net_R": probabilities,
                        "constant_training_prevalence": prevalence,
                        "prediction_is_immutable": True,
                    }
                    append_event(events, "prediction", payload)
                    added_predictions += 1
                    seen.add(record_id)
                    predictions[record_id] = payload
                    continue
                except (KeyError, TypeError, ValueError, ArithmeticError,
                        OverflowError):
                    reason = "feature_or_model_prediction_invalid"
            append_event(events, "skip", {
                "record_id": record_id, "created_at": record["created_at"],
                "recorded_at_utc": stamp(now), "reason": reason,
                "prediction_backfill_allowed": False,
            })
            added_skips += 1
            seen.add(record_id)
        elif record.get("status") == "CLOSED":
            # The observer missed the OPEN window. Mark it, do not backfill.
            append_event(events, "skip", {
                "record_id": record_id, "created_at": record["created_at"],
                "recorded_at_utc": stamp(now),
                "reason": "closed_before_prediction_capture",
                "prediction_backfill_allowed": False,
            })
            added_skips += 1
            seen.add(record_id)

    # Outcomes are appended separately, and only after the fixed horizon has
    # elapsed and the canonical ledger confirms a timely eligible close.
    for record_id in sorted(predictions):
        if record_id in scored or record_id not in records_by_id:
            continue
        record = records_by_id[record_id]
        if record.get("status") != "CLOSED":
            continue
        if not dataset_builder.eligible_closed(record):
            append_event(events, "excluded", {
                "record_id": record_id, "created_at": record["created_at"],
                "recorded_at_utc": stamp(now),
                "reason": "closed_outcome_not_eligible_or_timely",
                "prediction_backfill_allowed": False,
            })
            added_skips += 1
            scored.add(record_id)
            continue
        resolved = parse(record["resolved_at"])
        if resolved > now:
            raise ValueError("CLOCK_INTEGRITY: cannot score a future outcome")
        target_r = float(learner.research_R(record))
        append_event(events, "score", {
            "record_id": record_id,
            "scored_at_utc": stamp(now),
            "evaluate_at": record["evaluate_at"],
            "label_available_at": record["resolved_at"],
            "target_r_after_frozen_costs": round(target_r, 12),
            "label_positive_net_R": int(target_r > 0),
            "outcome_is_after_fixed_horizon": True,
            "late_outcome_excluded": False,
            "bundle_id": bundle["bundle_id"],
        })
        added_scores += 1
        scored.add(record_id)

    return {
        "events": events,
        "added_predictions": added_predictions,
        "added_scores": added_scores,
        "added_skips": added_skips,
    }


def _cluster_interval(values):
    if len(values) < 4:
        return {"clusters": len(values), "mean": None, "ci95": None}
    center = sum(values) / len(values)
    variance = sum((value-center)**2 for value in values) / (len(values)-1)
    margin = 1.96 * math.sqrt(variance / len(values))
    return {"clusters": len(values), "mean": round(center, 10),
            "ci95": [round(center-margin, 10), round(center+margin, 10)],
            "interpretation": "descriptive UTC-day cluster interval; not a formal alpha test"}


def build_report(bundle, events, run_time):
    predictions, scored, seen = prediction_index(events)
    scores = {event["payload"]["record_id"]: event["payload"]
              for event in events if event["kind"] == "score"}
    excluded = [event for event in events if event["kind"] == "excluded"]
    joined = [(predictions[ident], scores[ident]) for ident in sorted(scores)]
    rows = [{"record_id": pred["record_id"], "label": score["label_positive_net_R"]}
            for pred, score in joined]
    result = {
        "schema": "paper-ml-forward-report-v1",
        "generated_at_utc": stamp(run_time),
        "bundle_id": bundle["bundle_id"],
        "cohort_start_utc": bundle["cohort_start_utc"],
        "candidate_model_ids": {name: item["model_id"]
                                for name, item in bundle["models"].items()},
        "predictions_recorded": len(predictions),
        "outcomes_scored": len(scores),
        "skipped_without_prediction": sum(event["kind"] == "skip" for event in events),
        "excluded_predicted_outcomes": len(excluded),
        "pending_outcomes": len(predictions) - len(scores) - len(excluded),
        "evaluation_status": "COLLECTING_PROSPECTIVE_COHORT",
        "champion": None,
        "promotion_decision": "NONE_NO_AUTOMATIC_PROMOTION",
        "historical_validation_used_for_early_stopping": True,
        "paper_only": True,
        "real_orders": False,
        "automatic_allocation_change": False,
        "models": {},
        "strata": {},
        "day_cluster_deltas": {},
        "event_journal_tip_sha256": events[-1]["hash"] if events else ZERO_HASH,
        "event_journal_events": len(events),
    }
    if not joined:
        result["reason"] = "No prospective outcomes have matured yet."
        return result
    prevalence = float(bundle["training_positive_prevalence"])
    constant_probs = [prevalence] * len(joined)
    constant_metrics = ml_baseline.metrics(
        rows, constant_probs, prevalence)
    probabilities_by_model = {
        name: [pred["probabilities_positive_net_R"][name] for pred, _ in joined]
        for name in bundle["models"]
    }
    result["constant_training_prevalence"] = {
        "probability": prevalence, "metrics": constant_metrics}
    for name, probabilities in probabilities_by_model.items():
        metrics = ml_baseline.metrics(rows, probabilities, prevalence)
        result["models"][name] = {
            "metrics": metrics,
            "delta_brier_vs_constant": round(
                metrics["brier_score"]-constant_metrics["brier_score"], 10),
            "delta_log_loss_vs_constant": round(
                metrics["log_loss"]-constant_metrics["log_loss"], 10),
        }
    logistic = result["models"].get("logistic_regression", {}).get("metrics")
    if logistic:
        for name, item in result["models"].items():
            item["delta_brier_vs_logistic"] = round(
                item["metrics"]["brier_score"]-logistic["brier_score"], 10)
            item["delta_log_loss_vs_logistic"] = round(
                item["metrics"]["log_loss"]-logistic["log_loss"], 10)

    grouped = {}
    daily = {}
    for pred, score in joined:
        stratum = "|".join(str(pred.get(key)) for key in
                           ("strategy", "side", "horizon_hours", "symbol"))
        grouped.setdefault(stratum, []).append((pred, score))
        day = parse(pred["created_at"]).date().isoformat()
        daily.setdefault(day, []).append((pred, score))
    for key, group in grouped.items():
        group_rows = [{"record_id": p["record_id"],
                       "label": s["label_positive_net_R"]} for p, s in group]
        result["strata"][key] = {
            "n": len(group),
            "positive_rate": round(sum(r["label"] for r in group_rows)/len(group_rows), 8),
        }
    for name in bundle["models"]:
        day_brier, day_logloss = [], []
        for day, group in sorted(daily.items()):
            diffs_brier, diffs_logloss = [], []
            for pred, score in group:
                y = score["label_positive_net_R"]
                p = pred["probabilities_positive_net_R"][name]
                q = prevalence
                eps = 1e-12
                model_log = -(y*math.log(max(eps,p)) +
                              (1-y)*math.log(max(eps,1-p)))
                base_log = -(y*math.log(max(eps,q)) +
                             (1-y)*math.log(max(eps,1-q)))
                diffs_brier.append((p-y)**2-(q-y)**2)
                diffs_logloss.append(model_log-base_log)
            day_brier.append(sum(diffs_brier)/len(diffs_brier))
            day_logloss.append(sum(diffs_logloss)/len(diffs_logloss))
        result["day_cluster_deltas"][name] = {
            "brier_loss_delta_vs_constant": _cluster_interval(day_brier),
            "log_loss_delta_vs_constant": _cluster_interval(day_logloss),
            "utc_days": len(daily),
        }
    result["evaluation_status"] = "PROSPECTIVE_DIAGNOSTICS_ONLY"
    return result


def run(now=None):
    import engine
    now = now or dt.datetime.now(UTC)
    records, event_count, ledger_tip, _ = engine.replay()
    STATE.mkdir(parents=True, exist_ok=True)
    if not BUNDLE_PATH.exists():
        bundle = initialize_bundle(records, event_count, ledger_tip)
        report = {
            "schema": "paper-ml-forward-report-v1",
            "generated_at_utc": bundle["created_at_utc"],
            "bundle_id": bundle["bundle_id"],
            "cohort_start_utc": bundle["cohort_start_utc"],
            "evaluation_status": "INITIALIZED_WAITING_FOR_NEW_OPEN_EVENTS",
            "champion": None,
            "promotion_decision": "NONE_NO_AUTOMATIC_PROMOTION",
            "paper_only": True,
            "real_orders": False,
        }
        REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n",
                               encoding="utf-8")
        return report
    bundle = read_bundle()
    events = read_events()
    original_event_count = len(events)
    processed = process_records(records, bundle, events, now=now)
    events = processed["events"]
    new_events = events[original_event_count:]
    if new_events:
        with EVENTS_PATH.open("a", encoding="utf-8") as stream:
            for event in new_events:
                stream.write(canonical(event) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    report = build_report(bundle, events, now)
    report.update({key: processed[key] for key in
                   ("added_predictions", "added_scores", "added_skips")})
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n",
                           encoding="utf-8")
    return report


def verify_only():
    bundle = read_bundle()
    events = read_events()
    report = build_report(bundle, events, dt.datetime.now(UTC))
    return {"bundle_id": bundle["bundle_id"], "events": len(events),
            "report_status": report["evaluation_status"],
            "prediction_count": report["predictions_recorded"],
            "scored_count": report["outcomes_scored"],
            "journal_tip_sha256": report["event_journal_tip_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.run == args.verify_only:
        parser.error("choose exactly one of --run or --verify-only")
    result = run() if args.run else verify_only()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
