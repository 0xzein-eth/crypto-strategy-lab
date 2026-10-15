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

    def test_paired_frozen_monitoring_does_not_substitute_unmatched_trades(self):
        from learner import stable_bucket
        days=[(dt.date(2026,9,1)+dt.timedelta(days=i)).isoformat()
              for i in range(80)]
        selected=[day for day in days if stable_bucket("holdout:"+day,5)==0]
        self.assertGreaterEqual(len(selected),4)
        rows=[]
        for i,day in enumerate(days):
            rows.append(row("A"+str(i),"BR-v3",day=day,value=0.7))
            if day not in selected:
                rows.append(row("C"+str(i),"CTRL-v1",day=day,value=0.1))
        result=mc.compare(rows)["arms"]["BR-v3"]
        self.assertEqual(result["paired_holdout_pairs"],0)
        self.assertIsNone(result["paired_holdout_descriptive_lcb_R"])
        self.assertGreater(result["paired_train_pairs"],0)
        self.assertEqual(result["matched_pairs"]+result["unmatched_arm_closes"],len(days))

    def test_dashboard_is_ranking_only_and_ledger_source_linked(self):
        report={
          "timestamp":"2026-10-15T03:00:00Z",
          "ledger_tip_sha256":"a"*64,
          "scheduling_diagnostics":{"estimated_10m_slot_coverage":0.96},
          "fixed_horizon_outcomes":{"strategy":{
              "RSI-v1":{"eligible_timely_perpetual_closed":40,
                        "eligible_distinct_entry_utc_days":3,
                        "eligible_after_friction_expectancy_R":0.9,
                        "eligible_after_friction_day_cluster_lcb_R":-0.2,
                        "eligible_timely_perpetual_win_rate":0.65},
              "MR-v3":{"eligible_timely_perpetual_closed":210,
                       "eligible_distinct_entry_utc_days":11,
                       "eligible_after_friction_expectancy_R":0.2,
                       "eligible_after_friction_day_cluster_lcb_R":-0.1,
                       "eligible_timely_perpetual_win_rate":0.51},
              "CTRL-v1":{"eligible_timely_perpetual_closed":400,
                         "eligible_distinct_entry_utc_days":12,
                         "eligible_after_friction_expectancy_R":-0.04}
          }}}
        comparison={"arms":{"RSI-v1":{"matched_pairs":4,"matched_fraction":0.1,
                    "paired_holdout_pairs":0,"paired_holdout_utc_days":0},
                     "MR-v3":{"matched_pairs":110,"matched_fraction":0.52,
                    "paired_holdout_pairs":30,"paired_holdout_utc_days":6}}}
        result=mc.dashboard(report,comparison)
        self.assertEqual(result["all_evaluated_hypotheses"],["RSI-v1","MR-v3"])
        self.assertEqual(result["sufficient_sample_hypotheses"],["MR-v3"])
        self.assertEqual(result["source_ledger_tip_sha256"],"a"*64)
        self.assertFalse(result["arms"]["RSI-v1"]["edge_proven"])
        self.assertTrue(result["not_promotion_input"])
        self.assertTrue(result["no_order_execution"])

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
        self.assertEqual(stats["matched_pairs"],
                         stats["paired_train_pairs"]+stats["paired_holdout_pairs"])
        self.assertLessEqual(stats["paired_holdout_utc_days"],8)


if __name__ == "__main__":
    unittest.main()
