"""Read-only PAPER cohort diagnostics: truthful data quantities vs eligible quality."""
import copy
import unittest
import dataset_health as d

NOW="2026-10-18T16:00:00Z"


def rec(id_,arm="TPREG-v1",status="CLOSED",horizon=2,market="perpetual",
        late=False,spread=0.02,created="2026-10-17T12:00:00Z",
        due="2026-10-18T12:00:00Z"):
    r={"id":id_, "strategy":arm, "status":status, "horizon_hours":horizon,
       "market_type":market, "late_excluded":late,
       "created_at":created, "evaluate_at":due,
       "provider":"okx-swap" if market=="perpetual" else "kraken-spot-proxy",
       "normalized_R":0.1, "stress_normalized_R":-0.2,
       "friction_stress":{"source_spread_pct":spread}}
    return r


class CohortHealthTests(unittest.TestCase):
    def setUp(self):
        self.records=[
            rec("LAB-1"),
            rec("LAB-2",horizon=8,late=True),
            rec("LAB-3",status="OPEN",arm="BRREG-v1",horizon=4),
            rec("LAB-4",status="OPEN",arm="BRREG-v1",horizon=24,
                due="2026-10-20T12:00:00Z"),
            rec("LAB-5",market="spot_proxy",horizon=12),
            rec("LAB-6",arm="CTRL-v1",horizon=2,spread=None),
        ]
        self.report={
            "timestamp":NOW, "ledger_tip_sha256":"real-hash-example",
            "verified_events":10, "net_pnl_usd":-500,
            "source_errors":{"XRP:okx-swap":"example"},
            "scheduling_diagnostics":{"estimated_10m_slot_coverage":0.96},
            "entry_opportunity_audit":{"confirmed_arm_opportunities":{"TPREG-v1":1}}}
        self.matched={"arms":{"TPREG-v1":{"matched_pairs":1,
                                           "matched_fraction":0.3333,
                                           "matched_entry_utc_days":1}}}

    def test_separates_started_pending_tardy_spot_and_eligible(self):
        original=copy.deepcopy(self.records)
        output=d.evaluate(self.records,self.report,self.matched)
        self.assertEqual(self.records,original)
        self.assertEqual(output["totals"]["opened"],6)
        self.assertEqual(output["totals"]["closed"],4)
        self.assertEqual(output["totals"]["open_now"],2)
        self.assertEqual(output["totals"]["open_due_pending"],1)
        self.assertEqual(output["totals"]["late_closed"],1)
        self.assertEqual(output["totals"]["spot_proxy_closed"],1)
        self.assertEqual(output["totals"]["eligible_timely_perpetual_closed"],2)
        self.assertEqual(output["arms"]["TPREG-v1"]["eligible_timely_perpetual_closed"],1)
        self.assertEqual(output["arms"]["BRREG-v1"]["open_due_pending"],1)
        self.assertEqual(output["arms"]["TPREG-v1"]["matched_control_pairs"],1)
        self.assertEqual(output["arms"]["TPREG-v1"]["matched_control_fraction"],0.3333)
        self.assertEqual(output["arms"]["TPREG-v1"]["horizons"]["2"]
                         ["after_fee_mean_R_of_eligible"],0.1)
        self.assertEqual(output["arms"]["TPREG-v1"]["horizons"]["2"]
                         ["stress_scenario_mean_R_of_eligible"],-0.2)
        self.assertEqual(output["arms"]["TPREG-v1"]["horizons"]["12"]
                         ["eligible_timely_perpetual_closed"],0)
        self.assertEqual(output["arms"]["CTRL-v1"]["entry_spread_not_observed"],1)
        self.assertEqual(output["source_venue_closed_counts"]["okx-swap"],3)
        self.assertEqual(output["source_venue_closed_counts"]["kraken-spot-proxy"],1)
        self.assertEqual(output["latest_tick_entry_opportunities"],
                         self.report["entry_opportunity_audit"])
        self.assertFalse(output["arms"]["TPREG-v1"]["edge_proven"])
        self.assertEqual(output["published_simulation_pnl_unchanged_usd"],-500)

    def test_no_missing_match_cannot_claim_a_match(self):
        r=d.evaluate(self.records,self.report)
        self.assertIsNone(r["arms"]["BRREG-v1"]["matched_control_pairs"])
        self.assertTrue(r["no_strategy_promotion"])
        # All rows are preserved; no extra observations are synthesized.
        self.assertEqual(r["totals"]["opened"],len(self.records))

    def test_duplicate_id_and_unsupported_horizon_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            d.evaluate(self.records+[self.records[0]],self.report)
        bad=copy.deepcopy(self.records)
        bad[0]["horizon_hours"]=3
        with self.assertRaisesRegex(ValueError,"unsupported"):
            d.evaluate(bad,self.report)

    def test_reject_malformed_time_but_accept_real_intrarun_quote(self):
        modified=copy.deepcopy(self.records)
        modified[0]["created_at"]="2026-10-18T16:03:00Z"
        self.assertEqual(d.evaluate(modified,self.report)["totals"]["opened"],6)
        modified[0]["created_at"]="2026-10-18T16:20:00Z"
        with self.assertRaisesRegex(ValueError,"too far"):
            d.evaluate(modified,self.report)
        with self.assertRaisesRegex(ValueError,"timezone"):
            d.evaluate(self.records,dict(self.report,timestamp="2026-10-18T16:00:00"))

    def test_all_six_fixed_horizons_published(self):
        out=d.evaluate(self.records,self.report)
        for arm in ("CTRL-v1","BRREG-v1","TPREG-v1"):
            self.assertEqual(set(out["arms"][arm]["horizons"]),{"1","2","4","8","12","24"})


if __name__=="__main__":
    unittest.main()
