"""Training-run provenance tests."""
import unittest
from unittest.mock import patch

import engine
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


if __name__ == "__main__":
    unittest.main()
