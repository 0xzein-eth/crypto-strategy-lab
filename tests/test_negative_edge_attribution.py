"""Read-only negative expectancy attribution regression; no selection."""
import datetime as dt
import unittest
import negative_edge_attribution as diag

START=dt.date(2026,9,1)


def trade(i, *, r=-1, regime="24h_down", h=4, sector="major"):
    return {
        "id":str(i),"status":"CLOSED","strategy":"BR-v3",
        "created_at":(START+dt.timedelta(days=i%25)).isoformat()+"T12:00:00Z",
        "market_type":"perpetual","late_excluded":False,
        "normalized_R":r,"research_risk_pct":1.5,
        "horizon_hours":h,"side":"LONG","symbol":"BTC",
        "regime":regime,"evidence":{"sampling_stratum":[sector,"falling","moderate"]},
    }


class NegativeAttributionTests(unittest.TestCase):
    def test_cost_negative_horizon_regime_sector_without_promotion(self):
        report=diag.evaluate([trade(i) for i in range(125)])
        self.assertEqual(report["eligible_closes"],125)
        for name,key in (("horizon_hours","4"),("entry_regime","24h_down"),
                         ("side","LONG"),("sector","major")):
            r=report["dimensions"][name][key]
            self.assertTrue(r["descriptive_negative_warning"])
            self.assertEqual(r["distinct_entry_utc_days"],25)
            self.assertLess(r["after_cost_mean_R"],0)
        self.assertTrue(report["no_strategy_selection_or_auto_reweight"])
        self.assertFalse(report["multiple_testing_adjusted"])

    def test_sparse_and_missing_metadata_not_masked(self):
        records=[trade(i) for i in range(3)]
        records[0].pop("regime")
        records[0]["evidence"]={}
        report=diag.evaluate(records)
        self.assertEqual(report["missing_frozen_metadata"]["entry_regime"],1)
        self.assertFalse(report["dimensions"]["horizon_hours"]["4"]["descriptive_negative_warning"])
        self.assertTrue(report["dimensions"]["horizon_hours"]["4"]["insufficient_independent_evidence"])

    def test_ineligible_legacy_missing_or_late_excluded(self):
        record=trade(1)
        record["late_excluded"]=True
        self.assertEqual(diag.evaluate([record])["eligible_closes"],0)


if __name__=="__main__":
    unittest.main()
