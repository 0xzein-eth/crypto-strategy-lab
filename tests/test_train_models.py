"""Training-run provenance and paired-comparison tests."""
import unittest
from unittest.mock import patch

import engine
import ml_baseline
import train_models


class TrainModelsTests(unittest.TestCase):
    def test_report_keeps_event_count_and_hash_head_in_correct_fields(self):
        dataset = {
            "schema": "crypto-paper-supervised-dataset-v1",
            "feature_names": [],
            "examples": [],
            "eligible_examples": 0,
            "excluded_records": 0,
            "target_definition": "test",
            "features_are_open_time_only": True,
            "labels_available_only_after_evaluate_at": True,
            "spot_and_late_outcomes_excluded": True,
            "not_for_live_orders": True,
        }
        with patch.object(engine, "replay",
                          return_value=({}, 12345, "a"*64, 12400)), \
             patch("dataset_builder.build_dataset", return_value=dataset), \
             patch("dataset_builder.chronological_split",
                   side_effect=ValueError("INSUFFICIENT_DATA: test")):
            result = train_models.run()
        self.assertEqual(result["source_ledger_events"], 12345)
        self.assertEqual(result["source_ledger_tip_sha256"], "a"*64)
        self.assertEqual(result["status"], "INSUFFICIENT_OR_INVALID_DATA")

    def test_comparison_uses_same_validation_rows_and_training_rate_constant(self):
        rows = [
            {"record_id": "a", "label": 0},
            {"record_id": "b", "label": 1},
            {"record_id": "c", "label": 0},
            {"record_id": "d", "label": 1},
        ]
        logistic = {
            "validation": ml_baseline.metrics(rows, [0.2, 0.8, 0.2, 0.8], 0.5)
        }
        gb = {
            "validation": ml_baseline.metrics(rows, [0.1, 0.9, 0.1, 0.9], 0.5)
        }
        mlp = {
            "validation": ml_baseline.metrics(rows, [0.6, 0.6, 0.4, 0.4], 0.5)
        }
        comparison = train_models._comparison(
            {"logistic_regression": logistic,
             "gradient_boosting": gb,
             "mlp_backprop": mlp}, rows, 0.5)
        self.assertEqual(comparison["evaluation_rows"], 4)
        self.assertEqual(
            [p["record_id"] for p in comparison["constant_baseline"]["validation_predictions"]],
            ["a", "b", "c", "d"])
        self.assertTrue(
            comparison["models"]["gradient_boosting"]["beats_logistic_on_brier"])
        self.assertFalse(
            comparison["models"]["mlp_backprop"]["beats_logistic_on_brier"])
        self.assertEqual(comparison["promotion_decision"], "NONE_DIAGNOSTIC_ONLY")
        self.assertFalse(comparison["validation_is_pristine_holdout"])


if __name__ == "__main__":
    unittest.main()
