import unittest
from research_quality.equity_ensemble import FAMILIES, ensemble_votes

class EquityEnsembleRegression(unittest.TestCase):
    def test_registered_count(self):
        self.assertEqual(len(FAMILIES),5)
    def test_two_of_three(self):
        votes=ensemble_votes({"BREAKOUT20":"BUY","DONCHIAN40":"BUY","DONCHIAN60":"FLAT"})
        self.assertTrue(votes["breakout_confirmation"])
    def test_single_vote_abstains(self):
        votes=ensemble_votes({"RSI_REVERT":"BUY"})
        self.assertFalse(votes["reversal_confirmation"])
    def test_exit_is_not_entry(self):
        votes=ensemble_votes({"RSI_REVERT":"EXIT","RSI_RECOVERY35":"BUY","BOLLINGER_REENTRY20":"EXIT"})
        self.assertFalse(votes["reversal_confirmation"])
