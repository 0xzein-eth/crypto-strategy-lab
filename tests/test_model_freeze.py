"""Enforce the preregistered PAPER ML model and feature freeze."""
import inspect
import json
from pathlib import Path
import unittest

import dataset_builder
import ml_baseline
import ml_shadow_models


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "research/model_freeze_v1.json").read_text())


class ModelFreezeTests(unittest.TestCase):
    def test_feature_schema_matches_frozen_sources(self):
        schema = MANIFEST["feature_schema"]
        self.assertTrue(schema["ordered"])
        self.assertEqual(schema["continuous_feature_count"],
                         len(dataset_builder.BASE_FEATURES))
        self.assertEqual(len(dataset_builder.BASE_FEATURES), 22)
        self.assertEqual(schema["categorical_groups"]["side"],
                         ["LONG", "SHORT"])
        self.assertEqual(schema["categorical_groups"]["horizon_hours"],
                         list(dataset_builder.HORIZONS))
        self.assertEqual(schema["categorical_groups"]["symbol_source"],
                         "universe.SYMBOLS")
        self.assertEqual(schema["categorical_groups"]["strategy_source"],
                         "learner.BASELINES + learner.ADVANCED")
        self.assertEqual(
            len(dataset_builder.FEATURE_NAMES),
            len(set(dataset_builder.FEATURE_NAMES)))
        self.assertFalse(schema["allow_changes_during_cohort"])

    def test_candidate_parameters_match_implementation_defaults(self):
        candidates = {item["name"]: item for item in MANIFEST["candidates"]}
        expected = {
            "logistic_regression": (
                ml_baseline.fit,
                {"max_epochs": 30, "batch_size": 256, "learning_rate": 0.05,
                 "l2": 0.001, "patience": 5, "seed": 17}),
            "gradient_boosting": (
                ml_shadow_models.fit_gradient_boosting,
                {"rounds": 24, "learning_rate": 0.05,
                 "max_thresholds": 12, "min_leaf": 12}),
            "mlp_backprop": (
                ml_shadow_models.fit_mlp,
                {"hidden_units": 16, "max_epochs": 30, "batch_size": 128,
                 "learning_rate": 0.01, "l2": 0.0005,
                 "patience": 6, "seed": 29}),
        }
        self.assertEqual(set(candidates), set(expected))
        for name, (function, frozen_parameters) in expected.items():
            signature = inspect.signature(function)
            actual = {key: signature.parameters[key].default
                      for key in frozen_parameters}
            self.assertEqual(candidates[name]["parameters"], frozen_parameters)
            self.assertEqual(actual, frozen_parameters)

    def test_historical_validation_cannot_select_a_champion(self):
        historical = MANIFEST["historical_validation"]
        self.assertTrue(historical["previously_inspected"])
        self.assertTrue(historical["used_for_early_stopping"])
        self.assertFalse(historical["pristine_holdout"])
        self.assertFalse(historical["may_select_champion"])
        self.assertEqual(MANIFEST["status"],
                         "PREREGISTERED_CANDIDATES_NO_CHAMPION")
        self.assertTrue(MANIFEST["safety"]["paper_only"])
        self.assertFalse(MANIFEST["safety"]["real_orders"])
        self.assertFalse(MANIFEST["safety"]["automatic_allocation_change"])


if __name__ == "__main__":
    unittest.main()
