import unittest
import ml_economic_review


class EconomicReviewTests(unittest.TestCase):
    def test_after_fee_metrics_and_r_drawdown(self):
        rows = [
            {"sample_id":"a","entry_at":"2026-01-01T00:00:00Z","horizon_hours":1,"probability_net_profit":0.7,"label_net_profit":1,"net_pnl_usd":10.0,"normalized_R":0.1},
            {"sample_id":"b","entry_at":"2026-01-02T00:00:00Z","horizon_hours":1,"probability_net_profit":0.3,"label_net_profit":0,"net_pnl_usd":-20.0,"normalized_R":-0.2},
        ]
        result=ml_economic_review.evaluate(rows)
        self.assertEqual(result["overall"]["n"],2)
        self.assertEqual(result["overall"]["net_pnl_usd"],-10.0)
        self.assertAlmostEqual(result["overall"]["expectancy_R"],-0.05)
        self.assertAlmostEqual(result["overall"]["max_drawdown_R"],0.2)
        self.assertEqual(result["promotion"],"PROHIBITED_SHADOW_ONLY")

    def test_empty_predictions_are_safe(self):
        result=ml_economic_review.evaluate([])
        self.assertEqual(result["prediction_count"],0)
        self.assertIsNone(result["overall"]["brier"])


if __name__ == "__main__":
    unittest.main()
