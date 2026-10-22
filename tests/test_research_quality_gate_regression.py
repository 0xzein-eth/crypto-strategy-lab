import unittest
from research_quality.after_cost_gate import evaluate

class ShadowCostGateTests(unittest.TestCase):
    def test_no_forecast_stays_in_research(self):
        out=evaluate(None,0.05,0.05)
        self.assertEqual(out["status"],"NO_FORECAST")
        self.assertFalse(out["paper_orders"])
        self.assertFalse(out["live_orders"])
    def test_fee_drag_veto(self):
        self.assertEqual(evaluate(0.10,0.05,0.05)["status"],"COST_VETO")
    def test_research_pass_is_never_trade_authorization(self):
        result=evaluate(0.8,0.05,0.05,spread_pct=0.04,impact_pct=0.02)
        self.assertEqual(result["status"],"RESEARCH_PASS")
        self.assertFalse(result["paper_orders"])
    def test_bad_values_rejected(self):
        for invalid in (float("inf"),float("nan"),-0.01,True):
            with self.subTest(invalid=str(invalid)):
                with self.assertRaises(ValueError):
                    evaluate(None,invalid,0.05)
