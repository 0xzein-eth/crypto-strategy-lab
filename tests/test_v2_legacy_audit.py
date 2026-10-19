"""Proof that canonical research dollars are NOT a cash-funded portfolio."""
import copy
import unittest
import v2.legacy_audit as audit


def trade(ident, side, entry, exit_price=None, stake=10000, status="CLOSED",
          strategy="BR-proxy-v1", late=False, provider="perpetual"):
    row = {
        "id": ident, "created_at": entry, "notional_usd": stake,
        "status": status, "strategy": strategy,
        "market_type": provider, "late_excluded": late,
        "fee_per_side_pct": .05,
    }
    if status == "CLOSED":
        # Simulated +0.2% gross minus 0.1% roundtrip fee.
        row.update(fee_round_trip_usd=10,
                   signed_return_pct=0.2,
                   net_pnl_usd=10,
                   resolved_at=exit_price)
    return row


class LegacyFeeAudit(unittest.TestCase):
    def test_gross_fee_net_and_funded_account_warning(self):
        rows = [
            trade("LAB-1", "LONG", "2026-10-19T00:00:00Z",
                  "2026-10-19T01:00:00Z"),
            trade("LAB-2", "SHORT", "2026-10-19T00:30:00Z",
                  "2026-10-19T01:30:00Z", strategy="VWAP-v1"),
            trade("LAB-3", "LONG", "2026-10-19T01:05:00Z",
                  status="OPEN"),
        ]
        original = copy.deepcopy(rows)
        result = audit.compute(rows)
        self.assertEqual(rows, original)
        self.assertEqual(result["gross_price_pnl_usd"], "40.00")
        self.assertEqual(result["modeled_roundtrip_fees_usd"], "20.00")
        self.assertEqual(result["modeled_net_pnl_usd"], "20.00")
        self.assertEqual(result["currently_open_nominal_exposure_usd"], "10000.00")
        self.assertEqual(result["hypothetical_peak_concurrent_notional_usd"],"20000.00")
        self.assertEqual(result["hypothetical_peak_initial_margin_usd"], "6666.67")
        self.assertTrue(result["do_not_use_as_account_equity"])
        self.assertFalse(result["real_account_equity_available"])
        self.assertEqual(result["by_strategy"]["VWAP-v1"]["eligible_timely_perpetual_closed"],1)
        self.assertEqual(result["mean_gross_return_pct_per_close_notional"],"0.200000")

    def test_reconciles_only_actual_snapshot(self):
        record=[trade("LAB-1","LONG","2026-10-19T00:00:00Z","2026-10-19T01:00:00Z")]
        c=audit.compute(record)
        self.assertTrue(audit.verify_snapshot(c,{"created":1,"closed":1,
                         "total_round_trip_fees_usd":10,"net_pnl_usd":10}))
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            audit.verify_snapshot(c,{"created":1,"closed":1,
                           "total_round_trip_fees_usd":9.99,"net_pnl_usd":10.10})
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            audit.verify_snapshot(c,{"created":2,"closed":1,
                           "total_round_trip_fees_usd":10,"net_pnl_usd":10})

    def test_malformed_pnl_notional_and_duplicates_fail(self):
        good=trade("LAB-1","LONG","2026-10-19T00:00:00Z","2026-10-19T01:00:00Z")
        bad=dict(good,net_pnl_usd=11)
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            audit.compute([bad])
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            audit.compute([good,copy.deepcopy(good)])
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            audit.compute([dict(good, notional_usd=0)])
        with self.assertRaisesRegex(ValueError,"invalid hypothetical leverage"):
            audit.compute([good],leverage=0)

    def test_late_and_spot_are_counted_but_not_called_eligible(self):
        a=trade("LAB-1","LONG","2026-10-19T00:00:00Z",
                "2026-10-19T01:00:00Z",late=True)
        b=trade("LAB-2","SHORT","2026-10-19T00:00:00Z",
                "2026-10-19T01:30:00Z",provider="spot_proxy")
        report=audit.compute([a,b])
        self.assertEqual(report["late_closes"],1)
        self.assertEqual(report["spot_proxy_closes"],1)
        self.assertEqual(report["by_strategy"]["BR-proxy-v1"]["eligible_timely_perpetual_closed"],0)
        self.assertEqual(report["modeled_roundtrip_fees_usd"],"20.00")


if __name__=="__main__":
    unittest.main()
