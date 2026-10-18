"""Regression tests for fail-closed negative-edge diagnostics."""
import datetime as dt
import unittest
import negative_edge_diagnostic as diag

def record(i, day, value):
    return {"id": str(i), "strategy": "BR-v3",
            "created_at": day+"T12:00:00Z", "status": "CLOSED",
            "market_type": "perpetual", "late_excluded": False,
            "normalized_R": value, "horizon_hours": 4,
            "research_risk_pct": 1.5}

class NegativeEdgeTests(unittest.TestCase):
    def test_sparse_sample_never_flags_or_claims_edge(self):
        arm = diag.evaluate([record(1, "2026-10-01", -2)])["arms"]["BR-v3"]
        self.assertTrue(arm["insufficient_evidence"])
        self.assertFalse(arm["negative_expectancy_warning"])
        self.assertFalse(arm["edge_proven"])

    def test_sustained_negative_training_warns(self):
        rows = [record(i, (dt.date(2026, 9, 1)+dt.timedelta(days=i%35)).isoformat(), -1)
                for i in range(250)]
        arm = diag.evaluate(rows)["arms"]["BR-v3"]
        self.assertFalse(arm["insufficient_evidence"])
        self.assertTrue(arm["negative_expectancy_warning"])
        self.assertFalse(arm["edge_proven"])

    def test_monitoring_is_not_used_for_warning(self):
        import learner
        rows = []
        for i in range(45):
            day = (dt.date(2026, 8, 1)+dt.timedelta(days=i)).isoformat()
            value = 3 if learner.stable_bucket("holdout:"+day, 5) == 0 else -1
            for j in range(8):
                rows.append(record(i*8+j, day, value))
        arm = diag.evaluate(rows)["arms"]["BR-v3"]
        self.assertTrue(arm["negative_expectancy_warning"])
        self.assertGreater(arm["monitoring_closed_not_used_for_diagnosis"], 0)

    def test_only_genuine_training_matched_controls_can_warn(self):
        days=[(dt.date(2026, 8, 1)+dt.timedelta(days=i)).isoformat()
              for i in range(45)]
        rows=[record(i, d, -1) for i,d in enumerate(days) for _ in range(3)]
        # A lower bound on paired differences needs enough real matched TRAIN
        # controls and genuine distinct entry days, not a profitable unmatched arm.
        comparison={"arms":{"BR-v3":{
            "paired_train_pairs":90,"paired_train_utc_days":25,
            "paired_train_descriptive_ucb_R":-0.35,
            "matched_fraction":0.7}}}
        negative=diag.evaluate(rows,comparison)["arms"]["BR-v3"]
        self.assertTrue(negative["negative_expectancy_warning"])
        self.assertTrue(negative["worse_than_matched_control_training_warning"])
        self.assertTrue(negative["both_absolute_and_relative_negative_warning"])
        self.assertFalse(negative["edge_proven"])
        missing=diag.evaluate(rows)["arms"]["BR-v3"]
        self.assertFalse(missing["worse_than_matched_control_training_warning"])
        # Too few independent matched DAYS cannot trigger a relative alert.
        comparison["arms"]["BR-v3"]["paired_train_utc_days"]=3
        small=diag.evaluate(rows,comparison)["arms"]["BR-v3"]
        self.assertFalse(small["worse_than_matched_control_training_warning"])
        comparison["arms"]["BR-v3"]["paired_train_utc_days"]=25
        comparison["arms"]["BR-v3"]["paired_train_descriptive_ucb_R"]=0.01
        unproven=diag.evaluate(rows,comparison)["arms"]["BR-v3"]
        self.assertFalse(unproven["worse_than_matched_control_training_warning"])

    def test_monitoring_changes_do_not_alter_training_relative_warning(self):
        import learner
        days=[(dt.date(2026, 8, 1)+dt.timedelta(days=i)).isoformat()
              for i in range(45)]
        rows=[record(i, d, -1) for i,d in enumerate(days) for _ in range(3)]
        comparison={"arms":{"BR-v3":{
            "paired_train_pairs":90,"paired_train_utc_days":25,
            "paired_train_descriptive_ucb_R":-0.2}}}
        a=diag.evaluate(rows,comparison)["arms"]["BR-v3"]
        modified=[dict(r) for r in rows]
        for r in modified:
            if learner.stable_bucket("holdout:"+learner.day_of(r),5)==0:
                r["normalized_R"]=9.0
        b=diag.evaluate(modified,comparison)["arms"]["BR-v3"]
        self.assertEqual(a["worse_than_matched_control_training_warning"],
                         b["worse_than_matched_control_training_warning"])
        self.assertEqual(a["negative_expectancy_warning"],
                         b["negative_expectancy_warning"])

    def test_invalid_nonfinite_record_excluded_by_eligibility(self):
        arm = diag.evaluate([record(1, "2026-10-01", float("nan"))])["arms"]["BR-v3"]
        self.assertEqual(arm["eligible_closed"], 0)

if __name__ == "__main__":
    unittest.main()
