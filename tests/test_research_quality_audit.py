import unittest
from research_quality.audit import historic_crypto, wallet, equity

class AuditTests(unittest.TestCase):
    def test_fee_dominance(self):
        r=historic_crypto({"closed":2,"wins":1,"losses":1,
            "net_pnl_usd":-15,"total_round_trip_fees_usd":20,"profit_factor":0.5})
        self.assertEqual(r["before_fees_usd"],5)
        self.assertFalse(r["price_edge_exceeds_friction"])
    def test_no_false_equity_winrate(self):
        r=equity({"market":"LQ45","currency":"IDR","closed_trades":0,
            "initial_capital":"10000000","simulated_equity":"10000000",
            "real_orders":0,"win_rate":0,"profit_factor":0})
        self.assertIsNone(r["win_rate"])
        self.assertIsNone(r["profit_factor"])
    def test_wallet_is_not_validated_by_one_trade(self):
        r=wallet({"closed_positions":1,"initial_simulated_capital_usdt":"1000",
            "current_simulated_equity_usdt":"998.65",
            "observed_closed_win_rate":0,"funding_source_complete":False})
        self.assertFalse(r["adequate_for_strategy_selection"])
        self.assertAlmostEqual(r["return_pct"],-0.135)
    def test_negative_fee_rejected(self):
        with self.assertRaises(ValueError):
            historic_crypto({"closed":1,"wins":1,"losses":0,
                "net_pnl_usd":10,"total_round_trip_fees_usd":-1})
if __name__ == "__main__":
    unittest.main()
