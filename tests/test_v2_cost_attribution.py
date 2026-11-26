import unittest
from decimal import Decimal

from v2.cost_attribution import reconcile


def wallet():
    return {
        "real_order_submissions": 0,
        "simulated_fee_total_usdt": "0.39",
        "recorded_closed_outcomes": [
            {"id": "a", "strategy": "A", "price_pnl_usdt": "0.50",
             "entry_fee_usdt": "0.10", "exit_fee_usdt": "0.10",
             "net_after_bidask_and_fee_before_unverified_funding_usdt": "0.30",
             "late_excluded_from_timely_study": True},
            {"id": "b", "strategy": "B", "price_pnl_usdt": "-0.20",
             "entry_fee_usdt": "0.10", "exit_fee_usdt": "0.10",
             "net_after_bidask_and_fee_before_unverified_funding_usdt": "-0.40",
             "late_excluded_from_timely_study": False},
        ],
    }


def funding(rows):
    return {"closed_wallet_results_with_measured_funding": rows}


def funded(ident, cash, net):
    return {"id": ident, "settled_cash_paid_usdt": cash,
            "historical_closed_net_after_measured_funding_usdt": net,
            "funding_settlements_authentic": True, "exchange_fill_known": False}


class CostAttributionTests(unittest.TestCase):
    def test_full_cost_reconciliation(self):
        result = reconcile(wallet(), funding([funded("a", "0.02", "0.28"),
                                               funded("b", "-0.01", "-0.39")]))
        self.assertEqual(result["closed_wallet_outcomes"], 2)
        self.assertEqual(result["assumed_top_of_book_crossing_price_pnl_usdt"], "0.300000")
        self.assertEqual(result["fees_from_rounded_trade_rows_usdt"], "0.400000")
        self.assertEqual(result["net_after_bidask_and_fees_before_funding_usdt"], "-0.100000")
        self.assertEqual(result["signed_settled_funding_cash_paid_usdt"], "0.010000")
        self.assertEqual(result["net_after_measured_funding_usdt"], "-0.110000")
        self.assertTrue(result["settled_funding_coverage"]["complete_for_closed_wallet_rows"])
        self.assertEqual(result["observed_late_exits_over_30m"], 1)

    def test_net_row_reconciliation_residual_is_zero_when_arithmetic_matches(self):
        result = reconcile(wallet(), funding([funded("a", "0", "0"),
                                               funded("b", "0", "0")]))
        self.assertEqual(result["trade_row_net_reconciliation_residual_usdt"], "0.000000")

    def test_net_row_reconciliation_residual_exposes_mismatch(self):
        source = wallet()
        source["recorded_closed_outcomes"][0][
            "net_after_bidask_and_fee_before_unverified_funding_usdt"
        ] = "0.31"
        result = reconcile(source, funding([funded("a", "0", "0"),
                                             funded("b", "0", "0")]))
        self.assertEqual(result["trade_row_net_reconciliation_residual_usdt"], "0.010000")
        self.assertIn("sum(row price pnl)", result["trade_row_net_reconciliation_formula"])

    def test_full_precision_reconciliation_is_separate_from_rounded_residual(self):
        source = wallet()
        rows = source["recorded_closed_outcomes"]
        rows[0].update({
            "price_pnl_unrounded_usdt": "0.504",
            "entry_fee_unrounded_usdt": "0.1004",
            "exit_fee_unrounded_usdt": "0.1004",
            "net_after_bidask_and_fee_before_unverified_funding_unrounded_usdt": "0.3032",
        })
        rows[1].update({
            "price_pnl_unrounded_usdt": "-0.204",
            "entry_fee_unrounded_usdt": "0.1004",
            "exit_fee_unrounded_usdt": "0.1004",
            "net_after_bidask_and_fee_before_unverified_funding_unrounded_usdt": "-0.4048",
        })
        result = reconcile(source, funding([funded("a", "0", "0"),
                                             funded("b", "0", "0")]))
        self.assertTrue(result["full_precision_source_available_for_all_closed_rows"])
        self.assertEqual(result["full_precision_price_pnl_usdt"], "0.300000")
        self.assertEqual(result["full_precision_fees_usdt"], "0.401600")
        self.assertEqual(result["full_precision_net_before_funding_usdt"], "-0.101600")
        self.assertEqual(result["full_precision_net_reconciliation_residual_usdt"], "0.000000")

    def test_full_precision_reconciliation_is_unavailable_when_any_row_lacks_fields(self):
        result = reconcile(wallet(), funding([funded("a", "0", "0"),
                                               funded("b", "0", "0")]))
        self.assertFalse(result["full_precision_source_available_for_all_closed_rows"])
        self.assertIsNone(result["full_precision_net_reconciliation_residual_usdt"])

    def test_missing_funding_remains_unknown_not_zero(self):
        result = reconcile(wallet(), funding([funded("a", "0.02", "0.28")]))
        self.assertEqual(result["settled_funding_coverage"]["unknown_intervals_not_assumed_zero"], 1)
        self.assertIsNone(result["net_after_measured_funding_usdt"])

    def test_unmatched_funding_id_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unmatched funding id"):
            reconcile(wallet(), funding([funded("x", "0", "0")]))

    def test_non_authentic_funding_fails_closed(self):
        row = funded("a", "0", "0")
        row["funding_settlements_authentic"] = False
        with self.assertRaisesRegex(ValueError, "provenance not authentic"):
            reconcile(wallet(), funding([row]))


if __name__ == "__main__":
    unittest.main()
