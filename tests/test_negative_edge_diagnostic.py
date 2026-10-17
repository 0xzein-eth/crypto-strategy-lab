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

    def test_invalid_nonfinite_training_rejected(self):
        with self.assertRaises(ValueError):
            diag.evaluate([record(1, "2026-10-01", float("nan"))])

if __name__ == "__main__":
    unittest.main()
