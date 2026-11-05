import unittest
import ml_ablation
import ml_train


class MatchedAblationTests(unittest.TestCase):
    def test_feature_sets_preserve_baseline_and_add_distinct_groups(self):
        self.assertEqual(ml_ablation.FEATURE_SETS["baseline"], tuple(ml_train.NUMERIC))
        self.assertIn("price_vs_sma20_pct", ml_ablation.FEATURE_SETS["trend"])
        self.assertIn("rsi14_delta", ml_ablation.FEATURE_SETS["momentum"])
        self.assertIn("atr14_pct", ml_ablation.FEATURE_SETS["volatility"])
        self.assertIn("wick_imbalance", ml_ablation.FEATURE_SETS["candle"])
        self.assertGreater(len(ml_ablation.FEATURE_SETS["all_engineered"]),
                           len(ml_ablation.FEATURE_SETS["baseline"]))

    def test_all_feature_sets_use_same_horizon_cohort(self):
        report = ml_ablation.run_ablation([])
        self.assertEqual(len(report["results"]), 6)
        for horizon in report["results"]:
            self.assertEqual(horizon["cohort_n"], 0)
            for result in horizon["feature_sets"].values():
                self.assertEqual(result["matched_cohort_n"], 0)
                self.assertEqual(result["status"], "INSUFFICIENT_DATA")
                self.assertIsNone(result["test_brier_delta_vs_baseline"])
        self.assertEqual(report["promotion"], "PROHIBITED_SHADOW_ONLY")


if __name__ == "__main__":
    unittest.main()
