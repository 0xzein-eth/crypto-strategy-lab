"""Deterministic logistic-regression gradient-descent tests."""
import unittest

import ml_baseline


class LogisticBaselineTests(unittest.TestCase):
    def test_gradient_descent_learns_separable_training_pattern(self):
        train = []
        validation = []
        for i in range(100):
            x = -1.0 if i % 2 == 0 else 1.0
            row = {"record_id": f"train-{i}", "features": {"x": x},
                   "label": int(x > 0)}
            train.append(row)
        for i in range(40):
            x = -1.0 if i % 2 == 0 else 1.0
            row = {"record_id": f"valid-{i}", "features": {"x": x},
                   "label": int(x > 0)}
            validation.append(row)
        result = ml_baseline.fit(
            train, validation, ["x"], max_epochs=30,
            batch_size=20, learning_rate=0.1, patience=8)
        self.assertGreater(result["validation"]["roc_auc"], 0.95)
        self.assertLess(result["validation"]["brier_score"],
                        result["validation"]["constant_base_rate_brier"])
        self.assertTrue(result["shadow_only"])
        self.assertFalse(result["automatic_allocation_change"])
        self.assertFalse(result["live_orders"])
        self.assertGreater(
            ml_baseline.predict(result["model"], {"x": 1.0}),
            ml_baseline.predict(result["model"], {"x": -1.0}))

    def test_rejects_single_class_training_or_validation(self):
        rows = [{"record_id": str(i), "features": {"x": float(i)},
                 "label": 1} for i in range(40)]
        with self.assertRaisesRegex(ValueError, "both classes"):
            ml_baseline.fit(rows, rows, ["x"])


if __name__ == "__main__":
    unittest.main()
