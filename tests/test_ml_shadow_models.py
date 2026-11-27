"""Deterministic tests for PAPER-only Gradient Boosting and MLP shadow models."""
import unittest

import ml_shadow_models


def rows(prefix, count):
    result = []
    for i in range(count):
        x = -1.0 if i % 2 == 0 else 1.0
        z = (i % 7) / 7.0
        result.append({
            "record_id": f"{prefix}-{i}",
            "features": {"x": x, "z": z},
            "label": int(x > 0),
        })
    return result


class ShadowModelTests(unittest.TestCase):
    def test_gradient_boosting_learns_pattern_and_stays_shadow_only(self):
        result = ml_shadow_models.fit_gradient_boosting(
            rows("train", 160), rows("valid", 60), ["x", "z"],
            rounds=12, min_leaf=8)
        self.assertGreater(result["validation"]["roc_auc"], 0.9)
        self.assertTrue(result["shadow_only"])
        self.assertFalse(result["automatic_allocation_change"])
        self.assertFalse(result["live_orders"])
        self.assertGreater(
            ml_shadow_models.predict_gradient_boosting(
                result["model"], {"x": 1.0, "z": 0.2}),
            ml_shadow_models.predict_gradient_boosting(
                result["model"], {"x": -1.0, "z": 0.2}))

    def test_mlp_backprop_learns_pattern_and_stays_shadow_only(self):
        result = ml_shadow_models.fit_mlp(
            rows("train", 160), rows("valid", 60), ["x", "z"],
            hidden_units=6, max_epochs=35, patience=10,
            learning_rate=0.03, seed=11)
        self.assertGreater(result["validation"]["roc_auc"], 0.85)
        self.assertTrue(result["shadow_only"])
        self.assertFalse(result["automatic_allocation_change"])
        self.assertFalse(result["live_orders"])
        self.assertGreater(
            ml_shadow_models.predict_mlp(
                result["model"], {"x": 1.0, "z": 0.2}),
            ml_shadow_models.predict_mlp(
                result["model"], {"x": -1.0, "z": 0.2}))

    def test_models_reject_single_class_training(self):
        single = [{"record_id": str(i), "features": {"x": float(i)},
                   "label": 1} for i in range(80)]
        valid = [{"record_id": f"v{i}", "features": {"x": float(i)},
                  "label": int(i % 2)} for i in range(40)]
        with self.assertRaisesRegex(ValueError, "both classes"):
            ml_shadow_models.fit_gradient_boosting(
                single, valid, ["x"], min_leaf=4)
        with self.assertRaisesRegex(ValueError, "both classes"):
            ml_shadow_models.fit_mlp(single, valid, ["x"])

    def test_models_reject_nonfinite_features(self):
        train = rows("train", 80)
        train[0]["features"]["x"] = float("nan")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            ml_shadow_models.fit_gradient_boosting(
                train, rows("valid", 40), ["x", "z"], min_leaf=4)


if __name__ == "__main__":
    unittest.main()
