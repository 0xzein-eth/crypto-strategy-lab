import unittest

from v2.exit_latency_audit import audit, TIMELY_LIMIT_SECONDS


def row(ident, strategy="FB-v3", symbol="BTC", opened="2026-11-01T00:00:00Z",
        closed="2026-11-01T00:05:00Z"):
    return {
        "id": ident, "strategy": strategy, "symbol": symbol,
        "fixed_evaluate_at": opened, "actually_closed_at": closed,
    }


class ExitLatencyAuditTests(unittest.TestCase):
    def test_buckets_and_group_summaries_are_observation_only(self):
        report = {
            "latest_real_observation_utc": "2026-11-01T02:00:00Z",
            "closed_positions": 3, "open_positions": 0,
            "recorded_closed_outcomes": [
                row("a", closed="2026-11-01T00:05:00Z"),
                row("b", strategy="VWAP-v1", symbol="ETH",
                    closed="2026-11-01T00:20:00Z"),
                row("c", closed="2026-11-01T01:01:00Z"),
            ],
        }
        result = audit(report)
        self.assertEqual(result["closed_outcome_count"], 3)
        self.assertEqual(result["delay_buckets"],
                         {"0-5m": 1, "5-15m": 0, "15-30m": 1,
                          "30-60m": 0, "60m+": 1})
        self.assertEqual(result["exit_delay"]["over_30m"], 1)
        self.assertEqual(result["by_strategy"]["VWAP-v1"]["count"], 1)
        self.assertTrue(result["frozen_trial_policy_unchanged"])
        self.assertTrue(result["wallet_or_source_journal_modified"] is False)
        self.assertTrue(result["strategy_returns_and_rankings_omitted"])

    def test_exact_30_minute_boundary_is_timely(self):
        report = {"recorded_closed_outcomes": [
            row("boundary", closed="2026-11-01T00:30:00Z")
        ]}
        result = audit(report)
        self.assertEqual(result["exit_delay"]["over_30m"], 0)
        self.assertEqual(result["delay_buckets"]["15-30m"], 1)
        self.assertEqual(TIMELY_LIMIT_SECONDS, 1800)

    def test_negative_delay_fails_closed(self):
        report = {"recorded_closed_outcomes": [
            row("bad", opened="2026-11-01T00:10:00Z",
                closed="2026-11-01T00:05:00Z")
        ]}
        with self.assertRaisesRegex(ValueError, "CLOCK_INTEGRITY"):
            audit(report)

    def test_missing_records_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_UNAVAILABLE"):
            audit({"closed_positions": 10})


if __name__ == "__main__":
    unittest.main()
