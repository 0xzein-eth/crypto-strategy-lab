import unittest
import ml_dataset

def closed(**overrides):
    row = {
        "id": "LAB-1", "status": "CLOSED", "market_type": "perpetual",
        "late_excluded": False, "horizon_hours": 4,
        "provider": "okx-swap", "exit_provider": "okx-swap",
        "instrument": "BTC-USDT-SWAP", "exit_instrument": "BTC-USDT-SWAP",
        "entry_price": 100.0, "exit_price": 101.0, "net_pnl_usd": 90.0,
        "normalized_R": 0.6, "signed_return_pct": 1.0, "outcome": "WIN",
        "entry_observed_at": "2026-10-01T00:00:00Z",
        "created_at": "2026-10-01T00:00:01Z",
        "evaluate_at": "2026-10-01T04:00:01Z",
        "exit_observed_at": "2026-10-01T04:00:10Z",
        "delay_seconds": 9, "fee_round_trip_usd": 10.0,
        "strategy": "FB-v3", "side": "LONG", "symbol": "BTC",
        "regime": "24h_up", "cluster": "CRYPTO_BETA",
        "evidence": {"rsi14": 42.5, "price_change_24h_pct": -1.2,
                     "quote_volume_24h": 5000000.0},
    }
    row.update(overrides)
    return row

class DatasetBuilderTests(unittest.TestCase):
    def test_only_open_time_features_and_matured_labels(self):
        row = ml_dataset.make_row(closed())
        self.assertEqual(row["features"]["rsi14"], 42.5)
        self.assertNotIn("exit_price", row["features"])
        self.assertNotIn("net_pnl_usd", row["features"])
        self.assertEqual(row["labels"]["net_profit"], 1)
        self.assertEqual(row["features_asof"], row["entry_at"])

    def test_missing_features_remain_null(self):
        row = ml_dataset.make_row(closed(evidence={"rsi14": None}))
        self.assertIsNone(row["features"]["rsi14"])

    def test_excludes_late_spot_and_venue_mismatch(self):
        rows, summary = ml_dataset.build_dataset([
            closed(), closed(id="LAB-2", late_excluded=True),
            closed(id="LAB-3", market_type="spot_proxy"),
            closed(id="LAB-4", exit_provider="bybit-linear")])
        self.assertEqual([r["sample_id"] for r in rows], ["LAB-1"])
        self.assertEqual(summary["excluded"]["late_or_missing_late_flag"], 1)
        self.assertEqual(summary["excluded"]["not_perpetual"], 1)
        self.assertEqual(summary["excluded"]["invalid_or_mismatched_observation"], 1)

    def test_exit_before_evaluate_is_rejected(self):
        self.assertFalse(ml_dataset._candidate(
            closed(exit_observed_at="2026-10-01T03:59:59Z")))

    def test_open_records_never_become_labels(self):
        rows, summary = ml_dataset.build_dataset([closed(status="OPEN")])
        self.assertEqual(rows, [])
        self.assertEqual(summary["excluded"]["not_closed"], 1)

    def test_deterministic_order(self):
        a = closed(id="LAB-10", created_at="2026-10-02T00:00:00Z")
        b = closed(id="LAB-11", created_at="2026-10-01T00:00:00Z")
        first, _ = ml_dataset.build_dataset([a, b])
        second, _ = ml_dataset.build_dataset([b, a])
        self.assertEqual([r["sample_id"] for r in first],
                         [r["sample_id"] for r in second])

if __name__ == "__main__":
    unittest.main()
