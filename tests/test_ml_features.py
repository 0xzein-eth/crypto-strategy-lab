import unittest
import ml_features


class OpenFeatureEngineeringTests(unittest.TestCase):
    def test_relative_features_use_only_open_values(self):
        features = {"last_close": 105.0, "sma20": 100.0, "sma50": 110.0,
                    "vwap20": 102.0, "rsi14": 60.0, "rsi14prev": 55.0,
                    "atr14": 2.1, "z20": 1.5, "vol_ratio": 1.2,
                    "prior20_range_width": 0.08,
                    "upper_wick_ratio": 0.2, "lower_wick_ratio": 0.4}
        result = ml_features.derive_open_features(features)
        self.assertAlmostEqual(result["price_vs_sma20_pct"], 5.0)
        self.assertAlmostEqual(result["price_vs_sma50_pct"], -100 * (1 - 105/110))
        self.assertAlmostEqual(result["price_vs_vwap20_pct"], 100 * (105/102 - 1))
        self.assertEqual(result["rsi14_centered"], 10.0)
        self.assertEqual(result["rsi14_delta"], 5.0)
        self.assertAlmostEqual(result["atr14_pct"], 2.0)
        self.assertAlmostEqual(result["wick_imbalance"], 0.2)

    def test_missing_and_invalid_denominators_stay_null(self):
        result = ml_features.derive_open_features({"last_close": 0, "sma20": 0})
        self.assertIsNone(result["price_vs_sma20_pct"])
        self.assertIsNone(result["rsi14_delta"])
        self.assertIsNone(result["atr14_pct"])

    def test_augmentation_preserves_timestamp_and_original_fields(self):
        row = {"features_asof": "2026-11-01T00:00:00Z",
               "features": {"last_close": 101, "sma20": 100},
               "labels": {"net_profit": 1}}
        augmented = ml_features.augment_row(row)
        self.assertEqual(augmented["derived_features_asof"], row["features_asof"])
        self.assertAlmostEqual(augmented["features"]["price_vs_sma20_pct"], 1.0, places=10)
        self.assertEqual(augmented["labels"], row["labels"])
        self.assertNotIn("net_profit", augmented["features"])

    def test_missingness_is_segmented_by_strategy(self):
        rows = [
            {"features": {"strategy": "CTRL-v1", "horizon_hours": 1, "rsi14": None}},
            {"features": {"strategy": "RSI-v1", "horizon_hours": 1, "rsi14": 50}},
        ]
        report = ml_features.audit_availability(rows)
        self.assertEqual(report["by_strategy"]["CTRL-v1"]["features"]["rsi14"]["share"], 1.0)
        self.assertEqual(report["by_strategy"]["RSI-v1"]["features"]["rsi14"]["share"], 0.0)
        self.assertTrue(report["features_are_open_time_only"])
        self.assertFalse(report["missing_values_imputed"])


if __name__ == "__main__":
    unittest.main()
