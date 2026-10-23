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
            "real_orders":0,"paper_only":True,"win_rate":0,"profit_factor":0})
        self.assertIsNone(r["win_rate"])
        self.assertIsNone(r["profit_factor"])
    def test_wallet_is_not_validated_by_one_trade(self):
        r=wallet({"closed_positions":1,"initial_simulated_capital_usdt":"1000",
            "current_simulated_equity_usdt":"998.65",
            "observed_closed_win_rate":0,"funding_source_complete":False,
            "paper_only":True,"real_order_submissions":0})
        self.assertFalse(r["adequate_for_strategy_selection"])
        self.assertAlmostEqual(r["return_pct"],-0.135)
    def test_cash_wallet_rejects_real_orders(self):
        with self.assertRaisesRegex(ValueError,"PAPER_INTEGRITY"):
            equity({"market":"NASDAQ","currency":"USD","closed_trades":0,
                    "initial_capital":10000,"simulated_equity":10000,
                    "paper_only":True,"real_orders":1})
    def test_crypto_wallet_rejects_real_orders(self):
        with self.assertRaisesRegex(ValueError,"PAPER_INTEGRITY"):
            wallet({"closed_positions":0,"initial_simulated_capital_usdt":1000,
                    "current_simulated_equity_usdt":1000,
                    "paper_only":True,"real_order_submissions":1})
    def test_negative_fee_rejected(self):
        with self.assertRaises(ValueError):
            historic_crypto({"closed":1,"wins":1,"losses":0,
                "net_pnl_usd":10,"total_round_trip_fees_usd":-1})
    def test_fractional_or_negative_counts_are_not_truncated(self):
        for closed,wins,losses in ((1.5,1,.5),(2,-1,3)):
            with self.assertRaises(ValueError):
                historic_crypto({"closed":closed,"wins":wins,"losses":losses,
                    "net_pnl_usd":0,"total_round_trip_fees_usd":10})
if __name__ == "__main__":
    unittest.main()
