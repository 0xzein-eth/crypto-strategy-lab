"""Blind prospective ML cohort: immutable predictions, no backfill, delayed labels."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dataset_builder
import ml_forward_validation as forward

UTC = dt.timezone.utc


def sample_record(record_id="LAB-90001", status="OPEN", created=None,
                  late_excluded=False, target=0.2):
    created = created or dt.datetime(2026, 11, 23, 0, 1, tzinfo=UTC)
    due = created + dt.timedelta(hours=4)
    closed = due + dt.timedelta(minutes=1)
    evidence = {
        "bar_span": "15m confirmed OKX USDT-SWAP",
        "last_close": 100.0, "last_open": 99.0, "last_high": 102.0,
        "last_low": 98.0, "sma20": 99.0, "sma50": 98.0,
        "sma20prev": 98.5, "sma50prev": 97.5, "rsi14": 60.0,
        "rsi14prev": 55.0, "z20": 0.5, "atr14": 2.0,
        "prev_high20": 101.0, "prev_low20": 95.0, "vol_ratio": 1.2,
        "prior20_range_width": 10.0, "older20_range_width": 12.0,
        "prior20_mean_range": 2.0, "upper_wick_ratio": 0.2,
        "lower_wick_ratio": 0.3, "vwap20": 99.0,
    }
    return {
        "id": record_id, "status": status, "market_type": "perpetual",
        "late_excluded": late_excluded, "provider": "okx-swap",
        "horizon_hours": 4, "created_at": forward.stamp(created),
        "evaluate_at": forward.stamp(due),
        "exit_observed_at": forward.stamp(closed),
        "resolved_at": forward.stamp(closed),
        "evidence": evidence, "regime": "24h_up", "side": "LONG",
        "symbol": "BTC", "strategy": "FB-v3",
        "normalized_R": target, "research_risk_pct": 1.5,
        "net_pnl_usd": 1.0,
    }


def test_bundle():
    manifest = forward.load_manifest()
    models = {}
    for name in ("logistic_regression", "gradient_boosting", "mlp_backprop"):
        model = {"feature_names": list(dataset_builder.FEATURE_NAMES),
                 "test_candidate": name}
        models[name] = {"model": model, "model_id": forward.model_digest(model)}
    payload = {
        "schema": forward.VERSION, "version": 1,
        "created_at_utc": "2026-11-23T00:00:00Z",
        "cohort_start_utc": "2026-11-23T00:00:00Z",
        "training_labels_available_through_utc": "2026-11-22T23:00:00Z",
        "source_ledger_events": 100, "source_ledger_tip_sha256": "a" * 64,
        "eligible_historical_examples": 100, "training_rows": 70,
        "early_stopping_rows": 20, "training_positive_prevalence": 0.5,
        "feature_names": list(dataset_builder.FEATURE_NAMES),
        "feature_schema_sha256": forward.feature_schema_hash(dataset_builder.FEATURE_NAMES),
        "manifest_sha256": __import__("hashlib").sha256(
            forward.MANIFEST_PATH.read_bytes()).hexdigest(),
        "code_fingerprint": forward.code_fingerprint(),
        "models": models,
        "candidate_selection": "NONE_ALL_PREREGISTERED_CANDIDATES_FROZEN",
        "historical_validation_used_for_early_stopping": True,
        "historical_validation_is_not_prospective_evidence": True,
        "paper_only": True, "real_orders": False,
        "automatic_allocation_change": False,
    }
    return {**payload, "bundle_id": forward.digest(payload)}


class ForwardValidationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = test_bundle()
        self.now = dt.datetime(2026, 11, 23, 0, 2, tzinfo=UTC)

    def test_prediction_is_captured_once_only_while_open(self):
        opened = sample_record()
        with patch.object(forward, "_predict", return_value=0.6):
            result = forward.process_records([opened], self.bundle, [], self.now)
            events = result["events"]
            again = forward.process_records([opened], self.bundle, events, self.now)
        self.assertEqual(result["added_predictions"], 1)
        self.assertEqual(again["added_predictions"], 0)
        self.assertEqual(len([e for e in events if e["kind"] == "prediction"]), 1)
        prediction = events[0]["payload"]
        self.assertEqual(set(prediction["probabilities_positive_net_R"]),
                         {"logistic_regression", "gradient_boosting", "mlp_backprop"})
        self.assertTrue(prediction["prediction_is_immutable"])

    def test_closed_record_without_open_prediction_is_never_backfilled(self):
        closed = sample_record(status="CLOSED")
        later = dt.datetime(2026, 11, 23, 4, 3, tzinfo=UTC)
        result = forward.process_records([closed], self.bundle, [], later)
        self.assertEqual(result["added_predictions"], 0)
        self.assertEqual(result["added_skips"], 1)
        self.assertEqual(result["events"][0]["kind"], "skip")
        self.assertEqual(result["events"][0]["payload"]["reason"],
                         "closed_before_prediction_capture")
        self.assertFalse(result["events"][0]["payload"]["prediction_backfill_allowed"])

    def test_stale_open_record_is_skipped_not_backfilled(self):
        stale = sample_record()
        stale_now = dt.datetime(2026, 11, 23, 0, 17, tzinfo=UTC)
        result = forward.process_records([stale], self.bundle, [], stale_now)
        self.assertEqual(result["added_predictions"], 0)
        self.assertEqual(result["events"][0]["payload"]["reason"],
                         "prediction_capture_window_missed")

    def test_outcome_scored_only_after_timely_close_and_only_once(self):
        opened = sample_record()
        with patch.object(forward, "_predict", return_value=0.6):
            first = forward.process_records([opened], self.bundle, [], self.now)
        closed = sample_record(status="CLOSED")
        later = dt.datetime(2026, 11, 23, 4, 3, tzinfo=UTC)
        scored = forward.process_records([closed], self.bundle,
                                          first["events"], later)
        repeated = forward.process_records([closed], self.bundle,
                                            scored["events"], later)
        self.assertEqual(scored["added_scores"], 1)
        self.assertEqual(repeated["added_scores"], 0)
        self.assertEqual([e["kind"] for e in scored["events"]],
                         ["prediction", "score"])
        self.assertEqual(scored["events"][-1]["payload"]["label_positive_net_R"], 1)

    def test_late_close_is_excluded_and_does_not_change_prediction(self):
        opened = sample_record()
        with patch.object(forward, "_predict", return_value=0.6):
            first = forward.process_records([opened], self.bundle, [], self.now)
        late = sample_record(status="CLOSED", late_excluded=True)
        later = dt.datetime(2026, 11, 23, 4, 3, tzinfo=UTC)
        result = forward.process_records([late], self.bundle, first["events"], later)
        self.assertEqual(result["added_scores"], 0)
        self.assertEqual(result["events"][-1]["kind"], "excluded")
        self.assertEqual(result["events"][0]["kind"], "prediction")

    def test_hash_chain_detects_tampering(self):
        events = []
        forward.append_event(events, "skip", {"record_id": "LAB-X", "reason": "test"})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            changed = dict(events[0])
            changed["payload"] = {"record_id": "LAB-X", "reason": "altered"}
            path.write_text(json.dumps(changed) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash chain"):
                forward.read_events(path)

    def test_bundle_cannot_be_reused_after_feature_code_changes(self):
        bundle = dict(self.bundle)
        payload = {key: value for key, value in bundle.items() if key != "bundle_id"}
        payload["code_fingerprint"] = "0" * 64
        tampered = {**payload, "bundle_id": forward.digest(payload)}
        with self.assertRaisesRegex(ValueError, "source changed"):
            forward.verify_bundle(tampered)


if __name__ == "__main__":
    unittest.main()
