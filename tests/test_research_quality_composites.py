import unittest
from research_quality.composites import evaluate, COMPOSITES
class CompositeTests(unittest.TestCase):
    def test_two_votes_needed(self):
        result=evaluate({"TREND-v1":"LONG"})
        self.assertEqual(result["consensus_trend_breakout_v1"]["signal"],"ABSTAIN")
    def test_agreement(self):
        result=evaluate({"TREND-v1":"LONG","BR-v3":"LONG"})
        self.assertEqual(result["consensus_trend_breakout_v1"]["signal"],"LONG")
        self.assertFalse(result["consensus_trend_breakout_v1"]["orders_authorized"])
    def test_conflict_veto(self):
        result=evaluate({"TREND-v1":"LONG","BR-v3":"LONG","DC-v1":"SHORT"})
        self.assertEqual(result["consensus_trend_breakout_v1"]["signal"],"ABSTAIN")
    def test_buy_alias(self):
        result=evaluate({"TREND-v1":"BUY","BR-v3":"BUY"})
        self.assertEqual(result["consensus_trend_breakout_v1"]["signal"],"LONG")
    def test_five_separate_hypotheses(self):
        self.assertEqual(len(COMPOSITES),5)
if __name__=="__main__": unittest.main()
