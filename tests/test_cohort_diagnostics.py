"""Standalone offline checks for immutable v8 cohort economics and data provenance."""
import datetime as dt
import unittest
from unittest.mock import patch

import cohort_diagnostics
import engine


BASE = dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc)


def outcome(strategy, net, fee=10.0, provenance=False, market="perpetual",
            late=False, hour=4, day=20, stress=None):
    evidence = {"bar_span": "15m confirmed OKX USDT-SWAP",
                "bar_time": f"2026-10-{day:02d}T11:45:00Z"} if provenance else {}
    result = {
        "status": "CLOSED", "market_type": market,
        "late_excluded": late, "strategy": strategy, "horizon_hours": hour,
        "created_at": f"2026-10-{day:02d}T12:00:00Z",
        "net_pnl_usd": net, "fee_round_trip_usd": fee, "evidence": evidence,
    }
    if stress is not None:
        result["stress_net_pnl_usd"] = stress
    return result


class CohortDiagnosticTests(unittest.TestCase):
    def test_correlated_cohorts_reconcile_and_do_not_promote(self):
        rows = [
            outcome("IBREAK-v1", 25, provenance=True, stress=10),
            outcome("IBREAK-v1", -15, provenance=True, stress=-30),
            outcome("IBREAK-v1", 5, provenance=True, hour=1, day=21),
            outcome("CTRL-v1", -7, stress=-20),
            outcome("IBREAK-v1", 300, late=True),
            outcome("IBREAK-v1", 400, market="spot_proxy"),
            outcome("RSI-v1", -4),
            {"status": "OPEN", "strategy": "IBREAK-v1"}
        ]
        report = cohort_diagnostics.summarize(rows)
        self.assertTrue(report["strictly_descriptive_no_allocation_feedback"])
        self.assertTrue(report["not_independent_trials"])
        self.assertEqual(report["closed_partition"]["all_closed"], 7)
        self.assertEqual(report["closed_partition"]["eligible_timely_perpetual_closed"], 5)
        self.assertEqual(report["closed_partition"]["late_perpetual_closed"], 1)
        self.assertEqual(report["closed_partition"]["non_perpetual_closed"], 1)
        self.assertEqual(report["closed_partition"]["eligible_confirmed_15m_candle"], 3)
        self.assertEqual(report["closed_partition"]["eligible_direction_proxy_or_neutral_control"], 1)
        self.assertEqual(report["closed_partition"]["eligible_unverified_advanced_signal_metadata"], 1)
        money = report["eligible_cost_reconciliation"]
        self.assertEqual(money["n"], 5)
        self.assertEqual(money["net_fee_only_usd"], 4)
        self.assertEqual(money["fees_usd"], 50)
        self.assertEqual(money["gross_before_fee_usd"], 54)
        self.assertEqual(money["stress_model_covered"], 3)
        rows = report["by_strategy_horizon_provenance"]
        grouped = [x for x in rows if x["strategy"] == "IBREAK-v1" and x["horizon_hours"] == 4]
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["n"], 2)
        self.assertEqual(grouped[0]["observed_distinct_utc_entry_days"], 1)
        self.assertEqual(grouped[0]["net_fee_only_usd"], 10)
        self.assertEqual(sum(x["net_fee_only_usd"] for x in rows), money["net_fee_only_usd"])

    def test_open_only_is_valid_no_champion(self):
        d = cohort_diagnostics.summarize([{"status": "OPEN"}])
        self.assertEqual(d["closed_partition"], {})
        self.assertEqual(d["eligible_cost_reconciliation"]["n"], 0)
        self.assertEqual(d["by_strategy_horizon_provenance"], [])
        self.assertIsNone(d["eligible_cost_reconciliation"]["mean_net_usd_per_hypothesis"])

    def test_missing_15m_source_skips_proxy_instead_of_polluting_no_signal(self):
        now = BASE
        quote = {"symbol": "BTC", "price": 100.0, "pct24h": 3.0,
                 "quote_volume_24h": 20_000_000,
                 "observed_at": engine.stamp(now), "provider": "okx-swap",
                 "market_type": "perpetual", "instrument": "BTC-USDT-SWAP"}
        check = {}
        with patch.object(engine, "SYMBOLS", ("BTC",)):
            got = engine.new_candidates({}, lambda symbol,provider: quote,
                now, 116, 1, advanced=lambda symbol,ticker: None,
                reobserve=lambda symbol,provider: quote,
                clock=lambda: now, opportunity_audit=check)
        self.assertEqual(got, [])
        self.assertEqual(check["unavailable_confirmed_candle_slots"], 1)
        self.assertEqual(check["slots_with_no_confirmed_signal"], 0)
        self.assertEqual(check["no_confirmed_signal_baseline_probes_allowed"], 0)
        self.assertEqual(check["new_paper_opens_by_arm"], {})

    def test_invalid_monetary_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid canonical net PnL"):
            cohort_diagnostics.summarize([outcome("CTRL-v1", float("nan"))])


if __name__ == "__main__":
    unittest.main()
