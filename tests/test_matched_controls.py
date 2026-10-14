"""Regression tests for the read-only matched-control report."""
import copy
import datetime as dt
import unittest
import matched_controls as mc


def row(ident, arm, day="2026-10-08", hour=12, minute=0, value=1.0):
    return {
        "id": ident, "strategy": arm,
        "created_at": f"{day}T{hour:02d}:{minute:02d}:00Z",
        "status": "CLOSED", "market_type": "perpetual",
        "late_excluded": False, "normalized_R": value,
        "research_risk_pct": 1.5, "horizon_hours": 4,
        "symbol": "BTC", "side": "LONG", "regime": "24h_up",
    }


class MatchedControlTests(unittest.TestCase):
    def test_nearest_one_to_one_and_order_invariant(self):
        rows = [
            row("C1", "CTRL-v1", minute=5, value=0.2),
            row("A1", "BR-v3", minute=4, value=1.2),
            row("A2", "BR-v3", minute=6, value=2.0),
        ]
        snapshot = copy.deepcopy(rows)
        result = mc.compare(rows)
        self.assertEqual(result, mc.compare(list(reversed(rows))))
        stats = result["arms"]["BR-v3"]
        self.assertEqual(stats["matched_pairs"], 1)
        self.assertEqual(stats["unmatched_arm_closes"], 1)
        self.assertEqual(stats["mean_paired_delta_fee_adjusted_R"], 1.0)
        self.assertEqual(rows, snapshot)

    def test_strict_keys_and_entry_time(self):
        control = row("C", "CTRL-v1")
        for patch in (
            {"symbol": "ETH"}, {"side": "SHORT"},
            {"horizon_hours": 8}, {"regime": "24h_down"},
            {"created_at": "2026-10-09T12:00:00Z"},
            {"created_at": "2026-10-08T15:00:00Z"},
        ):
            with self.subTest(patch=patch):
                trade = dict(row("A", "BR-v3"), **patch)
                self.assertEqual(mc.compare([control, trade])["arms"]["BR-v3"]["matched_pairs"], 0)

    def test_only_eligible_and_stress_separate(self):
        control = dict(row("C", "CTRL-v1", value=0.5), stress_normalized_R=0.1)
        arm = dict(row("A", "BR-v3", value=1.0), stress_normalized_R=0.2)
        late = dict(row("L", "BR-v3"), late_excluded=True)
        spot = dict(row("S", "BR-v3"), market_type="spot_proxy")
        open_ = dict(row("O", "BR-v3"), status="OPEN")
        result = mc.compare([control, arm, late, spot, open_])
        stats = result["arms"]["BR-v3"]
        self.assertEqual(result["eligible_closed"], 2)
        self.assertEqual(stats["mean_paired_delta_fee_adjusted_R"], 0.5)
        self.assertEqual(stats["mean_paired_delta_after_friction_scenario_R"], 0.1)

    def test_positive_cluster_still_not_proven(self):
        rows = []
        for i in range(8):
            day = (dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat()
            rows += [row("C" + str(i), "CTRL-v1", day=day, value=-0.1),
                     row("A" + str(i), "BR-v3", day=day, value=1.0)]
        stats = mc.compare(rows)["arms"]["BR-v3"]
        self.assertEqual(stats["matched_entry_utc_days"], 8)
        self.assertGreater(stats["day_cluster_95pct_descriptive_lcb_after_friction_R"], 0)
        self.assertFalse(stats["edge_proven"])


if __name__ == "__main__":
    unittest.main()
